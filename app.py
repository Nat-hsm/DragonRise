from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort
from flask_login import UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.sql import text
from sqlalchemy import create_engine, text, func
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os
import logging
import bleach
import secrets
from werkzeug.utils import secure_filename
import re
from utils.security import init_security, PasswordManager, require_api_key, admin_required, sanitize_input, sanitize_filename, user_data_access_required, verify_content_type, log_access_attempt
from utils.logging_config import LogConfig, log_activity
from utils.database import setup_database
from utils.image_analyzer import ImageAnalyzer
from utils.time_utils import is_peak_hour, get_points_multiplier, get_peak_hours_message, get_current_peak_hour_info
from config import get_config, validate_config
from extensions import db, login_manager, migrate, cognito_auth
from authlib.integrations.flask_client import OAuth
from urllib.parse import urlencode

# Load environment variables
load_dotenv()

# Create Flask app
app = Flask(__name__)

# Configure logging before anything else
logging.basicConfig(level=logging.INFO)

# Load configuration based on environment
config = get_config()
app.config.from_object(config)

# Set allowed file extensions for uploads
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')

# Validate configuration
validate_config(config)

# Initialize app with environment-specific settings
config.init_app(app)

# Initialize extensions with app
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'
migrate.init_app(app, db)

# Initialize security features
_, limiter, limit_requests = init_security(app)

# Initialize logging
log_config = LogConfig(app)

# Setup database with fallback
try:
    engine = setup_database(app, db)
    app.logger.info("Database setup complete")
except Exception as e:
    app.logger.error(f"Failed to setup database: {str(e)}")
    # Continue anyway to allow app initialization, but functionality will be limited

# Import models AFTER extensions are initialized
from models import User, House, ClimbLog, StandingLog, StepLog, Achievement, init_houses, get_leaderboard, get_house_rankings, get_user_stats, init_admin

# Initialize cognito auth in app.py (add to your initialization section)
cognito_auth.init_app(app)

# Initialize OAuth
oauth = OAuth(app)
oauth.register(
    name='oidc',
    authority=f'https://cognito-idp.{app.config["AWS_REGION"]}.amazonaws.com/{app.config["COGNITO_USER_POOL_ID"]}',
    client_id=app.config['COGNITO_CLIENT_ID'],
    client_secret=app.config['COGNITO_CLIENT_SECRET'],
    server_metadata_url=f'https://cognito-idp.{app.config["AWS_REGION"]}.amazonaws.com/{app.config["COGNITO_USER_POOL_ID"]}/.well-known/openid-configuration',
    client_kwargs={'scope': 'email openid profile'}
)

# Add security headers to all responses
@app.after_request
def add_security_headers(response):
    """Add security headers to HTTP response"""
    # Update CSP to allow unsafe-inline for styles and scripts during development
    # In production, you should use nonces or hashes instead
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

# Add template filter to sanitize output
@app.template_filter('sanitize')
def sanitize_template(value):
    """Template filter to sanitize output"""
    if isinstance(value, str):
        return sanitize_input(value)
    return value

# Check for XSS attempts in request data
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

