from flask import request, abort, current_app
from functools import wraps
from flask_login import current_user
from werkzeug.security import generate_password_hash, check_password_hash
import re
import bleach
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def sanitize_input(text):
    """Sanitize user input to prevent XSS and other injection attacks"""
    if text is None:
        return None
    # Remove potentially dangerous tags and attributes
    cleaned_text = bleach.clean(
        text,
        tags=[],  # No HTML tags allowed
        strip=True
    )
    return cleaned_text

def sanitize_filename(filename):
    """Sanitize a filename to prevent path traversal and command injection"""
    if filename is None:
        return None
    # Remove potentially dangerous characters
    cleaned_filename = re.sub(r'[^\w\.-]', '_', filename)
    # Prevent path traversal
    cleaned_filename = cleaned_filename.lstrip('.')
    return cleaned_filename

def user_data_access_required(f):
    """Decorator to ensure users only access their own data"""
    @wraps(f)
    def decorated_function(user_id, *args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if int(user_id) != current_user.id and not current_user.is_admin:
            log_access_attempt(False, f.__name__, f"Unauthorized access to user {user_id} by user {current_user.id}")
            abort(403)
        return f(user_id, *args, **kwargs)
    return decorated_function

def verify_content_type(content_type):
    """Decorator to verify request content type"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if request.content_type and content_type in request.content_type:
                return f(*args, **kwargs)
            else:
                abort(415)  # Unsupported Media Type
        return decorated_function
    return decorator

def log_access_attempt(success, resource, details):
    """Log access attempt for security monitoring"""
    status = "Success" if success else "Denied"
    user_id = current_user.id if current_user.is_authenticated else None
    current_app.logger.info(f"Access {status}: User={user_id}, Resource={resource}, Details={details}")

class PasswordManager:
    @staticmethod
    def hash_password(password):
        return generate_password_hash(password)
        
    @staticmethod
    def check_password(hash_password, password):
        return check_password_hash(hash_password, password)

def require_api_key(f):
    """Decorator to require API key for access"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
        if api_key != current_app.config.get('API_KEY'):
            log_access_attempt(False, "API Access", "Invalid API key")
            abort(401)
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            log_access_attempt(False, f.__name__, "Admin access attempt by non-admin user")
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def init_security(app):
    """Initialize all security features"""
    # Setup rate limiting
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"]
    )
    
    # Setup CSP headers
    @app.after_request
    def add_security_headers(response):
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        response.headers['Content-Security-Policy'] = csp
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        return response
    
    # Function to limit concurrent requests
    def limit_requests(max_requests=10):
        # Implementation details depend on specific requirements
        pass
    
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SECURITY_CSRF_ENABLE'] = False
    
    return app, limiter, limit_requests