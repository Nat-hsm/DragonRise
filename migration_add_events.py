from app import app, db
from models import Event
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Create events table if it doesn't exist"""
    logger.info("Starting migration to add events table")
    
    with app.app_context():
        logger.info("Creating events table if it doesn't exist")
        # Create the events table
        db.create_all()
        logger.info("Events table created successfully")
    
    logger.info("Migration completed successfully")

if __name__ == "__main__":
    run_migration()