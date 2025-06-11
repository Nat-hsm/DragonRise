"""
Update app.py with these security enhancements to protect against
forced browsing and cross-site scripting vulnerabilities.
"""

# Add these imports at the top of app.py
from utils.access_control import user_data_access_required, verify_content_type, log_access_attempt
from utils.xss_protection import sanitize_input, sanitize_rich_text, sanitize_filename, add_xss_protection_headers
from flask import current_app, request, flash, redirect, url_for, jsonify, abort
from flask_login import login_required, current_user
import os
import re
from datetime import datetime, timezone
from werkzeug.utils import secure_filename

# Replace the existing add_security_headers function with this enhanced version
@app.after_request
def add_security_headers(response):
    """Add security headers to HTTP response"""
    # Add XSS protection headers
    response = add_xss_protection_headers(response)
    
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    # Referrer policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # HTTP Strict Transport Security (HSTS)
    if request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # Feature Policy / Permissions Policy
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    
    return response

# Add this function to sanitize all template variables
@app.template_filter('sanitize')
def sanitize_template(value):
    """Template filter to sanitize output"""
    if isinstance(value, str):
        return sanitize_input(value)
    return value

# Update the get_user_stats function to use the user_data_access_required decorator
@app.route('/user/<int:user_id>/stats')
@login_required
@user_data_access_required
def user_stats(user_id):
    """Get user statistics with access control"""
    stats = get_user_stats(user_id)
    if stats:
        return jsonify(stats)
    return abort(404)

# Update the upload_screenshot function to use sanitize_filename
@app.route('/upload-screenshot', methods=['POST'])
@login_required
@limiter.limit("1000 per minute")  # Changed from 10 to 1000 per minute
@verify_content_type('multipart/form-data')
def upload_screenshot():
    try:
        # Check if a file was uploaded
        if 'screenshot' not in request.files:
            flash('No file selected', 'danger')
            return redirect(url_for('dashboard'))
            
        file = request.files['screenshot']
        
        # Check if filename is empty
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('dashboard'))
            
        # Sanitize the filename
        original_filename = file.filename
        sanitized_filename = sanitize_filename(original_filename)
        
        if sanitized_filename != original_filename:
            current_app.logger.warning(f"Filename sanitized: {original_filename} -> {sanitized_filename}")
            
        file.filename = sanitized_filename
            
        if file and allowed_file(file.filename):
            # Create uploads directory if it doesn't exist
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Secure the filename and save file
            filename = secure_filename(file.filename)
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
            unique_filename = f"{current_user.id}_{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            
            # Check file size before saving (limit to 5MB)
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            if file_size > 5 * 1024 * 1024:  # 5MB
                flash('File size exceeds the 5MB limit', 'danger')
                return redirect(url_for('dashboard'))
                
            file.seek(0)  # Reset file pointer to beginning
            file.save(filepath)
            
            # Log successful upload
            log_access_attempt(True, "File Upload", f"File {filename} uploaded successfully")
            
            # Process the image...
            # [Rest of the function remains the same]
        else:
            flash('Invalid file type. Please upload a PNG or JPG image.', 'danger')
            log_access_attempt(False, "File Upload", f"Invalid file type: {file.filename}")
    except Exception as e:
        app.logger.error(f'Screenshot upload error: {str(e)}')
        flash('An error occurred while processing your screenshot', 'danger')
        log_access_attempt(False, "File Upload", f"Error: {str(e)}")
    
    return redirect(url_for('dashboard'))

# Add this function to check for common XSS patterns in request data
@app.before_request
def check_for_xss_attempts():
    """Check for potential XSS attacks in request data"""
    # Common XSS patterns to check for
    xss_patterns = [
        r'<script.*?>',
        r'javascript:',
        r'onerror=',
        r'onload=',
        r'onclick=',
        r'onmouseover=',
        r'eval\(',
        r'document\.cookie',
        r'alert\(',
    ]
    
    # Check URL parameters
    for key, value in request.args.items():
        if isinstance(value, str):
            for pattern in xss_patterns:
                if re.search(pattern, value, re.IGNORECASE):
                    app.logger.warning(f"Potential XSS attempt detected in URL parameter: {key}={value}")
                    abort(400)  # Bad Request
    
    # Check form data
    if request.form:
        for key, value in request.form.items():
            if isinstance(value, str):
                for pattern in xss_patterns:
                    if re.search(pattern, value, re.IGNORECASE):
                        app.logger.warning(f"Potential XSS attempt detected in form data: {key}={value}")
                        abort(400)  # Bad Request