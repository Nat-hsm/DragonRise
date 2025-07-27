#!/bin/bash
# Complete reset and redeploy script for DragonRise application

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting complete reset and redeployment of DragonRise...${NC}"

# Check if PEM key exists
if [ ! -f "$PEM_KEY" ]; then
    echo -e "${RED}PEM key not found at $PEM_KEY${NC}"
    exit 1
fi

# Ensure PEM key has correct permissions
chmod 400 "$PEM_KEY"

# Create a comprehensive cleanup script for the EC2 instance
cat > /tmp/deep_cleanup.sh << 'EOF'
#!/bin/bash
# Comprehensive cleanup script for DragonRise

echo "Starting comprehensive cleanup..."

# Stop all related services
echo "Stopping services..."
sudo systemctl stop dragonrise
sudo systemctl stop nginx

# Backup important data
echo "Creating backups..."
TIMESTAMP=$(date +"%Y%m%d%H%M%S")
BACKUP_DIR="/home/ec2-user/backups/$TIMESTAMP"
mkdir -p $BACKUP_DIR

# Backup database
if [ -f "/home/ec2-user/DragonRise/dragonrise.db" ]; then
    cp /home/ec2-user/DragonRise/dragonrise.db $BACKUP_DIR/
    echo "Database backed up"
fi

# Backup environment files
if [ -f "/home/ec2-user/DragonRise/.env" ]; then
    cp /home/ec2-user/DragonRise/.env $BACKUP_DIR/
    echo "Environment file backed up"
fi

# Remove all application files except backups and venv
echo "Removing application files..."
find /home/ec2-user/DragonRise -mindepth 1 -not -path "/home/ec2-user/DragonRise/venv*" -not -path "/home/ec2-user/backups*" -delete

# Clean Python cache across the system
echo "Cleaning Python cache..."
find /home/ec2-user/DragonRise -name "*.pyc" -delete
find /home/ec2-user/DragonRise -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Clear logs
echo "Clearing log files..."
sudo truncate -s 0 /var/log/dragonrise/error.log
sudo truncate -s 0 /var/log/dragonrise/access.log
sudo truncate -s 0 /var/log/dragonrise/wsgi.log
sudo truncate -s 0 /var/log/nginx/error.log
sudo truncate -s 0 /var/log/nginx/access.log

# Ensure required directories exist with proper permissions
echo "Creating required directories..."
mkdir -p /home/ec2-user/DragonRise/instance
mkdir -p /home/ec2-user/DragonRise/templates
mkdir -p /home/ec2-user/DragonRise/static/css
mkdir -p /home/ec2-user/DragonRise/static/js
mkdir -p /home/ec2-user/DragonRise/static/uploads

# Set correct ownership
echo "Setting proper permissions..."
sudo chown -R ec2-user:ec2-user /home/ec2-user/DragonRise
sudo chmod -R 755 /home/ec2-user/DragonRise

# Check and create log directories if they don't exist
if [ ! -d "/var/log/dragonrise" ]; then
    sudo mkdir -p /var/log/dragonrise
    sudo chown -R ec2-user:ec2-user /var/log/dragonrise
    sudo chmod -R 755 /var/log/dragonrise
fi

# Restore backed up database if needed
if [ -f "$BACKUP_DIR/dragonrise.db" ]; then
    cp $BACKUP_DIR/dragonrise.db /home/ec2-user/DragonRise/
    echo "Database restored from backup"
fi

# Restore environment file if needed
if [ -f "$BACKUP_DIR/.env" ]; then
    cp $BACKUP_DIR/.env /home/ec2-user/DragonRise/
    echo "Environment file restored from backup"
fi

echo "Comprehensive cleanup completed successfully"
EOF

# Upload and execute the cleanup script
echo -e "${YELLOW}Uploading and executing comprehensive cleanup script...${NC}"
scp -i "$PEM_KEY" /tmp/deep_cleanup.sh "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod +x /tmp/deep_cleanup.sh && /tmp/deep_cleanup.sh"

# Copy app.py to app_fixed.py locally before uploading
echo -e "${GREEN}Preparing app_fixed.py from app.py...${NC}"
cp app.py app_fixed.py

