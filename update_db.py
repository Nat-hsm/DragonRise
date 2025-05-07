"""
Database update script to add peak hour settings table
"""
from app import app, db
from datetime import time
from models import PeakHourSetting

def update_database():
    """Update database schema and add peak hour settings table"""
    with app.app_context():
        print("Creating peak_hour_settings table...")
        # Create the table
        db.create_all()
        
        # Check if we need to add default peak hours
        if PeakHourSetting.query.count() == 0:
            print("Adding default peak hour settings...")
            
            # Define default peak hours
            morning_peak = PeakHourSetting(
                name="Morning Peak",
                start_time=time(8, 45),
                end_time=time(9, 15),
                multiplier=2,
                is_active=True
            )
            
            lunch_peak = PeakHourSetting(
                name="Lunch Peak",
                start_time=time(11, 30),
                end_time=time(13, 0),
                multiplier=2,
                is_active=True
            )
            
            evening_peak = PeakHourSetting(
                name="Evening Peak",
                start_time=time(17, 30),
                end_time=time(18, 30),
                multiplier=2,
                is_active=True
            )
            
            db.session.add_all([morning_peak, lunch_peak, evening_peak])
            db.session.commit()
            print("Default peak hour settings added successfully!")
        else:
            print("Peak hour settings already exist, skipping defaults.")
        
        print("Database update completed successfully!")

if __name__ == "__main__":
    # Confirm before proceeding
    confirm = input("This will update the database schema. Continue? (y/n): ")
    if confirm.lower() == 'y':
        update_database()
    else:
        print("Operation cancelled.")