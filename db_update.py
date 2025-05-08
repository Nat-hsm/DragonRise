import sqlite3
from app import app, db
from models import init_admin

def update_database():
    print("Updating database schema...")
    conn = sqlite3.connect('instance/dragonrise.db')
    cursor = conn.cursor()
    
    # Check if is_admin column exists
    cursor.execute("PRAGMA table_info(users);")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'is_admin' not in columns:
        print("Adding is_admin column to users table")
        cursor.execute('ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0')
        conn.commit()
    
    conn.close()
    print("Schema update complete")

if __name__ == '__main__':
    update_database()
    
    # Create admin user
    with app.app_context():
        print("Creating admin user...")
        result = init_admin()
        if result:
            print("Admin user created successfully")
        else:
            print("Admin user already exists")