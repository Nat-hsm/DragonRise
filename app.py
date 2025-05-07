from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf.csrf import CSRFError, CSRFProtect
from flask_wtf import FlaskForm
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.sql import text
from sqlalchemy import create_engine, text, func
from datetime import datetime, timedelta, timezone  # Add timezone import
from dotenv import load_dotenv
import os
import logging
from werkzeug.utils import secure_filename
import re
from utils.security import init_security, PasswordManager, require_api_key, admin_required
from utils.logging_config import LogConfig, log_activity
from utils.database import setup_database
from utils.image_analyzer import ImageAnalyzer
from utils.time_utils import is_peak_hour, get_points_multiplier, get_peak_hours_message
from config import get_config, validate_config
from extensions import db, login_manager, migrate

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
csrf, limiter, limit_requests = init_security(app)

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
from models import User, House, ClimbLog, StandingLog, Achievement, init_houses, get_leaderboard, get_house_rankings, get_user_stats, init_admin

@app.route('/')
def index():
    houses = House.query.order_by(House.total_points.desc()).all()
    return render_template('index.html', houses=houses)

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if request.method == 'POST':
        try:
            username = request.form['username'].strip()
            password = request.form['password']
            house = request.form['house']

            # Validate input
            if not username or not password or not house:
                flash('All fields are required', 'danger')
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
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        try:
            username = request.form['username'].strip()
            password = request.form['password']

            # Use case-insensitive username matching
            user = User.query.filter(User.username.ilike(username)).first()
            if user and user.check_password(password):
                login_user(user)
                # Update last login time
                user.last_login = datetime.now(timezone.utc)
                db.session.commit()
                
                log_activity(app, user.id, 'Login', 'Success')
                flash('Welcome back, Dragon Climber!', 'success')
                next_page = request.args.get('next')
                
                # Redirect admin users to admin dashboard
                if user.is_admin:
                    return redirect(next_page or url_for('admin_dashboard'))
                else:
                    return redirect(next_page or url_for('dashboard'))

            log_activity(app, None, 'Login Failed', 'Invalid Credentials')
            flash('Invalid username or password', 'danger')

        except Exception as e:
            app.logger.error(f'Login error: {str(e)}')
            flash('An error occurred during login', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
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
    houses = House.query.order_by(House.total_points.desc()).all()
    recent_logs = StandingLog.query.filter_by(user_id=current_user.id)\
        .order_by(StandingLog.timestamp.desc()).limit(5).all()
    return render_template('standing_dashboard.html', 
                         houses=houses, 
                         user=current_user, 
                         recent_logs=recent_logs)

@app.route('/admin-dashboard')
@login_required
@admin_required
def admin_dashboard():
    # Get all users
    users = User.query.all()
    
    # Get all houses
    houses = House.query.order_by(House.name).all()
    
    # Calculate total statistics
    total_stats = {
        'flights': db.session.query(func.sum(User.total_flights)).scalar() or 0,
        'standing_time': db.session.query(func.sum(User.total_standing_time)).scalar() or 0,
        'points': db.session.query(func.sum(User.total_points)).scalar() or 0
    }
    
    # Mock activity logs (in a real app, you'd fetch these from a database)
    activity_logs = [
        {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'), 'username': 'System', 'action': 'System Startup', 'details': 'Application initialized'},
        {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'), 'username': 'Admin', 'action': 'Login', 'details': 'Admin logged in'}
    ]
    
    return render_template('admin_dashboard.html',
                         users=users,
                         houses=houses,
                         total_stats=total_stats,
                         activity_logs=activity_logs)

@app.route('/analytics-dashboard')
@login_required
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
    
    # Prepare climbing data
    climbing_data = {
        'flights': [house.total_flights for house in houses],
        'points': [house.total_flights * 10 for house in houses]
    }
    
    # Prepare standing data
    standing_data = {
        'minutes': [getattr(house, 'total_standing_time', 0) for house in houses],
        'points': [getattr(house, 'total_standing_time', 0) for house in houses]  # 1 point per minute
    }
    
    # Prepare combined data
    combined_data = {
        'climbing_points': [house.total_flights * 10 for house in houses],
        'standing_points': [getattr(house, 'total_standing_time', 0) for house in houses],
        'total_points': [house.total_points for house in houses]
    }
    
    return render_template('analytics_dashboard.html',
                         houses=houses,
                         house_names=house_names,
                         house_colors=house_colors_list,
                         climbing_data=climbing_data,
                         standing_data=standing_data,
                         combined_data=combined_data)

@app.route('/log_climb', methods=['POST'])
@login_required
def log_climb():
    try:
        flights = int(request.form['flights'])
        if flights <= 0:
            flash('Please enter a valid number of flights', 'danger')
            return redirect(url_for('dashboard'))

        # Check if it's peak hour for multiplier
        multiplier = get_points_multiplier()
        points = flights * 10 * multiplier

        # Create climb log
        log = ClimbLog(user_id=current_user.id, flights=flights, points=points)

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
        multiplier_text = f" (2x multiplier!)" if multiplier > 1 else ""
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
def log_standing():
    try:
        minutes = int(request.form['minutes'])
        
        if minutes <= 0:
            flash('Please enter a valid number of minutes', 'danger')
            return redirect(url_for('standing_dashboard'))

        # Check if it's peak hour for multiplier
        multiplier = get_points_multiplier()
        points = minutes * multiplier
        
        # Create standing log
        log = StandingLog(user_id=current_user.id, minutes=minutes, points=points)

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
        multiplier_text = f" (2x multiplier!)" if multiplier > 1 else ""
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

@app.route('/upload-screenshot', methods=['POST'])
@login_required
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
            
        if file and allowed_file(file.filename):
            # Create uploads directory if it doesn't exist
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Secure the filename and save file
            filename = secure_filename(file.filename)
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
            unique_filename = f"{current_user.id}_{timestamp}_{filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            # Create image analyzer and process the image
            image_analyzer = ImageAnalyzer()
            file.seek(0)  # Reset file pointer to beginning
            result = image_analyzer.analyze_image(file)
            
            if result.get('success'):
                flights = result.get('flights')
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
                multiplier_text = f" (2x multiplier!)" if multiplier > 1 else ""
                log_activity(app, current_user.id, 'Screenshot Climb Logged', f'{flights} flights{multiplier_text}')
                flash(f'Successfully processed screenshot! Added {points} points for {flights} flights.{multiplier_text}', 'success')
            else:
                flash(f'Could not process screenshot: {result.get("error", "Unknown error")}', 'danger')
        else:
            flash('Invalid file type. Please upload a PNG or JPG image.', 'danger')
    except Exception as e:
        app.logger.error(f'Screenshot upload error: {str(e)}')
        flash('An error occurred while processing your screenshot', 'danger')
    
    return redirect(url_for('dashboard'))

@app.route('/upload-standing-screenshot', methods=['POST'])
@login_required
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
            
                if minutes <= 0:
                    flash('Could not detect standing time from the screenshot', 'danger')
                    return redirect(url_for('standing_dashboard'))
                
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
                multiplier_text = f" (2x multiplier!)" if multiplier > 1 else ""
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

@app.route('/api/house_points')
@require_api_key
def house_points():
    houses = House.query.all()
    return jsonify([{
        'name': house.name,
        'points': house.total_points,
        'members': house.member_count
    } for house in houses])

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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

@app.context_processor
def utility_processor():
    def get_house_count():
        return House.query.count()
    
    # Add peak hour information to all templates
    return {
        'get_house_count': get_house_count,
        'is_peak_hour': is_peak_hour(),
        'peak_hours_message': get_peak_hours_message()
    }

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

if __name__ == '__main__':
    app.run(debug=True)