@app.route('/')
def index():
    houses = House.query.order_by(House.total_points.desc()).all()
    return render_template('index.html', houses=houses)

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("200 per minute")  # Changed from 5 to 200 per minute
def register():
    if request.method == 'POST':
        try:
            username = sanitize_input(request.form['username']).strip()
            password = request.form['password']
            house = sanitize_input(request.form['house'])

            # Validate input
            if not username or not password or not house:
                flash('All fields are required', 'danger')
                return redirect(url_for('register'))
                
            # Validate username format
            if not re.match(r'^[a-zA-Z0-9_-]{3,30}$', username):
                flash('Username must be 3-30 characters and contain only letters, numbers, underscores, and hyphens', 'danger')
                return redirect(url_for('register'))

            if User.query.filter_by(username=username).first():
                flash('Username already exists', 'danger')
                log_activity(app, None, 'Registration Failed', 'Username Exists')
                return redirect(url_for('register'))

            # Create new user with hashed password
            user = User(username=username, house=house)
            user.set_password(password)

            house_obj = House.query.filter_by(name=house).first()
            if house_obj:
                house_obj.member_count += 1
                db.session.add(user)
                db.session.commit()
                log_activity(app, user.id, 'Registration', 'Success')
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Invalid house selection', 'danger')
                log_activity(app, None, 'Registration Failed', 'Invalid House')
                return redirect(url_for('register'))

        except Exception as e:
            app.logger.error(f'Registration error: {str(e)}')
            db.session.rollback()
            flash('An error occurred during registration', 'danger')
            return redirect(url_for('register'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("200 per minute")
def login():
    if request.method == 'POST':
        # Keep your existing POST handling code
        pass
    
    # For GET requests, add these parameters to force a new session
    redirect_uri = app.config.get('COGNITO_REDIRECT_URI')
    params = {
        'prompt': 'login',
        'max_age': 0,  # Force re-authentication
        'id_token_hint': None  # Ignore any existing session
    }
    return oauth.oidc.authorize_redirect(redirect_uri, **params)

@app.route('/signup')
@limiter.limit("200 per minute")
def signup():
    """Direct users to Cognito signup flow"""
    redirect_uri = app.config.get('COGNITO_REDIRECT_URI')
    # Add parameters that force a fresh session
    params = {
        'prompt': 'login',
        'max_age': 0,
        'state': 'signup'
    }
    return oauth.oidc.authorize_redirect(redirect_uri, **params)

@app.route('/auth/callback')
def auth_callback():
    try:
        # Get authorization code
        code = request.args.get('code')
        state = request.args.get('state', 'login')
        
        if not code:
            app.logger.error("No authorization code received in callback")
            flash('Authentication failed: No authorization code received', 'danger')
            return redirect(url_for('index'))
        
        app.logger.info(f"Code received (first 8 chars): {code[:8]}... State: {state}")
        
        # Exchange code for token
        token_response = cognito_auth.get_token(code)
        
        if not token_response:
            app.logger.error("Token exchange failed - no response received")
            flash('Failed to authenticate: Could not exchange token', 'danger')
            return redirect(url_for('index'))
        
        app.logger.info(f"Token exchange successful! User authenticated.")
        
        # Get ID token and access token
        id_token = token_response.get('id_token')
        access_token = token_response.get('access_token')
        
        # Validate token
        claims = cognito_auth.validate_token(id_token)
        if not claims:
            flash('Invalid token', 'danger')
            return redirect(url_for('index'))
        
        # Get user info
        cognito_username = claims.get('cognito:username')
        email = claims.get('email')
        
        # Check if this is the admin user from Cognito (case-insensitive)
        is_admin_login = cognito_username.lower() == 'admin'
        
        # Check if user already exists in our database
        user = User.query.filter(User.username.ilike(cognito_username)).first()
        
        if not user:
            # New user - handle signup flow
            if state == 'signup' or is_admin_login:
                if is_admin_login:
                    # Create admin user automatically
                    user = User(
                        username='Admin',
                        email=email,
                        house='Admin',
                        is_admin=True
                    )
                    # Generate a secure password (they'll authenticate via Cognito)
                    import secrets
                    random_password = secrets.token_urlsafe(16)
                    user.set_password(random_password)
                    
                    db.session.add(user)
                    db.session.commit()
                    
                    # Log the admin user in
                    login_user(user)
                    
                    # Store tokens in session
                    session['cognito_id_token'] = id_token
                    session['cognito_access_token'] = access_token
                    
                    log_activity(app, user.id, 'Admin Registration', 'Success via Cognito')
                    flash('Admin account created successfully!', 'success')
                    return redirect(url_for('admin_dashboard'))
                else:
                    # Regular user signup, continue with house selection
                    session['temp_cognito_data'] = {
                        'username': cognito_username,
                        'email': email,
                        'id_token': id_token,
                        'access_token': access_token
                    }
                    return redirect(url_for('complete_registration'))
            else:
                # User doesn't exist but tried to login
                flash('Please register first', 'warning')
                return redirect(url_for('signup'))
        else:
            # Existing user - log them in
            
            # Ensure admin status is correct for admin user
            if is_admin_login and not user.is_admin:
                user.is_admin = True
                db.session.commit()
            
            login_user(user)
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            
            log_activity(app, user.id, 'Cognito Login', 'Success')
            flash('Welcome back, Dragon Climber!', 'success')
            
            # Store tokens in session
            session['cognito_id_token'] = id_token
            session['cognito_access_token'] = access_token
            
            # Redirect admin users to admin dashboard
            if user.is_admin:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))  # Instead of dashboard
            
    except Exception as e:
        app.logger.error(f'Auth callback error: {str(e)}')
        flash('Authentication error', 'danger')
        return redirect(url_for('index'))

