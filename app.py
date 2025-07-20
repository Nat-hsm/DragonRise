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
                
                # Validate flights is within reasonable range
                if flights <= 0 or flights > 1000:
                    flash('Invalid number of flights detected in the screenshot', 'danger')
                    return redirect(url_for('dashboard'))
                    
                # Get today's date
                today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                tomorrow = today + timedelta(days=1)
                
                # Find the most recent climb log for today
                latest_log = ClimbLog.query.filter(
                    ClimbLog.user_id == current_user.id,
                    ClimbLog.timestamp >= today,
                    ClimbLog.timestamp < tomorrow
                ).order_by(ClimbLog.flights.desc()).first()
                
                # Calculate incremental flights to avoid double counting
                existing_flights = latest_log.flights if latest_log else 0
                
                if flights <= existing_flights:
                    flash('No new flights detected. Your current recorded flights for today is already higher.', 'warning')
                    return redirect(url_for('dashboard'))
                
                incremental_flights = flights - existing_flights
                
                # Check if it's peak hour for multiplier
                multiplier = get_points_multiplier()
                points = incremental_flights * 10 * multiplier
                
                # Log the climb
                log = ClimbLog(user_id=current_user.id, flights=flights, points=points)
                
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
                log_activity(app, current_user.id, 'Screenshot Climb Logged', f'{incremental_flights} new flights{multiplier_text}')
                flash(f'Successfully processed screenshot! Added {points} points for {incremental_flights} new flights.{multiplier_text}', 'success')
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
            unique_filename = f"{current_user.id}_standing_{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            # Create image analyzer and process the image
            image_analyzer = ImageAnalyzer()
            file.seek(0)  # Reset file pointer to beginning
            result = image_analyzer.analyze_standing_image(file)
            
            if result.get('success'):
                minutes = result.get('minutes', 0)
                
                # Get today's date
                today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                tomorrow = today + timedelta(days=1)
                
                # Find the most recent standing log for today
                latest_log = StandingLog.query.filter(
                    StandingLog.user_id == current_user.id,
                    StandingLog.timestamp >= today,
                    StandingLog.timestamp < tomorrow
                ).order_by(StandingLog.minutes.desc()).first()
                
                # Calculate incremental minutes to avoid double counting
                existing_minutes = latest_log.minutes if latest_log else 0
                
                if minutes <= existing_minutes:
                    flash('No new standing time detected. Your current recorded minutes for today is already higher.', 'warning')
                    return redirect(url_for('dashboard'))
                
                incremental_minutes = minutes - existing_minutes
                
                # Check if it's peak hour for multiplier
                multiplier = get_points_multiplier()
                points = incremental_minutes * multiplier
                
                # Set notes to None for screenshot uploads
                notes = None
                
                # Log the standing time
                log = StandingLog(user_id=current_user.id, minutes=minutes, points=points, notes=notes)
                
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
                log_activity(app, current_user.id, 'Screenshot Standing Logged', f'{incremental_minutes} new minutes{multiplier_text}')
                flash(f'Successfully processed screenshot! Added {points} points for {incremental_minutes} new minutes of standing time.{multiplier_text}', 'success')
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
                
                if hasattr(current_user, 'total_steps'):
                    # Get today's date
                    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    tomorrow = today + timedelta(days=1)
                    
                    # Find the most recent step log for today
                    latest_log = StepLog.query.filter(
                        StepLog.user_id == current_user.id,
                        StepLog.timestamp >= today,
                        StepLog.timestamp < tomorrow
                    ).order_by(StepLog.steps.desc()).first()
                    
                    # Calculate incremental steps to avoid double counting
                    existing_steps = latest_log.steps if latest_log else 0
                    
                    if steps <= existing_steps:
                        flash('No new steps detected. Your current recorded steps for today is already higher.', 'warning')
                        return redirect(url_for('dashboard'))
                    
                    incremental_steps = steps - existing_steps
                    
                    # Check if it's peak hour for multiplier
                    multiplier = get_points_multiplier()
                    points = (incremental_steps // 100) * multiplier
                    
                    # Log the steps
                    log = StepLog(user_id=current_user.id, steps=steps, points=points)
                    
                    # Update user stats
                    current_user.total_steps += incremental_steps
                    current_user.total_points += points
                    
                    # Update house points
                    house = House.query.filter_by(name=current_user.house).first()
                    if house:
                        house.total_points += points
                        if hasattr(house, 'total_steps'):
                            house.total_steps += incremental_steps
                    
                    db.session.add(log)
                    db.session.commit()
                    
                    # Add multiplier info to the message if applicable
                    multiplier_text = f" ({multiplier}x multiplier!)" if multiplier > 1 else ""
                    log_activity(app, current_user.id, 'Screenshot Steps Logged', f'{incremental_steps} new steps{multiplier_text}')
                    flash(f'Successfully processed screenshot! Added {points} points for {incremental_steps} new steps.{multiplier_text}', 'success')
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
                           active_event_points_for_user=active_event_points_for_user)  # NEW: Pass the dictionary to template

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
        flash('Google Fit connected successfully! Your steps will be synced automatically.', 'success')
        
        # Perform initial sync
        from background_tasks import sync_google_fit_for_user
        sync_google_fit_for_user(current_user)
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        app.logger.error(f"Google Fit callback error: {str(e)}")
        flash('An error occurred while connecting to Google Fit', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/get_google_fit_steps', methods=['GET'])
@login_required
def get_google_fit_steps():
    # Get token from user model instead of session
    access_token = current_user.google_fit_token
    if not access_token:
        return jsonify({"error": "Google Fit not linked"}), 401

    # Get today's start and end time in milliseconds
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    start_of_day = datetime(now.year, now.month, now.day)
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

        # Add success flag to indicate request was successful
        return jsonify({"success": True, "steps": total_steps_today})

    except Exception as e:
        app.logger.error(f"Error fetching Google Fit steps: {str(e)}")
        return jsonify({"error": "An error occurred while fetching steps"}), 500

@app.route('/google_fit_auth')
@login_required
def google_fit_auth():
    """Initialize Google Fit OAuth flow"""
    # Create a random state token to prevent request forgery
    state = secrets.token_urlsafe(16)
    session['google_oauth_state'] = state
    
    # Get credentials from environment variables
    client_id = os.environ.get('GOOGLE_CLIENT_ID')
    redirect_uri = os.environ.get('GOOGLE_FIT_REDIRECT_URI')
    
    if not client_id or not redirect_uri:
        flash('Google Fit integration is not properly configured.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Define scope for Google Fit API access
    scopes = [
        'https://www.googleapis.com/auth/fitness.activity.read',
        'https://www.googleapis.com/auth/fitness.location.read'
    ]
    
    # Build authorization URL
    auth_url = (
        'https://accounts.google.com/o/oauth2/auth'
        f'?client_id={client_id}'
        f'&redirect_uri={redirect_uri}'
        f'&scope={"+".join(scopes)}'
        '&response_type=code'
        '&access_type=offline'
        '&prompt=consent'  # Force to always get refresh token
        f'&state={state}'
    )
    
    # Log the authorization attempt
    log_activity(app, current_user.id, 'Google Fit Auth', 'Started Google Fit authorization')
    
    # Redirect user to Google's OAuth consent page
    return redirect(auth_url)

@app.route('/garmin_auth')
@login_required
def garmin_auth():
    """Initialize Garmin Connect OAuth flow using PKCE"""
    try:
        # Get credentials from environment variables
        client_id = os.environ.get('GARMIN_CLIENT_ID')
        redirect_uri = os.environ.get('GARMIN_REDIRECT_URI')
        
        if not client_id or not redirect_uri:
            app.logger.error("Garmin Connect integration is not properly configured")
            flash('Garmin Connect integration is not properly configured.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Generate PKCE code verifier and challenge
        code_verifier = pkce.generate_code_verifier(length=128)
        code_challenge = pkce.get_code_challenge(code_verifier)
        
        # Store code verifier in session for later use
        session['garmin_code_verifier'] = code_verifier
        
        # Generate state parameter to prevent CSRF
        state = secrets.token_urlsafe(16)
        session['garmin_oauth_state'] = state
        
        # Build authorization URL
        auth_url = (
            "https://connectapi.garmin.com/di-oauth2-service/oauth/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            "&response_type=code"
            f"&code_challenge={code_challenge}"
            "&code_challenge_method=S256"
            f"&state={state}"
            "&scope=activity:read,activity:write"
        )
        
        # Log the authorization attempt
        log_activity(app, current_user.id, 'Garmin Auth', 'Started Garmin Connect authorization')
        
        # Redirect user to Garmin's OAuth consent page
        return redirect(auth_url)
    except Exception as e:
        app.logger.error(f"Garmin auth initialization error: {str(e)}")
        flash('An error occurred while connecting to Garmin Connect', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/garmin_callback')
@login_required
def garmin_callback():
    """Handle Garmin Connect OAuth callback"""
    try:
        # Check for error
        error = request.args.get('error')
        if error:
            app.logger.error(f"Garmin authorization failed: {error}")
            flash(f"Garmin authorization failed: {error}", "danger")
            return redirect(url_for('dashboard'))
        
        # Get authorization code
        code = request.args.get('code')
        if not code:
            app.logger.error("No authorization code received from Garmin")
            flash("No authorization code received from Garmin", "danger")
            return redirect(url_for('dashboard'))
        
        # Verify state to prevent CSRF
        state = request.args.get('state')
        stored_state = session.get('garmin_oauth_state')
        if not state or state != stored_state:
            app.logger.warning("Garmin OAuth state mismatch - possible CSRF attack")
            flash("Authentication failed - security verification failed", "danger")
            return redirect(url_for('dashboard'))
        
        # Get PKCE code verifier from session
        code_verifier = session.get('garmin_code_verifier')
        if not code_verifier:
            app.logger.error("Missing PKCE code verifier for Garmin authentication")
            flash("Authentication session expired. Please try again.", "danger")
            return redirect(url_for('dashboard'))
        
        # Get credentials from environment variables
        client_id = os.environ.get('GARMIN_CLIENT_ID')
        client_secret = os.environ.get('GARMIN_CLIENT_SECRET')
        redirect_uri = os.environ.get('GARMIN_REDIRECT_URI')
        
        if not client_id or not client_secret or not redirect_uri:
            app.logger.error("Garmin Connect integration is not properly configured")
            flash("Garmin Connect integration is not properly configured", "danger")
            return redirect(url_for('dashboard'))
        
        # Exchange the authorization code for tokens
        token_url = "https://connectapi.garmin.com/oauth-service/oauth/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        response = requests.post(token_url, data=data, headers=headers, timeout=10)
        app.logger.info(f"Garmin token exchange response: {response.status_code} - {response.text}")
        
        if response.status_code != 200:
            app.logger.error(f"Failed to get Garmin access token: {response.status_code} - {response.text}")
            flash("Failed to connect to Garmin. Please try again later.", "danger")
            return redirect(url_for('dashboard'))
        
        # Parse token response
        token_info = response.json()
        
        # Store tokens in session or database
        session['garmin_access_token'] = token_info.get("access_token")
        session['garmin_refresh_token'] = token_info.get("refresh_token")
        expires_in = token_info.get("expires_in", 3600)
        
        # Store token expiry
        session['garmin_token_expiry'] = datetime.now(timezone.utc).timestamp() + expires_in
        
        # Store in user model if needed
        if hasattr(current_user, 'garmin_access_token'):
            current_user.garmin_access_token = token_info.get("access_token")
            current_user.garmin_refresh_token = token_info.get("refresh_token")
            current_user.garmin_token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            db.session.commit()
        
        # Log the successful connection
        log_activity(app, current_user.id, 'Garmin Connected', 'Garmin Connect account connected successfully')
        flash("Garmin Connect account linked successfully!", "success")
        
        # Clear OAuth session data
        session.pop('garmin_code_verifier', None)
        session.pop('garmin_oauth_state', None)
        
        return redirect(url_for('dashboard'))
    
    except Exception as e:
        app.logger.error(f"Error in Garmin callback: {str(e)}")
        flash("An error occurred while connecting to Garmin. Please try again.", "danger")
        return redirect(url_for('dashboard'))

@app.route('/get_garmin_steps')
@login_required
def get_garmin_steps():
    """Get steps data from Garmin Connect for the current day"""
    try:
        access_token = session.get('garmin_access_token')
        if not access_token:
            app.logger.warning("Garmin not linked for user trying to get steps data")
            return jsonify({"error": "Garmin not linked"}), 401

        # Calculate time range for today
        now = datetime.utcnow()
        start_of_day = datetime(now.year, now.month, now.day)
        end_of_day = start_of_day + timedelta(days=1)

        # Use seconds, not milliseconds
        start_time_seconds = int(start_of_day.timestamp())
        end_time_seconds = int(end_of_day.timestamp())

        url = f'https://apis.garmin.com/wellness-api/rest/dailies?uploadStartTimeInSeconds={start_time_seconds}&uploadEndTimeInSeconds={end_time_seconds}'
        headers = {"Authorization": f"Bearer {access_token}"}

        r = requests.get(url, headers=headers, timeout=10)
        app.logger.debug(f"Garmin API status: {r.status_code}")
        
        if r.status_code == 401:
            # Token expired or invalid
            app.logger.warning("Garmin access token expired or invalid")
            return jsonify({"error": "Authentication expired. Please reconnect your Garmin account."}), 401
        elif r.status_code != 200:
            app.logger.error(f"Garmin API error: {r.status_code} - {r.text}")
            return jsonify({"error": "Failed to fetch Garmin data"}), r.status_code
        
        data = r.json()
        steps = data[0].get('steps', 0) if data else 0
        stairs = data[0].get('floorsClimbed', 0) if data else 0
        
        # Log success
        log_activity(app, current_user.id, 'Garmin Data Fetched', f'Retrieved {steps} steps and {stairs} stairs')
        return jsonify({"steps": steps, "stairs": stairs})
    
    except requests.exceptions.Timeout:
        app.logger.error("Timeout while connecting to Garmin API")
        return jsonify({"error": "Connection to Garmin timed out. Please try again."}), 504
    except requests.exceptions.ConnectionError:
        app.logger.error("Connection error while connecting to Garmin API")
        return jsonify({"error": "Connection to Garmin failed. Please check your internet connection."}), 503
    except Exception as e:
        app.logger.error(f"Garmin fetch error: {str(e)}")
        return jsonify({"error": "An error occurred while fetching Garmin data"}), 500

@app.route('/get_garmin_weekly')
@login_required
def get_garmin_weekly():
    """Get weekly data from Garmin Connect for the past 7 days"""
    try:
        access_token = session.get('garmin_access_token')
        if not access_token:
            app.logger.warning("Garmin not linked for user trying to get weekly data")
            return jsonify({"error": "Garmin not linked"}), 401

        now = datetime.utcnow()
        week = []
        headers = {"Authorization": f"Bearer {access_token}"}

        for i in range(6, -1, -1):  # 6 days ago to today
            day = now - timedelta(days=i)
            start_of_day = datetime(day.year, day.month, day.day)
            end_of_day = start_of_day + timedelta(days=1)
            start_time_seconds = int(start_of_day.timestamp())
            end_time_seconds = int(end_of_day.timestamp())

            url = (
                f'https://apis.garmin.com/wellness-api/rest/dailies'
                f'?uploadStartTimeInSeconds={start_time_seconds}&uploadEndTimeInSeconds={end_time_seconds}'
            )

            try:
                r = requests.get(url, headers=headers, timeout=10)
                
                if r.status_code == 401:
                    app.logger.warning("Garmin access token expired or invalid")
                    return jsonify({"error": "Authentication expired. Please reconnect your Garmin account."}), 401
                elif r.status_code != 200:
                    app.logger.error(f"Garmin API error for {start_of_day.strftime('%Y-%m-%d')}: {r.status_code}")
                    week.append({
                        "calendarDate": start_of_day.strftime('%Y-%m-%d'),
                        "steps": 0,
                        "floorsClimbed": 0,
                        "error": f"Failed to fetch data"
                    })
                    continue
                
                data = r.json()
                if isinstance(data, list) and data:
                    day_data = data[0]
                    week.append({
                        "calendarDate": day_data.get("calendarDate", start_of_day.strftime('%Y-%m-%d')),
                        "steps": day_data.get("steps", 0),
                        "floorsClimbed": day_data.get("floorsClimbed", 0)
                    })
                else:
                    week.append({
                        "calendarDate": start_of_day.strftime('%Y-%m-%d'),
                        "steps": 0,
                        "floorsClimbed": 0,
                        "error": "No data available for this day"
                    })
            except requests.exceptions.Timeout:
                app.logger.error(f"Timeout while fetching Garmin data for {start_of_day.strftime('%Y-%m-%d')}")
                week.append({
                    "calendarDate": start_of_day.strftime('%Y-%m-%d'),
                    "steps": 0,
                    "floorsClimbed": 0,
                    "error": "Request timed out"
                })
            except requests.exceptions.ConnectionError:
                app.logger.error(f"Connection error while fetching Garmin data for {start_of_day.strftime('%Y-%m-%d')}")
                week.append({
                    "calendarDate": start_of_day.strftime('%Y-%m-%d'),
                    "steps": 0,
                    "floorsClimbed": 0,
                    "error": "Connection failed"
                })
            except Exception as e:
                app.logger.error(f"Error fetching Garmin data for {start_of_day.strftime('%Y-%m-%d')}: {str(e)}")
                week.append({
                    "calendarDate": start_of_day.strftime('%Y-%m-%d'),
                    "steps": 0,
                    "floorsClimbed": 0,
                    "error": "An unexpected error occurred"
                })
        
        # Sort by date
        week.sort(key=lambda x: x["calendarDate"])
        
        # Log successful retrieval
        log_activity(app, current_user.id, 'Garmin Weekly Data Fetched', f'Retrieved weekly data ({len(week)} days)')
        return jsonify({"week": week})
    
    except Exception as e:
        app.logger.error(f"Garmin weekly fetch error: {str(e)}")
        return jsonify({"error": "An error occurred while fetching Garmin weekly data"}), 500

@app.route('/analytics-dashboard')
@login_required
@admin_required
def analytics_dashboard():
    """Analytics dashboard for admin users to view usage statistics"""
    # Verify admin status again as an extra precaution
    if not current_user.is_admin:
        log_access_attempt(False, "Analytics Dashboard", "Non-admin access attempt")
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
        
    # Check if there's an active event
    active_event = get_active_event()
    
    # Get data for analytics
    try:
        # Get total user count
        total_users = User.query.filter(User.is_admin == False).count()
        
        # Get active users (users who logged in within the last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        active_users = User.query.filter(
            User.is_admin == False,
            User.last_login >= thirty_days_ago
        ).count()
        
        # Prepare house stats and query filters based on active event
        houses = House.query.all()
        house_stats = []
        
        # Prepare query filters based on active event
        if active_event:
            # For an active event, we need to filter logs by the event time period
            # Ensure event dates are timezone-aware
            event_start = active_event.start_date
            event_end = active_event.end_date
            
            if event_start.tzinfo is None:
                event_start = event_start.replace(tzinfo=timezone.utc)
            if event_end.tzinfo is None:
                event_end = event_end.replace(tzinfo=timezone.utc)
                
            climb_query_filter = ClimbLog.timestamp.between(event_start, event_end)
            standing_query_filter = StandingLog.timestamp.between(event_start, event_end)
            steps_query_filter = StepLog.timestamp.between(event_start, event_end)
            
            # Get event-specific points for each house
            house_event_points = {}
            for house in houses:
                house_event_points[house.name] = get_event_points(house_name=house.name)
        else:
            # For all-time stats, no time filter is needed
            climb_query_filter = True
            standing_query_filter = True
            steps_query_filter = True
            house_event_points = None
        
        # Get total activities per type (filtered by event period if an event is active)
        total_climbs = db.session.query(func.count(ClimbLog.id)).filter(climb_query_filter).scalar() or 0
        total_standings = db.session.query(func.count(StandingLog.id)).filter(standing_query_filter).scalar() or 0
        total_step_logs = db.session.query(func.count(StepLog.id)).filter(steps_query_filter).scalar() or 0
        
        # Get house activity distribution
        for house in houses:
            house_users = User.query.filter_by(house=house.name).all()
            user_ids = [user.id for user in house_users]
            
            if user_ids:  # Only query if there are users in the house
                # Apply event time filter if there's an active event
                climbs = db.session.query(func.count(ClimbLog.id)).filter(
                    ClimbLog.user_id.in_(user_ids),
                    climb_query_filter
                ).scalar() or 0
                
                standings = db.session.query(func.count(StandingLog.id)).filter(
                    StandingLog.user_id.in_(user_ids),
                    standing_query_filter
                ).scalar() or 0
                
                steps = db.session.query(func.count(StepLog.id)).filter(
                    StepLog.user_id.in_(user_ids),
                    steps_query_filter
                ).scalar() or 0
            else:
                climbs = standings = steps = 0
            
            # Use event-specific points if an event is active
            points = house_event_points[house.name]['total_points'] if active_event and house_event_points else house.total_points
            
            house_stats.append({
                'name': house.name,
                'climbs': climbs,
                'standings': standings,
                'steps': steps,
                'total_activities': climbs + standings + steps,
                'points': points,
                'members': house.member_count
            })
        
        # Calculate activity distribution by day of week
        days_of_week = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_stats = []
        
        for i, day in enumerate(days_of_week):
            # In SQLite, weekday is 0-6 where 0 is Sunday, so we need to adjust
            # Adjust i to match SQLite's weekday function (Sunday=0, Monday=1, etc.)
            sqlite_day = (i + 1) % 7
            
            # Apply event time filter if there's an active event
            climbs = db.session.query(func.count(ClimbLog.id)).filter(
                func.strftime('%w', ClimbLog.timestamp) == str(sqlite_day),
                climb_query_filter
            ).scalar() or 0
            
            standings = db.session.query(func.count(StandingLog.id)).filter(
                func.strftime('%w', StandingLog.timestamp) == str(sqlite_day),
                standing_query_filter
            ).scalar() or 0
            
            steps = db.session.query(func.count(StepLog.id)).filter(
                func.strftime('%w', StepLog.timestamp) == str(sqlite_day),
                steps_query_filter
            ).scalar() or 0
            
            day_stats.append({
                'day': day,
                'climbs': climbs,
                'standings': standings,
                'steps': steps,
                'total': climbs + standings + steps
            })
        
        # Get activity trend over last 30 days
        trend_data = []
        now = datetime.now(timezone.utc)  # Ensure we use timezone-aware datetime
        
        for i in range(30, 0, -1):
            date = now - timedelta(days=i)
            next_date = date + timedelta(days=1)
            date_str = date.strftime('%Y-%m-%d')
            
            # Skip dates outside event period if an event is active
            if active_event:
                # Convert dates to aware datetimes
                event_start = active_event.start_date
                event_end = active_event.end_date
                
                if event_start.tzinfo is None:
                    event_start = event_start.replace(tzinfo=timezone.utc)
                if event_end.tzinfo is None:
                    event_end = event_end.replace(tzinfo=timezone.utc)
                
                # Check if date is within event period
                if date > event_end or next_date < event_start:
                    trend_data.append({
                        'date': date_str,
                        'climbs': 0,
                        'standings': 0,
                        'steps': 0,
                        'total': 0
                    })
                    continue
                
                # For event days, adjust range to overlap with event
                start_range = max(date, event_start)
                end_range = min(next_date, event_end)
            else:
                # For normal view, just use date ranges
                start_range = date
                end_range = next_date
            
            # Ensure dates are timezone-aware
            if start_range.tzinfo is None:
                start_range = start_range.replace(tzinfo=timezone.utc)
            if end_range.tzinfo is None:
                end_range = end_range.replace(tzinfo=timezone.utc)
            
            # Create SQL filters
            date_filter = and_(
                ClimbLog.timestamp >= start_range,
                ClimbLog.timestamp < end_range
            )
            
            date_filter_standing = and_(
                StandingLog.timestamp >= start_range,
                StandingLog.timestamp < end_range
            )
            
            date_filter_steps = and_(
                StepLog.timestamp >= start_range,
                StepLog.timestamp < end_range
            )
            
            # Query activity counts
            climbs = db.session.query(func.count(ClimbLog.id)).filter(date_filter).scalar() or 0
            standings = db.session.query(func.count(StandingLog.id)).filter(date_filter_standing).scalar() or 0
            steps = db.session.query(func.count(StepLog.id)).filter(date_filter_steps).scalar() or 0
            
            trend_data.append({
                'date': date_str,
                'climbs': climbs,
                'standings': standings,
                'steps': steps,
                'total': climbs + standings + steps
            })
        
        # Log successful access
        log_access_attempt(True, "Analytics Dashboard", "Admin access successful")
        
        return render_template('analytics_dashboard.html',
                            total_users=total_users,
                            active_users=active_users,
                            total_climbs=total_climbs,
                            total_standings=total_standings,
                            total_step_logs=total_step_logs,
                            house_stats=house_stats,
                            day_stats=day_stats,
                            trend_data=trend_data,
                            active_event=active_event)
    
    except Exception as e:
        app.logger.error(f"Error in analytics dashboard: {str(e)}")
        flash('An error occurred while loading analytics data', 'danger')
        return redirect(url_for('admin_dashboard'))
