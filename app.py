from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFError, CSRFProtect
from flask_wtf import FlaskForm
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from datetime import datetime
from dotenv import load_dotenv
import os
import logging
import watchtower
from utils.security import init_security, PasswordManager, require_api_key
from utils.logging_config import LogConfig, log_activity
# Import models from models.py
from models import User, House, ClimbLog, Achievement, init_houses, get_leaderboard, get_house_rankings, get_user_stats
# Import configuration
from config import get_config, validate_config

# Load environment variables
load_dotenv()

# Create Flask app
app = Flask(__name__)

# Load configuration based on environment
config = get_config()
app.config.from_object(config)

# Validate configuration
validate_config(config)

# Initialize app with environment-specific settings
config.init_app(app)

# Create engine with connection pooling from config settings
engine = create_engine(
    app.config['SQLALCHEMY_DATABASE_URI'],
    poolclass=QueuePool,
    **app.config['SQLALCHEMY_ENGINE_OPTIONS']
)

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)

# Initialize security features
csrf, limiter, limit_requests = init_security(app)

# Initialize logging
log_config = LogConfig(app)

# Add CloudWatch logging if configured
if app.config.get('AWS_ACCESS_KEY_ID') and app.config.get('AWS_SECRET_ACCESS_KEY'):
    handler = watchtower.CloudWatchLogHandler(
        log_group=app.config['CLOUDWATCH_LOG_GROUP'],
        stream_name=app.config['CLOUDWATCH_LOG_STREAM'],
        create_log_group=True
    )
    app.logger.addHandler(handler)
    logging.getLogger('sqlalchemy.engine').addHandler(handler)

# Set log level from config
app.logger.setLevel(app.config['LOG_LEVEL'])

# Database connection management
def get_db_connection():
    try:
        connection = engine.connect()
        return connection
    except OperationalError as e:
        app.logger.error(f"Database connection error: {e}")
        raise
    except SQLAlchemyError as e:
        app.logger.error(f"SQLAlchemy error: {e}")
        raise

@app.route('/')
def index():
    houses = House.query.order_by(House.total_points.desc()).all()
    return render_template('index.html', houses=houses)

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
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
@limiter.limit("5 per minute")
def login():
    form = FlaskForm()
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                username = request.form['username'].strip()
                password = request.form['password']

                user = User.query.filter_by(username=username).first()
                if user and user.check_password(password):
                    login_user(user)
                    user.last_login = datetime.utcnow()  # Update last login time
                    db.session.commit()
                    log_activity(app, user.id, 'Login', 'Success')
                    flash('Welcome back, Dragon Climber!', 'success')
                    next_page = request.args.get('next')
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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def init_db():
    with app.app_context():
        db.create_all()
        # Create houses if they don't exist
        for house_name in app.config['HOUSES']:
            if not House.query.filter_by(name=house_name).first():
                house = House(name=house_name)
                db.session.add(house)
        try:
            db.session.commit()
        except Exception as e:
            app.logger.error(f"Error initializing database: {str(e)}")
            db.session.rollback()

@app.route('/health')
def health_check():
    try:
        # Check database connection
        with engine.connect() as connection:
            connection.execute("SELECT 1")
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        app.logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
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

# Initialize the database when the app is started
if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=app.config['DEBUG'])
