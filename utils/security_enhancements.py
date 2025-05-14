"""
Security enhancement utilities for DragonRise application
"""
import os
import re
import bleach
from functools import wraps
from flask import current_app, request, abort, g
from flask_login import current_user

def sanitize_input(text, allow_tags=None):
    """
    Sanitize user input to prevent XSS attacks
    
    Args:
        text (str): Text to sanitize
        allow_tags (list): List of allowed HTML tags, None for no tags
        
    Returns:
        str: Sanitized text
    """
    if text is None:
        return None
        
    # Default: strip all HTML tags
    if allow_tags is None:
        return bleach.clean(str(text), tags=[], strip=True)
    
    # Allow specific HTML tags
    return bleach.clean(str(text), tags=allow_tags, strip=True)

def validate_username(username):
    """
    Validate username format
    
    Args:
        username (str): Username to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    if not username:
        return False
        
    # Only allow alphanumeric characters, underscores, and hyphens
    # Length between 3 and 30 characters
    pattern = r'^[a-zA-Z0-9_-]{3,30}$'
    return bool(re.match(pattern, username))

def validate_integer(value, min_value=None, max_value=None):
    """
    Validate integer input
    
    Args:
        value: Value to validate
        min_value (int): Minimum allowed value
        max_value (int): Maximum allowed value
        
    Returns:
        bool: True if valid, False otherwise
    """
    try:
        int_value = int(value)
        
        if min_value is not None and int_value < min_value:
            return False
            
        if max_value is not None and int_value > max_value:
            return False
            
        return True
    except (ValueError, TypeError):
        return False

def get_admin_password():
    """
    Get admin password from environment variable
    
    Returns:
        str: Admin password or a secure default if not set
    """
    # Get from environment variable
    admin_password = os.environ.get('ADMIN_PASSWORD')
    
    # If not set, use a secure default (this should be changed in production)
    if not admin_password:
        admin_password = os.urandom(16).hex()
        current_app.logger.warning(
            "ADMIN_PASSWORD environment variable not set! "
            "Using a randomly generated password. "
            "Please set ADMIN_PASSWORD for consistent admin access."
        )
    
    return admin_password

def verify_user_access(user_id):
    """
    Verify current user has access to the specified user's data
    
    Args:
        user_id (int): User ID to check access for
        
    Returns:
        bool: True if access is allowed, False otherwise
    """
    # Admin can access any user's data
    if current_user.is_admin:
        return True
        
    # Users can only access their own data
    return current_user.id == int(user_id)

def user_access_required(f):
    """
    Decorator to ensure user can only access their own data
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = kwargs.get('user_id') or request.args.get('user_id') or request.form.get('user_id')
        
        if not user_id:
            # If no user_id specified, assume it's for the current user
            return f(*args, **kwargs)
            
        if not verify_user_access(user_id):
            abort(403)  # Forbidden
            
        return f(*args, **kwargs)
    return decorated_function

def is_safe_url(target):
    """
    Check if a URL is safe to redirect to
    
    Args:
        target (str): URL to check
        
    Returns:
        bool: True if safe, False otherwise
    """
    ref_url = request.host_url
    test_url = target
    
    # Make sure the URL starts with a slash and doesn't include a protocol or domain
    return test_url.startswith('/') and not test_url.startswith('//') and '//' not in test_url