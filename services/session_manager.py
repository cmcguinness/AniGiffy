import os
import time
import shutil
import secrets
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, config):
        self.config = config
        self.user_data_dir = Path(config.USER_DATA_DIR)
        self.session_lifetime = config.CLEANUP_CONFIG['session_lifetime'] * 3600  # Convert to seconds
        self.orphan_file_age = config.CLEANUP_CONFIG['orphan_file_age'] * 3600

        # Ensure base directory exists
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

    def create_session_id(self):
        """Generate a secure session ID"""
        return secrets.token_urlsafe(32)

    def get_session_dir(self, session_id):
        """Get the directory path for a session"""
        return self.user_data_dir / session_id

    def initialize_session_storage(self, session_id):
        """Create directory structure for a new session"""
        session_dir = self.get_session_dir(session_id)

        try:
            # Create subdirectories
            (session_dir / 'uploads').mkdir(parents=True, exist_ok=True)
            (session_dir / 'projects').mkdir(parents=True, exist_ok=True)
            (session_dir / 'output').mkdir(parents=True, exist_ok=True)

            # Create metadata file
            metadata = {
                'created': time.time(),
                'last_accessed': time.time(),
            }

            logger.info(f"Initialized session storage for: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize session storage: {e}")
            return False

    def update_session_access(self, session_id):
        """Update the last accessed time for a session"""
        session_dir = self.get_session_dir(session_id)
        if session_dir.exists():
            # Touch the directory to update modification time
            session_dir.touch(exist_ok=True)

    def validate_session(self, session_id):
        """Check if a session is valid and not expired"""
        if not session_id:
            return False

        session_dir = self.get_session_dir(session_id)

        if not session_dir.exists():
            return False

        # Check if session has expired
        created_time = session_dir.stat().st_mtime
        if time.time() - created_time > self.session_lifetime:
            logger.info(f"Session expired: {session_id}")
            return False

        return True

    def safe_path(self, session_id, *path_parts):
        """
        Generate a safe path within a session directory.
        Prevents directory traversal attacks.
        """
        base = self.get_session_dir(session_id).resolve()
        target = (base / Path(*path_parts)).resolve()

        # Ensure target is within base directory
        if not str(target).startswith(str(base)):
            raise ValueError("Invalid path: directory traversal detected")

        return target

    def cleanup_old_sessions(self):
        """Remove sessions older than the configured lifetime"""
        if not self.user_data_dir.exists():
            return

        cutoff_time = time.time() - self.session_lifetime
        cleaned_count = 0

        try:
            for session_dir in self.user_data_dir.iterdir():
                if not session_dir.is_dir():
                    continue

                # Check if session is old enough to clean up
                created_time = session_dir.stat().st_mtime
                if created_time < cutoff_time:
                    try:
                        shutil.rmtree(session_dir)
                        cleaned_count += 1
                        logger.info(f"Cleaned up old session: {session_dir.name}")
                    except Exception as e:
                        logger.error(f"Failed to cleanup session {session_dir.name}: {e}")

            if cleaned_count > 0:
                logger.info(f"Cleanup completed: removed {cleaned_count} old sessions")

        except Exception as e:
            logger.error(f"Session cleanup failed: {e}")

    def get_session_stats(self, session_id):
        """Get statistics about a session's storage usage"""
        session_dir = self.get_session_dir(session_id)

        if not session_dir.exists():
            return None

        stats = {
            'total_size': 0,
            'image_count': 0,
            'project_count': 0,
            'output_count': 0,
        }

        try:
            # Calculate total size
            for file_path in session_dir.rglob('*'):
                if file_path.is_file():
                    stats['total_size'] += file_path.stat().st_size

            # Count files in each directory
            uploads_dir = session_dir / 'uploads'
            if uploads_dir.exists():
                stats['image_count'] = len(list(uploads_dir.glob('*')))

            projects_dir = session_dir / 'projects'
            if projects_dir.exists():
                stats['project_count'] = len(list(projects_dir.glob('*.json')))

            output_dir = session_dir / 'output'
            if output_dir.exists():
                stats['output_count'] = len(list(output_dir.glob('*.gif')))

        except Exception as e:
            logger.error(f"Failed to get session stats: {e}")

        return stats

    def delete_session(self, session_id):
        """Manually delete a session and all its data"""
        session_dir = self.get_session_dir(session_id)

        if session_dir.exists():
            try:
                shutil.rmtree(session_dir)
                logger.info(f"Deleted session: {session_id}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete session {session_id}: {e}")
                return False

        return False
