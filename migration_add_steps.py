"""
Migration script to add steps-related columns and tables to the database
"""
from app import app, db
from sqlalchemy import Column, Integer
from models import User, House, StepLog

def add_steps_columns():
    with app.app_context():
        # Check if total_steps column exists for User
        if not hasattr(User, 'total_steps'):
            db.engine.execute('ALTER TABLE users ADD COLUMN total_steps INTEGER DEFAULT 0')
            print("Added total_steps column to User model")
            
        # Check if total_steps column exists for House
        if not hasattr(House, 'total_steps'):
            db.engine.execute('ALTER TABLE houses ADD COLUMN total_steps INTEGER DEFAULT 0')
            print("Added total_steps column to House model")
            
        # Create step_logs table if it doesn't exist
        if not db.engine.has_table('step_logs'):
            StepLog.__table__.create(db.engine)
            print("Created step_logs table")
            
        db.session.commit()
        print("Database schema updated successfully for steps tracking")

if __name__ == '__main__':
    add_steps_columns()