# Create an updated gunicorn configuration file
cat > /tmp/gunicorn.conf.py << 'EOF'
"""Gunicorn configuration file with optimized settings"""
import multiprocessing

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes - using fewer workers for stability
workers = 2  # Fixed at 2 workers instead of dynamic calculation
worker_class = 'sync'
worker_connections = 1000
timeout = 60  # Increased timeout
keepalive = 2

# Prevent memory leaks
max_requests = 1000
max_requests_jitter = 200

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None

# Logging
errorlog = '/var/log/dragonrise/error.log'
accesslog = '/var/log/dragonrise/access.log'
loglevel = 'info'
EOF

# Create a robust WSGI file with better error handling
cat > /tmp/wsgi.py << 'EOF'
"""
WSGI file for DragonRise application with error handling
"""
import logging
import sys
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/var/log/dragonrise/wsgi.log')
    ]
)

# Log startup information
logging.info("WSGI file loading...")
logging.info(f"Python version: {sys.version}")
logging.info(f"Python path: {sys.path}")

try:
    # Import the Flask application
    from app_fixed import app as application
    logging.info("Successfully imported app_fixed application")
except Exception as e:
    # Log import errors in detail
    logging.error(f"Failed to import app_fixed: {str(e)}")
    logging.error(traceback.format_exc())
    
    # Create a minimal fallback application
    from flask import Flask
    application = Flask(__name__)
    
    @application.route('/')
    def index():
        return "Application Error: The DragonRise application failed to load."

# This is for local development only
if __name__ == "__main__":
    application.run()
EOF

# Create an updated systemd service file
cat > /tmp/dragonrise.service << 'EOF'
[Unit]
Description=DragonRise Gunicorn Service
After=network.target

[Service]
User=ec2-user
Group=ec2-user
WorkingDirectory=/home/ec2-user/DragonRise
Environment="PATH=/home/ec2-user/DragonRise/venv/bin"
EnvironmentFile=/home/ec2-user/DragonRise/.env
ExecStart=/home/ec2-user/DragonRise/venv/bin/gunicorn --config /home/ec2-user/DragonRise/gunicorn.conf.py wsgi:application
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Upload the updated configuration files
echo -e "${YELLOW}Uploading configuration files...${NC}"
scp -i "$PEM_KEY" /tmp/gunicorn.conf.py "$EC2_HOST:$APP_DIR/"
scp -i "$PEM_KEY" /tmp/wsgi.py "$EC2_HOST:$APP_DIR/"
scp -i "$PEM_KEY" /tmp/dragonrise.service "$EC2_HOST:/tmp/"

# Install the service file
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo cp /tmp/dragonrise.service /etc/systemd/system/"

# Update the rsync command to exclude static/uploads directory
echo -e "${YELLOW}Uploading entire application...${NC}"
rsync -avz --delete --exclude 'venv/' --exclude '.git/' --exclude '__pycache__/' \
    --exclude '*.pyc' --exclude '.env.root' --exclude '.env.production' \
    --exclude 'dragonrise.db.*' --exclude 'archived/' \
    --exclude 'static/uploads/' \
    -e "ssh -i $PEM_KEY" . "$EC2_HOST:$APP_DIR/"

# Create a script to restore AWS credentials if they are missing
cat > /tmp/restore_aws_creds.sh << 'EOF'
#!/bin/bash
# Check and restore AWS credentials

# Check if .env file has AWS credentials
if [ -f "/home/ec2-user/DragonRise/.env" ]; then
    if ! grep -q "AWS_ACCESS_KEY_ID" /home/ec2-user/DragonRise/.env; then
        echo "AWS credentials missing in .env file, checking backups..."
        
        # Look for latest backup with .env file
        LATEST_BACKUP=$(find /home/ec2-user/backups -name ".env" -type f | sort -r | head -n 1)
        
        if [ -n "$LATEST_BACKUP" ]; then
            echo "Found backup .env at $LATEST_BACKUP"
            
            # Extract AWS credentials
            AWS_ACCESS_KEY_ID=$(grep "AWS_ACCESS_KEY_ID" "$LATEST_BACKUP" | cut -d'=' -f2)
            AWS_SECRET_ACCESS_KEY=$(grep "AWS_SECRET_ACCESS_KEY" "$LATEST_BACKUP" | cut -d'=' -f2)
            AWS_REGION=$(grep "AWS_REGION" "$LATEST_BACKUP" | cut -d'=' -f2)
            
            if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
                echo "Restoring AWS credentials to .env file"
                echo "" >> /home/ec2-user/DragonRise/.env
                echo "# AWS Configuration" >> /home/ec2-user/DragonRise/.env
                echo "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID" >> /home/ec2-user/DragonRise/.env
                echo "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY" >> /home/ec2-user/DragonRise/.env
                echo "AWS_REGION=$AWS_REGION" >> /home/ec2-user/DragonRise/.env
                echo "AWS credentials restored"
            else
                echo "Could not extract AWS credentials from backup"
            fi
        else
            echo "No backup .env file found"
        fi
    else
        echo "AWS credentials already present in .env file"
    fi
