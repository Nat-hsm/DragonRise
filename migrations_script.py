from app import app, db
from alembic import op
import sqlalchemy as sa

def upgrade_database():
    with app.app_context():
        # Add total_standing_time column to users table if it doesn't exist
        with db.engine.connect() as conn:
            # Check if column exists in users table
            result = conn.execute(sa.text(
                "SELECT COUNT(*) FROM pragma_table_info('users') WHERE name='total_standing_time'"
            )).scalar()
            
            if result == 0:
                print("Adding total_standing_time column to users table...")
                conn.execute(sa.text(
                    "ALTER TABLE users ADD COLUMN total_standing_time INTEGER DEFAULT 0"
                ))
            
            # Check if column exists in houses table
            result = conn.execute(sa.text(
                "SELECT COUNT(*) FROM pragma_table_info('houses') WHERE name='total_standing_time'"
            )).scalar()
            
            if result == 0:
                print("Adding total_standing_time column to houses table...")
                conn.execute(sa.text(
                    "ALTER TABLE houses ADD COLUMN total_standing_time INTEGER DEFAULT 0"
                ))
            
            # Check if standing_logs table exists
            result = conn.execute(sa.text(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='standing_logs'"
            )).scalar()
            
            if result == 0:
                print("Creating standing_logs table...")
                conn.execute(sa.text("""
                    CREATE TABLE standing_logs (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        minutes INTEGER NOT NULL,
                        points INTEGER NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        notes TEXT,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                """))
                
                # Create indexes for standing_logs
                conn.execute(sa.text(
                    "CREATE INDEX idx_standing_user_timestamp ON standing_logs (user_id, timestamp)"
                ))
                conn.execute(sa.text(
                    "CREATE INDEX idx_standing_timestamp ON standing_logs (timestamp)"
                ))
            
            print("Database schema updated successfully!")

if __name__ == "__main__":
    upgrade_database()