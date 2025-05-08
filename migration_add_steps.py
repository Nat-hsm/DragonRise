"""
Migration script to add steps-related columns and tables to the database
"""
from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        try:
            print("Starting migration to add steps columns...")
            
            # Add total_steps column to users table if it doesn't exist
            try:
                db.session.execute(text("ALTER TABLE users ADD COLUMN total_steps INTEGER DEFAULT 0"))
                print("Added total_steps column to users table")
            except Exception as e:
                print(f"Note: {str(e)}")
                print("Column may already exist or there was an error")
            
            # Add total_steps column to houses table if it doesn't exist
            try:
                db.session.execute(text("ALTER TABLE houses ADD COLUMN total_steps INTEGER DEFAULT 0"))
                print("Added total_steps column to houses table")
            except Exception as e:
                print(f"Note: {str(e)}")
                print("Column may already exist or there was an error")
            
            # Create step_logs table if it doesn't exist
            db.session.execute(text("""
                CREATE TABLE IF NOT EXISTS step_logs (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    steps INTEGER NOT NULL,
                    points INTEGER NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    notes VARCHAR(200),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """))
            print("Created step_logs table (if it didn't exist)")
            
            # Create indexes for step_logs table
            db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_step_user_timestamp ON step_logs (user_id, timestamp)"))
            db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_step_timestamp ON step_logs (timestamp)"))
            print("Created indexes for step_logs table")
            
            db.session.commit()
            print("Migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"Migration failed: {str(e)}")
            raise e

if __name__ == "__main__":
    migrate()