else
    echo ".env file not found"
fi

# Create AWS credential directory if it doesn't exist
mkdir -p ~/.aws

# Set proper permissions for AWS credentials
if [ -f ~/.aws/credentials ]; then
    chmod 600 ~/.aws/credentials
fi

if [ -f ~/.aws/config ]; then
    chmod 600 ~/.aws/config
fi
EOF

# Upload and execute the AWS credentials restoration script
echo -e "${YELLOW}Checking and restoring AWS credentials...${NC}"
scp -i "$PEM_KEY" /tmp/restore_aws_creds.sh "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod +x /tmp/restore_aws_creds.sh && /tmp/restore_aws_creds.sh"

# Add this after your AWS credentials restoration section
# Create a script to fix Cognito redirect URIs in .env file
cat > /tmp/fix_cognito_redirect.sh << 'EOF'
#!/bin/bash
# Fix Cognito redirect URIs in .env file

ENV_FILE="/home/ec2-user/DragonRise/.env"

if [ -f "$ENV_FILE" ]; then
    echo "Checking Cognito redirect URIs in .env file..."
    
    # Check if the redirect URI is pointing to localhost or 127.0.0.1
    if grep -q "COGNITO_REDIRECT_URI=http://127.0.0.1" "$ENV_FILE" || \
       grep -q "COGNITO_REDIRECT_URI=https://127.0.0.1" "$ENV_FILE" || \
       grep -q "COGNITO_REDIRECT_URI=http://localhost" "$ENV_FILE" || \
       grep -q "COGNITO_REDIRECT_URI=https://localhost" "$ENV_FILE"; then
        
        echo "Found local development redirect URI in .env file. Updating to production URL..."
        
        # Replace the redirect URI with the production URL
        sed -i 's|COGNITO_REDIRECT_URI=http://127.0.0.1:[0-9]*/auth/callback|COGNITO_REDIRECT_URI=https://dragonrise.pro/auth/callback|g' "$ENV_FILE"
        sed -i 's|COGNITO_REDIRECT_URI=https://127.0.0.1:[0-9]*/auth/callback|COGNITO_REDIRECT_URI=https://dragonrise.pro/auth/callback|g' "$ENV_FILE"
        sed -i 's|COGNITO_REDIRECT_URI=http://localhost:[0-9]*/auth/callback|COGNITO_REDIRECT_URI=https://dragonrise.pro/auth/callback|g' "$ENV_FILE"
        sed -i 's|COGNITO_REDIRECT_URI=https://localhost:[0-9]*/auth/callback|COGNITO_REDIRECT_URI=https://dragonrise.pro/auth/callback|g' "$ENV_FILE"
        
        # If no match was found, add the correct redirect URI
        if ! grep -q "COGNITO_REDIRECT_URI=https://dragonrise.pro/auth/callback" "$ENV_FILE"; then
            echo "COGNITO_REDIRECT_URI=https://dragonrise.pro/auth/callback" >> "$ENV_FILE"
            echo "Added production redirect URI to .env file"
        else
            echo "Production redirect URI already exists in .env file"
        fi
        
        echo "Cognito redirect URI updated to production URL"
    else
        echo "Checking if production redirect URI exists..."
        if ! grep -q "COGNITO_REDIRECT_URI=" "$ENV_FILE"; then
            echo "COGNITO_REDIRECT_URI=https://dragonrise.pro/auth/callback" >> "$ENV_FILE"
            echo "Added production redirect URI to .env file"
        else
            echo "Redirect URI already exists in .env file"
        fi
    fi
    
    # Also check COGNITO_DOMAIN format
    if grep -q "COGNITO_DOMAIN=us-east-14qwsyldo1" "$ENV_FILE"; then
        echo "Cognito domain appears to be in the correct format"
    else
        echo "Checking and fixing Cognito domain format..."
        # If the domain is not in the correct format, update it
        if grep -q "COGNITO_DOMAIN=" "$ENV_FILE"; then
            sed -i 's|COGNITO_DOMAIN=.*|COGNITO_DOMAIN=us-east-14qwsyldo1|g' "$ENV_FILE"
            echo "Updated Cognito domain to correct format"
        else
            echo "COGNITO_DOMAIN=us-east-14qwsyldo1" >> "$ENV_FILE"
            echo "Added Cognito domain to .env file"
        fi
    fi

    echo "Cognito configuration in .env file verified and updated if needed"
