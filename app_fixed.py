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
from utils.time_utils import is_peak_hour, get_points_multiplier, get_peak_hours_message, get_current_peak_hour_info
from config import get_config, validate_config
from extensions import db, login_manager, migrate
import json

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
from models import User, House, ClimbLog, StandingLog, StepLog, Achievement, init_houses, get_leaderboard, get_house_rankings, get_user_stats, init_admin
@app.route('/')
def index():
    houses = House.query.order_by(House.total_points.desc()).all()
    return render_template('index.html', houses=houses)

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("200 per minute")  # Changed from 5 to 200 per minute
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
@limiter.limit("200 per minute")  # Changed from 5 per minute
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

@app.route('/steps-dashboard')
@login_required
def steps_dashboard():
    houses = House.query.order_by(House.total_points.desc()).all()
    recent_logs = StepLog.query.filter_by(user_id=current_user.id)\
        .order_by(StepLog.timestamp.desc()).limit(5).all()
    return render_template('steps_dashboard.html', 
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
                         peak_hours=peak_hours,
                         total_stats=total_stats,
                         activity_logs=activity_logs)
@app.route('/admin-dashboard/delete-user', methods=['POST'])
@login_required
@admin_required
def delete_user():
    try:
        user_id = request.form.get('user_id')
        if not user_id:
            flash('User ID is required', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        # Find the user
        user = User.query.get_or_404(int(user_id))
        
        # Don't allow deleting the admin user
        if user.is_admin:
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
        log_activity(app, current_user.id, 'User Deleted', f'User {username} was deleted')
        flash(f'User {username} has been deleted', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting user: {str(e)}")
        flash('An error occurred while deleting the user', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin-dashboard/reset-house', methods=['POST'])
@login_required
@admin_required
def reset_house():
    try:
        house_id = request.form.get('house_id')
        if not house_id:
            flash('House ID is required', 'danger')
            return redirect(url_for('admin_dashboard'))
            
        # Find the house
        house = House.query.get_or_404(int(house_id))
        
        # Store house name for logging
        house_name = house.name
        
        # Reset house statistics
        old_points = house.total_points
        house.total_points = 0
        house.total_flights = 0
        house.total_standing_time = 0
        
        # Reset points for all users in this house
        users_in_house = User.query.filter_by(house=house.name).all()
        for user in users_in_house:
            if not user.is_admin:  # Don't reset admin user stats
                user.total_points = 0
                user.total_flights = 0
                user.total_standing_time = 0
        
        # Commit changes
        db.session.commit()
        
        # Log the activity
        log_activity(app, current_user.id, 'House Reset', f'House {house_name} points reset from {old_points} to 0')
        flash(f'House {house_name} has been reset. All points and statistics are now zero.', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error resetting house: {str(e)}")
        flash('An error occurred while resetting the house', 'danger')
    
    return redirect(url_for('admin_dashboard'))
@app.route('/admin-dashboard/add-peak-hour', methods=['POST'])
@login_required
@admin_required
def add_peak_hour():
    try:
        name = request.form.get('name')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        multiplier = int(request.form.get('multiplier', 2))
        
        # Validate input
        if not name or not start_time_str or not end_time_str:
            flash('All fields are required', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Parse time strings to time objects
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()
        
        # Create new peak hour setting
        from models import PeakHourSetting
        new_setting = PeakHourSetting(
            name=name,
            start_time=start_time,
            end_time=end_time,
            multiplier=multiplier,
            is_active=True
        )
        
        db.session.add(new_setting)
        db.session.commit()
        
        # Log the activity
        log_activity(app, current_user.id, 'Peak Hour Added', f'Added new peak hour: {name}')
        flash(f'Peak hour "{name}" has been added successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error adding peak hour: {str(e)}")
        flash('An error occurred while adding the peak hour', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin-dashboard/edit-peak-hour', methods=['POST'])
@login_required
@admin_required
def edit_peak_hour():
    try:
        setting_id = request.form.get('setting_id')
        name = request.form.get('name')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        multiplier = int(request.form.get('multiplier', 2))
        
        # Validate input
        if not setting_id or not name or not start_time_str or not end_time_str:
            flash('All fields are required', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Find the peak hour setting
        from models import PeakHourSetting
        setting = PeakHourSetting.query.get_or_404(int(setting_id))
        
        # Parse time strings to time objects
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()
        
        # Update setting
        setting.name = name
        setting.start_time = start_time
        setting.end_time = end_time
        setting.multiplier = multiplier
        
        db.session.commit()
        
        # Log the activity
        log_activity(app, current_user.id, 'Peak Hour Updated', f'Updated peak hour: {name}')
        flash(f'Peak hour "{name}" has been updated successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error updating peak hour: {str(e)}")
        flash('An error occurred while updating the peak hour', 'danger')
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin-dashboard/toggle-peak-hour', methods=['POST'])
@login_required
@admin_required
def toggle_peak_hour():
    try:
        setting_id = request.form.get('setting_id')
        if not setting_id:
            flash('Setting ID is required', 'danger')
            return redirect(url_for('admin_dashboard'))
        
        # Find the peak hour setting
        from models import PeakHourSetting
        setting = PeakHourSetting.query.get_or_404(int(setting_id))
        
        # Toggle active status
        setting.is_active = not setting.is_active
        
        db.session.commit()
        
        # Log the activity
        status = "activated" if setting.is_active else "deactivated"
        log_activity(app, current_user.id, 'Peak Hour Status Changed', f'{setting.name} {status}')
        flash(f'Peak hour "{setting.name}" has been {status}', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error toggling peak hour: {str(e)}")
        flash('An error occurred while updating the peak hour status', 'danger')
    
    return redirect(url_for('admin_dashboard'))
@app.route('/analytics-dashboard')
@login_required
def analytics_dashboard():
    try:
        # Add debug logging to identify data issues
        app.logger.info("Analytics dashboard requested by user: %s", current_user.username)
        
        # Query houses with explicit column selection to avoid missing attributes
        houses = House.query.order_by(House.name).all()
        
        app.logger.info("Found %d houses for analytics dashboard", len(houses))
        for house in houses:
            app.logger.debug("House: %s, flights: %s, standing: %s, steps: %s, points: %s", 
                           house.name, 
                           getattr(house, 'total_flights', 0),
                           getattr(house, 'total_standing_time', 0),
                           getattr(house, 'total_steps', 0),
                           getattr(house, 'total_points', 0))
        
        # Fallback for empty data
        if not houses:
            # Return template with empty data
            app.logger.warning("No houses found for analytics dashboard")
            return render_template('analytics_dashboard.html',
                                houses=[],
                                house_names=json.dumps([]),
                                house_colors=json.dumps([]),
                                climbing_data=json.dumps({'flights': [], 'points': []}),
                                standing_data=json.dumps({'minutes': [], 'points': []}),
                                steps_data=json.dumps({'steps': [], 'points': []}),
                                combined_data=json.dumps({'climbing_points': [], 'standing_points': [], 'steps_points': [], 'total_points': []}),
                                now=int(datetime.now().timestamp()))
        
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
        
        # Add sample data if everything is zero (for testing)
        if all(house.total_points == 0 for house in houses):
            app.logger.warning("All houses have zero points - adding sample data for display")
            # This is just for visualization when no real data exists
            for i, house in enumerate(houses):
                factor = i + 1
                house.total_flights = 5 * factor
                house.total_standing_time = 20 * factor
                house.total_steps = 1000 * factor
                house.total_points = (5 * 10 + 20 + 10) * factor
        
        # Prepare climbing data
        climbing_data = {
            'flights': [house.total_flights for house in houses],
            'points': [house.total_flights * 10 for house in houses]
        }
        
        # Prepare standing data
        standing_data = {
            'minutes': [house.total_standing_time for house in houses],
            'points': [house.total_standing_time for house in houses]
        }
        
        # Prepare steps data
        steps_data = {
            'steps': [house.total_steps for house in houses],
            'points': [(house.total_steps // 100) for house in houses]
        }
        
        # Prepare combined data
        combined_data = {
            'climbing_points': [house.total_flights * 10 for house in houses],
            'standing_points': [house.total_standing_time for house in houses],
            'steps_points': [(house.total_steps // 100) for house in houses],
            'total_points': [house.total_points for house in houses]
        }
        
        # Add a timestamp to force browser to reload the script (cache busting)
        now = int(datetime.now().timestamp())
        
        # Log the data we're about to send for debugging
        app.logger.debug("Chart data: houses=%s, colors=%s, climbing=%s, standing=%s, steps=%s, combined=%s",
                       house_names, house_colors_list, climbing_data, standing_data, steps_data, combined_data)
        
        # Add explicit debug before rendering
        debug_data = {
            'house_names_type': type(house_names).__name__,
            'house_names': house_names,
            'house_colors_type': type(house_colors_list).__name__,
            'house_colors': house_colors_list,
            'climbing_data_type': type(climbing_data).__name__,
            'climbing_data': climbing_data
        }
        app.logger.info(f"Debug data: {debug_data}")
        
        # Use tojson filter in the template instead of json.dumps
        return render_template('analytics_dashboard.html',
                            houses=houses,
                            house_names=json.dumps(house_names),  # Convert to JSON string
                            house_colors=json.dumps(house_colors_list),
                            climbing_data=json.dumps(climbing_data),
                            standing_data=json.dumps(standing_data),
                            steps_data=json.dumps(steps_data),
                            combined_data=json.dumps(combined_data),
                            now=now)
    except Exception as e:
        app.logger.error(f"Error rendering analytics dashboard: {str(e)}", exc_info=True)
        return render_template('analytics_error.html', error_message=str(e)), 500

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
@limiter.limit("1000 per minute")  # Changed from 10 to 1000 per minute (or added if missing)
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
            
            # Save file first
            file.save(filepath)
            app.logger.info(f"Saved file: {filepath}")
            
            # Create image analyzer and process the image
            try:
                image_analyzer = ImageAnalyzer()
                file.seek(0)  # Reset file pointer to beginning
                result = image_analyzer.analyze_image(file)
                
                if result.get('success'):
                    flights = result.get('flights')
                    
                    # Check if it's peak hour for multiplier
                    multiplier = get_points_multiplier()
                    points = flights * 10 * multiplier
                    
                    # Add fallback notice if applicable
                    fallback_notice = " (using estimate)" if result.get('fallback_used') else ""
                    
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
                    log_activity(app, current_user.id, 'Screenshot Climb Logged', f'{flights} flights{multiplier_text}{fallback_notice}')
                    flash(f'Successfully processed screenshot! Added {points} points for {flights} flights.{multiplier_text}{fallback_notice}', 'success')
                else:
                    error_msg = result.get("error", "Unknown error")
                    app.logger.error(f"Screenshot processing error: {error_msg}")
                    flash(f'Could not process screenshot: {error_msg}', 'danger')
            except Exception as e:
                app.logger.error(f'Image processing error: {str(e)}')
                flash(f'Error processing upload: {str(e)}', 'danger')
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
            try:
                image_analyzer = ImageAnalyzer()
                file.seek(0)  # Reset file pointer to beginning
                result = image_analyzer.analyze_steps_image(file)
                
                if result.get('success'):
                    steps = result.get('steps')
                    
                    # Check if it's peak hour for multiplier
                    multiplier = get_points_multiplier()
                    points = (steps // 100) * multiplier
                    
                    # Log the steps
                    log = StepLog(user_id=current_user.id, steps=steps, points=points)
                    
                    # Update user stats
                    if hasattr(current_user, 'total_steps'):
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
                        
                        # Add fallback info if applicable
                        fallback_text = " (using fallback)" if result.get('fallback_used') else ""
                        # Add multiplier info if applicable
                        multiplier_text = f" ({multiplier}x multiplier!)" if multiplier > 1 else ""
                        
                        log_activity(app, current_user.id, 'Screenshot Steps Logged', 
                                    f'{steps} steps{multiplier_text}{fallback_text}')
                        flash(f'Successfully processed screenshot! Added {points} points for {steps} steps.{multiplier_text}{fallback_text}', 'success')
                    else:
                        flash('Steps tracking is not available yet. Please run the migration script.', 'warning')
                else:
                    flash(f'Could not process screenshot: {result.get("error", "Unknown error")}', 'danger')
            except Exception as e:
                app.logger.error(f'Steps image processing error: {str(e)}')
                flash('Error processing upload: ' + str(e), 'danger')
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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
    app.run(debug=True)