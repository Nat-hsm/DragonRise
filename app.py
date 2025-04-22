from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from datetime import datetime
from dotenv import load_dotenv
import os
from utils.security import init_security, PasswordManager, require_api_key
from utils.logging_config import LogConfig, log_activity

# Load environment variables
load_dotenv()

def check_environment_variables():
    required_vars = ['SECRET_KEY', 'API_KEY']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Add this after load_dotenv()
check_environment_variables()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///dragonrise.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)

# Initialize security features
csrf, limiter, limit_requests = init_security(app)

# Initialize logging
log_config = LogConfig(app)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    house = db.Column(db.String(20), nullable=False)
    total_flights = db.Column(db.Integer, default=0)
    total_points = db.Column(db.Integer, default=0)
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    logs = db.relationship('ClimbLog', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = PasswordManager.hash_password(password)

    def check_password(self, password):
        return PasswordManager.check_password(self.password_hash, password)

class House(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)
    total_points = db.Column(db.Integer, default=0)
    total_flights = db.Column(db.Integer, default=0)
    member_count = db.Column(db.Integer, default=0)

class ClimbLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    flights = db.Column(db.Integer, nullable=False)
    points = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

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

            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                log_activity(app, user.id, 'Login', 'Success')
                flash('Welcome back, Dragon Climber!', 'success')
                next_page = request.args.get('next')
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

@app.route('/log_climb', methods=['POST'])
@login_required
def log_climb():
    try:
        flights = int(request.form['flights'])
        if flights <= 0:
            flash('Please enter a valid number of flights', 'danger')
            return redirect(url_for('dashboard'))

        points = flights * 10

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
        houses = ['Black', 'Blue', 'Green', 'White', 'Gold', 'Purple']
        for house_name in houses:
            if not House.query.filter_by(name=house_name).first():
                house = House(name=house_name)
                db.session.add(house)
        try:
            db.session.commit()
        except Exception as e:
            print(f"Error initializing database: {str(e)}")
            db.session.rollback()

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
    return dict(get_house_count=get_house_count)

@app.teardown_appcontext
def shutdown_session(exception=None):
    db.session.remove()

if __name__ == '__main__':
    app.run(debug=True)
