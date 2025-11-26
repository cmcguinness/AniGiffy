import uuid
import logging
from pathlib import Path
from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.utils import secure_filename
from PIL import Image

from extensions import limiter

logger = logging.getLogger(__name__)

bp = Blueprint('frames', __name__, url_prefix='/api/frames')


@bp.route('/upload', methods=['POST'])
@limiter.limit("10 per minute, 50 per hour")
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
            return jsonify({
                'error': 'Invalid file type',
                'message': f'Allowed types: {", ".join(current_app.config["ALLOWED_EXTENSIONS"])}'
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

        # Generate unique filename
        ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
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

        # Get image dimensions
        width, height = img.size

        logger.info(f"Image uploaded: {filename} ({width}x{height}, {file_size} bytes)")

        return jsonify({
            'success': True,
            'filename': filename,
            'path': f"uploads/{filename}",
            'size': file_size,
            'width': width,
            'height': height
        }), 200

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