# Add route to complete registration (house selection)
@app.route('/complete-registration', methods=['GET', 'POST'])
def complete_registration():
    # Check if we have temporary Cognito data
    if 'temp_cognito_data' not in session:
        flash('Registration session expired', 'danger')
        return redirect(url_for('signup'))
    
    cognito_data = session['temp_cognito_data']
    
    if request.method == 'POST':
        try:
            house = sanitize_input(request.form['house'])
            
            # Create new user with data from Cognito
            user = User(
                username=cognito_data['username'],
                house=house, 
                email=cognito_data['email']
            )
            
            # Generate a random password for the user (they'll use Cognito to authenticate)
            import secrets
            random_password = secrets.token_urlsafe(12)
            user.set_password(random_password)
            
            house_obj = House.query.filter_by(name=house).first()
            if house_obj:
                house_obj.member_count += 1
                db.session.add(user)
                db.session.commit()
                
                # Log the user in
                login_user(user)
                
                # Store tokens in session
                session['cognito_id_token'] = cognito_data['id_token']
                session['cognito_access_token'] = cognito_data['access_token']
                
                # Clear temporary data
                session.pop('temp_cognito_data', None)
                
                log_activity(app, user.id, 'Registration', 'Success via Cognito')
                flash('Registration successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid house selection', 'danger')
        
        except Exception as e:
            app.logger.error(f'Registration completion error: {str(e)}')
            flash('An error occurred during registration', 'danger')
    
    return render_template('complete_registration.html')

@app.route('/logout')
@login_required
def logout():
    # Store the current user's identity before logging out
    user_id = current_user.id if current_user.is_authenticated else None
    
    # Standard Flask-Login logout
    logout_user()
    
    # Clear all Flask session data
    session.clear()
    
    # Log activity
    if user_id:
        log_activity(app, user_id, 'Logout', 'Success')
    
    # Build Cognito logout URL with proper URL encoding and global_logout parameter
    from urllib.parse import quote
    domain = app.config.get('COGNITO_DOMAIN')
    client_id = app.config.get('COGNITO_CLIENT_ID')
    logout_uri = quote(url_for('index', _external=True))
    
    cognito_logout_url = f"https://{domain}.auth.{app.config.get('AWS_REGION')}.amazoncognito.com/logout?client_id={client_id}&logout_uri={logout_uri}&global_signout=true"
    
    flash('You have been logged out.', 'info')
    return redirect(cognito_logout_url)

