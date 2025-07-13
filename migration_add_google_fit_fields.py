from app import app, db
from sqlalchemy import text, inspect
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Add Google Fit fields to User model"""
    logger.info("Starting migration to add Google Fit fields to User model")
    
    with app.app_context():
        # Get the actual table names from SQLite
        inspector = inspect(db.engine)
        all_tables = inspector.get_table_names()
        logger.info(f"Found tables: {all_tables}")
        
        # Determine actual table names
        user_table = next((t for t in all_tables if t.lower().endswith('user') or t.lower().endswith('users')), 'users')
        step_log_table = next((t for t in all_tables if t.lower().endswith('steplog') or t.lower().endswith('step_logs')), 'step_logs')
        
        logger.info(f"Using table names: user_table={user_table}, step_log_table={step_log_table}")
        
        # Check if columns exist first
        columns_to_add = [
            ('google_fit_token', 'VARCHAR(500)'),
            ('google_refresh_token', 'VARCHAR(500)'),
            ('google_token_expiry', 'DATETIME')
        ]
        
        connection = db.engine.connect()
        
        # Add columns to User table
        for column_name, column_type in columns_to_add:
            try:
                # Check if column exists first to avoid errors
                result = connection.execute(text(f"SELECT * FROM pragma_table_info('{user_table}') WHERE name='{column_name}'"))
                if not result.fetchone():
                    connection.execute(text(f"ALTER TABLE {user_table} ADD COLUMN {column_name} {column_type}"))
                    logger.info(f"Added column {column_name} to User model")
                else:
                    logger.info(f"Column {column_name} already exists in User model")
            except Exception as e:
                logger.error(f"Error adding column {column_name}: {str(e)}")
        
        # Add source column to StepLog table
        try:
            result = connection.execute(text(f"SELECT * FROM pragma_table_info('{step_log_table}') WHERE name='source'"))
            if not result.fetchone():
                connection.execute(text(f"ALTER TABLE {step_log_table} ADD COLUMN source VARCHAR(50)"))
                logger.info(f"Added source column to StepLog model")
            else:
                logger.info(f"Source column already exists in StepLog model")
        except Exception as e:
            logger.error(f"Error adding source column to StepLog: {str(e)}")
        
        logger.info("Migration completed successfully")

if __name__ == "__main__":
    run_migration()