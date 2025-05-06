from app import app, db
from models import User
from utils.security import PasswordManager

with app.app_context():
    # First try to find admin
    admin = User.query.filter(User.username.ilike('Admin')).first()
    print(f"Admin exists: {admin is not None}")
    
    if admin:
        # Update existing admin password
        admin.set_password('123')
        admin.is_admin = True
        admin.house = 'Admin'
        db.session.commit()
        print("Admin user updated")
    else:
        # Create new admin
        admin = User(username='Admin', house='Admin', is_admin=True)
        admin.set_password('123')
        db.session.add(admin)
        db.session.commit()
        print("Admin user created")