@app.route('/admin-dashboard')
@login_required
@admin_required
def admin_dashboard():
    # Verify admin status again as an extra precaution
    if not current_user.is_admin:
        log_access_attempt(False, "Admin Dashboard", "Non-admin access attempt")
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))  # Update this line
        
    # Get all users
    users = User.query.all()
    
    # Get all houses
    houses = House.query.order_by(House.name).all()
    
    # Get peak hour settings
    try:
        from models import get_peak_hour_settings
        peak_hours = get_peak_hour_settings()
    except Exception as e:
        app.logger.error(f"Error getting peak hour settings: {str(e)}")
        peak_hours = []
    
    # Calculate total statistics
    total_stats = {
        'flights': db.session.query(func.sum(User.total_flights)).scalar() or 0,
        'standing_time': db.session.query(func.sum(User.total_standing_time)).scalar() or 0,
        'steps': db.session.query(func.sum(User.total_steps)).scalar() or 0,
        'points': db.session.query(func.sum(User.total_points)).scalar() or 0
    }
    
    # Get activity logs
    activity_logs = [
        {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'), 'username': 'System', 'action': 'System Startup', 'details': 'Application initialized'},
        {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'), 'username': 'Admin', 'action': 'Login', 'details': 'Admin logged in'}
    ]
    
    log_access_attempt(True, "Admin Dashboard", "Admin access successful")
    return render_template('admin_dashboard.html',
                         users=users,
                         houses=houses,
                         peak_hours=peak_hours,
                         total_stats=total_stats,
                         activity_logs=activity_logs)

@app.route('/admin-dashboard/delete-user', methods=['POST'])
@login_required
@admin_required
@limiter.limit("200 per minute")  # Add rate limiting here instead
@verify_content_type('application/x-www-form-urlencoded')
def delete_user():
    # Verify admin status again as an extra precaution
    if not current_user.is_admin:
        log_access_attempt(False, "Delete User", "Non-admin access attempt")
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('admin_dashboard'))
        
    try:
        user_id = request.form.get('user_id')
        if not user_id:
            flash('User ID is required', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        # Validate user_id is an integer
        try:
            user_id = int(user_id)
        except ValueError:
            flash('Invalid user ID', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        # Find the user
        user = User.query.get_or_404(user_id)
        
        # Don't allow deleting the admin user
        if user.is_admin:
            log_access_attempt(False, "Delete User", f"Attempted to delete admin user: {user.username}")
            flash('Cannot delete admin user', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Get user's house to update member count
        house = House.query.filter_by(name=user.house).first()
        if house:
            house.remove_member()
            
            # Subtract user's points from house total
            house.total_points -= user.total_points
            house.total_flights -= user.total_flights
            if hasattr(house, 'total_standing_time'):
                house.total_standing_time -= user.total_standing_time
        
        # Delete user's logs
        ClimbLog.query.filter_by(user_id=user_id).delete()
        StandingLog.query.filter_by(user_id=user_id).delete()
        
        # Delete user
        username = user.username  # Store for logging
        db.session.delete(user)
        db.session.commit()
        
        # Log the activity
        log_access_attempt(True, "Delete User", f"User {username} was deleted")
        log_activity(app, current_user.id, 'User Deleted', f'User {username} was deleted')
        flash(f'User {username} has been deleted', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting user: {str(e)}")
        flash('An error occurred while deleting the user', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/log_climb', methods=['POST'])
@login_required
@limiter.limit("200 per minute")
@verify_content_type('application/x-www-form-urlencoded')
def log_climb():
    try:
        # Validate flights is an integer
        try:
            flights = int(request.form['flights'])
        except (ValueError, TypeError):
            flash('Please enter a valid number of flights', 'danger')
            return redirect(url_for('dashboard'))
            
        if flights <= 0 or flights > 1000:  # Added upper limit
            flash('Please enter a valid number of flights (1-1000)', 'danger')
            return redirect(url_for('dashboard'))

        # Sanitize notes if provided
        notes = None
        if 'notes' in request.form and request.form['notes']:
            notes = sanitize_input(request.form['notes'])

        # Check if it's peak hour for multiplier
        multiplier = get_points_multiplier()
        points = flights * 10 * multiplier

        # Create climb log
        log = ClimbLog(user_id=current_user.id, flights=flights, points=points, notes=notes)

        # Update user stats
        current_user.total_flights += flights
        current_user.total_points += points

        # Update house points
        house = House.query.filter_by(name=current_user.house).first()
        if not house:
            raise ValueError('Invalid house association')

        house.total_points += points
        house.total_flights += flights

        db.session.add(log)
        db.session.commit()

        # Add multiplier info to the message if applicable
        multiplier_text = f" ({multiplier}x multiplier!)" if multiplier > 1 else ""
        log_activity(app, current_user.id, 'Climb Logged', f'{flights} flights{multiplier_text}')
        flash(f'Added {points} points to {current_user.house} house!{multiplier_text}', 'success')

    except ValueError as e:
        flash('Please enter a valid number of flights', 'danger')
        app.logger.warning(f'Invalid climb input: {str(e)}')
    except Exception as e:
        flash('An error occurred while logging your climb', 'danger')
        app.logger.error(f'Climb logging error: {str(e)}')
        db.session.rollback()

    return redirect(url_for('dashboard'))

@app.route('/log_standing', methods=['POST'])
@login_required
@limiter.limit("200 per minute")
@verify_content_type('application/x-www-form-urlencoded')
def log_standing():
    try:
        # Validate minutes is an integer
        try:
            minutes = int(request.form['minutes'])
        except (ValueError, TypeError):
            flash('Please enter a valid number of minutes', 'danger')
            return redirect(url_for('standing_dashboard'))
            
        if minutes <= 0 or minutes > 1440:  # Added upper limit (24 hours)
            flash('Please enter a valid number of minutes (1-1440)', 'danger')
            return redirect(url_for('standing_dashboard'))

        # Sanitize notes if provided
        notes = None
        if 'notes' in request.form and request.form['notes']:
            notes = sanitize_input(request.form['notes'])

        # Check if it's peak hour for multiplier
        multiplier = get_points_multiplier()
        points = minutes * multiplier
        
        # Create standing log
        log = StandingLog(user_id=current_user.id, minutes=minutes, points=points, notes=notes)

        # Update user stats with multiplier
        current_user.total_standing_time += minutes
        current_user.total_points += points

        # Update house points
        house = House.query.filter_by(name=current_user.house).first()
        if not house:
            raise ValueError('Invalid house association')

        # Update house stats with multiplier
        house.total_points += points
        if hasattr(house, 'total_standing_time'):
            house.total_standing_time += minutes
        else:
            app.logger.warning(f"House {house.name} doesn't have total_standing_time attribute")

        db.session.add(log)
        db.session.commit()

        # Add multiplier info to the message if applicable
        multiplier_text = f" ({multiplier}x multiplier!)" if multiplier > 1 else ""
        log_activity(app, current_user.id, 'Standing Time Logged', f'{minutes} minutes{multiplier_text}')
        flash(f'Added {points} points to {current_user.house} house for standing time!{multiplier_text}', 'success')

    except ValueError as e:
        flash('Please enter a valid number of minutes', 'danger')
        app.logger.warning(f'Invalid standing time input: {str(e)}')
    except Exception as e:
        flash('An error occurred while logging your standing time', 'danger')
        app.logger.error(f'Standing time logging error: {str(e)}')
        db.session.rollback()

    return redirect(url_for('dashboard'))

@app.route('/log_steps', methods=['POST'])
@login_required
def log_steps():
    try:
        steps = int(request.form['steps'])
        if steps <= 0:
            flash('Please enter a valid number of steps', 'danger')
            return redirect(url_for('steps_dashboard'))

        # Check if it's peak hour for multiplier
        multiplier = get_points_multiplier()
        points = (steps // 100) * multiplier  # 1 point per 100 steps, with multiplier

        # Create step log
        log = StepLog(user_id=current_user.id, steps=steps, points=points)

        # Update user stats
        if hasattr(current_user, 'total_steps'):
            current_user.total_steps += steps
            current_user.total_points += points

            # Update house points
            house = House.query.filter_by(name=current_user.house).first()
            if not house:
                raise ValueError('Invalid house association')

            house.total_points += points
            if hasattr(house, 'total_steps'):
                house.total_steps += steps

            db.session.add(log)
            db.session.commit()

            # Add multiplier info to the message if applicable
            multiplier_text = f" ({multiplier}x multiplier!)" if multiplier > 1 else ""
            log_activity(app, current_user.id, 'Steps Logged', f'{steps} steps{multiplier_text}')
            flash(f'Added {points} points to {current_user.house} house!{multiplier_text}', 'success')
        else:
            flash('Steps tracking is not available yet. Please run the migration script.', 'warning')

    except ValueError as e:
        flash('Please enter a valid number of steps', 'danger')
        app.logger.warning(f'Invalid steps input: {str(e)}')
    except Exception as e:
        flash('An error occurred while logging your steps', 'danger')
        app.logger.error(f'Steps logging error: {str(e)}')
        db.session.rollback()

    return redirect(url_for('dashboard'))

@app.route('/upload-screenshot', methods=['POST'])
@login_required
@limiter.limit("1000 per minute")
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
            app.logger.warning(f"Filename sanitized: {original_filename} -> {sanitized_filename}")
            
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
            
            # Create image analyzer and process the image
            image_analyzer = ImageAnalyzer()
            file.seek(0)  # Reset file pointer to beginning
            result = image_analyzer.analyze_image(file)
            
            if result.get('success'):
                flights = result.get('flights')
                
                # Validate flights is within reasonable range
                if flights <= 0 or flights > 1000:
                    flash('Invalid number of flights detected in the screenshot', 'danger')
                    return redirect(url_for('dashboard'))
                    
                timestamp_str = result.get('timestamp')
                
                # Check if it's peak hour for multiplier
                multiplier = get_points_multiplier()
                points = flights * 10 * multiplier
                
                # Log the climb
                log = ClimbLog(user_id=current_user.id, flights=flights, points=points)
                
                # Update user stats
                current_user.total_flights += flights
                current_user.total_points += points
                
                # Update house points
                house = House.query.filter_by(name=current_user.house).first()
                if house:
                    house.total_points += points
                    house.total_flights += flights
                
                db.session.add(log)
                db.session.commit()
                
                # Add multiplier info to the message if applicable
                multiplier_text = f" ({multiplier}x multiplier!)" if multiplier > 1 else ""
                log_activity(app, current_user.id, 'Screenshot Climb Logged', f'{flights} flights{multiplier_text}')
                flash(f'Successfully processed screenshot! Added {points} points for {flights} flights.{multiplier_text}', 'success')
            else:
                flash(f'Could not process screenshot: {result.get("error", "Unknown error")}', 'danger')
        else:
            flash('Invalid file type. Please upload a PNG or JPG image.', 'danger')
            log_access_attempt(False, "File Upload", f"Invalid file type: {file.filename}")
    except Exception as e:
        app.logger.error(f'Screenshot upload error: {str(e)}')
        flash('An error occurred while processing your screenshot', 'danger')
        log_access_attempt(False, "File Upload", f"Error: {str(e)}")
    
    return redirect(url_for('dashboard'))

@app.route('/upload-standing-screenshot', methods=['POST'])
@login_required
@limiter.limit("1000 per minute")  # Added rate limiting
def upload_standing_screenshot():
    try:
        # Check if a file was uploaded
        if 'screenshot' not in request.files:
            flash('No file selected', 'danger')
            return redirect(url_for('standing_dashboard'))
            
        file = request.files['screenshot']
        
        # Check if filename is empty
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('standing_dashboard'))
            
        if file and allowed_file(file.filename):
            # Create uploads directory if it doesn't exist
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Secure the filename and save file
            filename = secure_filename(file.filename)
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
            unique_filename = f"{current_user.id}_standing_{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            # Create image analyzer and process the image
            image_analyzer = ImageAnalyzer()
            file.seek(0)  # Reset file pointer to beginning
            result = image_analyzer.analyze_standing_image(file)
            
            if result.get('success'):
                minutes = result.get('minutes', 0)
                
                # Check if it's peak hour for multiplier
                multiplier = get_points_multiplier()
                points = minutes * multiplier
                
                # Log the standing time
                log = StandingLog(user_id=current_user.id, minutes=minutes, points=points)
                
                # Update user stats
                current_user.total_standing_time += minutes
                current_user.total_points += points
                
                # Update house points
                house = House.query.filter_by(name=current_user.house).first()
                if house:
                    house.total_points += points
                    if hasattr(house, 'total_standing_time'):
                        house.total_standing_time += minutes
                
                db.session.add(log)
                db.session.commit()
                
                # Add multiplier info to the message if applicable
                multiplier_text = f" ({multiplier}x multiplier!)" if multiplier > 1 else ""
                log_activity(app, current_user.id, 'Screenshot Standing Logged', f'{minutes} minutes{multiplier_text}')
                flash(f'Successfully processed screenshot! Added {points} points for {minutes} minutes of standing time.{multiplier_text}', 'success')
            else:
                flash(f'Could not process screenshot: {result.get("error", "Unknown error")}', 'danger')
        else:
            flash('Invalid file type. Please upload a PNG or JPG image.', 'danger')
    except Exception as e:
        app.logger.error(f'Standing screenshot upload error: {str(e)}')
        flash('An error occurred while processing your screenshot', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/upload-steps-screenshot', methods=['POST'])
@login_required
@limiter.limit("1000 per minute")  # Added rate limiting
def upload_steps_screenshot():
    try:
        # Check if a file was uploaded
        if 'screenshot' not in request.files:
            flash('No file selected', 'danger')
            return redirect(url_for('steps_dashboard'))
            
        file = request.files['screenshot']
        
        # Check if filename is empty
        if file.filename == '':
            flash('No file selected', 'danger')
            return redirect(url_for('steps_dashboard'))
            
        if file and allowed_file(file.filename):
            # Create uploads directory if it doesn't exist
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Secure the filename and save file
            filename = secure_filename(file.filename)
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
            unique_filename = f"{current_user.id}_steps_{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            # Create image analyzer and process the image
            image_analyzer = ImageAnalyzer()
            file.seek(0)  # Reset file pointer to beginning
            result = image_analyzer.analyze_steps_image(file)
            
            if result.get('success'):
                steps = result.get('steps', 0)
                
                if hasattr(current_user, 'total_steps'):
                    # Check if it's peak hour for multiplier
                    multiplier = get_points_multiplier()
                    points = (steps // 100) * multiplier
                    
                    # Log the steps
                    log = StepLog(user_id=current_user.id, steps=steps, points=points)
                    
                    # Update user stats
                    current_user.total_steps += steps
                    current_user.total_points += points
                    
                    # Update house points
                    house = House.query.filter_by(name=current_user.house).first()
                    if house:
                        house.total_points += points
                        if hasattr(house, 'total_steps'):
                            house.total_steps += steps
                    
                    db.session.add(log)
                    db.session.commit()
                    
                    # Add multiplier info to the message if applicable
                    multiplier_text = f" ({multiplier}x multiplier!)" if multiplier > 1 else ""
                    log_activity(app, current_user.id, 'Screenshot Steps Logged', f'{steps} steps{multiplier_text}')
                    flash(f'Successfully processed screenshot! Added {points} points for {steps} steps.{multiplier_text}', 'success')
                else:
                    flash('Steps tracking is not available yet. Please run the migration script.', 'warning')
            else:
                flash(f'Could not process screenshot: {result.get("error", "Unknown error")}', 'danger')
        else:
            flash('Invalid file type. Please upload a PNG or JPG image.', 'danger')
    except Exception as e:
        app.logger.error(f'Steps screenshot upload error: {str(e)}')
        flash('An error occurred while processing your screenshot', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/api/house_points')
@require_api_key
def house_points():
    houses = House.query.all()
    return jsonify([{
        'name': house.name,
        'points': house.total_points,
        'members': house.member_count
    } for house in houses])

@app.route('/health')
def health_check():
    try:
        # Check database connection
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 200
    except Exception as e:
        app.logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }), 500

# Error handlers
@app.errorhandler(OperationalError)
def handle_db_connection_error(e):
    app.logger.error(f"Database connection error: {e}")
    return "Database connection error. Please try again later.", 500

@app.errorhandler(SQLAlchemyError)
def handle_sqlalchemy_error(e):
    app.logger.error(f"Database error: {e}")
    return "An error occurred while processing your request.", 500

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    app.logger.warning(f"Forbidden access attempt: {request.path}")
    return render_template('404.html'), 403  # Use 404 template to not confirm existence

@app.errorhandler(400)
def bad_request_error(error):
    app.logger.warning(f"Bad request: {request.path}")
    return "Bad request. The server could not understand your request.", 400

@app.context_processor
def utility_processor():
    def get_house_count():
        return House.query.count()
    
    # Add peak hour information to all templates
    is_peak, multiplier, peak_name = get_current_peak_hour_info()
    return {
        'get_house_count': get_house_count,
        'is_peak_hour': is_peak,
        'peak_hour_multiplier': multiplier,
        'peak_hour_name': peak_name,
        'peak_hours_message': get_peak_hours_message(),
        'sanitize': sanitize_input  # Add sanitize function to all templates
    }

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

def init_db():
    """Initialize the database with required initial data"""
    app.logger.info("Initializing database...")
    try:
        with app.app_context():
            # Create tables
            db.create_all()
            app.logger.info("Database tables created")
            
            # Initialize houses
            init_houses()
            app.logger.info("Houses initialized")
            
            # Initialize admin user
            init_admin()
            app.logger.info("Admin user initialized")
            
            # Initialize peak hours
            from models import init_peak_hours
            init_peak_hours()
            app.logger.info("Peak hours initialized")
            
            return True
    except OperationalError as e:
        app.logger.error(f"Database initialization error: {str(e)}")
        return False
    except Exception as e:
        app.logger.error(f"Unexpected error during database initialization: {str(e)}")
        return False

def allowed_file(filename):
    """Check if the file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg'})

if __name__ == '__main__':
    # Initialize the admin user on startup
    with app.app_context():
        result = init_admin()
        if result == "created":
            print("Admin user created")
        elif result == "updated":
            print("Admin user credentials updated")
        else:
            print("Admin user already exists")
    
    # Use debug mode from environment variable and set port to 5000
    debug_mode = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')
    app.run(debug=debug_mode, port=5001)

@app.route('/dashboard')
@login_required
def dashboard():
    """Unified dashboard combining flights, steps, and standing activities"""
    # Redirect admin to admin dashboard if they try to access this
    if current_user.is_admin:
        flash('Admin users should use the Admin Dashboard', 'info')
        return redirect(url_for('admin_dashboard'))
    
    # Get house data for the leaderboard
    houses = House.query.order_by(House.total_points.desc()).all()
    
    # Get recent logs for the current user
    recent_climb_logs = ClimbLog.query.filter_by(user_id=current_user.id)\
        .order_by(ClimbLog.timestamp.desc()).limit(3).all()
    
    recent_standing_logs = StandingLog.query.filter_by(user_id=current_user.id)\
        .order_by(StandingLog.timestamp.desc()).limit(3).all()
    
    recent_steps_logs = StepLog.query.filter_by(user_id=current_user.id)\
        .order_by(StepLog.timestamp.desc()).limit(3).all()
    
    # Combine all activities into a single timeline
    all_activities = []
    
    # Add climb logs
    for log in recent_climb_logs:
        all_activities.append({
            'type': 'climb',
            'value': log.flights,
            'points': log.points,
            'timestamp': log.timestamp,
            'formatted_timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M') if hasattr(log.timestamp, 'strftime') else str(log.timestamp)
        })
    
    # Add standing logs
    for log in recent_standing_logs:
        all_activities.append({
            'type': 'standing',
            'value': log.minutes,
            'points': log.points,
            'timestamp': log.timestamp,
            'formatted_timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M') if hasattr(log.timestamp, 'strftime') else str(log.timestamp)
        })
    
    # Add steps logs
    for log in recent_steps_logs:
        all_activities.append({
            'type': 'steps',
            'value': log.steps,
            'points': log.points,
            'timestamp': log.timestamp,
            'formatted_timestamp': log.timestamp.strftime('%Y-%m-%d %H:%M') if hasattr(log.timestamp, 'strftime') else str(log.timestamp)
        })
    
    # Sort all activities by timestamp (most recent first)
    all_activities.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return render_template('unified_dashboard.html',
                           houses=houses,
                           all_activities=all_activities,
                           recent_climb_logs=recent_climb_logs,
                           recent_standing_logs=recent_standing_logs,
                           recent_steps_logs=recent_steps_logs)

@app.route('/analytics-dashboard')
@login_required
@admin_required
def analytics_dashboard():
    """Analytics dashboard for administrators"""
    # Verify admin status again as an extra precaution
    if not current_user.is_admin:
        log_access_attempt(False, "Analytics Dashboard", "Non-admin access attempt")
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    houses = House.query.order_by(House.name).all()
    
    # Get all logs for reference (if needed)
    climb_logs = ClimbLog.query.order_by(ClimbLog.timestamp.desc()).limit(1000).all()
    standing_logs = StandingLog.query.order_by(StandingLog.timestamp.desc()).limit(1000).all()
    steps_logs = StepLog.query.order_by(StepLog.timestamp.desc()).limit(1000).all()
    
    # Prepare data for charts
    house_names = [house.name for house in houses]
    
    # Define colors for each house
    house_colors = {
        'Black': 'rgba(51, 51, 51, 0.8)',
        'Blue': 'rgba(0, 102, 204, 0.8)',
        'Green': 'rgba(0, 153, 51, 0.8)',
        'White': 'rgba(248, 249, 250, 0.8)',
        'Gold': 'rgba(255, 204, 0, 0.8)',
        'Purple': 'rgba(102, 0, 153, 0.8)'
    }
    
    house_colors_list = [house_colors.get(name, 'rgba(150, 150, 150, 0.8)') for name in house_names]
    
    # Prepare climbing data
    climbing_data = {
        'flights': [house.total_flights for house in houses],
        'points': [house.total_flights * 10 for house in houses]
    }
    
    # Prepare standing data
    standing_data = {
        'minutes': [getattr(house, 'total_standing_time', 0) for house in houses],
        'points': [getattr(house, 'total_standing_time', 0) for house in houses]
    }
    
    # Prepare steps data
    steps_data = {
        'steps': [getattr(house, 'total_steps', 0) for house in houses],
        'points': [getattr(house, 'total_steps', 0) // 100 for house in houses]
    }
    
    # Prepare combined data
    combined_data = {
        'climbing_points': [house.total_flights * 10 for house in houses],
        'standing_points': [getattr(house, 'total_standing_time', 0) for house in houses],
        'steps_points': [getattr(house, 'total_steps', 0) // 100 for house in houses],
        'total_points': [house.total_points for house in houses]
    }
    
    # Get activity by house
    house_activity = {}
    for house in houses:
        house_activity[house.name] = {
            'flights': house.total_flights,
            'standing_time': house.total_standing_time,
            'steps': house.total_steps if hasattr(house, 'total_steps') else 0,
            'points': house.total_points,
            'member_count': house.member_count
        }
    log_access_attempt(True, "Analytics Dashboard", "Admin access successful")
    return render_template('analytics_dashboard.html',
                         houses=houses,
                         house_names=house_names,
                         house_colors=house_colors_list,
                         climbing_data=climbing_data,
                         standing_data=standing_data,
                         steps_data=steps_data,
                         combined_data=combined_data,
                         climb_logs=climb_logs,
                         standing_logs=standing_logs,
                         steps_logs=steps_logs,
                         house_activity=house_activity)