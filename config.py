import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Base configuration class"""
    
    # Flask Configuration
    SECRET_KEY = os.getenv('SECRET_KEY')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'pool_timeout': 30,
        'pool_recycle': 1800,
        'max_overflow': 10
    }
    
    # Security Configuration
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=60)
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour
    
    # Rate Limiting
    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    RATELIMIT_STORAGE_URL = os.getenv('RATELIMIT_STORAGE_URL', 'memory://')
    RATELIMIT_STRATEGY = 'fixed-window-elastic-expiry'
    
    # AWS Configuration
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    CLOUDWATCH_LOG_GROUP = 'DragonRise'
    CLOUDWATCH_LOG_STREAM = 'application-logs'
    
    # Application Configuration
    HOUSES = ['Black', 'Blue', 'Green', 'White', 'Gold', 'Purple']
    POINTS_PER_FLIGHT = 10
    MAX_FLIGHTS_PER_LOG = 100
    
    # Cache Configuration
    CACHE_TYPE = 'simple'
    CACHE_DEFAULT_TIMEOUT = 300
    
    # API Configuration
    API_KEY = os.getenv('API_KEY')
    API_RATE_LIMIT = "100 per day"


class ProductionConfig(Config):
    """Production configuration"""
    
    DEBUG = False
    TESTING = False
    
    # Enhanced security for production
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    
    # Production database settings
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,
        'pool_timeout': 30,
        'pool_recycle': 1800,
        'max_overflow': 20
    }
    
    # Production cache settings
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.getenv('REDIS_URL')
    
    # Production logging
    LOG_LEVEL = 'ERROR'
    
    # SSL Configuration
    SSL_REDIRECT = True
    
    @classmethod
    def init_app(cls, app):
        # Production-specific initialization
        # Log to stderr
        import logging
        from logging import StreamHandler
        file_handler = StreamHandler()
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)


class DevelopmentConfig(Config):
    """Development configuration"""
    
    DEBUG = True
    DEVELOPMENT = True
    
    # Development-specific settings
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = True
    
    # Development database settings
    SQLALCHEMY_TRACK_MODIFICATIONS = True
    
    # Development logging
    LOG_LEVEL = 'DEBUG'
    
    @classmethod
    def init_app(cls, app):
        # Development-specific initialization
        pass


class TestingConfig(Config):
    """Testing configuration"""
    
    TESTING = True
    DEBUG = True
    
    # Use SQLite for testing
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    
    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False
    
    # Testing-specific settings
    SERVER_NAME = 'localhost.localdomain'
    
    # Disable rate limiting for testing
    RATELIMIT_ENABLED = False
    
    @classmethod
    def init_app(cls, app):
        # Testing-specific initialization
        pass


class DockerConfig(ProductionConfig):
    """Docker configuration"""
    
    @classmethod
    def init_app(cls, app):
        ProductionConfig.init_app(app)
        
        # Log to stdout/stderr
        import logging
        from logging import StreamHandler
        file_handler = StreamHandler()
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)


def get_config():
    """Get configuration class based on environment"""
    config_map = {
        'development': DevelopmentConfig,
        'testing': TestingConfig,
        'production': ProductionConfig,
        'docker': DockerConfig,
        'default': DevelopmentConfig
    }
    
    env = os.getenv('FLASK_ENV', 'default')
    return config_map.get(env, DevelopmentConfig)


# Configuration validation
def validate_config(config):
    """Validate configuration settings"""
    required_settings = [
        'SECRET_KEY',
        'SQLALCHEMY_DATABASE_URI',
        'API_KEY'
    ]
    
    missing = [setting for setting in required_settings if not getattr(config, setting, None)]
    
    if missing:
        raise ValueError(f"Missing required configuration settings: {', '.join(missing)}")
    
    return True


# Example usage in app.py:
"""
from config import get_config, validate_config

config = get_config()
app.config.from_object(config)
validate_config(config)
config.init_app(app)
"""