else
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi
EOF

# Upload and execute the Cognito redirect URI fix script
echo -e "${YELLOW}Fixing Cognito redirect URIs...${NC}"
scp -i "$PEM_KEY" /tmp/fix_cognito_redirect.sh "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod +x /tmp/fix_cognito_redirect.sh && /tmp/fix_cognito_redirect.sh"

# Restart the DragonRise service to apply the Cognito changes
echo -e "${GREEN}Applying Cognito configuration changes...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl restart dragonrise"

# Create a script to verify and update Cognito app client settings
cat > /tmp/fix_cognito_client.sh << 'EOF'
#!/bin/bash
# Fix Cognito app client configuration in AWS

# Load AWS credentials from .env file
ENV_FILE="/home/ec2-user/DragonRise/.env"
if [ -f "$ENV_FILE" ]; then
    # Source the .env file to get AWS credentials
    export $(grep -v '^#' $ENV_FILE | xargs)
    
    echo "Checking Cognito app client configuration..."
    
    # Get the Cognito client ID and user pool ID from .env
    CLIENT_ID=$(grep "COGNITO_CLIENT_ID" $ENV_FILE | cut -d'=' -f2)
    USER_POOL_ID=$(grep "COGNITO_USER_POOL_ID" $ENV_FILE | cut -d'=' -f2)
    
    if [ -z "$CLIENT_ID" ] || [ -z "$USER_POOL_ID" ]; then
        echo "Error: Could not find Cognito client ID or user pool ID in .env file"
        exit 1
    fi
    
    echo "Using Cognito client ID: $CLIENT_ID"
    echo "Using user pool ID: $USER_POOL_ID"
    
    # Update the callback URL in Cognito app client
    echo "Updating callback URL in Cognito app client..."
    aws cognito-idp update-user-pool-client \
        --user-pool-id $USER_POOL_ID \
        --client-id $CLIENT_ID \
        --callback-urls "https://dragonrise.pro/auth/callback" \
        --logout-urls "https://dragonrise.pro/" \
        --allowed-o-auth-flows "code" \
        --allowed-o-auth-scopes "email" "openid" "profile" \
        --allowed-o-auth-flows-user-pool-client \
        --supported-identity-providers "COGNITO"
    
    if [ $? -eq 0 ]; then
        echo "Successfully updated Cognito app client configuration"
    else
        echo "Failed to update Cognito app client configuration"
        
        # If direct update fails, provide instructions
        echo "
MANUAL STEPS TO FIX COGNITO:
1. Log in to AWS Console
2. Go to Amazon Cognito > User Pools
3. Select your user pool (ID: $USER_POOL_ID)
4. Go to 'App integration' > 'App client settings'
5. For the client with ID $CLIENT_ID:
   - Add 'https://dragonrise.pro/auth/callback' to 'Callback URL(s)'
   - Add 'https://dragonrise.pro/' to 'Sign out URL(s)'
   - Ensure 'Authorization code grant' is selected under 'Allowed OAuth Flows'
   - Ensure 'email', 'openid', and 'profile' are selected under 'Allowed OAuth Scopes'
6. Click 'Save changes'
"
    fi
    
    # Make sure AWS CLI is configured with the correct region
    echo "Making sure AWS CLI is using the correct region..."
    AWS_REGION=$(grep "AWS_REGION" $ENV_FILE | cut -d'=' -f2)
    if [ -n "$AWS_REGION" ]; then
        aws configure set default.region $AWS_REGION
        echo "AWS region set to $AWS_REGION"
    fi
