"""
Access control utilities for DragonRise application
"""
from functools import wraps
from flask import abort, request, redirect, url_for, flash, current_app
from flask_login import current_user

def user_data_access_required(f):
    """
    Decorator to ensure a user can only access their own data or admin can access any data
    
    This decorator checks if the requested user_id matches the current user's ID
    or if the current user is an admin.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Get user_id from various possible sources
        user_id = kwargs.get('user_id')
        if not user_id:
            user_id = request.args.get('user_id')
        if not user_id:
            user_id = request.form.get('user_id')
            
        # If no user_id is specified, assume it's for the current user
        if not user_id:
            return f(*args, **kwargs)
            
        try:
            # Convert to int for comparison
            user_id = int(user_id)
            
            # Allow access if current user is admin or accessing their own data
            if current_user.is_admin or current_user.id == user_id:
                return f(*args, **kwargs)
            else:
                current_app.logger.warning(
                    f"Unauthorized access attempt: User {current_user.id} "
                    f"tried to access data for user {user_id}"
                )
                abort(403)  # Forbidden
        except (ValueError, TypeError):
            # If user_id is not a valid integer
            current_app.logger.warning(f"Invalid user_id in request: {user_id}")
            abort(400)  # Bad Request
            
    return decorated_function

def verify_csrf_token():
    """
    Verify that CSRF token is present and valid for POST requests
    
    This function is used by the CSRF protection middleware,
    but can be called explicitly for additional checks.
    """
    # Flask-WTF handles CSRF protection automatically
    # This function is a placeholder for additional custom checks
    pass

def verify_content_type(required_type='application/x-www-form-urlencoded'):
    """
    Decorator to ensure the request has the correct content type
    
    Args:
        required_type (str): The required Content-Type header value
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if request.method == 'POST':
                content_type = request.headers.get('Content-Type', '')
                if required_type not in content_type and 'multipart/form-data' not in content_type:
                    current_app.logger.warning(
                        f"Invalid Content-Type: {content_type}, expected: {required_type}"
                    )
                    abort(400)  # Bad Request
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def log_access_attempt(success, resource, details=None):
    """
    Log access attempts for security monitoring
    
    Args:
        success (bool): Whether the access attempt was successful
        resource (str): The resource being accessed
        details (str): Additional details about the access attempt
    """
    from utils.logging_config import log_activity
    
    user_id = current_user.id if current_user.is_authenticated else None
    action = "Access Granted" if success else "Access Denied"
    
    log_activity(current_app, user_id, action, f"{resource}: {details or 'No details'}")