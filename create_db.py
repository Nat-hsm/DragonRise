from app import app, db
from models import User, House, ClimbLog, StandingLog, Achievement

with app.app_context():
    # Drop all tables
    db.drop_all()
    
    # Create all tables
    db.create_all()
    
    # Create houses
    houses = ['Black', 'Blue', 'Green', 'White', 'Gold', 'Purple']
    for house_name in houses:
        house = House(name=house_name)
        db.session.add(house)
    
    try:
        db.session.commit()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        db.session.rollback()