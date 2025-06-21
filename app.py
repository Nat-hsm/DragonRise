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
    
    # For GET requests, use OAuth with explicit redirect URI
    # Instead of dynamically generating it
    redirect_uri = app.config.get('COGNITO_REDIRECT_URI')
    return oauth.oidc.authorize_redirect(redirect_uri)

@app.route('/signup')
@limiter.limit("200 per minute")
def signup():
    """Direct users to Cognito signup flow"""
    redirect_uri = url_for('auth_callback', _external=True)
    # Explicitly set state to 'signup' to indicate this is a registration flow
    return oauth.oidc.authorize_redirect(redirect_uri, state="signup")

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
        
        # Rest of your authentication logic here...
        
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
        
        # Get user attributes
        user_attrs = cognito_auth.get_user_attributes(access_token)
        
        # Check if user already exists in our database
        user = User.query.filter(User.username.ilike(cognito_username)).first()
        
        if not user:
            # New user - handle signup flow
            if state == 'signup':
                # Redirect to house selection page with token in session
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
            login_user(user)
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            
            log_activity(app, user.id, 'Cognito Login', 'Success')
            flash('Welcome back, Dragon Climber!', 'success')
            
            # Store tokens in session
            session['cognito_id_token'] = id_token
            session['cognito_access_token'] = access_token
            
            return redirect(url_for('dashboard'))
            
    except Exception as e:
        app.logger.error(f'Auth callback error: {str(e)}')
        flash(f'Authentication error: {str(e)}', 'danger')  # Show the actual error
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
    # Clear session data
    session.pop('user', None)
    session.pop('cognito_id_token', None)
    session.pop('cognito_access_token', None)
    
    # Standard Flask-Login logout
    logout_user()
    flash('You have been logged out.', 'info')
    
    try:
        # Return to Cognito logout if OAuth is available
        return redirect(oauth.oidc.api_base_url + 
                      '/logout?client_id=' + app.config['COGNITO_CLIENT_ID'] +
                      '&logout_uri=' + url_for('index', _external=True))
    except:
        # Fallback to regular logout if OAuth fails
        return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Redirect admin to admin dashboard
    if current_user.is_admin:
        flash('Admin users should use the Admin Dashboard', 'info')
        return redirect(url_for('admin_dashboard'))
        
    houses = House.query.order_by(House.total_points.desc()).all()
    recent_logs = ClimbLog.query.filter_by(user_id=current_user.id)\
        .order_by(ClimbLog.timestamp.desc()).limit(5).all()
    return render_template('dashboard.html', 
                         houses=houses, 
                         user=current_user, 
                         recent_logs=recent_logs)

@app.route('/standing-dashboard')
@login_required
def standing_dashboard():
    # Redirect admin to admin dashboard
    if current_user.is_admin:
        flash('Admin users should use the Admin Dashboard', 'info')
        return redirect(url_for('admin_dashboard'))
        
    houses = House.query.order_by(House.total_points.desc()).all()
    recent_logs = StandingLog.query.filter_by(user_id=current_user.id)\
        .order_by(StandingLog.timestamp.desc()).limit(5).all()
    return render_template('standing_dashboard.html', 
                         houses=houses, 
                         user=current_user, 
                         recent_logs=recent_logs)

@app.route('/steps-dashboard')
@login_required
def steps_dashboard():
    # Redirect admin to admin dashboard
    if current_user.is_admin:
        flash('Admin users should use the Admin Dashboard', 'info')
        return redirect(url_for('admin_dashboard'))
        
    houses = House.query.order_by(House.total_points.desc()).all()
    recent_logs = StepLog.query.filter_by(user_id=current_user.id)\
        .order_by(StepLog.timestamp.desc()).limit(5).all()
    return render_template('steps_dashboard.html', 
                         houses=houses, 
                         user=current_user, 
                         recent_logs=recent_logs)

