import uuid
import logging
from pathlib import Path
from flask import Blueprint, request, jsonify, session, current_app, send_file
from werkzeug.utils import secure_filename

from models.project import Project
from config import config
from extensions import limiter

logger = logging.getLogger(__name__)

bp = Blueprint('generate', __name__, url_prefix='/api/generate')


@bp.route('/preview', methods=['POST'])
@limiter.limit("5 per minute, 20 per hour")
def generate_preview():
    """Generate a preview GIF with limited frames"""
    try:
        data = request.get_json()
        project_data = data.get('project')

        if not project_data:
            return jsonify({'error': 'No project data provided'}), 400

        # Create project from data
        project = Project.from_dict(project_data)

        if len(project.frames) == 0:
            return jsonify({
                'error': 'No frames',
                'message': 'Project must have at least one frame'
            }), 400

        # Validate project
        is_valid, errors = project.validate(config)
        if not is_valid:
            return jsonify({
                'error': 'Validation failed',
                'message': ', '.join(errors)
            }), 400

        # Generate output filename
        output_filename = f"preview_{uuid.uuid4().hex[:8]}.gif"

        # Create output directory
        output_dir = current_app.session_manager.safe_path(session['id'], 'output')
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / output_filename

        # Get max_frames from request, default to 10 if not specified
        max_frames = data.get('maxFrames', 10)

        # Build preview GIF
        success, message = current_app.gif_builder.create_preview_gif(
            project,
            output_path,
            current_app.session_manager,
            session['id'],
            max_frames=max_frames
        )

        if not success:
            return jsonify({
                'error': 'Failed to generate preview',
                'message': message
            }), 500

        # Get file size
        file_size = output_path.stat().st_size

        logger.info(f"Preview generated: {output_filename} ({file_size} bytes)")

        return jsonify({
            'success': True,
            'filename': output_filename,
            'path': f"/api/generate/file/{output_filename}",
            'size': file_size,
            'message': message
        }), 200

    except Exception as e:
        logger.error(f"Preview generation failed: {e}")
        return jsonify({
            'error': 'Preview generation failed',
            'message': str(e)
        }), 500


@bp.route('/full', methods=['POST'])
@limiter.limit("5 per minute, 20 per hour")
def generate_full():
    """Generate the full GIF"""
    try:
        data = request.get_json()
        project_data = data.get('project')

        if not project_data:
            return jsonify({'error': 'No project data provided'}), 400

        # Create project from data
        project = Project.from_dict(project_data)

        if len(project.frames) == 0:
            return jsonify({
                'error': 'No frames',
                'message': 'Project must have at least one frame'
            }), 400

        # Validate project
        is_valid, errors = project.validate(config)
        if not is_valid:
            return jsonify({
                'error': 'Validation failed',
                'message': ', '.join(errors)
            }), 400

        # Generate output filename
        safe_name = secure_filename(project.name) or 'animation'
        output_filename = f"{safe_name}_{uuid.uuid4().hex[:8]}.gif"

        # Create output directory
        output_dir = current_app.session_manager.safe_path(session['id'], 'output')
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / output_filename

        # Build GIF
        success, message, file_size = current_app.gif_builder.build_gif(
            project,
            output_path,
            current_app.session_manager,
            session['id']
        )

        if not success:
            return jsonify({
                'error': 'Failed to generate GIF',
                'message': message
            }), 500

        logger.info(f"GIF generated: {output_filename} ({file_size} bytes)")

        return jsonify({
            'success': True,
            'filename': output_filename,
            'path': f"/api/generate/file/{output_filename}",
            'size': file_size,
            'message': message
        }), 200

    except Exception as e:
        logger.error(f"GIF generation failed: {e}")
        return jsonify({
            'error': 'GIF generation failed',
            'message': str(e)
        }), 500


@bp.route('/file/<filename>', methods=['GET'])
def get_file(filename):
    """Serve a generated GIF file"""
    try:
        # Secure filename
        filename = secure_filename(filename)

        # Get file path
        file_path = current_app.session_manager.safe_path(session['id'], 'output', filename)

        if not file_path.exists():
            return jsonify({
                'error': 'File not found',
                'message': f'GIF file does not exist: {filename}'
            }), 404

        return send_file(
            file_path,
            mimetype='image/gif',
            as_attachment=False,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Failed to serve file: {e}")
        return jsonify({
            'error': 'Failed to serve file',
            'message': str(e)
        }), 500


@bp.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download a generated GIF file"""
    try:
        # Secure filename
        filename = secure_filename(filename)

        # Get file path
        file_path = current_app.session_manager.safe_path(session['id'], 'output', filename)

        if not file_path.exists():
            return jsonify({
                'error': 'File not found',
                'message': f'GIF file does not exist: {filename}'
            }), 404

        return send_file(
            file_path,
            mimetype='image/gif',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        return jsonify({
            'error': 'Failed to download file',
            'message': str(e)
        }), 500


@bp.route('/list', methods=['GET'])
def list_outputs():
    """List all generated GIFs for current session"""
    try:
        output_dir = current_app.session_manager.safe_path(session['id'], 'output')

        if not output_dir.exists():
            return jsonify({'gifs': []}), 200

        gifs = []
        for file_path in output_dir.glob('*.gif'):
            if file_path.is_file():
                file_size = file_path.stat().st_size
                modified = file_path.stat().st_mtime

                gifs.append({
                    'filename': file_path.name,
                    'path': f"/api/generate/file/{file_path.name}",
                    'size': file_size,
                    'modified': modified
                })

        # Sort by modification time (newest first)
        gifs.sort(key=lambda g: g['modified'], reverse=True)

        return jsonify({'gifs': gifs}), 200

    except Exception as e:
        logger.error(f"Failed to list GIFs: {e}")
        return jsonify({
            'error': 'Failed to list GIFs',
            'message': str(e)
        }), 500