else
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi
EOF

# Upload and execute the Cognito app client fix script
echo -e "${YELLOW}Fixing Cognito app client configuration...${NC}"
scp -i "$PEM_KEY" /tmp/fix_cognito_client.sh "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod +x /tmp/fix_cognito_client.sh && /tmp/fix_cognito_client.sh"

# Also create a double-check script for Cognito domain format
cat > /tmp/verify_cognito_domain.sh << 'EOF'
#!/bin/bash
# Verify and fix the Cognito domain format

ENV_FILE="/home/ec2-user/DragonRise/.env"
if [ -f "$ENV_FILE" ]; then
    echo "Verifying Cognito domain format..."
    
    # Get the current COGNITO_DOMAIN value
    COGNITO_DOMAIN=$(grep "COGNITO_DOMAIN" $ENV_FILE | cut -d'=' -f2)
    
    # Check if it contains the full domain path
    if [[ "$COGNITO_DOMAIN" == *".auth."*".amazoncognito.com"* ]]; then
        echo "Cognito domain is in the full URL format. Extracting prefix..."
        # Extract the prefix (e.g., "us-east-14qwsyldo1" from "us-east-14qwsyldo1.auth.us-east-1.amazoncognito.com")
        PREFIX=$(echo $COGNITO_DOMAIN | cut -d'.' -f1)
        echo "Extracted prefix: $PREFIX"
        
        # Update the .env file with just the prefix
        sed -i "s|COGNITO_DOMAIN=.*|COGNITO_DOMAIN=$PREFIX|g" $ENV_FILE
        echo "Updated Cognito domain to use prefix only: $PREFIX"
    else
        echo "Cognito domain is already in the correct format: $COGNITO_DOMAIN"
    fi
    
    # Make sure the AWS_REGION is correctly set
    AWS_REGION=$(grep "AWS_REGION" $ENV_FILE | cut -d'=' -f2)
    if [ -z "$AWS_REGION" ]; then
        echo "AWS_REGION not found in .env file. Adding default value 'us-east-1'"
        echo "AWS_REGION=us-east-1" >> $ENV_FILE
    else
        echo "AWS_REGION is set to: $AWS_REGION"
    fi
else
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi
EOF

# Upload and execute the Cognito domain verification script
echo -e "${YELLOW}Verifying Cognito domain format...${NC}"
scp -i "$PEM_KEY" /tmp/verify_cognito_domain.sh "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod +x /tmp/verify_cognito_domain.sh && /tmp/verify_cognito_domain.sh"

# Restart the DragonRise service to apply all changes
echo -e "${GREEN}Applying all Cognito configuration changes...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl restart dragonrise"

# Set proper permissions on the server
echo -e "${YELLOW}Setting proper permissions...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod -R 755 $APP_DIR && chmod 644 $APP_DIR/*.py && chmod 644 $APP_DIR/gunicorn.conf.py"

# Verify file structure
echo -e "${YELLOW}Verifying file structure...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "ls -la $APP_DIR"

# Create a script to verify the wsgi file and fix common issues
cat > /tmp/verify_wsgi.py << 'EOF'
#!/usr/bin/env python3
"""
Verify that the wsgi.py file can be imported correctly
"""
import os
import sys
import importlib
import traceback

