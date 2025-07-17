from flask_login import UserMixin
from datetime import datetime, timezone, timedelta, time
from sqlalchemy import Index
from extensions import db  # Import from extensions instead of app

class User(UserMixin, db.Model):
    """User model for authentication and profile management"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    house = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True, index=True)
    total_flights = db.Column(db.Integer, default=0)
    total_points = db.Column(db.Integer, default=0)
    total_standing_time = db.Column(db.Integer, default=0)  # Total standing time in minutes
    total_steps = db.Column(db.Integer, default=0)  # Total steps count
    join_date = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    
    # Google Fit integration
    google_fit_token = db.Column(db.String(500), nullable=True)
    google_refresh_token = db.Column(db.String(500), nullable=True)
    google_token_expiry = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    logs = db.relationship('ClimbLog', backref='user', lazy=True,
                         cascade='all, delete-orphan')
    standing_logs = db.relationship('StandingLog', backref='user', lazy=True,
                                  cascade='all, delete-orphan')
    step_logs = db.relationship('StepLog', backref='user', lazy=True,
                              cascade='all, delete-orphan')
    achievements = db.relationship('Achievement', secondary='user_achievements',
                                lazy='subquery', backref=db.backref('users', lazy=True))

    # Indexes
    __table_args__ = (
        Index('idx_user_username_house', 'username', 'house'),
        Index('idx_user_email_username', 'email', 'username'),
        Index('idx_user_house_points', 'house', 'total_points'),
    )

    def __init__(self, username, house, email=None, is_admin=False):
        self.username = username
        self.house = house
        self.email = email
        self.is_admin = is_admin

    def set_password(self, password):
        """Set hashed password"""
        from utils.security import PasswordManager
        self.password_hash = PasswordManager.hash_password(password)

    def check_password(self, password):
        """Verify password"""
        from utils.security import PasswordManager
        return PasswordManager.check_password(self.password_hash, password)

    def update_points(self, flights):
        """Update user points and flights"""
        self.total_flights += flights
        self.total_points += flights * 10

    def update_standing_time(self, minutes):
        """Update user standing time"""
        self.total_standing_time += minutes
        # Add points for standing time (1 point per minute)
        self.total_points += minutes
        
    def update_steps(self, steps):
        """Update user steps and points"""
        self.total_steps += steps
        # Add points for steps (1 point per 100 steps)
        self.total_points += steps // 100

    def __repr__(self):
        return f'<User {self.username}>'

    # Add a method to get the user's house
    def get_house(self):
        return House.query.filter_by(name=self.house).first()


class House(db.Model):
    """House model for group management"""
    __tablename__ = 'houses'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False, index=True)
    total_points = db.Column(db.Integer, default=0)
    total_flights = db.Column(db.Integer, default=0)
    total_standing_time = db.Column(db.Integer, default=0)  # Total standing time in minutes
    total_steps = db.Column(db.Integer, default=0)  # Total steps count
    member_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    last_activity = db.Column(db.DateTime)

    # Indexes
    __table_args__ = (
        Index('idx_house_name_points', 'name', 'total_points'),
        Index('idx_house_points_members', 'total_points', 'member_count'),
    )

    def __init__(self, name):
        self.name = name

    def update_points(self, flights):
        """Update house points and flights"""
        self.total_flights += flights
        self.total_points += flights * 10
        self.last_activity = datetime.now(timezone.utc)

    def update_standing_time(self, minutes):
        """Update house standing time and points"""
        self.total_standing_time += minutes
        self.total_points += minutes  # 1 point per minute
        self.last_activity = datetime.now(timezone.utc)
        
    def update_steps(self, steps):
        """Update house steps and points"""
        # This will be used after migration adds total_steps column
        if hasattr(self, 'total_steps'):
            self.total_steps += steps
            self.total_points += steps // 100  # 1 point per 100 steps
            self.last_activity = datetime.now(timezone.utc)

    def add_member(self):
        """Increment member count"""
        self.member_count += 1

    def remove_member(self):
        """Decrement member count"""
        if self.member_count > 0:
            self.member_count -= 1

    def __repr__(self):
        return f'<House {self.name}>'


class ClimbLog(db.Model):
    """Climb log model for tracking user activities"""
    __tablename__ = 'climb_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    flights = db.Column(db.Integer, nullable=False)
    points = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    notes = db.Column(db.String(200))  # Optional notes for the climb

    # Indexes
    __table_args__ = (
        Index('idx_climb_user_timestamp', 'user_id', 'timestamp'),
        Index('idx_climb_timestamp', 'timestamp'),
    )

    def __init__(self, user_id, flights, points=None, notes=None):
        from flask import current_app
        
        self.user_id = user_id
        self.flights = flights
        
        if points is not None:
            self.points = points
        else:
            # Use config value if available, fallback to default of 10
            points_per_flight = current_app.config.get('POINTS_PER_FLIGHT', 10)
            self.points = flights * points_per_flight
        
        if notes:
            self.notes = notes

    @property
    def formatted_timestamp(self):
        """Return formatted timestamp in local time (UTC+8)"""
        # Convert UTC time to local time (UTC+8)
        local_time = self.timestamp + timedelta(hours=8)
        return local_time.strftime('%Y-%m-%d %H:%M:%S')

    def __repr__(self):
        return f'<ClimbLog {self.user_id} - {self.flights} flights>'


class StandingLog(db.Model):
    """Standing log model for tracking user standing time"""
    __tablename__ = 'standing_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    minutes = db.Column(db.Integer, nullable=False)  # Standing time in minutes
    points = db.Column(db.Integer, nullable=False)   # Points earned (1 per minute)
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    notes = db.Column(db.String(200))  # Optional notes

    # Indexes
    __table_args__ = (
        Index('idx_standing_user_timestamp', 'user_id', 'timestamp'),
        Index('idx_standing_timestamp', 'timestamp'),
    )

    def __init__(self, user_id, minutes, points=None, notes=None):
        self.user_id = user_id
        self.minutes = minutes
        self.points = points if points is not None else minutes  # Allow custom points for multipliers
        if notes:
            self.notes = notes

    @property
    def formatted_timestamp(self):
        """Return formatted timestamp in local time (UTC+8)"""
        # Convert UTC time to local time (UTC+8)
        local_time = self.timestamp + timedelta(hours=8)
        return local_time.strftime('%Y-%m-%d %H:%M:%S')

    def __repr__(self):
        return f'<StandingLog {self.user_id} - {self.minutes} minutes>'


class StepLog(db.Model):
    """Step log model for tracking user steps"""
    __tablename__ = 'step_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # FIXED
    steps = db.Column(db.Integer, nullable=False)
    points = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    source = db.Column(db.String(50), nullable=True)

    def __repr__(self):
        return f"<StepLog {self.id}: {self.steps} steps by user {self.user_id}>"


# Add Achievement model for future gamification
class Achievement(db.Model):
    """Achievement model for gamification"""
    __tablename__ = 'achievements'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    points_required = db.Column(db.Integer)
    flights_required = db.Column(db.Integer)
    icon = db.Column(db.String(100))  # Path to achievement icon
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Achievement {self.name}>'


# User Achievement association table
user_achievements = db.Table('user_achievements',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('achievement_id', db.Integer, db.ForeignKey('achievements.id'), primary_key=True),
    db.Column('earned_at', db.DateTime, default=datetime.now(timezone.utc))
)


def init_houses():
    """Initialize default houses"""
    default_houses = ['Black', 'Blue', 'Green', 'White', 'Gold', 'Purple']
    for house_name in default_houses:
        if not House.query.filter_by(name=house_name).first():
            house = House(name=house_name)
            db.session.add(house)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise e


def get_leaderboard(limit=10):
    """Get top users by points, excluding admins"""
    return User.query.filter_by(is_admin=False).order_by(User.total_points.desc()).limit(limit).all()


def get_house_rankings():
    """Get houses ranked by total points"""
    return House.query.order_by(House.total_points.desc()).all()


def get_user_stats(user_id):
    """Get detailed user statistics"""
    stats = {
        'total_flights': ClimbLog.query.with_entities(
            db.func.sum(ClimbLog.flights)
        ).filter_by(user_id=user_id).scalar() or 0,
        'total_points': ClimbLog.query.with_entities(
            db.func.sum(ClimbLog.points)
        ).filter_by(user_id=user_id).scalar() or 0,
        'climb_count': ClimbLog.query.filter_by(user_id=user_id).count(),
        'standing_time': StandingLog.query.with_entities(
            db.func.sum(StandingLog.minutes)
        ).filter_by(user_id=user_id).scalar() or 0,
        'standing_count': StandingLog.query.filter_by(user_id=user_id).count(),
        'last_climb': ClimbLog.query.filter_by(user_id=user_id)
            .order_by(ClimbLog.timestamp.desc()).first(),
        'last_standing': StandingLog.query.filter_by(user_id=user_id)
            .order_by(StandingLog.timestamp.desc()).first()
    }
    
    # Add step stats if the table exists
    try:
        stats['total_steps'] = StepLog.query.with_entities(
            db.func.sum(StepLog.steps)
        ).filter_by(user_id=user_id).scalar() or 0
        stats['steps_count'] = StepLog.query.filter_by(user_id=user_id).count()
        stats['last_steps'] = StepLog.query.filter_by(user_id=user_id) \
            .order_by(StepLog.timestamp.desc()).first()
    except Exception:
        # If step_logs table doesn't exist yet, set defaults
        stats['total_steps'] = 0
        stats['steps_count'] = 0
        stats['last_steps'] = None
    
    return stats


def init_admin():
    """Initialize or update admin user"""
    from utils.security import PasswordManager
    admin = User.query.filter_by(username='Admin').first()
    if not admin:
        admin = User.query.filter(User.username.ilike('Admin')).first()
        if admin:
            # Update existing admin
            admin.set_password('123')
            admin.is_admin = True
            admin.house = 'Admin'
            try:
                db.session.commit()
                return "updated"
            except Exception as e:
                db.session.rollback()
                raise e
        else:
            # Create new admin
            admin = User(username='Admin', house='Admin', is_admin=True)
            admin.set_password('123')
            db.session.add(admin)
            try:
                db.session.commit()
                return "created"
            except Exception as e:
                db.session.rollback()
                raise e
    return "exists"


class PeakHourSetting(db.Model):
    """Peak hour settings model for configurable peak hours"""
    __tablename__ = 'peak_hour_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)  # e.g., "Morning Peak", "Lunch Peak"
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    multiplier = db.Column(db.Integer, default=2)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))
    
    def __init__(self, name, start_time, end_time, multiplier=2, is_active=True):
        self.name = name
        self.start_time = start_time
        self.end_time = end_time
        self.multiplier = multiplier
        self.is_active = is_active
    
    @property
    def formatted_time_range(self):
        """Return formatted time range string"""
        start_str = self.start_time.strftime('%I:%M%p').lstrip('0').lower()
        end_str = self.end_time.strftime('%I:%M%p').lstrip('0').lower()
        return f"{start_str}-{end_str}"
    
    def __repr__(self):
        return f'<PeakHourSetting {self.name}: {self.formatted_time_range}>'


def get_peak_hour_settings():
    """Get all active peak hour settings"""
    return PeakHourSetting.query.order_by(PeakHourSetting.start_time).all()


def init_peak_hours():
    """Initialize default peak hour settings if none exist"""
    if PeakHourSetting.query.count() == 0:
        # Define default peak hours
        morning_peak = PeakHourSetting(
            name="Morning Peak",
            start_time=time(8, 45),
            end_time=time(9, 15),
            multiplier=2,
            is_active=True
        )
        
        lunch_peak = PeakHourSetting(
            name="Lunch Peak",
            start_time=time(11, 30),
            end_time=time(13, 0),
            multiplier=2,
            is_active=True
        )
        
        evening_peak = PeakHourSetting(
            name="Evening Peak",
            start_time=time(17, 30),
            end_time=time(18, 30),
            multiplier=2,
            is_active=True
        )
        
        db.session.add_all([morning_peak, lunch_peak, evening_peak])
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            raise e


class Event(db.Model):
    """Event model for time-limited competitions"""
    __tablename__ = 'events'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))
    
    def __init__(self, name, description, start_date, end_date, is_active=False):
        self.name = name
        self.description = description
        self.start_date = start_date
        self.end_date = end_date
        self.is_active = is_active
        
    def __repr__(self):
        return f'<Event {self.name} ({self.start_date.strftime("%Y-%m-%d")} to {self.end_date.strftime("%Y-%m-%d")})>'

def get_active_event():
    """Get the currently active event if any"""
    return Event.query.filter_by(is_active=True).first()

def is_in_active_event(current_time=None):
    """Check if the given datetime is within an active event period"""
    if current_time is None:
        current_time = datetime.now(timezone.utc)
    elif current_time.tzinfo is None:
        # Ensure the datetime is timezone-aware
        current_time = current_time.replace(tzinfo=timezone.utc)
    
    event = Event.query.filter(
        Event.start_date <= current_time,
        Event.end_date >= current_time,
        Event.is_active == True  # FIXED: Changed from active to is_active
    ).first()
    
    return event is not None

def get_event_points(user_id=None, house_name=None):
    """
    Calculate points earned during the active event period
    Can be used for either a user or a house
    
    Args:
        user_id: User ID (optional)
        house_name: House name (optional)
        
    Returns:
        dict: Dictionary of points data during the event period
    """
    event = get_active_event()
    if not event:
        return None  # No active event
    
    # Prepare result structure
    result = {
        'total_points': 0,
        'total_flights': 0,
        'total_standing_time': 0,
        'total_steps': 0,
        'event_name': event.name,
        'start_date': event.start_date,
        'end_date': event.end_date
    }
    
    # Get climbing points during event period
    if user_id:
        climb_logs = ClimbLog.query.filter(
            ClimbLog.user_id == user_id,
            ClimbLog.timestamp >= event.start_date,
            ClimbLog.timestamp <= event.end_date
        ).all()
    elif house_name:
        # For house, get all users in house
        user_ids = [user.id for user in User.query.filter_by(house=house_name).all()]
        if not user_ids:
            return result
            
        climb_logs = ClimbLog.query.filter(
            ClimbLog.user_id.in_(user_ids),
            ClimbLog.timestamp >= event.start_date,
            ClimbLog.timestamp <= event.end_date
        ).all()
    else:
        return result
    
    # Sum up climbing activity
    for log in climb_logs:
        result['total_flights'] += log.flights
        result['total_points'] += log.points
    
    # Get standing time points during event period
    if user_id:
        standing_logs = StandingLog.query.filter(
            StandingLog.user_id == user_id,
            StandingLog.timestamp >= event.start_date,
            StandingLog.timestamp <= event.end_date
        ).all()
    elif house_name:
        standing_logs = StandingLog.query.filter(
            StandingLog.user_id.in_(user_ids),
            StandingLog.timestamp >= event.start_date,
            StandingLog.timestamp <= event.end_date
        ).all()
    
    # Sum up standing time activity
    for log in standing_logs:
        result['total_standing_time'] += log.minutes
        result['total_points'] += log.points
    
    # Get steps during event period
    if hasattr(ClimbLog, 'steps'):  # Check if steps feature is available
        if user_id:
            steps_logs = StepLog.query.filter(
                StepLog.user_id == user_id,
                StepLog.timestamp >= event.start_date,
                StepLog.timestamp <= event.end_date
            ).all()
        elif house_name:
            steps_logs = StepLog.query.filter(
                StepLog.user_id.in_(user_ids),
                StepLog.timestamp >= event.start_date,
                StepLog.timestamp <= event.end_date
            ).all()
        
        # Sum up steps activity
        for log in steps_logs:
            result['total_steps'] += log.steps
            result['total_points'] += log.points
    
    return result

def should_award_points():
    """
    Determine whether points should be awarded based on active events
    
    Returns:
        bool: True if points should be awarded, False otherwise
    """
    # If there's no active event, always award points
    active_event = get_active_event()
    if not active_event:
        return True
        
    # If there is an active event, check if we're within its timeframe
    current_time = datetime.now(timezone.utc)
    return is_in_active_event(current_time)