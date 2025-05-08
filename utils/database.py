from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import OperationalError, SQLAlchemyError
import logging
import os

logger = logging.getLogger(__name__)

def setup_database(app, db):
    """Setup database connection with fallback to SQLite if needed"""
    try:
        # Get database URL from config
        db_url = app.config['SQLALCHEMY_DATABASE_URI']
        app.logger.info(f"Connecting to database: {db_url}")
        
        # Create engine with connection pooling
        engine_options = app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {})
        
        # Add connect_args for SQLite if needed
        if 'sqlite' in db_url:
            engine_options['connect_args'] = {"check_same_thread": False}
            
            # Extract file path from SQLite URL
            if db_url.startswith('sqlite:///'):
                db_file = db_url[10:]  # Remove 'sqlite:///'
                
                # Create directory if needed
                db_dir = os.path.dirname(db_file)
                if db_dir and not os.path.exists(db_dir):
                    os.makedirs(db_dir)
                    app.logger.info(f"Created database directory: {db_dir}")
        
        engine = create_engine(
            db_url,
            poolclass=QueuePool,
            **engine_options
        )
        
        # Test connection - FIXED: Use text() for raw SQL in SQLAlchemy 2.0+
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            app.logger.info("Database connection successful")
        
        return engine
    
    except OperationalError as e:
        app.logger.error(f"Database connection error: {str(e)}")
        
        # If we're in development and not already using SQLite, try SQLite fallback
        if app.config.get('DEBUG', False) and 'sqlite' not in db_url.lower():
            app.logger.warning("Attempting to use SQLite as fallback database")
            try:
                # Use SQLite as fallback
                sqlite_url = 'sqlite:///dragonrise.db'
                app.config['SQLALCHEMY_DATABASE_URI'] = sqlite_url
                
                # Create new engine with SQLite
                sqlite_engine = create_engine(
                    sqlite_url,
                    connect_args={"check_same_thread": False},
                )
                
                # Test SQLite connection - FIXED: Use text()
                with sqlite_engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                    app.logger.info("SQLite fallback connection successful")
                
                return sqlite_engine
            
            except Exception as sqlite_error:
                app.logger.error(f"SQLite fallback failed: {str(sqlite_error)}")
                raise
        else:
            raise
    
    except Exception as e:
        app.logger.error(f"Unexpected database error: {str(e)}")
        raise