def verify_wsgi():
    """Check if wsgi.py can be imported"""
    print("WSGI verification started")
    print(f"Python version: {sys.version}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    
    # Make sure the current directory is in the path
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
        print(f"Added current directory to Python path")
    
    try:
        # Try to import the wsgi module
        import wsgi
        print("Successfully imported wsgi module")
        
        # Check if application exists
        if hasattr(wsgi, 'application'):
            print("Found application in wsgi module")
            return True
        else:
            print("ERROR: No application found in wsgi module")
            return False
            
    except Exception as e:
        print(f"ERROR importing wsgi: {str(e)}")
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = verify_wsgi()
    sys.exit(0 if success else 1)
EOF

# Upload and run the wsgi verification script
echo -e "${YELLOW}Verifying WSGI configuration...${NC}"
scp -i "$PEM_KEY" /tmp/verify_wsgi.py "$EC2_HOST:$APP_DIR/"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && chmod +x verify_wsgi.py && python3 verify_wsgi.py"

# Create a script to setup and update the virtual environment
cat > /tmp/setup_venv.sh << 'EOF'
#!/bin/bash
# Script to properly setup the Python virtual environment

cd /home/ec2-user/DragonRise

# Check if venv exists, if not create it
if [ ! -d "venv" ]; then
    echo "Creating new Python virtual environment..."
    python3 -m venv venv
fi

# Activate the virtual environment
source venv/bin/activate

# Update pip to latest version
pip install --upgrade pip

# Install wheel to ensure binary packages work correctly
pip install wheel

# Install the required packages
echo "Installing required Python packages..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    # Install core packages if requirements.txt is missing
    pip install flask flask-sqlalchemy flask-login flask-wtf flask-limiter python-dotenv 
    pip install werkzeug sqlalchemy authlib boto3 requests flask-migrate gunicorn
    pip install bleach pillow cryptography pyjwt
fi

# Verify Flask is installed
echo "Checking Flask installation:"
pip show flask

# Deactivate the virtual environment
deactivate

echo "Virtual environment setup completed"
EOF

# Upload and execute the virtual environment setup script
echo -e "${YELLOW}Setting up Python virtual environment...${NC}"
scp -i "$PEM_KEY" /tmp/setup_venv.sh "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod +x /tmp/setup_venv.sh && /tmp/setup_venv.sh"

# After setting up the virtual environment, verify Python imports
echo -e "${YELLOW}Verifying Python imports with virtual environment...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && source venv/bin/activate && python -c 'import flask; print(\"Flask version:\", flask.__version__); import wsgi; print(\"wsgi imported successfully\")' || echo 'Error importing modules'"

# Create a script to verify the systemd configuration
cat > /tmp/verify_systemd.sh << 'EOF'
#!/bin/bash
# Verify and fix the systemd service configuration

echo "Verifying systemd service configuration..."

# Check if the service file exists
if [ ! -f "/etc/systemd/system/dragonrise.service" ]; then
    echo "ERROR: Service file not found!"
    exit 1
fi

# Check ExecStart path
EXEC_START=$(grep "ExecStart" /etc/systemd/system/dragonrise.service)
echo "Current ExecStart: $EXEC_START"

# Make sure wsgi.py exists
if [ ! -f "/home/ec2-user/DragonRise/wsgi.py" ]; then
    echo "ERROR: wsgi.py file not found!"
    exit 1
fi

# Verify gunicorn can be found in the venv
if [ ! -f "/home/ec2-user/DragonRise/venv/bin/gunicorn" ]; then
    echo "ERROR: gunicorn not found in virtual environment!"
    source /home/ec2-user/DragonRise/venv/bin/activate
    pip install gunicorn
    deactivate
fi

echo "Systemd service configuration looks good"
exit 0
EOF

# Upload and execute the systemd verification script
echo -e "${YELLOW}Verifying systemd service configuration...${NC}"
scp -i "$PEM_KEY" /tmp/verify_systemd.sh "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod +x /tmp/verify_systemd.sh && sudo /tmp/verify_systemd.sh"

# Restart services with proper sequence
echo -e "${GREEN}Restarting services with correct sequence...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    # Reload systemd configuration
    sudo systemctl daemon-reload
    
    # Start services in correct order
    sudo systemctl restart dragonrise
    sleep 3  # Give Gunicorn time to start
    sudo systemctl restart nginx
    
    # Verify services are running
    echo 'DragonRise service status:'
    sudo systemctl status dragonrise --no-pager
    
    echo 'Nginx service status:'
    sudo systemctl status nginx --no-pager
"

# Check for errors in the logs
echo -e "${YELLOW}Checking application logs for errors...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sleep 5 && sudo tail -n 20 /var/log/dragonrise/error.log"

# Create a fixed version of the WSGI file that correctly exports the application
cat > /tmp/fixed_wsgi.py << 'EOF'
"""
WSGI file for DragonRise application
"""
from app_fixed import app

# This explicitly names the application variable that Gunicorn will use
application = app

if __name__ == "__main__":
    application.run()
EOF

# Upload the fixed WSGI file
echo -e "${YELLOW}Uploading fixed WSGI file...${NC}"
scp -i "$PEM_KEY" /tmp/fixed_wsgi.py "$EC2_HOST:$APP_DIR/wsgi.py"

# Verify the new WSGI file works properly
echo -e "${YELLOW}Verifying fixed WSGI file...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && source venv/bin/activate && python -c 'import wsgi; print(\"Application found in wsgi:\", hasattr(wsgi, \"application\"))' || echo 'Error importing wsgi'"

# Restart the dragonrise service
echo -e "${GREEN}Restarting dragonrise service...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl restart dragonrise && sleep 3 && sudo systemctl status dragonrise --no-pager"

# Add after the dragonrise service restart section

# Create a Cloudflare-friendly Nginx configuration with permissive CSP
echo -e "${YELLOW}Configuring Nginx with Cloudflare-friendly settings and permissive CSP...${NC}"
cat > /tmp/cloudflare-nginx-fix.conf << 'EOF'
server {
    listen 80;
    server_name dragonrise.pro;
    
    # Redirect HTTP to HTTPS
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name dragonrise.pro;

    # SSL Configuration
    ssl_certificate /home/ec2-user/DragonRise/certificates/cert.pem;
    ssl_certificate_key /home/ec2-user/DragonRise/certificates/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    # Cloudflare settings
    set_real_ip_from 103.21.244.0/22;
    set_real_ip_from 103.22.200.0/22;
    set_real_ip_from 103.31.4.0/22;
    set_real_ip_from 104.16.0.0/13;
    set_real_ip_from 104.24.0.0/14;
    set_real_ip_from 108.162.192.0/18;
    set_real_ip_from 131.0.72.0/22;
    set_real_ip_from 141.101.64.0/18;
    set_real_ip_from 162.158.0.0/15;
    set_real_ip_from 172.64.0.0/13;
    set_real_ip_from 173.245.48.0/20;
    set_real_ip_from 188.114.96.0/20;
    set_real_ip_from 190.93.240.0/20;
    set_real_ip_from 197.234.240.0/22;
    set_real_ip_from 198.41.128.0/17;
    set_real_ip_from 2400:cb00::/32;
    set_real_ip_from 2606:4700::/32;
    set_real_ip_from 2803:f800::/32;
    set_real_ip_from 2405:b500::/32;
    set_real_ip_from 2405:8100::/32;
    set_real_ip_from 2c0f:f248::/32;
    set_real_ip_from 2a06:98c0::/29;
    real_ip_header CF-Connecting-IP;
    
    # Main application proxy with CSP fix
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Add permissive CSP headers
        add_header Content-Security-Policy "default-src * data: blob: 'unsafe-inline' 'unsafe-eval';" always;
        add_header Access-Control-Allow-Origin "*" always;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
        add_header Access-Control-Allow-Headers "*" always;
    }

    # Static files with permissive settings
    location /static/ {
        alias /home/ec2-user/DragonRise/static/;
        autoindex off;
        
        # Add permissive headers for static content
        add_header Content-Security-Policy "default-src * data: blob: 'unsafe-inline' 'unsafe-eval';" always;
        add_header Access-Control-Allow-Origin "*" always;
        add_header Cache-Control "public, max-age=31536000" always;
        
        # Ensure text/css content type for CSS files
        location ~* \.css$ {
            add_header Content-Type "text/css";
            add_header Access-Control-Allow-Origin "*" always;
            add_header Content-Security-Policy "default-src * data: blob: 'unsafe-inline' 'unsafe-eval';" always;
            alias /home/ec2-user/DragonRise/static/$uri;
        }
        
        # Ensure application/javascript content type for JS files
        location ~* \.js$ {
            add_header Content-Type "application/javascript";
            add_header Access-Control-Allow-Origin "*" always;
            add_header Content-Security-Policy "default-src * data: blob: 'unsafe-inline' 'unsafe-eval';" always;
            alias /home/ec2-user/DragonRise/static/$uri;
        }
    }
}
EOF

