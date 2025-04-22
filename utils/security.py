from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import request, abort
import os

def init_security(app):
    # Initialize CSRF protection
    csrf = CSRFProtect(app)
    
    # Initialize rate limiter
    limiter = Limiter(
        app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )
    
    # Add rate limit decorators
    def limit_requests(f):
        @wraps(f)
        @limiter.limit("5 per minute")
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated_function
    
    return csrf, limiter, limit_requests

class PasswordManager:
    @staticmethod
    def hash_password(password):
        return generate_password_hash(password)
    
    @staticmethod
    def check_password(password_hash, password):
        return check_password_hash(password_hash, password)

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if api_key and api_key == os.environ.get('API_KEY'):
            return f(*args, **kwargs)
        abort(401)
    return decorated_function
