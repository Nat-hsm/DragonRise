from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import Index
from app import db

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
    join_date = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    logs = db.relationship('ClimbLog', backref='user', lazy=True,
                         cascade='all, delete-orphan')

    # Indexes
    __table_args__ = (
        Index('idx_user_username_house', 'username', 'house'),
        Index('idx_user_email_username', 'email', 'username'),
        Index('idx_user_house_points', 'house', 'total_points'),
    )

    def __init__(self, username, house, email=None):
        self.username = username
        self.house = house
        self.email = email

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

    def __repr__(self):
        return f'<User {self.username}>'


class House(db.Model):
    """House model for group management"""
    __tablename__ = 'houses'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False, index=True)
    total_points = db.Column(db.Integer, default=0)
    total_flights = db.Column(db.Integer, default=0)
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

    def __init__(self, user_id, flights):
        self.user_id = user_id
        self.flights = flights
        self.points = flights * 10

    @property
    def formatted_timestamp(self):
        """Return formatted timestamp"""
        return self.timestamp.strftime('%Y-%m-%d %H:%M:%S')

    def __repr__(self):
        return f'<ClimbLog {self.user_id} - {self.flights} flights>'


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
        'last_climb': ClimbLog.query.filter_by(user_id=user_id)
            .order_by(ClimbLog.timestamp.desc()).first()
    }
