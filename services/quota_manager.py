import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class QuotaManager:
    def __init__(self, config, session_manager):
        self.config = config
        self.session_manager = session_manager
        self.quotas = config.QUOTAS

    def check_storage_quota(self, session_id):
        """Check if session has exceeded total storage quota"""
        try:
            stats = self.session_manager.get_session_stats(session_id)
            if stats is None:
                return True  # New session, no storage used yet - allow

            if stats['total_size'] >= self.quotas['max_total_storage']:
                logger.warning(f"Session {session_id} exceeded storage quota")
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking storage quota: {e}")
            return True  # On error, allow rather than block

    def check_image_count_quota(self, session_id):
        """Check if session has exceeded max image count"""
        try:
            stats = self.session_manager.get_session_stats(session_id)
            if stats is None:
                return True  # New session, no images yet - allow upload

            if stats['image_count'] >= self.quotas['max_images']:
                logger.warning(f"Session {session_id} exceeded image count quota")
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking image count quota: {e}")
            return True  # On error, allow upload rather than block

    def check_project_count_quota(self, session_id):
        """Check if session has exceeded max project count"""
        try:
            stats = self.session_manager.get_session_stats(session_id)
            if stats is None:
                return False

            if stats['project_count'] >= self.quotas['max_projects']:
                logger.warning(f"Session {session_id} exceeded project count quota")
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking project count quota: {e}")
            return False

    def check_file_size(self, file_size):
        """Check if a single file exceeds max upload size"""
        if file_size > self.quotas['max_upload_size']:
            logger.warning(f"File size {file_size} exceeds max upload size")
            return False
        return True

    def check_dimensions(self, width, height):
        """Check if image dimensions are within limits"""
        max_dim = self.quotas['max_dimension']
        if width > max_dim or height > max_dim:
            logger.warning(f"Dimensions {width}x{height} exceed max dimension {max_dim}")
            return False
        return True

    def check_frame_count(self, frame_count):
        """Check if frame count is within limits"""
        if frame_count > self.quotas['max_frames']:
            logger.warning(f"Frame count {frame_count} exceeds max frames")
            return False
        return True

    def check_output_size(self, output_size):
        """Check if output GIF size is within limits"""
        if output_size > self.quotas['max_output_size']:
            logger.warning(f"Output size {output_size} exceeds max output size")
            return False
        return True

    def get_remaining_quota(self, session_id):
        """Get remaining quota information for a session"""
        try:
            stats = self.session_manager.get_session_stats(session_id)
            if stats is None:
                return None

            return {
                'storage': {
                    'used': stats['total_size'],
                    'limit': self.quotas['max_total_storage'],
                    'remaining': self.quotas['max_total_storage'] - stats['total_size'],
                    'percentage': (stats['total_size'] / self.quotas['max_total_storage']) * 100
                },
                'images': {
                    'used': stats['image_count'],
                    'limit': self.quotas['max_images'],
                    'remaining': self.quotas['max_images'] - stats['image_count']
                },
                'projects': {
                    'used': stats['project_count'],
                    'limit': self.quotas['max_projects'],
                    'remaining': self.quotas['max_projects'] - stats['project_count']
                }
            }

        except Exception as e:
            logger.error(f"Error getting remaining quota: {e}")
            return None

    def can_upload(self, session_id, file_size):
        """
        Check if a file can be uploaded based on all relevant quotas
        """
        # Check file size
        if not self.check_file_size(file_size):
            return False, "File size exceeds maximum allowed"

        # Check image count
        if not self.check_image_count_quota(session_id):
            return False, "Maximum number of images reached"

        # Check total storage
        if not self.check_storage_quota(session_id):
            return False, "Storage quota exceeded"

        # Check if adding this file would exceed storage quota
        stats = self.session_manager.get_session_stats(session_id)
        if stats:
            if stats['total_size'] + file_size > self.quotas['max_total_storage']:
                return False, "Adding this file would exceed storage quota"

        return True, "OK"
