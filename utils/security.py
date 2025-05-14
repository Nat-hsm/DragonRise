from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import request, abort, jsonify, session, flash, redirect, url_for
from flask_login import current_user
import os

def init_security(app):
    # Process rate limit configuration
    default_limits = app.config.get('RATELIMIT_DEFAULT', ["200 per day", "50 per hour"])
    if isinstance(default_limits, str):
        default_limits = default_limits.split(';')
    
    # Initialize rate limiter with app configuration values
    limiter = Limiter(
        key_func=get_remote_address,  # Explicitly name the key_func argument
        app=app,
        default_limits=default_limits,
        storage_uri=app.config.get('RATELIMIT_STORAGE_URL', "memory://"),
        strategy="fixed-window"
    )
    
    # Add rate limit decorators
    def limit_requests(f):
        @wraps(f)
        @limiter.limit("200 per minute")  # Changed from 5 per minute
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)
        return decorated_function
    
    # Return None for csrf and keep other values
    return None, limiter, limit_requests

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

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required. This page is only accessible to administrators.', 'danger')
            return redirect(url_for('dashboard') if not current_user.is_admin else url_for('login'))
        return f(*args, **kwargs)
    return decorated_function