import os
import uuid
import logging
import tempfile
from pathlib import Path
from flask import Blueprint, request, jsonify, session, current_app, send_file, after_this_request
from werkzeug.utils import secure_filename
from PIL import Image

from config import config
from extensions import limiter

logger = logging.getLogger(__name__)

bp = Blueprint('frames', __name__, url_prefix='/api/frames')


@bp.route('/upload', methods=['POST'])
@limiter.limit(config.RATE_LIMITS['upload'])
def upload_image():
    """Upload an image file"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Validate file extension
        if not current_app.image_processor.validate_file_extension(file.filename):
            ext_seen = Path(file.filename).suffix.lower().lstrip('.') or '(none)'
            allowed = ", ".join(sorted(current_app.config["ALLOWED_EXTENSIONS"]))
            return jsonify({
                'error': 'Invalid file type',
                'message': f'"{file.filename}" has extension "{ext_seen}". Allowed types: {allowed}'
            }), 400

        # Check file size
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning

        can_upload, message = current_app.quota_manager.can_upload(session['id'], file_size)
        if not can_upload:
            return jsonify({
                'error': 'Upload not allowed',
                'message': message
            }), 429

        # Generate unique filename. Derive the extension from the original
        # filename directly -- secure_filename() strips non-ASCII names down to
        # nothing (e.g. "photo.jpg" in Cyrillic), which used to crash here.
        ext = Path(file.filename).suffix.lower().lstrip('.')
        ext = {'jpe': 'jpg', 'jfif': 'jpg', 'jpeg': 'jpg'}.get(ext, ext) or 'img'
        filename = f"{uuid.uuid4().hex}.{ext}"

        # Save to uploads directory
        uploads_dir = current_app.session_manager.safe_path(session['id'], 'uploads')
        uploads_dir.mkdir(parents=True, exist_ok=True)

        file_path = uploads_dir / filename
        file.save(file_path)

        # Validate the image
        img, error = current_app.image_processor.load_and_validate_image(file_path)
        if error:
            file_path.unlink()  # Delete invalid file
            return jsonify({
                'error': 'Invalid image',
                'message': error
            }), 400

        # Oversized uploads are scaled down rather than rejected. Persist the
        # smaller version so it isn't re-scaled on every preview/generate.
        original_size = img.info.get('original_size')
        if original_size:
            if current_app.image_processor.save_downscaled(file_path, img):
                file_size = file_path.stat().st_size

        # Get image dimensions
        width, height = img.size

        # Check if image has transparency
        has_transparency = img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info)

        logger.info(f"Image uploaded: {filename} ({width}x{height}, {file_size} bytes, transparency={has_transparency})")

        response = {
            'success': True,
            'filename': filename,
            'path': f"uploads/{filename}",
            'size': file_size,
            'width': width,
            'height': height,
            'hasTransparency': has_transparency
        }

        if original_size:
            response['resizedFrom'] = {
                'width': original_size[0],
                'height': original_size[1]
            }
            response['message'] = (
                f'{file.filename} was {original_size[0]}x{original_size[1]} and '
                f'has been scaled down to {width}x{height} '
                f'(max {current_app.config["QUOTAS"]["max_dimension"]}px).'
            )

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        return jsonify({
            'error': 'Upload failed',
            'message': str(e)
        }), 500


@bp.route('/add', methods=['POST'])
def add_frame():
    """Add a frame to the project"""
    try:
        data = request.get_json()
        file_path = data.get('file')
        duration = int(data.get('duration', 100))

        if not file_path:
            return jsonify({'error': 'No file path provided'}), 400

        # Verify file exists
        full_path = current_app.session_manager.safe_path(session['id'], file_path)
        if not full_path.exists():
            return jsonify({
                'error': 'File not found',
                'message': f'Image file does not exist: {file_path}'
            }), 404

        # Create frame object
        frame_id = f"frame-{uuid.uuid4().hex[:8]}"

        return jsonify({
            'success': True,
            'frame': {
                'id': frame_id,
                'file': file_path,
                'duration': duration
            }
        }), 200

    except Exception as e:
        logger.error(f"Failed to add frame: {e}")
        return jsonify({
            'error': 'Failed to add frame',
            'message': str(e)
        }), 500


@bp.route('/<frame_id>', methods=['PUT'])
def update_frame(frame_id):
    """Update frame properties"""
    try:
        data = request.get_json()
        duration = data.get('duration')

        if duration is not None:
            duration = int(duration)
            if duration < 1:
                return jsonify({
                    'error': 'Invalid duration',
                    'message': 'Duration must be at least 1ms'
                }), 400

        return jsonify({
            'success': True,
            'frame': {
                'id': frame_id,
                'duration': duration
            }
        }), 200

    except Exception as e:
        logger.error(f"Failed to update frame: {e}")
        return jsonify({
            'error': 'Failed to update frame',
            'message': str(e)
        }), 500


@bp.route('/<frame_id>', methods=['DELETE'])
def delete_frame(frame_id):
    """Delete a frame"""
    try:
        # Frame deletion is handled client-side
        # This endpoint just confirms the action

        return jsonify({
            'success': True,
            'message': 'Frame deleted'
        }), 200

    except Exception as e:
        logger.error(f"Failed to delete frame: {e}")
        return jsonify({
            'error': 'Failed to delete frame',
            'message': str(e)
        }), 500


@bp.route('/reorder', methods=['PUT'])
def reorder_frames():
    """Reorder frames"""
    try:
        data = request.get_json()
        frame_ids = data.get('frameIds', [])

        if not isinstance(frame_ids, list):
            return jsonify({'error': 'Invalid frame IDs'}), 400

        return jsonify({
            'success': True,
            'frameIds': frame_ids
        }), 200

    except Exception as e:
        logger.error(f"Failed to reorder frames: {e}")
        return jsonify({
            'error': 'Failed to reorder frames',
            'message': str(e)
        }), 500


@bp.route('/list', methods=['GET'])
def list_images():
    """List all uploaded images for current session"""
    try:
        uploads_dir = current_app.session_manager.safe_path(session['id'], 'uploads')

        if not uploads_dir.exists():
            return jsonify({'images': []}), 200

        images = []
        for file_path in uploads_dir.glob('*'):
            if file_path.is_file():
                try:
                    # Get image info
                    img = Image.open(file_path)
                    width, height = img.size
                    file_size = file_path.stat().st_size

                    images.append({
                        'filename': file_path.name,
                        'path': f"uploads/{file_path.name}",
                        'size': file_size,
                        'width': width,
                        'height': height
                    })
                except Exception as e:
                    logger.error(f"Failed to read image {file_path.name}: {e}")

        # Sort by modification time (newest first)
        images.sort(key=lambda i: i['filename'], reverse=True)

        return jsonify({'images': images}), 200

    except Exception as e:
        logger.error(f"Failed to list images: {e}")
        return jsonify({
            'error': 'Failed to list images',
            'message': str(e)
        }), 500


@bp.route('/image/<filename>', methods=['GET'])
def get_image(filename):
    """Serve an uploaded image file"""
    try:
        from flask import send_file
        # Secure filename
        filename = secure_filename(filename)

        # Get file path
        file_path = current_app.session_manager.safe_path(session['id'], 'uploads', filename)

        if not file_path.exists():
            return jsonify({
                'error': 'File not found',
                'message': f'Image file does not exist: {filename}'
            }), 404

        return send_file(
            file_path,
            mimetype='image/png',
            as_attachment=False
        )

    except Exception as e:
        logger.error(f"Failed to serve image: {e}")
        return jsonify({
            'error': 'Failed to serve image',
            'message': str(e)
        }), 500


@bp.route('/align', methods=['POST'])
@limiter.limit(config.RATE_LIMITS['align'])
def align_frames():
    """Align frames so their backgrounds line up, rewriting the image files"""
    try:
        data = request.get_json()
        frames = data.get('frames', [])

        if len(frames) < 2:
            return jsonify({
                'error': 'Not enough frames',
                'message': 'Alignment needs at least two frames'
            }), 400

        max_frames = current_app.config['ALIGN_MAX_FRAMES']
        if len(frames) > max_frames:
            return jsonify({
                'error': 'Too many frames',
                'message': f'Alignment is limited to {max_frames} frames at a time'
            }), 400

        # Resolve every frame to a validated path before touching any of them
        paths = []
        for frame in frames:
            file_ref = frame.get('file') if isinstance(frame, dict) else frame
            if not file_ref:
                return jsonify({'error': 'Invalid frame', 'message': 'Frame has no file'}), 400

            path = current_app.session_manager.safe_path(session['id'], file_ref)
            if not path.exists():
                return jsonify({
                    'error': 'File not found',
                    'message': f'Image file does not exist: {file_ref}'
                }), 404
            paths.append(path)

        reference_index = int(data.get('referenceIndex', 0))

        result = current_app.image_aligner.align(paths, reference_index)

        if 'error' in result:
            return jsonify({
                'error': 'Alignment failed',
                'message': result['error']
            }), 422

        skipped = result['skipped']
        message = f"Aligned {result['aligned']} of {len(paths)} frames to {result['width']}x{result['height']}"
        if skipped:
            listed = ', '.join(str(s['index'] + 1) for s in skipped)
            message += f". Frame(s) {listed} didn't match the reference and were left as they were."

        logger.info(f"Alignment: {message}")

        return jsonify({
            'success': True,
            'aligned': result['aligned'],
            'skipped': skipped,
            'width': result['width'],
            'height': result['height'],
            'reference': result['reference'],
            'message': message
        }), 200

    except Exception as e:
        logger.error(f"Alignment failed: {e}")
        return jsonify({
            'error': 'Alignment failed',
            'message': str(e)
        }), 500


@bp.route('/export', methods=['POST'])
@limiter.limit(config.RATE_LIMITS['export'])
def export_frames():
    """Download the current frame images as a ZIP of PNGs"""
    try:
        data = request.get_json()
        frames = data.get('frames', [])

        if not frames:
            return jsonify({
                'error': 'No frames',
                'message': 'Add some frames before exporting'
            }), 400

        max_frames = current_app.config['QUOTAS']['max_frames']
        if len(frames) > max_frames:
            return jsonify({
                'error': 'Too many frames',
                'message': f'Export is limited to {max_frames} frames'
            }), 400

        entries = []
        for index, frame in enumerate(frames, start=1):
            file_ref = frame.get('file') if isinstance(frame, dict) else frame
            if not file_ref:
                return jsonify({'error': 'Invalid frame', 'message': 'Frame has no file'}), 400

            path = current_app.session_manager.safe_path(session['id'], file_ref)
            if not path.exists():
                return jsonify({
                    'error': 'File not found',
                    'message': f'Image file does not exist: {file_ref}'
                }), 404

            entries.append((path, _export_name(index, frame)))

        # The archive is written to a system temp file rather than the session
        # directory: PNG is several times larger than the stored JPEG, so a
        # full set would blow the session storage quota just by being offered
        # for download. It is deleted as soon as the response is sent.
        handle, archive_path = tempfile.mkstemp(suffix='.zip')
        os.close(handle)

        @after_this_request
        def cleanup(response):
            try:
                os.unlink(archive_path)
            except OSError as exc:
                logger.warning(f"Could not remove export archive: {exc}")
            return response

        current_app.frame_exporter.export_png_zip(entries, archive_path)
        logger.info(f"Exported {len(entries)} frame(s) for session {session['id']}")

        return send_file(
            archive_path,
            mimetype='application/zip',
            as_attachment=True,
            download_name='frames.zip'
        )

    except Exception as e:
        logger.error(f"Frame export failed: {e}")
        return jsonify({
            'error': 'Export failed',
            'message': str(e)
        }), 500


def _export_name(index, frame):
    """
    Name one exported file.

    Numbered by position so the set stays in animation order when a file
    manager sorts it alphabetically -- the stored filenames are UUIDs and
    carry no order. The name the user uploaded is appended when the browser
    passed it along, since a UUID tells them nothing about which shot it was.
    """
    original = frame.get('name') if isinstance(frame, dict) else None
    stem = Path(secure_filename(original or '')).stem
    return f"{index:02d}_{stem}.png" if stem else f"{index:02d}.png"
