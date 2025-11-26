import os
import secrets

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB max request size

    # Session settings
    SESSION_TYPE = 'filesystem'
    SESSION_FILE_DIR = os.path.join(os.getcwd(), 'flask_session')
    SESSION_PERMANENT = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # User data directory (outside static to prevent direct URL access)
    USER_DATA_DIR = os.path.join(os.getcwd(), 'user_data')

    # Resource quotas per session
    QUOTAS = {
        'max_upload_size': 10 * 1024 * 1024,  # 10MB per image
        'max_total_storage': 50 * 1024 * 1024,  # 50MB total per session
        'max_images': 50,  # Max images per project
        'max_frames': 200,  # Max frames in animation
        'max_output_size': 20 * 1024 * 1024,  # 20MB max GIF
        'max_dimension': 2000,  # Max width/height
        'max_projects': 10,  # Max projects per session
    }

    # Rate limiting (requests per time period)
    RATE_LIMITS = {
        'upload': '10 per minute, 50 per hour',
        'generate': '5 per minute, 20 per hour',
        'save_project': '30 per minute',
        'general_api': '100 per minute',
    }

    # Cleanup settings
    CLEANUP_CONFIG = {
        'session_lifetime': 168,  # hours (1 week) - sessions older than this are deleted
        'cleanup_interval': 24,  # hours - how often to run cleanup
        'orphan_file_age': 24,  # hours - remove orphaned files after this time
    }

    # Allowed file types
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ALLOWED_MIMETYPES = {
        'image/png',
        'image/jpeg',
        'image/gif',
        'image/webp'
    }

class DevelopmentConfig(Config):
    DEBUG = True
    ENV = 'development'

class ProductionConfig(Config):
    DEBUG = False
    ENV = 'production'
    SESSION_COOKIE_SECURE = True  # HTTPS only in production

# Default config
config = DevelopmentConfig()
