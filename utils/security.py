from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import request, abort, jsonify, session
import os

def init_security(app):
    # Initialize CSRF protection
    csrf = CSRFProtect(app)
    
    # Add a route to expose the CSRF token
    @app.route('/csrf-token', methods=['GET'])
    def get_csrf_token():
        # Generate a new token
        csrf_token = csrf.generate_csrf()
        return jsonify({'csrf_token': csrf_token})
    
    # Process rate limit configuration - Fix for the parser error
    default_limits = app.config.get('RATELIMIT_DEFAULT', ["200 per day", "50 per hour"])
    if isinstance(default_limits, str):
        default_limits = default_limits.split(';')
    
    # Initialize rate limiter with app configuration values - FIXED VERSION
    limiter = Limiter(
        get_remote_address,  # key_func as first positional argument
        app=app,  # app as a keyword argument
        default_limits=default_limits,
        storage_uri=app.config.get('RATELIMIT_STORAGE_URL', "memory://"),
        strategy="fixed-window"  # This is a valid strategy
    )
    
    # Add rate limit decorators with proper format
    def limit_requests(f):
        @wraps(f)
        @limiter.limit("5 per minute")  # Ensure this is a proper rate limit string
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