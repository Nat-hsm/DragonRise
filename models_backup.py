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
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    
    # Relationships
    logs = db.relationship('ClimbLog', backref='user', lazy=True,
                         cascade='all, delete-orphan')
    standing_logs = db.relationship('StandingLog', backref='user', lazy=True,
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

    def __repr__(self):
        return f'<User {self.username}>'


class House(db.Model):
    """House model for group management"""
    __tablename__ = 'houses'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False, index=True)
    total_points = db.Column(db.Integer, default=0)
    total_flights = db.Column(db.Integer, default=0)
    total_standing_time = db.Column(db.Integer, default=0)  # Total standing time in minutes
    member_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
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
        self.last_activity = datetime.utcnow()

    def update_standing_time(self, minutes):
        """Update house standing time and points"""
        self.total_standing_time += minutes
        self.total_points += minutes  # 1 point per minute
        self.last_activity = datetime.utcnow()

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
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
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
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Achievement {self.name}>'


# User Achievement association table
user_achievements = db.Table('user_achievements',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('achievement_id', db.Integer, db.ForeignKey('achievements.id'), primary_key=True),
    db.Column('earned_at', db.DateTime, default=datetime.utcnow)
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
    """Get top users by points"""
    return User.query.order_by(User.total_points.desc()).limit(limit).all()


def get_house_rankings():
    """Get houses ranked by total points"""
    return House.query.order_by(House.total_points.desc()).all()


def get_user_stats(user_id):
    """Get detailed user statistics"""
    return {
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
            admin.set_password('admin123')
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
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