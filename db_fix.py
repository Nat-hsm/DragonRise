"""
Permanent fix for database connection issues in DragonRise
"""
import os
import sqlite3
import shutil
from datetime import datetime

def backup_database():
    """Create a backup of the existing database file"""
    # Check if database file exists
    if os.path.exists('dragonrise.db'):
        # Create backup with timestamp
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        backup_file = f'dragonrise.db.{timestamp}.bak'
        shutil.copy2('dragonrise.db', backup_file)
        print(f"Created database backup: {backup_file}")
        return True
    return False

def check_instance_directory():
    """Check if instance directory exists and create it if needed"""
    if not os.path.exists('instance'):
        os.makedirs('instance')
        print("Created instance directory")
    return True

def create_database_file():
    """Create a new empty database file"""
    # Create in root directory
    conn = sqlite3.connect('dragonrise.db')
    conn.close()
    print("Created empty database file: dragonrise.db")
    
    # Create in instance directory
    conn = sqlite3.connect('instance/dragonrise.db')
    conn.close()
    print("Created empty database file: instance/dragonrise.db")
    
    return True

def update_env_file():
    """Update .env file to use the correct database path"""
    if not os.path.exists('.env'):
        print("ERROR: .env file not found")
        return False
    
    # Read current .env file
    with open('.env', 'r') as f:
        lines = f.readlines()
    
    # Update DATABASE_URL line
    new_lines = []
    db_url_updated = False
    for line in lines:
        if line.startswith('DATABASE_URL='):
            new_lines.append('DATABASE_URL=sqlite:///dragonrise.db\n')
            db_url_updated = True
        else:
            new_lines.append(line)
    
    # Add DATABASE_URL if it doesn't exist
    if not db_url_updated:
        new_lines.append('DATABASE_URL=sqlite:///dragonrise.db\n')
    
    # Write updated .env file
    with open('.env', 'w') as f:
        f.writelines(new_lines)
    
    print("Updated DATABASE_URL in .env file")
    return True

def create_symlink():
    """Create a symlink from instance/dragonrise.db to dragonrise.db"""
    try:
        # Remove existing files first
        if os.path.exists('instance/dragonrise.db'):
            os.remove('instance/dragonrise.db')
        
        # Create a hard link (more compatible than symlink on Windows)
        shutil.copy2('dragonrise.db', 'instance/dragonrise.db')
        print("Created copy of database in instance directory")
        return True
    except Exception as e:
        print(f"Error creating database link: {e}")
        return False

if __name__ == "__main__":
    print("DragonRise Database Fix Tool")
    print("===========================")
    print()
    
    # Backup existing database
    backup_database()
    
    # Check instance directory
    check_instance_directory()
    
    # Create database file
    create_database_file()
    
    # Update .env file
    update_env_file()
    
    # Create symlink
    create_symlink()
    
    print()
    print("Database fix complete!")
    print("Run your application with: python run.py")
    print()
    print("If you still encounter database errors, try:")
    print("1. Delete dragonrise.db and instance/dragonrise.db")
    print("2. Run this script again")
    print("3. Run python run.py to initialize the database")