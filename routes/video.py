import math
import uuid
import logging
from pathlib import Path
from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.utils import secure_filename
from PIL import Image

from extensions import limiter

logger = logging.getLogger(__name__)

bp = Blueprint('video', __name__, url_prefix='/api/video')


@bp.route('/upload', methods=['POST'])
@limiter.limit("3 per minute, 10 per hour")
def upload_video():
    """Upload a video file, probe its metadata, and return info"""
    try:
        vp = current_app.video_processor
        if not vp.available:
            return jsonify({
                'error': 'Video import unavailable',
                'message': 'ffmpeg is not installed on this server'
            }), 503

        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Validate extension
        if not vp.validate_video_extension(file.filename):
            allowed = ', '.join(current_app.config.get('ALLOWED_VIDEO_EXTENSIONS',
                                                        {'mp4', 'mov'}))
            return jsonify({
                'error': 'Invalid file type',
                'message': f'Allowed video types: {allowed}'
            }), 400

        # Check file size
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)

        max_video_size = current_app.config.get('QUOTAS', {}).get(
            'max_video_size', 100 * 1024 * 1024)
        if file_size > max_video_size:
            return jsonify({
                'error': 'File too large',
                'message': f'Video must be under {max_video_size // (1024*1024)}MB'
            }), 400

        # Save with UUID filename
        ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
        filename = f"{uuid.uuid4().hex}.{ext}"

        uploads_dir = current_app.session_manager.safe_path(session['id'], 'uploads')
        uploads_dir.mkdir(parents=True, exist_ok=True)
        file_path = uploads_dir / filename
        file.save(file_path)

        # Probe video
        info, error = vp.probe_video(file_path)
        if error:
            file_path.unlink(missing_ok=True)
            return jsonify({
                'error': 'Video probe failed',
                'message': error
            }), 400

        # Check duration limit
        max_duration = current_app.config.get('QUOTAS', {}).get(
            'max_video_duration', 120)
        if info['duration'] > max_duration:
            file_path.unlink(missing_ok=True)
            return jsonify({
                'error': 'Video too long',
                'message': f'Maximum duration is {max_duration} seconds'
            }), 400

        # Estimate frames at native FPS
        estimated_frames = math.ceil(info['duration'] * info['fps']) if info['fps'] > 0 else 0

        logger.info(f"Video uploaded: {filename} ({info['duration']}s, "
                     f"{info['width']}x{info['height']}, {info['fps']}fps)")

        # Clean up orphaned vframe files from previous extractions
        for old_frame in uploads_dir.glob('vframe_*.png'):
            old_frame.unlink(missing_ok=True)

        # Calculate remaining image slots for the client-side quota warning
        # Re-stat after cleanup; subtract 1 for the video file we just saved
        max_images = current_app.config.get('QUOTAS', {}).get('max_images', 100)
        stats = current_app.session_manager.get_session_stats(session['id'])
        current_image_count = (stats['image_count'] if stats else 0) - 1  # exclude video
        remaining_slots = max(0, max_images - max(0, current_image_count))

        return jsonify({
            'success': True,
            'filename': filename,
            'duration': info['duration'],
            'width': info['width'],
            'height': info['height'],
            'fps': info['fps'],
            'codec': info['codec'],
            'estimatedFrames': estimated_frames,
            'remainingSlots': remaining_slots,
        }), 200

    except Exception as e:
        logger.error(f"Video upload failed: {e}")
        return jsonify({
            'error': 'Video upload failed',
            'message': str(e)
        }), 500


@bp.route('/extract', methods=['POST'])
@limiter.limit("3 per minute, 10 per hour")
def extract_frames():
    """Extract frames from a previously uploaded video at a chosen FPS"""
    try:
        vp = current_app.video_processor
        if not vp.available:
            return jsonify({
                'error': 'Video import unavailable',
                'message': 'ffmpeg is not installed on this server'
            }), 503

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        filename = data.get('filename')
        fps = data.get('fps', 5)

        if not filename:
            return jsonify({'error': 'No filename provided'}), 400

        # Clamp FPS
        fps = max(0.5, min(30, float(fps)))

        # Locate video file
        uploads_dir = current_app.session_manager.safe_path(session['id'], 'uploads')
        video_path = uploads_dir / secure_filename(filename)

        if not video_path.exists():
            return jsonify({
                'error': 'Video not found',
                'message': 'The uploaded video file was not found'
            }), 404

        # Probe again to get duration for frame estimate
        info, error = vp.probe_video(video_path)
        if error:
            return jsonify({'error': 'Video probe failed', 'message': error}), 400

        estimated_count = math.ceil(info['duration'] * fps)

        # Clean up any orphaned vframe files from previous extractions
        for old_frame in uploads_dir.glob('vframe_*.png'):
            old_frame.unlink(missing_ok=True)

        # Check against remaining image quota
        # Re-stat after cleanup; subtract 1 for the video file (will be deleted)
        quotas = current_app.config.get('QUOTAS', {})
        max_images = quotas.get('max_images', 100)
        stats = current_app.session_manager.get_session_stats(session['id'])
        current_count = (stats['image_count'] if stats else 0) - 1  # exclude the video file
        current_count = max(0, current_count)
        remaining_slots = max_images - current_count

        if estimated_count > remaining_slots:
            return jsonify({
                'error': 'Quota exceeded',
                'message': (f'Extraction would produce ~{estimated_count} frames '
                           f'but only {remaining_slots} slots remain '
                           f'(limit: {max_images})')
            }), 400

        # Extract frames
        extracted_paths, error = vp.extract_frames(video_path, uploads_dir, fps)
        if error:
            return jsonify({'error': 'Extraction failed', 'message': error}), 500

        # Delete source video
        video_path.unlink(missing_ok=True)

        # Build response with frame info (matching /api/frames/upload format)
        frames = []
        for fpath in extracted_paths:
            try:
                img = Image.open(fpath)
                w, h = img.size
                has_transparency = img.mode in ('RGBA', 'LA') or \
                    (img.mode == 'P' and 'transparency' in img.info)
                fsize = fpath.stat().st_size

                frames.append({
                    'filename': fpath.name,
                    'path': f"uploads/{fpath.name}",
                    'width': w,
                    'height': h,
                    'hasTransparency': has_transparency,
                    'size': fsize,
                })
            except Exception as e:
                logger.error(f"Failed to read extracted frame {fpath.name}: {e}")

        logger.info(f"Extracted {len(frames)} frames from {filename} at {fps} FPS")

        return jsonify({
            'success': True,
            'frames': frames,
            'count': len(frames),
        }), 200

    except Exception as e:
        logger.error(f"Frame extraction failed: {e}")
        return jsonify({
            'error': 'Extraction failed',
            'message': str(e)
        }), 500
