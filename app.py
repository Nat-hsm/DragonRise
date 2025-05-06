from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf.csrf import CSRFError, CSRFProtect
from flask_wtf import FlaskForm
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.sql import text
from sqlalchemy import create_engine, text
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
from models import User, House, ClimbLog, Achievement, init_houses, get_leaderboard, get_house_rankings, get_user_stats, init_admin

# Set log level from config
app.logger.setLevel(app.config['LOG_LEVEL'])

@app.route('/')
def index():
    houses = House.query.order_by(House.total_points.desc()).all()
    return render_template('index.html', houses=houses)

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("20 per minute")  # Updated from 5 to 20
def register():
    form = FlaskForm()
    if request.method == 'POST':
        if form.validate_on_submit():
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

    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("20 per minute")  # Updated from 5 to 20
def login():
    form = FlaskForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                username = request.form['username'].strip()
                password = request.form['password']

                user = User.query.filter(User.username.ilike(username)).first()
                if user and user.check_password(password):
                    login_user(user)
                    user.last_login = datetime.now(timezone.utc)  # Update last login time
                    db.session.commit()
                    log_activity(app, user.id, 'Login', 'Success')
                    flash('Welcome back, Dragon Climber!', 'success')
                    next_page = request.args.get('next')
                    
                    # Redirect admin to admin dashboard
                    if user.is_admin:
                        return redirect(next_page or url_for('admin_dashboard'))
                    else:
                        return redirect(next_page or url_for('dashboard'))

                log_activity(app, None, 'Login Failed', 'Invalid Credentials')
                flash('Invalid username or password', 'danger')

            except Exception as e:
                app.logger.error(f'Login error: {str(e)}')
                flash('An error occurred during login', 'danger')

    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    form = FlaskForm()
    houses = House.query.order_by(House.total_points.desc()).all()
    recent_logs = ClimbLog.query.filter_by(user_id=current_user.id)\
        .order_by(ClimbLog.timestamp.desc()).limit(5).all()
    return render_template('dashboard.html', 
                         houses=houses, 
                         user=current_user, 
                         recent_logs=recent_logs,
                         form=form)

@app.route('/log_climb', methods=['POST'])
@login_required
def log_climb():
    form = FlaskForm()
    if form.validate_on_submit():
        try:
            flights = int(request.form['flights'])
            if flights <= 0 or flights > app.config['MAX_FLIGHTS_PER_LOG']:
                flash(f'Please enter a valid number of flights (1-{app.config["MAX_FLIGHTS_PER_LOG"]})', 'danger')
                return redirect(url_for('dashboard'))

            points = flights * app.config['POINTS_PER_FLIGHT']

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

            log_activity(app, current_user.id, 'Climb Logged', f'{flights} flights')
            flash(f'Added {points} points to {current_user.house} house!', 'success')

        except ValueError as e:
            flash('Please enter a valid number of flights', 'danger')
            app.logger.warning(f'Invalid climb input: {str(e)}')
        except Exception as e:
            flash('An error occurred while logging your climb', 'danger')
            app.logger.error(f'Climb logging error: {str(e)}')
            db.session.rollback()

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

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    # Get all non-admin users ranked by points
    leaderboard = User.query.filter_by(is_admin=False).order_by(User.total_points.desc()).all()
    houses = House.query.order_by(House.total_points.desc()).all()
    
    # Get system statistics
    stats = {
        'total_users': User.query.filter_by(is_admin=False).count(),
        'total_flights': db.session.query(db.func.sum(User.total_flights)).filter(User.is_admin==False).scalar() or 0,
        'total_logs': ClimbLog.query.count(),
        'app_version': '1.0',
    }
    
    return render_template(
        'admin_dashboard.html', 
        leaderboard=leaderboard, 
        houses=houses,
        stats=stats
    )

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

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
    app.logger.error(f'Server Error: {error}')
    return render_template('500.html'), 500

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    app.logger.warning(f'CSRF Error: {e}')
    flash('Security token expired. Please try again.', 'danger')
    return redirect(request.referrer or url_for('index'))

@app.route('/csrf-token')
def get_csrf():
    return jsonify({'csrf_token': csrf._get_csrf_token()})

@app.context_processor
def utility_processor():
    def get_house_count():
        return House.query.count()
    return dict(get_house_count=get_house_count)

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/upload', methods=['GET'])
@login_required
def upload_form():
    # Instead of rendering upload.html, redirect to dashboard
    return redirect(url_for('dashboard'))

