import os
import logging
from flask import Flask, session, request
from flask_session import Session
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler

from config import config
from extensions import limiter
from services.session_manager import SessionManager
from services.quota_manager import QuotaManager
from services.image_processor import ImageProcessor
from services.gif_builder import GifBuilder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(config)

# Initialize Flask-Session
Session(app)

# Initialize rate limiter with app
limiter.init_app(app)

# Initialize services
session_manager = SessionManager(config)
quota_manager = QuotaManager(config, session_manager)
image_processor = ImageProcessor(config)
gif_builder = GifBuilder(config, image_processor)

# Make services available to routes
app.session_manager = session_manager
app.quota_manager = quota_manager
app.image_processor = image_processor
app.gif_builder = gif_builder

# Set up cleanup scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(
    func=session_manager.cleanup_old_sessions,
    trigger='interval',
    hours=config.CLEANUP_CONFIG['cleanup_interval'],
    id='cleanup_old_sessions'
)
scheduler.start()

logger.info("Cleanup scheduler started")


@app.before_request
def ensure_session():
    """Ensure each request has a valid session"""
    if 'id' not in session:
        session['id'] = session_manager.create_session_id()
        session_manager.initialize_session_storage(session['id'])
        logger.info(f"New session created: {session['id']}")
    else:
        # Update last accessed time
        session_manager.update_session_access(session['id'])


@app.errorhandler(429)
def rate_limit_exceeded(e):
    """Handle rate limit errors"""
    return {
        'error': 'Rate limit exceeded',
        'message': 'Too many requests. Please try again later.'
    }, 429


@app.errorhandler(413)
def request_entity_too_large(e):
    """Handle file too large errors"""
    return {
        'error': 'File too large',
        'message': 'The uploaded file exceeds the maximum allowed size.'
    }, 413


@app.errorhandler(500)
def internal_error(e):
    """Handle internal server errors"""
    logger.error(f"Internal error: {e}")
    return {
        'error': 'Internal server error',
        'message': 'An unexpected error occurred. Please try again.'
    }, 500


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

    # Content Security Policy - allow inline styles for Bootstrap
    if 'text/html' in response.content_type:
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "img-src 'self' data: blob:; "
            "connect-src 'self'"
        )

    return response


# Import and register routes
from routes import frames, generate

app.register_blueprint(frames.bp)
app.register_blueprint(generate.bp)


# Main route
@app.route('/')
def index():
    """Main editor interface"""
    from flask import render_template
    return render_template('index.html')


if __name__ == '__main__':
    # Ensure required directories exist
    os.makedirs(config.USER_DATA_DIR, exist_ok=True)
    os.makedirs(config.SESSION_FILE_DIR, exist_ok=True)

    # Run the app
    logger.info("Starting AniGiffy server...")
    app.run(debug=config.DEBUG, host='0.0.0.0', port=5173)
