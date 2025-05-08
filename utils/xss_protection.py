"""
Cross-Site Scripting (XSS) protection utilities for DragonRise application
"""
import re
import bleach
from functools import wraps
from flask import request, abort, current_app, Response

# Define allowed HTML tags and attributes for rich text fields
ALLOWED_TAGS = ['p', 'br', 'strong', 'em', 'u', 'ul', 'ol', 'li']
ALLOWED_ATTRIBUTES = {
    '*': ['class'],
    'a': ['href', 'title', 'target'],
    'img': ['src', 'alt', 'title', 'width', 'height'],
}

def sanitize_html(text, allowed_tags=None, allowed_attributes=None):
    """
    Sanitize HTML content to prevent XSS attacks
    
    Args:
        text (str): Text to sanitize
        allowed_tags (list): List of allowed HTML tags
        allowed_attributes (dict): Dictionary of allowed attributes for each tag
        
    Returns:
        str: Sanitized text
    """
    if text is None:
        return None
        
    if allowed_tags is None:
        allowed_tags = []  # No tags allowed by default
        
    if allowed_attributes is None:
        allowed_attributes = {}
        
    return bleach.clean(
        str(text),
        tags=allowed_tags,
        attributes=allowed_attributes,
        strip=True
    )

def sanitize_input(text):
    """
    Sanitize user input by removing all HTML tags
    
    Args:
        text (str): Text to sanitize
        
    Returns:
        str: Sanitized text
    """
    return sanitize_html(text)

def sanitize_rich_text(text):
    """
    Sanitize rich text input allowing only safe HTML tags
    
    Args:
        text (str): Text to sanitize
        
    Returns:
        str: Sanitized text with safe HTML tags
    """
    return sanitize_html(text, ALLOWED_TAGS, ALLOWED_ATTRIBUTES)

def sanitize_filename(filename):
    """
    Sanitize a filename to prevent path traversal and command injection
    
    Args:
        filename (str): Filename to sanitize
        
    Returns:
        str: Sanitized filename
    """
    if filename is None:
        return None
        
    # Remove any directory components
    filename = re.sub(r'[/\\]', '', filename)
    
    # Remove any null bytes
    filename = filename.replace('\0', '')
    
    # Remove any special characters
    filename = re.sub(r'[^a-zA-Z0-9._-]', '', filename)
    
    return filename

def sanitize_request_params():
    """
    Decorator to sanitize all request parameters
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Sanitize GET parameters
            for key, value in request.args.items():
                request.args = request.args.copy()
                request.args[key] = sanitize_input(value)
                
            # Sanitize POST parameters
            if request.form:
                for key, value in request.form.items():
                    if isinstance(value, str):
                        request.form = request.form.copy()
                        request.form[key] = sanitize_input(value)
                        
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def add_xss_protection_headers(response):
    """
    Add XSS protection headers to a response
    
    Args:
        response: Flask response object
        
    Returns:
        response: Modified response with XSS protection headers
    """
    # X-XSS-Protection header
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Content-Security-Policy header
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "font-src 'self' https://cdn.jsdelivr.net; "
        "form-action 'self'; "
        "frame-ancestors 'self'; "
        "base-uri 'self'"
    )
    
    # X-Content-Type-Options header
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    return response