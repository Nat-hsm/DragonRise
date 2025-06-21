from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from utils.cognito import CognitoAuth

# Create extensions without initializing them
db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

# Make sure this code exists and is correct
cognito_auth = CognitoAuth()