import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime

class LogConfig:
    def __init__(self, app):
        self.app = app
        self.setup_logging()

    def setup_logging(self):
        # Create logs directory if it doesn't exist
        if not os.path.exists('logs'):
            os.makedirs('logs')

        # Set up file handlers for different log levels
        self.setup_error_logging()
        self.setup_access_logging()
        self.setup_security_logging()

    def setup_error_logging(self):
        # Use FileHandler instead of RotatingFileHandler on Windows to avoid file access issues
        if os.name == 'nt':  # Windows
            error_handler = logging.FileHandler('logs/error.log')
        else:
            error_handler = RotatingFileHandler(
                'logs/error.log',
                maxBytes=10240,
                backupCount=10
            )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(self.get_formatter())
        self.app.logger.addHandler(error_handler)

    def setup_access_logging(self):
        # Use FileHandler instead of RotatingFileHandler on Windows to avoid file access issues
        if os.name == 'nt':  # Windows
            access_handler = logging.FileHandler('logs/access.log')
        else:
            access_handler = RotatingFileHandler(
                'logs/access.log',
                maxBytes=10240,
                backupCount=10
            )
        access_handler.setLevel(logging.INFO)
        access_handler.setFormatter(self.get_formatter())
        self.app.logger.addHandler(access_handler)

    def setup_security_logging(self):
        # Use FileHandler instead of RotatingFileHandler on Windows to avoid file access issues
        if os.name == 'nt':  # Windows
            security_handler = logging.FileHandler('logs/security.log')
        else:
            security_handler = RotatingFileHandler(
                'logs/security.log',
                maxBytes=10240,
                backupCount=10
            )
        security_handler.setLevel(logging.WARNING)
        security_handler.setFormatter(self.get_formatter())
        self.app.logger.addHandler(security_handler)

    @staticmethod
    def get_formatter():
        return logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

def log_activity(app, user_id, action, status):
    """
    Log user activities
    """
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - User {user_id} - {action} - {status}"
    
    try:
        with open('logs/activity.log', 'a') as f:
            f.write(log_entry + '\n')
        
        # Only log important activities at INFO level to reduce log volume
        if action.startswith(('Login', 'Registration', 'Admin')):
            app.logger.info(log_entry)
    except Exception as e:
        app.logger.error(f"Failed to log activity: {str(e)}")