@app.route('/upload-screenshot', methods=['POST'])
@login_required
def upload_screenshot():
    form = FlaskForm()
    if form.validate_on_submit():
        try:
            # Check if a file was uploaded
            if 'screenshot' not in request.files:
                flash('No file selected', 'danger')
                return redirect(url_for('dashboard'))  # Changed from upload_form
                
            file = request.files['screenshot']
            
            # Check if filename is empty
            if file.filename == '':
                flash('No file selected', 'danger')
                return redirect(url_for('dashboard'))  # Changed from upload_form
                
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
                    
                    if flights is None:
                        flash('Could not determine flights from image. Please enter manually.', 'warning')
                        return render_template('manual_entry.html', 
                                             form=form, 
                                             image_path=filepath,
                                             timestamp=timestamp_str)
                    
                    # If timestamp wasn't detected, use current time
                    activity_time = None
                    if timestamp_str:
                        try:
                            # Try to parse the detected timestamp (flexible format)
                            activity_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M')
                        except ValueError:
                            # Try alternative formats or set to current time
                            formats = [
                                '%Y-%m-%d %H:%M:%S',
                                '%m/%d/%Y %H:%M',
                                '%d-%m-%Y %H:%M'
                            ]
                            for fmt in formats:
                                try:
                                    activity_time = datetime.strptime(timestamp_str, fmt)
                                    break
                                except ValueError:
                                    continue
                    
                    # If parsing fails or timestamp is missing, use current time
                    if not activity_time:
                        activity_time = datetime.now(timezone.utc)
                    
                    # Validate the flights count
                    if flights <= 0 or flights > app.config['MAX_FLIGHTS_PER_LOG']:
                        flash(f'Invalid number of flights detected: {flights}. Please enter manually.', 'warning')
                        return render_template('manual_entry.html', 
                                             form=form, 
                                             image_path=filepath,
                                             timestamp=activity_time.strftime('%Y-%m-%d %H:%M'))
                    
                    # Create notes with source information
                    notes = f"Auto-detected from screenshot. Timestamp: {activity_time.strftime('%Y-%m-%d %H:%M')}"
                    
                    # Calculate points
                    points = flights * app.config['POINTS_PER_FLIGHT']
                    
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
                    
                    log_activity(app, current_user.id, 'Screenshot Climb Logged', f'{flights} flights')
                    flash(f'Success! Added {flights} flights ({points} points) to your account!', 'success')
                    return redirect(url_for('dashboard'))
                    
                else:
                    # Analysis failed, show manual entry form
                    flash('Could not analyze the image. Please enter the details manually.', 'warning')
                    return render_template('manual_entry.html', 
                                         form=form, 
                                         image_path=filepath,
                                         error=result.get('error'))
            else:
                flash('Invalid file type. Please upload a JPG, JPEG or PNG file.', 'danger')
                return redirect(url_for('dashboard'))  # Changed from upload_form
                
        except Exception as e:
            app.logger.error(f"Screenshot upload error: {str(e)}")
            flash('An error occurred while processing your image', 'danger')
            return redirect(url_for('dashboard'))  # Changed from upload_form
    
    return redirect(url_for('dashboard'))  # Changed from upload_form

@app.route('/manual-entry', methods=['POST'])
@login_required
def manual_entry():
    form = FlaskForm()
    if form.validate_on_submit():
        try:
            flights = int(request.form['flights'])
            timestamp_str = request.form.get('timestamp')
            
            if flights <= 0 or flights > app.config['MAX_FLIGHTS_PER_LOG']:
                flash(f'Please enter a valid number of flights (1-{app.config["MAX_FLIGHTS_PER_LOG"]})', 'danger')
                return redirect(url_for('upload_form'))
            
            # Parse timestamp or use current time
            try:
                if timestamp_str:
                    activity_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M')
                else:
                    activity_time = datetime.now(timezone.utc)
            except ValueError:
                activity_time = datetime.now(timezone.utc)
            
            # Create notes
            notes = f"Manually entered from screenshot. Timestamp: {activity_time.strftime('%Y-%m-%d %H:%M')}"
            
            # Calculate points
            points = flights * app.config['POINTS_PER_FLIGHT']
            
            # Create climb log and update stats (same as auto-detection)
            log = ClimbLog(user_id=current_user.id, flights=flights, points=points, notes=notes)
            
            current_user.total_flights += flights
            current_user.total_points += points
            
            house = House.query.filter_by(name=current_user.house).first()
            if house:
                house.total_points += points
                house.total_flights += flights
            
            db.session.add(log)
            db.session.commit()
            
            log_activity(app, current_user.id, 'Manual Climb Logged', f'{flights} flights')
            flash(f'Success! Added {flights} flights ({points} points) to your account!', 'success')
            
        except ValueError:
            flash('Please enter a valid number of flights', 'danger')
        except Exception as e:
            app.logger.error(f"Manual entry error: {str(e)}")
            flash('An error occurred while logging your climb', 'danger')
            db.session.rollback()
            
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    # Print diagnostic information
    app.logger.info(f"Starting application in {os.getenv('FLASK_ENV', 'development')} mode")
    app.logger.info(f"Using database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    # Initialize database (but don't fail if it doesn't work)
    db_initialized = init_db()
    if not db_initialized:
        app.logger.warning("Database initialization failed, some functionality may be limited")
    
    # Run the app
    app.run(debug=app.config['DEBUG'])
