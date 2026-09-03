import os
import secrets

class Config:
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max request size

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
        'max_upload_size': 25 * 1024 * 1024,  # 25MB per image (modern phone photos)
        # Alignment writes PNG so its warp isn't compounded by JPEG loss, and a
        # photograph costs roughly six times as much that way. This has to cover
        # ALIGN_MAX_FRAMES frames at full resolution (~13MB each) or the two
        # limits contradict each other and a permitted alignment can't be stored.
        'max_total_storage': 1024 * 1024 * 1024,  # 1GB total per session
        'max_images': 200,  # Max images per project
        'max_frames': 200,  # Max frames in animation
        'max_output_size': 200 * 1024 * 1024,  # 200MB max output
        'max_dimension': 4096,  # Max width/height (4K resolution)
        'max_projects': 10,  # Max projects per session
        'max_video_size': 100 * 1024 * 1024,  # 100MB per video upload
        'max_video_duration': 120,  # seconds
    }

    # Rate limiting (requests per time period).
    # The upload limit has to clear a whole set in one drop: max_frames is 200
    # and the frontend uploads sequentially, awaiting each file, so a user
    # adding a folder of photos makes that many calls back to back. A cap of
    # 10/minute rejected the tail of any drop bigger than ten images. The
    # sequential upload is its own throttle -- each call decodes and resamples
    # a full-size photo -- so this bound exists to stop abuse, not to pace
    # legitimate use.
    RATE_LIMITS = {
        'upload': '120 per minute, 600 per hour',
        'generate': '5 per minute, 20 per hour',
        'save_project': '30 per minute',
        'general_api': '100 per minute',
        'video_upload': '3 per minute, 10 per hour',
        'align': '3 per minute, 20 per hour',
        'rotate': '10 per minute, 60 per hour',
        'export': '6 per minute, 30 per hour',
    }

    # Auto-alignment limits. Aligning is CPU-heavy (feature detection plus two
    # passes over every frame), so cap how much work one request can ask for.
    ALIGN_MAX_FRAMES = 60

    # Cleanup settings
    CLEANUP_CONFIG = {
        'session_lifetime': 168,  # hours (1 week) - sessions older than this are deleted
        'cleanup_interval': 24,  # hours - how often to run cleanup
        'orphan_file_age': 24,  # hours - remove orphaned files after this time
    }

    # Allowed file types
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'jpe', 'jfif', 'gif', 'webp'}
    ALLOWED_MIMETYPES = {
        'image/png',
        'image/jpeg',
        'image/gif',
        'image/webp'
    }

    # Video file types
    ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov'}
    ALLOWED_VIDEO_MIMETYPES = {'video/mp4', 'video/quicktime'}

class DevelopmentConfig(Config):
    DEBUG = True
    ENV = 'development'

class ProductionConfig(Config):
    DEBUG = False
    ENV = 'production'
    SESSION_COOKIE_SECURE = True  # HTTPS only in production

# Default config
config = DevelopmentConfig()
