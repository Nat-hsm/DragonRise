import os
import sqlite3
from app import app, db
from models import User, House, ClimbLog, StandingLog, Achievement

def reset_database():
    """
    Reset the database by dropping and recreating all tables.
    This ensures the schema matches the current model definitions.
    """
    with app.app_context():
        print("Dropping all tables...")
        db.drop_all()
        
        print("Creating all tables...")
        db.create_all()
        
        print("Initializing houses...")
        houses = ['Black', 'Blue', 'Green', 'White', 'Gold', 'Purple']
        for house_name in houses:
            house = House(name=house_name)
            db.session.add(house)
        
        print("Creating admin user...")
        admin = User(username='Admin', house='Admin', is_admin=True)
        admin.set_password('admin123')
        db.session.add(admin)
        
        try:
            db.session.commit()
            print("Database reset successfully!")
            return True
        except Exception as e:
            db.session.rollback()
            print(f"Error resetting database: {str(e)}")
            return False

if __name__ == "__main__":
    # Check if database file exists
    db_path = os.path.join('instance', 'dragonrise.db')
    if os.path.exists(db_path):
        print(f"Found existing database at {db_path}")
    else:
        print(f"No existing database found at {db_path}")
    
    # Confirm before proceeding
    confirm = input("This will reset the database and delete all data. Continue? (y/n): ")
    if confirm.lower() == 'y':
        success = reset_database()
        if success:
            print("Database has been reset with the correct schema.")
        else:
            print("Failed to reset database.")
    else:
        print("Operation cancelled.")