# Upload and apply the fixed Nginx configuration
scp -i "$PEM_KEY" /tmp/cloudflare-nginx-fix.conf "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    sudo mv /tmp/cloudflare-nginx-fix.conf /etc/nginx/conf.d/dragonrise.conf
    
    # Test Nginx configuration
    echo 'Testing Nginx configuration...'
    sudo nginx -t
    
    # Restart Nginx to apply changes
    echo 'Restarting Nginx...'
    sudo systemctl restart nginx
    
    # Check Nginx logs for errors
    echo 'Recent Nginx error logs:'
    sudo tail -n 10 /var/log/nginx/error.log
"

# Create a CSP-friendly version of the WSGI application
cat > /tmp/csp_wsgi.py << 'EOF'
"""
WSGI file for DragonRise application with permissive CSP headers
"""
from flask import Flask, request, make_response
from app_fixed import app

class CSPMiddleware:
    """Middleware to add permissive CSP headers to all responses"""
    
    def __init__(self, app):
        self.app = app
        
    def __call__(self, environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            new_headers = []
            has_csp = False
            
            # Process existing headers
            for name, value in headers:
                if name.lower() == 'content-security-policy':
                    # Replace restrictive CSP with permissive one
                    new_headers.append((name, "default-src * data: blob: 'unsafe-inline' 'unsafe-eval';"))
                    has_csp = True
                else:
                    new_headers.append((name, value))
            
            # Add CSP if not already present
            if not has_csp:
                new_headers.append(('Content-Security-Policy', 
                                  "default-src * data: blob: 'unsafe-inline' 'unsafe-eval';"))
            
            # Add CORS headers
            new_headers.append(('Access-Control-Allow-Origin', '*'))
            new_headers.append(('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'))
            new_headers.append(('Access-Control-Allow-Headers', '*'))
            
            return start_response(status, new_headers, exc_info)
        
        return self.app(environ, custom_start_response)

# Wrap the Flask application with the CSP middleware
application = CSPMiddleware(app)

if __name__ == "__main__":
    # Only used for local development
    app.run(debug=True)
EOF

# Upload the CSP-friendly WSGI file
echo -e "${YELLOW}Uploading CSP-friendly WSGI file...${NC}"
scp -i "$PEM_KEY" /tmp/csp_wsgi.py "$EC2_HOST:$APP_DIR/wsgi.py"

# Restart the DragonRise service to apply CSP changes
echo -e "${GREEN}Applying CSP fixes and restarting service...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    # Restart the application
    sudo systemctl restart dragonrise
    sleep 3
    
    # Verify service is running
    sudo systemctl status dragonrise --no-pager
    
    # Check for CSP-related errors
    echo 'Checking for CSP-related errors:'
    sudo grep -i 'csp\|security\|policy\|content-security' /var/log/dragonrise/error.log | tail -5
"

# Provide Cloudflare-specific instructions
echo -e "${YELLOW}Important Cloudflare Settings:${NC}"
echo -e "1. Log in to Cloudflare and go to your dragonrise.pro domain"
echo -e "2. Go to SSL/TLS > Edge Certificates and ensure the following:"
echo -e "   - 'Always Use HTTPS' is enabled"
echo -e "   - 'Minimum TLS Version' is set to TLS 1.2"
echo -e "3. In Cache > Configuration:"
echo -e "   - Click 'Purge Cache' > 'Purge Everything' to clear any cached CSP issues"
echo -e "4. In Page Rules, consider creating a rule with the pattern *dragonrise.pro/static/* that:"
echo -e "   - Sets 'Cache Level' to 'Bypass'"
echo -e "   - Disable security features for this path"
echo -e "5. Temporarily enable 'Development Mode' in Overview to bypass caching while testing"
echo -e ""
echo -e "After making these changes, the CSP issues with static files should be resolved."

echo -e "${GREEN}Complete redeployment finished!${NC}"
echo -e "${YELLOW}Important notes:${NC}"
echo -e "1. The EC2 server has been completely cleaned and reset"
echo -e "2. app_fixed.py has been replaced with the contents of app.py"
echo -e "3. An enhanced WSGI file with better error handling has been created"
echo -e "4. The virtual environment has been properly set up with all dependencies"
echo -e "5. To check for errors, run: ${BLUE}ssh -i $PEM_KEY $EC2_HOST \"sudo tail -f /var/log/dragonrise/error.log\"${NC}"
echo -e "6. Verify the application at: ${BLUE}https://dragonrise.pro${NC}"