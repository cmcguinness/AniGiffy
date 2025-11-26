"""Flask extensions - initialized separately to avoid circular imports"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Create limiter without app - will be initialized in app.py
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=["1000 per hour"]
)
