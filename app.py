from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort
from flask_login import UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.sql import text
from sqlalchemy import create_engine, text, func, and_
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
# Add the missing OAuth import
from authlib.integrations.flask_client import OAuth
from urllib.parse import urlencode, quote
# Import models - add init_houses, init_admin, and init_peak_hours to the imports
from models import User, House, ClimbLog, StandingLog, StepLog, Event, get_active_event, is_in_active_event, get_event_points, init_houses, init_admin, init_peak_hours, should_award_points

# For Google Fit Integration and Garmin API
import requests
import base64
import hashlib
import pkce  # pip install pkce

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
    
    # Check if there's an active event
    active_event = get_active_event()
    
    # If there's an active event, get event-specific points for each house
    house_event_points = {}
    if active_event:
        for house in houses:
            house_event_points[house.name] = get_event_points(house_name=house.name)
    
    return render_template('index.html', 
                          houses=houses,
                          active_event=active_event,
                          house_event_points=house_event_points)

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("200 per minute")
def register():
    """Redirect to Cognito signup flow"""
    flash('Please register using the secure AWS Cognito authentication system', 'info')
    return redirect(url_for('signup'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("200 per minute")
def login():
    """Direct users to Cognito login flow"""
    try:
        # For all requests, redirect to Cognito auth
        redirect_uri = app.config.get('COGNITO_REDIRECT_URI')
        
        # Use the updated CognitoAuth implementation to get the correct login URL
        login_url = cognito_auth.get_login_url()
        app.logger.info(f"Redirecting to Cognito login: {login_url}")
        
        return redirect(login_url)
    except Exception as e:
        app.logger.error(f"Error redirecting to login: {str(e)}")
        flash('An error occurred during login. Please try again.', 'danger')
        return redirect(url_for('index'))

@app.route('/signup')
@limiter.limit("200 per minute")
def signup():
    """Direct users to Cognito signup flow"""
    try:
        # Use the updated CognitoAuth implementation to get the correct login URL
        # Add state parameter to indicate this is a signup flow
        login_url = cognito_auth.get_login_url(state='signup')
        app.logger.info(f"Redirecting to Cognito signup: {login_url}")
        
        return redirect(login_url)
    except Exception as e:
        app.logger.error(f"Error redirecting to signup: {str(e)}")
        flash('An error occurred during signup. Please try again.', 'danger')
        return redirect(url_for('index'))

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
            
            # Store tokens in session
            session['cognito_id_token'] = id_token
            session['cognito_access_token'] = access_token
            
            # Redirect admin users to admin dashboard with appropriate message
            if user.is_admin:
                flash('Welcome to the admin dashboard!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash('Welcome back, Dragon Climber!', 'success')
                return redirect(url_for('dashboard'))
            
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
    
# Remove Google Fit tokens on logout
    current_user.google_fit_token = None
    current_user.google_refresh_token = None
    current_user.google_token_expiry = None
    db.session.commit()

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
        return redirect(url_for('dashboard'))
        
    # Get all users
    users = User.query.all()
    
    # Get all houses
    houses = House.query.order_by(House.name).all()
    
    # Check if there's an active event
    active_event = get_active_event()
    
    # Get event-specific points for users and houses if an event is active
    user_event_points = {}
    house_event_points = {}
    if active_event:
        # Get event points for each user
        for user in users:
            user_event_points[user.id] = get_event_points(user_id=user.id)
        
        # Get event points for each house
        for house in houses:
            house_event_points[house.name] = get_event_points(house_name=house.name)
    
    # Get peak hour settings
    try:
        from models import get_peak_hour_settings
        peak_hours = get_peak_hour_settings()
    except Exception as e:
        app.logger.error(f"Error getting peak hour settings: {str(e)}")
        peak_hours = []
    
    # Get events
    try:
        events = Event.query.order_by(Event.start_date.desc()).all()
    except Exception as e:
        app.logger.error(f"Error getting events: {str(e)}")
        events = []
    
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
                         activity_logs=activity_logs,
                         events=events,
                         active_event=active_event,
                         user_event_points=user_event_points,
                         house_event_points=house_event_points)

@app.route('/admin-dashboard/delete-user', methods=['POST'])
@login_required
@admin_required
@limiter.limit("200 per minute")
@verify_content_type('application/x-www-form-urlencoded')
def delete_user():
    """Delete a user from the database and optionally from Cognito"""
    try:
        user_id = request.form.get('user_id')
        delete_from_cognito = request.form.get('delete_from_cognito', 'false').lower() == 'true'
        
        if not user_id:
            flash('No user specified', 'danger')
            return redirect(url_for('user_management'))
            
        user = User.query.get(user_id)
        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('user_management'))
            
        if user.is_admin:
            log_access_attempt(False, "Delete User", f"Attempted to delete admin user: {user.username}")
            flash('Cannot delete admin user', 'danger')
            return redirect(url_for('user_management'))
            
        username = user.username
        email = user.email
        house_name = user.house
        
        # Delete from Cognito if requested
        if delete_from_cognito:
            try:
                # Try to find user in Cognito by username first, then by email if not found
                cognito_username = None
                
                # Search by username
                username_filter = f'username = "{username}"'
                cognito_users = cognito_sync.client.list_users(
                    UserPoolId=cognito_sync.user_pool_id,
                    Filter=username_filter
                )
                
                if cognito_users.get('Users'):
                    cognito_username = cognito_users['Users'][0]['Username']
                elif email:
                    # If not found by username, try by email
                    email_filter = f'email = "{email}"'
                    cognito_users = cognito_sync.client.list_users(
                        UserPoolId=cognito_sync.user_pool_id,
                        Filter=email_filter
                    )
                    if cognito_users.get('Users'):
                        cognito_username = cognito_users['Users'][0]['Username']
                
                # Delete user if found
                if cognito_username:
                    cognito_sync.client.admin_delete_user(
                        UserPoolId=cognito_sync.user_pool_id,
                        Username=cognito_username
                    )
                    flash(f'User {username} deleted from Cognito', 'success')
                else:
                    flash(f'User {username} not found in Cognito', 'warning')
            except Exception as e:
                app.logger.error(f"Error deleting user from Cognito: {str(e)}")
                flash(f'Failed to delete user from Cognito: {str(e)}', 'warning')
        
        # Update house member count and total points
        house = House.query.filter_by(name=house_name).first()
        if house:
            # Decrement member count
            if house.member_count > 0:
                house.member_count -= 1
            
            # Subtract user's points from house total
            house.total_points -= user.total_points
            house.total_flights -= user.total_flights
            if hasattr(house, 'total_standing_time'):
                house.total_standing_time -= user.total_standing_time
            if hasattr(house, 'total_steps') and hasattr(user, 'total_steps'):
                house.total_steps -= user.total_steps
            
        # Delete the user from our database
        db.session.delete(user)
        db.session.commit()
        
        log_activity(app, current_user.id, 'User Deleted', f'Deleted user {username}')
        flash(f'User {username} has been deleted', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting user: {str(e)}")
        flash('An error occurred while deleting the user', 'danger')
        
    return redirect(url_for('user_management'))

@app.route('/admin-dashboard/add-event', methods=['POST'])
@login_required
@admin_required
@limiter.limit("200 per minute")
@verify_content_type('application/x-www-form-urlencoded')
def add_event():
    try:
        name = request.form.get('name')
        description = request.form.get('description')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        
        # Validate input
        if not name or not start_date_str or not end_date_str:
            flash('Name, start date, and end date are required', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Parse dates
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        
        # Validate dates
        if end_date < start_date:
            flash('End date must be after start date', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Create new event
        new_event = Event(
            name=name,
            description=description,
            start_date=start_date,
            end_date=end_date,
            is_active=False  # New events are inactive by default
        )
        
        db.session.add(new_event)
        db.session.commit()
        
        # Log the activity
        log_activity(app, current_user.id, 'Event Created', f'Created new event: {name}')
        flash(f'Event "{name}" has been created successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error adding event: {str(e)}")
        flash('An error occurred while creating the event', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin-dashboard/edit-event', methods=['POST'])
@login_required
@admin_required
@limiter.limit("200 per minute")
@verify_content_type('application/x-www-form-urlencoded')
def edit_event():
    try:
        event_id = request.form.get('event_id')
        name = request.form.get('name')
        description = request.form.get('description')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        
        # Validate input
        if not event_id or not name or not start_date_str or not end_date_str:
            flash('All fields are required', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Find the event
        event = Event.query.get_or_404(int(event_id))
        
        # Parse dates
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        
        # Validate dates
        if end_date < start_date:
            flash('End date must be after start date', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Update event
        event.name = name
        event.description = description
        event.start_date = start_date
        event.end_date = end_date
        
        db.session.commit();
        
        # Log the activity
        log_activity(app, current_user.id, 'Event Updated', f'Updated event: {name}')
        flash(f'Event "{name}" has been updated successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating event: {str(e)}")
        flash('An error occurred while updating the event', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin-dashboard/toggle-event', methods=['POST'])
@login_required
@admin_required
@limiter.limit("200 per minute")
@verify_content_type('application/x-www-form-urlencoded')
def toggle_event():
    try:
        event_id = request.form.get('event_id')
        if not event_id:
            flash('Event ID is required', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Find the event
        event = Event.query.get_or_404(int(event_id))
        
        # Toggle active status
        if not event.is_active:
            # Check for any existing active events
            current_active_events = Event.query.filter_by(is_active=True).all()
            
            if current_active_events:
                # Log which events are being deactivated
                for active_event in current_active_events:
                    log_activity(app, current_user.id, 'Event Deactivated', 
                                f'Event "{active_event.name}" automatically deactivated when activating "{event.name}"')
                    app.logger.info(f'Auto-deactivating event: {active_event.name} (ID: {active_event.id})')
                
                # Deactivate all other events
                Event.query.filter_by(is_active=True).update({'is_active': False})
                app.logger.info(f'Successfully deactivated {len(current_active_events)} existing active events')
            
            # Activate this event
            event.is_active = True
            status_change = "activated"
            flash_class = "success"
            
            # Note: No longer resetting points - instead will display event-specific points
            
        else:
            # Deactivate this event
            event.is_active = False
            status_change = "deactivated"
            flash_class = "warning"
        
        db.session.commit()
        
        # Log the activity
        log_activity(app, current_user.id, f'Event {status_change.capitalize()}', f'{event.name} {status_change}')
        
        if status_change == "activated":
            flash(f'Event "{event.name}" has been activated. Points display will show only points accumulated during this event.', flash_class)
        else:
            flash(f'Event "{event.name}" has been deactivated. Points display now shows all-time points.', flash_class)
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error toggling event: {str(e)}")
        flash('An error occurred while updating the event status', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin-dashboard/delete-event', methods=['POST'])
@login_required
@admin_required
@limiter.limit("200 per minute")
@verify_content_type('application/x-www-form-urlencoded')
def delete_event():
    try:
        event_id = request.form.get('event_id')
        if not event_id:
            flash('Event ID is required', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Find the event
        event = Event.query.get_or_404(int(event_id))
        
        # Store name for confirmation message
        event_name = event.name
        
        # Don't allow deleting active events
        if event.is_active:
            flash('Cannot delete an active event. Please deactivate it first.', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Delete the event
        db.session.delete(event)
        db.session.commit()
        
        # Log the activity
        log_activity(app, current_user.id, 'Event Deleted', f'Deleted event: {event_name}')
        flash(f'Event "{event_name}" has been deleted', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting event: {str(e)}")
        flash('An error occurred while deleting the event', 'danger')
    
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
        db.session.add(log)

        # Check if we should award points (based on active event)
        if should_award_points():
            # Update user stats
            current_user.total_flights += flights
            current_user.total_points += points

            # Update house points
            house = House.query.filter_by(name=current_user.house).first()
            if house:
                house.total_points += points
                house.total_flights += flights
        else:
            # If we're outside the event period, record the activity but don't award points
            app.logger.info(f"Activity logged but no points awarded (outside active event): {flights} flights by user {current_user.id}")
            flash_message = "Your activity has been logged, but points are only awarded during active events."
            flash(flash_message, 'warning')
            
            # Commit the log entry only
            db.session.commit()
            return redirect(url_for('dashboard'))

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
                activity_date_str = result.get('date')  # Get date from the image
                
                # Parse the date from the image if available, otherwise use current date
                if activity_date_str:
                    try:
                        # Try to parse the date string in YYYY-MM-DD format
                        activity_date = datetime.strptime(activity_date_str, '%Y-%m-%d')
                        activity_date = activity_date.replace(tzinfo=timezone.utc)
                        
                        # Validate that the backdated timestamp is allowed
                        is_valid, message = validate_backdated_timestamp(activity_date)
                        if not is_valid:
                            flash(message, 'danger')
                            return redirect(url_for('dashboard'))
                            
                        # Set time to start of day
                        activity_date = activity_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    except ValueError:
                        # If date parsing fails, default to today
                        activity_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                else:
                    # Default to today if no date in image
                    activity_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                
                # Calculate tomorrow for the query
                tomorrow = activity_date + timedelta(days=1)
                
                # Validate flights is within reasonable range
                if flights <= 0 or flights > 1000:
                    flash('Invalid number of flights detected in the screenshot', 'danger')
                    return redirect(url_for('dashboard'))
                    
                # Find the most recent climb log for the activity date
                latest_log = ClimbLog.query.filter(
                    ClimbLog.user_id == current_user.id,
                    ClimbLog.timestamp >= activity_date,
                    ClimbLog.timestamp < tomorrow
                ).order_by(ClimbLog.flights.desc()).first()
                
                # Calculate incremental flights to avoid double counting
                existing_flights = latest_log.flights if latest_log else 0
                
                if flights <= existing_flights:
                    flash(f'No new flights detected. Your recorded flights for {activity_date.strftime("%Y-%m-%d")} is already higher.', 'warning')
                    return redirect(url_for('dashboard'))
                
                incremental_flights = flights - existing_flights
                
                # Check if it's peak hour for multiplier
                # For backdated activities, we use the current multiplier
                multiplier = get_points_multiplier()
                points = incremental_flights * 10 * multiplier
                
                # Log the climb with the activity date
                log = ClimbLog(user_id=current_user.id, flights=flights, points=points)
                log.timestamp = activity_date  # Set the backdated timestamp
                
                # Update user stats with only the incremental flights
                current_user.total_flights += incremental_flights
                current_user.total_points += points
                
                # Update house points with only the incremental flights
                house = House.query.filter_by(name=current_user.house).first()
                if house:
                    house.total_points += points
                    house.total_flights += incremental_flights
                
                db.session.add(log)
                db.session.commit()
                
                # Add multiplier info to the message if applicable
                multiplier_text = f" ({multiplier}x multiplier!)" if multiplier > 1 else ""
                log_activity(app, current_user.id, 'Screenshot Climb Logged', 
                             f'{incremental_flights} new flights{multiplier_text} for {activity_date.strftime("%Y-%m-%d")}')
                
                date_info = ""
                if activity_date.date() != datetime.now(timezone.utc).date():
                    date_info = f" for {activity_date.strftime('%Y-%m-%d')}"
                
                flash(f'Successfully processed screenshot! Added {points} points for {incremental_flights} new flights{date_info}.{multiplier_text}', 'success')
            else:
                flash(f'Could not process screenshot: {result.get("error", "Unknown error")}', 'danger')
        else:
            flash('Invalid file type. Please upload a PNG or JPG image.', 'danger')
    except Exception as e:
        app.logger.error(f'Screenshot upload error: {str(e)}')
        flash('An error occurred while processing your screenshot', 'danger')
        log_access_attempt(False, "File Upload", f"Error: {str(e)}")
    
    return redirect(url_for('dashboard'))

@app.route('/upload-standing-screenshot', methods=['POST'])
@login_required
@limiter.limit("1000 per minute")
def upload_standing_screenshot():
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
            unique_filename = f"{current_user.id}_standing_{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            # Create image analyzer and process the image
            image_analyzer = ImageAnalyzer()
            file.seek(0)  # Reset file pointer to beginning
            result = image_analyzer.analyze_standing_image(file)
            
            if result.get('success'):
                minutes = result.get('minutes', 0)
                activity_date_str = result.get('date')  # Get date from the image
                
                # Parse the date from the image if available, otherwise use current date
                if activity_date_str:
                    try:
                        # Try to parse the date string in YYYY-MM-DD format
                        activity_date = datetime.strptime(activity_date_str, '%Y-%m-%d')
                        activity_date = activity_date.replace(tzinfo=timezone.utc)
                        
                        # Validate that the backdated timestamp is allowed
                        is_valid, message = validate_backdated_timestamp(activity_date)
                        if not is_valid:
                            flash(message, 'danger')
                            return redirect(url_for('dashboard'))
                            
                        # Set time to start of day
                        activity_date = activity_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    except ValueError:
                        # If date parsing fails, default to today
                        activity_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                else:
                    # Default to today if no date in image
                    activity_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                
                # Calculate tomorrow for the query
                tomorrow = activity_date + timedelta(days=1)
                
                # Find the most recent standing log for the activity date
                latest_log = StandingLog.query.filter(
                    StandingLog.user_id == current_user.id,
                    StandingLog.timestamp >= activity_date,
                    StandingLog.timestamp < tomorrow
                ).order_by(StandingLog.minutes.desc()).first()
                
                # Calculate incremental minutes to avoid double counting
                existing_minutes = latest_log.minutes if latest_log else 0
                
                if minutes <= existing_minutes:
                    flash(f'No new standing time detected. Your recorded minutes for {activity_date.strftime("%Y-%m-%d")} is already higher.', 'warning')
                    return redirect(url_for('dashboard'))
                
                incremental_minutes = minutes - existing_minutes
                
                # Check if it's peak hour for multiplier
                multiplier = get_points_multiplier()
                points = incremental_minutes * multiplier
                
                # Log the standing time with backdated timestamp
                log = StandingLog(user_id=current_user.id, minutes=minutes, points=points, notes=None)
                log.timestamp = activity_date  # Set the backdated timestamp
                
                # Update user stats with only the incremental minutes
                current_user.total_standing_time += incremental_minutes
                current_user.total_points += points
                
                # Update house points with only the incremental minutes
                house = House.query.filter_by(name=current_user.house).first()
                if house:
                    house.total_points += points
                    if hasattr(house, 'total_standing_time'):
                        house.total_standing_time += incremental_minutes
                
                db.session.add(log)
                db.session.commit()
                
                # Add multiplier info to the message if applicable
                multiplier_text = f" ({multiplier}x multiplier!)" if multiplier > 1 else ""
                
                date_info = ""
                if activity_date.date() != datetime.now(timezone.utc).date():
                    date_info = f" for {activity_date.strftime('%Y-%m-%d')}"
                
                log_activity(app, current_user.id, 'Screenshot Standing Logged', 
                             f'{incremental_minutes} new minutes{multiplier_text}{date_info}')
                
                flash(f'Successfully processed screenshot! Added {points} points for {incremental_minutes} new minutes of standing time{date_info}.{multiplier_text}', 'success')
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
@limiter.limit("1000 per minute")
def upload_steps_screenshot():
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
                activity_date_str = result.get('date')  # Get date from the image
                
                if hasattr(current_user, 'total_steps'):
                    # Parse the date from the image if available, otherwise use current date
                    if activity_date_str:
                        try:
                            # Try to parse the date string in YYYY-MM-DD format
                            activity_date = datetime.strptime(activity_date_str, '%Y-%m-%d')
                            activity_date = activity_date.replace(tzinfo=timezone.utc)
                            
                            # Validate that the backdated timestamp is allowed
                            is_valid, message = validate_backdated_timestamp(activity_date)
                            if not is_valid:
                                flash(message, 'danger')
                                return redirect(url_for('dashboard'))
                                
                            # Set time to start of day
                            activity_date = activity_date.replace(hour=0, minute=0, second=0, microsecond=0)
                        except ValueError:
                            # If date parsing fails, default to today
                            activity_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    else:
                        # Default to today if no date in image
                        activity_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    
                    # Calculate tomorrow for the query
                    tomorrow = activity_date + timedelta(days=1)
                    
                    # Find the most recent step log for the activity date
                    latest_log = StepLog.query.filter(
                        StepLog.user_id == current_user.id,
                        StepLog.timestamp >= activity_date,
                        StepLog.timestamp < tomorrow
                    ).order_by(StepLog.steps.desc()).first()
                    
                    # Calculate incremental steps to avoid double counting
                    existing_steps = latest_log.steps if latest_log else 0
                    
                    if steps <= existing_steps:
                        flash(f'No new steps detected. Your recorded steps for {activity_date.strftime("%Y-%m-%d")} is already higher.', 'warning')
                        return redirect(url_for('dashboard'))
                    
                    incremental_steps = steps - existing_steps
                    
                    # Check if it's peak hour for multiplier
                    multiplier = get_points_multiplier()
                    points = (incremental_steps // 100) * multiplier
                    
                    # Log the steps with backdated timestamp
                    log = StepLog(user_id=current_user.id, steps=steps, points=points)
                    log.timestamp = activity_date  # Set the backdated timestamp
                    
                    # Update user stats
                    current_user.total_steps += incremental_steps
                    current_user.total_points += points
                    
                    # Update house points
                    house = House.query.filter_by(name=current_user.house).first()
                    if house:
                        house.total_points += points
                        house.total_steps += incremental_steps
                    
                    db.session.add(log)
                    db.session.commit()
                    
                    # Add multiplier info to the message if applicable
                    multiplier_text = f" ({multiplier}x multiplier!)" if multiplier > 1 else ""
                    
                    date_info = ""
                    if activity_date.date() != datetime.now(timezone.utc).date():
                        date_info = f" for {activity_date.strftime('%Y-%m-%d')}"
                    
                    log_activity(app, current_user.id, 'Screenshot Steps Logged', 
                                 f'{incremental_steps} new steps{multiplier_text}{date_info}')
                    
                    flash(f'Successfully processed screenshot! Added {points} points for {incremental_steps} new steps{date_info}.{multiplier_text}', 'success')
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
    
    # Add event information
    active_event = get_active_event()
    
    # Get user event points if logged in and event is active
    user_event_points = None
    if current_user.is_authenticated and active_event and not current_user.is_admin:
        user_event_points = get_event_points(user_id=current_user.id)
    
    # Add peak hour information to all templates
    is_peak, multiplier, peak_name = get_current_peak_hour_info()
    return {
        'get_house_count': get_house_count,
        'is_peak_hour': is_peak,
        'peak_hour_multiplier': multiplier,
        'peak_hour_name': peak_name,
        'peak_hours_message': get_peak_hours_message(),
        'sanitize': sanitize_input,  # Add sanitize function to all templates
        'active_event': active_event,
        'user_event_points': user_event_points
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
            
        # Start background sync tasks
        from background_tasks import start_background_tasks
        start_background_tasks()
    
    # Use debug mode from environment variable and set port to 5000
    debug_mode = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')
    app.run(debug=debug_mode, port=5001)

def get_leaderboard(limit=10):
    """Get top users ordered by total points, excluding admins"""
    return User.query.filter(User.is_admin == False).order_by(User.total_points.desc()).limit(limit).all()

@app.route('/dashboard')
@login_required
def dashboard():
    """Unified dashboard combining flights, steps, and standing activities"""
    # Redirect admin to admin dashboard if they try to access this
    if current_user.is_admin:
        flash('Admin users should use the Admin Dashboard', 'info')
        return redirect(url_for('admin_dashboard'))
    
    # Check if there's an active event
    active_event = get_active_event()
    
    # Get house data for the leaderboard
    houses = House.query.order_by(House.total_points.desc()).all()
    
    # If there's an active event, get event-specific points for each house
    house_event_points = {}
    active_event_points_for_user = {}  # NEW: Dictionary to store event points for each user
    
    if active_event:
        for house in houses:
            house_event_points[house.name] = get_event_points(house_name=house.name)
    
        # For events, we need to calculate the leaderboard dynamically
        all_users = User.query.filter(User.is_admin == False).all()
        user_points = []
        for user in all_users:
            event_points = get_event_points(user_id=user.id)
            if event_points:
                # NEW: Store the complete event points data for this user
                active_event_points_for_user[user.id] = event_points
                user_points.append({
                    'user': user,
                    'points': event_points['total_points']
                })
        # Sort by event points
        user_points.sort(key=lambda x: x['points'], reverse=True)
        # Take top 10
        leaderboard = [item['user'] for item in user_points[:10]]
    else:
        # Regular leaderboard
        leaderboard = get_leaderboard(limit=10)  # Get top 10 users
    
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
                           recent_steps_logs=recent_steps_logs,
                           leaderboard=leaderboard,
                           active_event=active_event,
                           house_event_points=house_event_points,
                           active_event_points_for_user=active_event_points_for_user,  # NEW: Pass the dictionary to template
                           now=datetime.utcnow(),  # NEW: Pass the current time to the template
                           )

@app.route('/google_fit_callback')
def google_fit_callback():
    # Get the authorization code from the callback
    code = request.args.get('code')
    if not code:
        flash('Authentication failed. Please try again.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Exchange the code for tokens
        client_id = os.environ.get('GOOGLE_CLIENT_ID')
        client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
        redirect_uri = os.environ.get('GOOGLE_FIT_REDIRECT_URI')
        
        response = requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri
            }
        )
        
        if response.status_code != 200:
            app.logger.error(f"Google OAuth error: {response.status_code} - {response.text}")
            flash('Failed to authenticate with Google Fit. Please try again.', 'danger')
            return redirect(url_for('dashboard'))
        
        data = response.json()
        
        # Store tokens in user model
        current_user.google_fit_token = data.get('access_token')
        current_user.google_refresh_token = data.get('refresh_token')
        expires_in = data.get('expires_in', 3600)
        current_user.google_token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        db.session.commit()
        
        # Log success
        log_activity(app, current_user.id, 'Google Fit Connected', 'Google Fit account connected successfully')
        flash('Google Fit connected successfully!', 'success')
        
        # Perform initial sync for the past week
        sync_result = sync_week_for_user(current_user)
        if sync_result["success"] and sync_result["total_steps"] > 0:
            flash(f'Successfully synced {sync_result["total_steps"]} steps from the past week ({sync_result["total_points"]} points)', 'success')
        elif sync_result["success"]:
            flash('No new steps found in the past week', 'info')
        else:
            flash(f'Connected to Google Fit but sync failed: {sync_result.get("error", "Unknown error")}', 'warning')
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        app.logger.error(f"Google Fit callback error: {str(e)}")
        flash('An error occurred while connecting to Google Fit', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/get_google_fit_steps', methods=['GET'])
@login_required
def get_google_fit_steps():
    access_token = current_user.google_fit_token
    if not access_token:
        return jsonify({"error": "Google Fit not linked"}), 401
    
    # Get the date parameter from the request (YYYY-MM-DD format)
    # If not provided, use today's date
    date_str = request.args.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400
    else:
        target_date = datetime.utcnow()
    
    # Make target_date timezone-aware
    if target_date.tzinfo is None:
        target_date = target_date.replace(tzinfo=timezone.utc)
    
    # Validate the backdated timestamp
    is_valid, message = validate_backdated_timestamp(target_date)
    if not is_valid:
        return jsonify({"error": message}), 400
    
    # Set to start of day
    start_of_day = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    end_of_day = start_of_day + timedelta(days=1)
    
    start_time_millis = int(start_of_day.timestamp() * 1000)
    end_time_millis = int(end_of_day.timestamp() * 1000)

    url = "https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    body = {
        "aggregateBy": [{
            "dataTypeName": "com.google.step_count.delta",
            "dataSourceId": "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"
        }],
        "bucketByTime": { "durationMillis": 86400000 },
        "startTimeMillis": start_time_millis,
        "endTimeMillis": end_time_millis
    }

    try:
        r = requests.post(url, headers=headers, json=body, timeout=10)
        if r.status_code != 200:
            app.logger.error(f"Google Fit API error: {r.status_code} - {r.text}")
            return jsonify({"error": "Failed to fetch Google Fit data"}), 400

        data = r.json()
        total_steps_today = 0
        buckets = data.get("bucket", [])
        for bucket in buckets:
            for dataset in bucket.get("dataset", []):
                for point in dataset.get("point", []):
                    for value in point.get("value", []):
                        total_steps_today += value.get("intVal", 0)

        # Update user and house stats
        # Only log if steps are greater than the last log for that specific day
        latest_log = StepLog.query.filter(
            StepLog.user_id == current_user.id,
            StepLog.timestamp >= start_of_day,
            StepLog.timestamp < end_of_day
        ).order_by(StepLog.steps.desc()).first()
        existing_steps = latest_log.steps if latest_log else 0

        if total_steps_today > existing_steps:
            incremental_steps = total_steps_today - existing_steps
            multiplier = get_points_multiplier()
            points = (incremental_steps // 100) * multiplier

            log = StepLog(user_id=current_user.id, steps=total_steps_today, points=points, source='google_fit')
            log.timestamp = start_of_day  # Set backdated timestamp
            db.session.add(log)

            current_user.total_steps += incremental_steps
            current_user.total_points += points

            house = House.query.filter_by(name=current_user.house).first()
            if house:
                house.total_steps += incremental_steps
                house.total_points += points

            db.session.commit()
            
            date_info = ""
            if target_date.date() != datetime.now(timezone.utc).date():
                date_info = f" for {start_of_day.strftime('%Y-%m-%d')}"
                
            log_activity(app, current_user.id, 'Google Fit Steps Synced', 
                         f'{incremental_steps} new steps{date_info} ({points} points)')

            return jsonify({
                "success": True, 
                "steps": total_steps_today,
                "date": start_of_day.strftime('%Y-%m-%d'),
                "points_added": points,
                "message": f"Added {points} points for {incremental_steps} new steps{date_info}"
            })
        else:
            return jsonify({
                "success": True, 
                "steps": total_steps_today,
                "date": start_of_day.strftime('%Y-%m-%d'),
                "points_added": 0,
                "message": f"No new steps to add for {start_of_day.strftime('%Y-%m-%d')}"
            })

    except Exception as e:
        app.logger.error(f"Error fetching Google Fit steps: {str(e)}")
        return jsonify({"error": "An error occurred while fetching steps"}), 500

def sync_google_fit_for_user(user):
    """Sync Google Fit data for a user for the past week and return detailed results"""
    if not user.google_fit_token or not user.google_refresh_token:
        return {"error": "Google Fit not linked", "success": False}
        
    try:
        # Refresh token if needed
        current_time = datetime.now(timezone.utc)
        token_expiry = ensure_tz_aware(user.google_token_expiry)
            
        if token_expiry and current_time > token_expiry:
            refresh_successful = refresh_google_fit_token(user)
            if not refresh_successful:
                return {"error": "Failed to refresh Google Fit token", "success": False}
                
        # Calculate date range - fetch data for past week
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=7)
        
        # Track results for each day
        days_data = []
        total_steps_synced = 0
        total_points_added = 0
        
        # Iterate through each day in the past week
        current_date = start_time
        while current_date < end_time:
            # Set to start of day
            day_start = datetime(current_date.year, current_date.month, current_date.day, tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)
            
            # Convert to milliseconds for Google Fit API
            day_start_ms = int(day_start.timestamp() * 1000)
            day_end_ms = int(day_end.timestamp() * 1000)
            
            # Build Google Fit API request
            headers = {
                'Authorization': f'Bearer {user.google_fit_token}'
            }
            
            # Use Google Fit REST API to fetch step count
            url = "https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate"
            body = {
                "aggregateBy": [{
                    "dataTypeName": "com.google.step_count.delta",
                    "dataSourceId": "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"
                }],
                "bucketByTime": {"durationMillis": 86400000},  # 24 hours
                "startTimeMillis": day_start_ms,
                "endTimeMillis": day_end_ms
            }
            
            response = requests.post(url, json=body, headers=headers)
            if response.status_code != 200:
                app.logger.warning(f"Google Fit API error for user {user.id} on {day_start.strftime('%Y-%m-%d')}: {response.status_code}")
                # Add error to the day's data
                days_data.append({
                    "date": day_start.strftime('%Y-%m-%d'),
                    "error": f"API error: {response.status_code}",
                    "steps": 0,
                    "points": 0,
                    "success": False
                })
                # Continue to next day
                current_date += timedelta(days=1)
                continue
                
            data = response.json()
            
            # Process the response to get step count
            steps = 0
            if 'bucket' in data:
                for bucket in data['bucket']:
                    if 'dataset' in bucket:
                        for dataset in bucket['dataset']:
                            if 'point' in dataset:
                                for point in dataset['point']:
                                    if 'value' in point:
                                        for value in point['value']:
                                            if 'intVal' in value:
                                                steps += value['intVal']
            
            # If no steps for this day, log it and continue
            if steps == 0:
                days_data.append({
                    "date": day_start.strftime('%Y-%m-%d'),
                    "message": "No steps recorded",
                    "steps": 0,
                    "points": 0,
                    "success": True
                })
                current_date += timedelta(days=1)
                continue
                
            # Compare with existing step logs to avoid double counting
            latest_log = StepLog.query.filter(
                StepLog.user_id == user.id,
                StepLog.timestamp >= day_start,
                StepLog.timestamp < day_end,
                StepLog.source == 'google_fit'
            ).order_by(StepLog.steps.desc()).first()
            
            # Calculate incremental steps if we have existing logs
            existing_steps = latest_log.steps if latest_log else 0
            incremental_steps = steps - existing_steps if existing_steps < steps else 0
                
            if incremental_steps <= 0:
                days_data.append({
                    "date": day_start.strftime('%Y-%m-%d'),
                    "message": f"No new steps (existing: {existing_steps}, new: {steps})",
                    "steps": steps,
                    "points": 0,
                    "success": True
                })
                current_date += timedelta(days=1)
                continue
                
            # Calculate points (1 point per 100 steps)
            # Apply multiplier only for current day, use 1x for previous days
            multiplier = 1
            if day_start.date() == datetime.now(timezone.utc).date():
                # Only use the multiplier for today
                multiplier = get_points_multiplier()
                
            points = (incremental_steps // 100) * multiplier
            
            # Create new step log
            log = StepLog(
                user_id=user.id, 
                steps=steps, 
                points=points,
                source='google_fit'
            )
            log.timestamp = day_start  # Set to the specific day
            
            # Update user stats with only the incremental steps
            user.total_steps = (user.total_steps or 0) + incremental_steps
            user.total_points += points
            
            # Update house points
            house = House.query.filter_by(name=user.house).first()
            if house:
                house.total_points += points
                # Make sure the house has total_steps attribute before updating
                if hasattr(house, 'total_steps'):
                    house.total_steps = (house.total_steps or 0) + incremental_steps
            
            db.session.add(log)
            db.session.commit()
            
            # Add to day results
            days_data.append({
                "date": day_start.strftime('%Y-%m-%d'),
                "message": f"Added {incremental_steps} steps",
                "steps": steps,
                "incremental_steps": incremental_steps,
                "points": points,
                "multiplier": multiplier,
                "success": True
            })
            
            # Accumulate stats
            total_steps_synced += incremental_steps
            total_points_added += points
            
            # Move to next day
            current_date += timedelta(days=1)
            
            # Sleep briefly to avoid API rate limits
            time.sleep(0.5)
        
        # Log activity for the whole sync
        if total_steps_synced > 0:
            log_activity(app, user.id, 'Google Fit Sync', 
                       f'Added {total_steps_synced} steps across {len(days_data)} days ({total_points_added} points)')
            
            return {
                "success": True,
                "message": f"Synced {total_steps_synced} steps across {len(days_data)} days ({total_points_added} points)",
                "total_steps": total_steps_synced,
                "total_points": total_points_added,
                "days": days_data
            }
        else:
            return {
                "success": True,
                "message": "No new steps to sync from the past week",
                "total_steps": 0,
                "total_points": 0,
                "days": days_data
            }
        
    except Exception as e:
        app.logger.error(f"Error syncing Google Fit week for user {user.id}: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def sync_all_google_fit_users():
    """Sync Google Fit data for all users with Google Fit integration"""
    try:
        # Get all users with Google Fit tokens
        users = User.query.filter(User.google_fit_token.isnot(None)).all()
        logger.info(f"Starting Google Fit sync for {len(users)} users")
        
        success_count = 0
        for user in users:
            # Use the new sync function that handles the full week
            result = sync_week_for_user(user)
            if result["success"] and result["total_steps"] > 0:
                success_count += 1
                logger.info(f"Successfully synced {result['total_steps']} steps for user {user.id}")
            elif not result["success"]:
                logger.error(f"Failed to sync Google Fit for user {user.id}: {result.get('error')}")
                
        logger.info(f"Google Fit sync completed. Successful syncs: {success_count}/{len(users)}")
    except Exception as e:
        logger.error(f"Error in sync_all_google_fit_users: {str(e)}")
        
@app.route('/user-management')
@login_required
@admin_required
@limiter.limit("200 per minute")
def user_management():
    """Dedicated page for user management with search functionality"""
    # Verify admin status as an extra precaution
    if not current_user.is_admin:
        log_access_attempt(False, "User Management", "Non-admin access attempt")
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Get search parameters
    search_term = request.args.get('search', '')
    search_field = request.args.get('field', 'username')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)  # Default to 50 users per page
    
    # Build the query
    query = User.query
    
    # Apply search filter if provided
    if search_term:
        if search_field == 'username':
            query = query.filter(User.username.ilike(f'%{search_term}%'))
        elif search_field == 'house':
            query = query.filter(User.house.ilike(f'%{search_term}%'))
        elif search_field == 'email':
            query = query.filter(User.email.ilike(f'%{search_term}%'))
    
    # Get total count for pagination
    total_users = query.count()
    
    # Apply pagination
    users = query.order_by(User.username).paginate(page=page, per_page=per_page)
    
    # Check if there's an active event
    active_event = get_active_event()
    
    # Get event-specific points for users if an event is active
    user_event_points = {}
    if active_event:
        # Get event points for each user on the current page
        for user in users.items:
            user_event_points[user.id] = get_event_points(user_id=user.id)
    
    # Get all houses for filtering
    houses = House.query.order_by(House.name).all()
    
    log_access_attempt(True, "User Management", "Admin access successful")
    return render_template('user_management.html',
                         users=users,
                         houses=houses,
                         search_term=search_term,
                         search_field=search_field,
                         total_users=total_users,
                         active_event=active_event,
                         user_event_points=user_event_points,
                         page=page,
                         per_page=per_page)