@app.route('/analytics-dashboard')
@login_required
@admin_required
def analytics_dashboard():
    houses = House.query.order_by(House.name).all()
    
    # Prepare data for charts
    house_names = [house.name for house in houses]
    
    # Define colors for each house - using the CSS variables
    house_colors = {
        'Black': 'rgba(51, 51, 51, 0.8)',
        'Blue': 'rgba(0, 102, 204, 0.8)',
        'Green': 'rgba(0, 153, 51, 0.8)',
        'White': 'rgba(248, 249, 250, 0.8)',
        'Gold': 'rgba(255, 204, 0, 0.8)',
        'Purple': 'rgba(102, 0, 153, 0.8)'
    }
    
    house_colors_list = [house_colors.get(name, 'rgba(150, 150, 150, 0.8)') for name in house_names]
    
    # Ensure all houses have the required attributes with default values
    for house in houses:
        if not hasattr(house, 'total_flights') or house.total_flights is None:
            house.total_flights = 0
        if not hasattr(house, 'total_standing_time') or house.total_standing_time is None:
            house.total_standing_time = 0
        if not hasattr(house, 'total_steps') or house.total_steps is None:
            house.total_steps = 0
        if not hasattr(house, 'total_points') or house.total_points is None:
            house.total_points = 0
    
    # Prepare climbing data
    climbing_data = {
        'flights': [house.total_flights for house in houses],
        'points': [house.total_flights * 10 for house in houses]
    }
    
    # Prepare standing data
    standing_data = {
        'minutes': [house.total_standing_time for house in houses],
        'points': [house.total_standing_time for house in houses]  # 1 point per minute
    }
    
    # Prepare steps data
    steps_data = {
        'steps': [house.total_steps for house in houses],
        'points': [(house.total_steps // 100) for house in houses]
    }
    
    # Prepare combined data with explicit type definitions
    combined_data = {
        'climbing_points': [house.total_flights * 10 for house in houses],
        'standing_points': [house.total_standing_time for house in houses],
        'steps_points': [(house.total_steps // 100) for house in houses],
        'total_points': [house.total_points for house in houses]
    }
    
    # Log data in a more readable format for debugging
    app.logger.info(f"Analytics data - Houses: {house_names}")
    app.logger.info(f"Climbing data: {climbing_data}")
    app.logger.info(f"Standing data: {standing_data}")
    app.logger.info(f"Steps data: {steps_data}")
    app.logger.info(f"Combined data: {combined_data}")
    
    return render_template('analytics_dashboard.html',
                         houses=houses,
                         house_names=house_names,
                         house_colors=house_colors_list,
                         climbing_data=climbing_data,
                         standing_data=standing_data,
                         steps_data=steps_data,
                         combined_data=combined_data)

@app.route('/user/<int:user_id>/stats')
@login_required
@user_data_access_required
def user_stats(user_id):
    """Get user statistics with access control"""
    stats = get_user_stats(user_id)
    if stats:
        return jsonify(stats)
    return abort(404)

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
@verify_content_type('application/x-www-form-urlencoded')
def delete_user():
    # Verify admin status again as an extra precaution
    if not current_user.is_admin:
        log_access_attempt(False, "Delete User", "Non-admin access attempt")
        flash('Access denied. Admin privileges required.', 'danger')
        return redirect(url_for('dashboard'))
        
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
@limiter.limit("20 per minute")  # Added rate limiting
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
@limiter.limit("20 per minute")  # Added rate limiting
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

    return redirect(url_for('standing_dashboard'))

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

    return redirect(url_for('steps_dashboard'))

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
    
    return redirect(url_for('standing_dashboard'))

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
    
    return redirect(url_for('steps_dashboard'))

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

@app.route('/debug-cognito')
def debug_cognito():
    """Debug Cognito configuration"""
    return f"""
    <h1>Cognito Debug</h1>
    <p><strong>Domain:</strong> {app.config.get('COGNITO_DOMAIN')}</p>
    <p><strong>User Pool ID:</strong> {app.config.get('COGNITO_USER_POOL_ID')}</p>
    <p><strong>Redirect URI:</strong> {app.config.get('COGNITO_REDIRECT_URI')}</p>
    <p><strong>Login URL:</strong> {cognito_auth.get_login_url()}</p>
    <p><a href="{cognito_auth.get_login_url()}">Test Login</a></p>
    """

@app.route('/debug-redirect')
def debug_redirect():
    """Debug redirect settings"""
    from flask import request
    
    current_url = request.url
    base_url = request.url_root.rstrip('/')
    configured_redirect = app.config.get('COGNITO_REDIRECT_URI')
    generated_redirect = url_for('auth_callback', _external=True)
    
    return f"""
    <h1>Redirect Debug</h1>
    <p><strong>Current URL:</strong> {current_url}</p>
    <p><strong>Base URL:</strong> {base_url}</p>
    <p><strong>Configured Redirect:</strong> {configured_redirect}</p>
    <p><strong>Generated Redirect:</strong> {generated_redirect}</p>
    <hr>
    <p>If these don't match, update your COGNITO_REDIRECT_URI in .env to: {generated_redirect}</p>
    <p>Make sure to update the allowed callback URLs in AWS Cognito console too.</p>
    """

@app.route('/debug-token')
def debug_token():
    """Debug token exchange process"""
    mock_code = "test_code"  # This won't actually work, just for debugging
    
    # Get the Cognito configuration
    domain = app.config.get('COGNITO_DOMAIN')
    client_id = app.config.get('COGNITO_CLIENT_ID')
    client_secret = app.config.get('COGNITO_CLIENT_SECRET')
    redirect_uri = app.config.get('COGNITO_REDIRECT_URI')
    
    return f"""
    <h1>Token Exchange Debug</h1>
    <p><strong>Domain:</strong> {domain}</p>
    <p><strong>Client ID:</strong> {client_id}</p>
    <p><strong>Client Secret:</strong> {'*' * 8}</p>
    <p><strong>Redirect URI:</strong> {redirect_uri}</p>
    <p><strong>Token URL:</strong> https://{domain}.auth.{app.config.get('AWS_REGION')}.amazoncognito.com/oauth2/token</p>
    """

@app.route('/auth-debug')
def auth_debug():
    code = request.args.get('code', 'No code')
    state = request.args.get('state', 'No state')
    error = request.args.get('error', 'No error')
    error_description = request.args.get('error_description', 'No description')
    
    token_debug = "No code to exchange"
    raw_response = "None"
    
    if code != 'No code':
        # Try to exchange the code for a token
        try:
            import requests
            
            token_url = f"https://{app.config.get('COGNITO_DOMAIN')}.auth.{app.config.get('AWS_REGION')}.amazoncognito.com/oauth2/token"
            
            # Client credentials in the form data instead of Basic Auth
            body = {
                'grant_type': 'authorization_code',
                'client_id': app.config.get('COGNITO_CLIENT_ID'),
                'client_secret': app.config.get('COGNITO_CLIENT_SECRET'),
                'code': code,
                'redirect_uri': app.config.get('COGNITO_REDIRECT_URI')
            }
            
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            response = requests.post(token_url, data=body, headers=headers)
            raw_response = response.text
            token_debug = f"Status: {response.status_code}, Content: {raw_response[:100]}..."
        except Exception as e:
            token_debug = f"Error: {str(e)}"
    
    # Rest of the function remains the same
    return f"""
    <h1>Auth Debug (Improved)</h1>
    <p><strong>Code:</strong> {code[:10]}...</p>
    <p><strong>State:</strong> {state}</p>
    <p><strong>Error:</strong> {error}</p>
    <p><strong>Error Description:</strong> {error_description}</p>
    <p><strong>Token Exchange:</strong> {token_debug}</p>
    <p><strong>Raw Response:</strong> <pre>{raw_response}</pre></p>
    <p><a href="/login">Try Login Again</a></p>
    """

@app.route('/cognito-test')
def cognito_test():
    """Test endpoint for Cognito token exchange"""
    try:
        # Generate a login URL for testing
        login_url = cognito_auth.get_login_url("test-auth-flow")
        
        # Get and display current configuration
        config = {
            'domain': app.config.get('COGNITO_DOMAIN'),
            'client_id': app.config.get('COGNITO_CLIENT_ID'),
            'redirect_uri': app.config.get('COGNITO_REDIRECT_URI'),
            'region': app.config.get('AWS_REGION'),
        }
        
        # Check if redirect URI matches current host
        current_host = request.host_url.rstrip('/')
        expected_callback = f"{current_host}/auth/callback"
        redirect_match = app.config.get('COGNITO_REDIRECT_URI') == expected_callback
        
        return f"""
        <h1>Cognito Authentication Test</h1>
        <h2>Configuration</h2>
        <ul>
            <li><strong>Domain:</strong> {config['domain']}</li>
            <li><strong>Client ID:</strong> {config['client_id']}</li>
            <li><strong>Redirect URI:</strong> {config['redirect_uri']}</li>
            <li><strong>Current Host:</strong> {current_host}</li>
            <li><strong>Expected Callback:</strong> {expected_callback}</li>
            <li><strong>Redirect Match:</strong> {'✅ Matches' if redirect_match else '❌ Mismatch! Update your .env file and AWS Console'}</li>
        </ul>
        <h2>Test Authentication</h2>
        <p><a href="{login_url}" class="btn btn-primary">Test Cognito Login</a></p>
        <h2>Troubleshooting</h2>
        <ol>
            <li>Make sure the allowed callback URL in AWS Console includes: {expected_callback}</li>
            <li>Verify the app client settings match what's in your .env file</li>
            <li>In AWS Console, check if the token endpoint auth is set to 'CLIENT_SECRET_POST'</li>
        </ol>
        """
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>"

@app.route('/token-debug')
def token_debug():
    """Detailed token debugging"""
    code = request.args.get('code', '')
    
    if not code:
        return """
        <h1>Token Exchange Debugger</h1>
        <p>Add a 'code' parameter to test token exchange manually</p>
        <p>Example: <code>/token-debug?code=your_code_here</code></p>
        """
    
    # Try both auth methods
    import requests
    from urllib.parse import urlencode
    from requests.auth import HTTPBasicAuth
    
    token_url = f"https://{app.config.get('COGNITO_DOMAIN')}.auth.{app.config.get('AWS_REGION')}.amazoncognito.com/oauth2/token"
    client_id = app.config.get('COGNITO_CLIENT_ID')
    client_secret = app.config.get('COGNITO_CLIENT_SECRET')
    redirect_uri = app.config.get('COGNITO_REDIRECT_URI')
    
    # Method 1: CLIENT_SECRET_POST
    headers1 = {'Content-Type': 'application/x-www-form-urlencoded'}
    body1 = {
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'redirect_uri': redirect_uri
    }
    
    # Method 2: CLIENT_SECRET_BASIC
    headers2 = {'Content-Type': 'application/x-www-form-urlencoded'}
    body2 = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri
    }
    auth2 = HTTPBasicAuth(client_id, client_secret)
    
    try:
        response1 = requests.post(token_url, headers=headers1, data=urlencode(body1))
        response2 = requests.post(token_url, headers=headers2, data=urlencode(body2), auth=auth2)
        
        return f"""
        <h1>Token Exchange Debugging</h1>
        <h2>CLIENT_SECRET_POST Method</h2>
        <p>Status: {response1.status_code}</p>
        <pre>{response1.text}</pre>
        
        <h2>CLIENT_SECRET_BASIC Method</h2>
        <p>Status: {response2.status_code}</p>
        <pre>{response2.text}</pre>
        """
    except Exception as e:
        return f"<h1>Error</h1><p>{str(e)}</p>"

@app.route('/test-auth-flow')
def test_auth_flow():
    """Test the complete authentication flow"""
    # Generate a random state value for CSRF protection
    import secrets
    state = secrets.token_hex(16)
    
    # Store the state in the session
    session['oauth_state'] = state
    
    # Generate login URL with the state parameter
    login_url = cognito_auth.get_login_url(state)
    
    # Display information about the flow
    return f"""
    <h1>AWS Cognito Authentication Flow Test</h1>
    <p>This will test the complete authentication flow with a fresh authorization code.</p>
    <p><strong>Steps:</strong></p>
    <ol>
        <li>Click the "Start Authentication" button below</li>
        <li>Log in or sign up with AWS Cognito</li>
        <li>You'll be redirected back to the callback URL</li>
        <li>The code will be automatically exchanged for tokens</li>
    </ol>
    <p><a href="{login_url}" class="btn btn-primary">Start Authentication</a></p>
    """
@app.route('/domain-debug')
def domain_debug():
    """Test different domain formats for Cognito"""
    # Current domain from config
    current_domain = app.config.get('COGNITO_DOMAIN')
    
    # Extract parts for testing different combinations
    parts = current_domain.split('-')
    if len(parts) > 2 and parts[0] == 'us' and parts[1] == 'east':
        region_prefix = f"{parts[0]}-{parts[1]}-"
        domain_suffix = parts[2]
    else:
        region_prefix = ""
        domain_suffix = current_domain
    
    # Generate test URLs with different domain formats
    test_urls = [
        {
            "name": "Current Configuration", 
            "url": f"https://{current_domain}.auth.{app.config.get('AWS_REGION')}.amazoncognito.com"
        },
        {
            "name": "Without Region in Domain", 
            "url": f"https://{domain_suffix}.auth.{app.config.get('AWS_REGION')}.amazoncognito.com"
        },
        {
            "name": "Domain-Only", 
            "url": f"https://{domain_suffix}.auth.amazoncognito.com"
        }
    ]
    
    # Generate HTML for testing each URL
    url_tests = ""
    for test in test_urls:
        url_tests += f"""
        <div class="mb-3">
            <h3>{test["name"]}</h3>
            <p><code>{test["url"]}</code></p>
            <a href="{test["url"]}" target="_blank" class="btn btn-sm btn-primary">Test URL</a>
        </div>
        """
    
    return f"""
    <h1>Cognito Domain Debugging</h1>
    <p>Testing different domain formats to find the correct one.</p>
    <p><strong>Current domain from config:</strong> {current_domain}</p>
    {url_tests}
    <hr>
    <h3>Instructions:</h3>
    <ol>
        <li>Check which URL works by clicking the "Test URL" buttons</li>
        <li>Look for the URL that loads the AWS Cognito login page</li>
        <li>Update your .env file with the correct domain prefix (the part before .auth...)</li>
    </ol>
    """