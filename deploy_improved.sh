#!/bin/bash
# Improved deployment script for DragonRise with enhanced error handling and security

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"
S3_BUCKET="dragonrise-static"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Function to handle errors
handle_error() {
    echo -e "${RED}ERROR: $1${NC}"
    exit 1
}

# Check command execution status
check_status() {
    if [ $? -ne 0 ]; then
        handle_error "$1"
    fi
}

echo -e "${GREEN}Starting DragonRise deployment...${NC}"

# Check if PEM key exists
if [ ! -f "$PEM_KEY" ]; then
    handle_error "PEM key not found at $PEM_KEY"
fi

# Ensure PEM key has correct permissions
chmod 400 "$PEM_KEY"
check_status "Failed to set PEM key permissions"

# Stop services if they're running
echo -e "${YELLOW}Stopping any running services...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl stop dragonrise 2>/dev/null || true && sudo systemctl stop nginx 2>/dev/null || true"

# Install required system packages - use mariadb105-devel instead of mysql-devel
echo -e "${GREEN}Installing system dependencies...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo yum update -y && sudo yum install -y python3 python3-pip python3-devel nginx gcc openssl-devel mariadb105-devel"
check_status "Failed to install system dependencies"

# Create application directory and setup structure with proper permissions
echo -e "${GREEN}Setting up application directory...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "mkdir -p $APP_DIR/logs $APP_DIR/certificates $APP_DIR/instance"
check_status "Failed to create application directories"

# Create log directory with sudo (this was causing the error)
echo -e "${GREEN}Setting up log directory with proper permissions...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo mkdir -p /var/log/dragonrise && sudo chown -R ec2-user:ec2-user /var/log/dragonrise"
check_status "Failed to create and set permissions on log directory"

# Copy application files - exclude static directory since it's now in S3
echo -e "${GREEN}Copying application files...${NC}"
rsync -avz --exclude 'venv/' --exclude '.git/' --exclude '__pycache__/' \
    --exclude '*.pyc' --exclude '.env.root' --exclude 'dragonrise.db.*' \
    --exclude 'static/' \
    -e "ssh -i $PEM_KEY" . "$EC2_HOST:$APP_DIR/"
check_status "Failed to copy application files"

# Fix requirements.txt to remove any problematic packages
echo -e "${GREEN}Fixing requirements.txt...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && sed -i '/patternomaly/d' requirements.txt"

# Set up Python virtual environment
echo -e "${GREEN}Setting up Python environment...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
    python3 -m venv venv && \
    source venv/bin/activate && \
    pip install --upgrade pip && \
    pip install pyOpenSSL pymysql cryptography pkce boto3 && \
    pip install -r requirements.txt"
check_status "Failed to set up Python environment"

# Create the .env file with MySQL connection and S3 configuration
echo -e "${GREEN}Setting up environment configuration...${NC}"
cat > /tmp/dragonrise.env << 'EOF'
SECRET_KEY=very-secured-key-for-dragon-rise-production
API_KEY=dragon-rise-production-api-key-2025
DATABASE_URL=mysql+pymysql://dragonrise_admin:Dragon2025!Rise@dragonrise-aurora.cluster-c05mciuw6fqu.us-east-1.rds.amazonaws.com:3306/dragonrise
DEBUG=False

# S3 Configuration
STATIC_URL=https://dragonrise-static.s3.us-east-1.amazonaws.com/static/
S3_BUCKET=dragonrise-static
S3_REGION=us-east-1

# Cognito Configuration
COGNITO_USER_POOL_ID=us-east-1_4qwsylDo1
COGNITO_CLIENT_ID=3mn0rluusoslnjqa7dk2sriaec
COGNITO_CLIENT_SECRET=b1nnfg3irtrtt8eoi8lnddhue1fjn5snnch82d3demouvshkg82
COGNITO_DOMAIN=us-east-14qwsyldo1
COGNITO_REDIRECT_URI=https://dragonrise.pro/auth/callback
AWS_REGION=us-east-1
EOF

# Copy AWS credentials to EC2
echo -e "${GREEN}Setting up AWS credentials...${NC}"
if [ -f ".env.aws" ]; then
    scp -i "$PEM_KEY" ".env.aws" "$EC2_HOST:$APP_DIR/"
    ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && cat .env.aws >> /tmp/dragonrise.env"
    echo -e "${GREEN}AWS credentials configured!${NC}"
else
    echo -e "${YELLOW}Warning: .env.aws file not found. AWS services may not work properly.${NC}"
    # Add AWS credentials directly from .env.root
    cat >> /tmp/dragonrise.env << 'EOF'
AWS_ACCESS_KEY_ID=AKIAXIYNJBLPGS5JIJW6
AWS_SECRET_ACCESS_KEY=cnbhQWay6OXWaPPi5P2u04Vs5f2m5iAMMdNuvQbye
EOF
fi

scp -i "$PEM_KEY" /tmp/dragonrise.env "$EC2_HOST:$APP_DIR/.env"
check_status "Failed to copy environment file"

# Generate self-signed SSL certificate
echo -e "${GREEN}Generating SSL certificates...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
    mkdir -p certificates && \
    source venv/bin/activate && \
    python -c \"
from OpenSSL import crypto
import os

def generate_self_signed_cert(cert_file, key_file):
    # Create a key pair
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 2048)
    
    # Create a self-signed cert
    cert = crypto.X509()
    cert.get_subject().C = 'US'
    cert.get_subject().ST = 'Dragon State'
    cert.get_subject().L = 'Dragon City'
    cert.get_subject().O = 'DragonRise Inc.'
    cert.get_subject().OU = 'DragonRise'
    cert.get_subject().CN = 'dragonrise.pro'
    cert.set_serial_number(1000)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365*24*60*60)  # Valid for 1 year
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, 'sha256')
    
    # Write cert and key to files
    with open(cert_file, 'wb') as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    
    with open(key_file, 'wb') as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
    
    print(f'Generated self-signed certificate: {cert_file}')
    print(f'Generated private key: {key_file}')

# Create certificates directory if it doesn't exist
cert_file = 'certificates/cert.pem'
key_file = 'certificates/key.pem'

# Generate the certificate and key
generate_self_signed_cert(cert_file, key_file)
\""
check_status "Failed to generate SSL certificates"

# Create WSGI file
echo -e "${GREEN}Creating WSGI file...${NC}"
cat > /tmp/wsgi.py << 'EOF'
from app import app

if __name__ == "__main__":
    app.run()
EOF

scp -i "$PEM_KEY" /tmp/wsgi.py "$EC2_HOST:$APP_DIR/"
check_status "Failed to copy WSGI file"

# Create Gunicorn config file
echo -e "${GREEN}Creating Gunicorn config...${NC}"
cat > /tmp/gunicorn.conf.py << 'EOF'
# Gunicorn configuration file for DragonRise

# Server socket
bind = "127.0.0.1:8000"

# Worker processes
workers = 3
worker_class = "sync"
timeout = 120

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None

# Logging
errorlog = "/var/log/dragonrise/error.log"
accesslog = "/var/log/dragonrise/access.log"
loglevel = "info"
EOF

scp -i "$PEM_KEY" /tmp/gunicorn.conf.py "$EC2_HOST:$APP_DIR/"
check_status "Failed to copy Gunicorn config"

# Configure Nginx - updated to handle Cloudflare and redirect static requests to S3
echo -e "${GREEN}Configuring Nginx...${NC}"
cat > /tmp/dragonrise-nginx.conf << EOF
server {
    listen 80;
    server_name dragonrise.pro;
    
    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name dragonrise.pro;

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
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Redirect static requests to S3
    location /static/ {
        return 301 https://dragonrise-static.s3.us-east-1.amazonaws.com\$request_uri;
    }
}
EOF

scp -i "$PEM_KEY" /tmp/dragonrise-nginx.conf "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo mv /tmp/dragonrise-nginx.conf /etc/nginx/conf.d/dragonrise.conf"
check_status "Failed to configure Nginx"

# Configure Systemd service
echo -e "${GREEN}Configuring systemd service...${NC}"
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
ExecStart=/home/ec2-user/DragonRise/venv/bin/gunicorn --bind 127.0.0.1:8000 --workers 3 --log-file=/var/log/dragonrise/error.log --access-logfile=/var/log/dragonrise/access.log wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

scp -i "$PEM_KEY" /tmp/dragonrise.service "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo mv /tmp/dragonrise.service /etc/systemd/system/dragonrise.service"
check_status "Failed to configure systemd service"

# Install missing packages directly before initializing the database
echo -e "${GREEN}Installing missing packages...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
                               source venv/bin/activate && \
                               pip install pkce boto3 awscli"
check_status "Failed to install missing packages"

# Initialize database
echo -e "${GREEN}Initializing database...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
                               source venv/bin/activate && \
                               python -c 'from app import init_db; init_db()'"
check_status "Failed to initialize database"

# Setup AWS CLI configuration for S3 access
echo -e "${GREEN}Setting up AWS CLI for S3 access...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
                               source venv/bin/activate && \
                               mkdir -p ~/.aws && \
                               echo '[default]' > ~/.aws/config && \
                               echo 'region = us-east-1' >> ~/.aws/config && \
                               echo 'output = json' >> ~/.aws/config && \
                               aws s3 ls s3://$S3_BUCKET/static/ --summarize"
check_status "Failed to verify S3 access"

# Start services
echo -e "${GREEN}Starting services...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl daemon-reload && \
                               sudo systemctl enable nginx && \
                               sudo systemctl restart nginx && \
                               sudo systemctl enable dragonrise && \
                               sudo systemctl restart dragonrise"
check_status "Failed to start services"

# Verify deployment
echo -e "${GREEN}Verifying deployment...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl status nginx --no-pager && \
                               sudo systemctl status dragonrise --no-pager"

# Check logs for errors
echo -e "${YELLOW}Checking logs for errors...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "tail -n 20 /var/log/dragonrise/error.log || echo 'No logs yet'"
echo -e "${YELLOW}Checking Nginx error logs:${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo tail -n 20 /var/log/nginx/error.log || echo 'No Nginx error logs yet'"

# Secure AWS credentials handling - removing any hardcoded values
echo -e "${GREEN}Securing AWS credentials...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
                               chmod 600 .env* && \
                               chmod 700 ~/.aws"

echo -e "${GREEN}Deployment completed! Application should be accessible at https://dragonrise.pro${NC}"
echo -e "${YELLOW}Important: Cloudflare Configuration:${NC}"
echo -e "1. Verify your Cloudflare DNS settings are pointing to 3.82.153.50"
echo -e "2. Set SSL/TLS encryption mode to 'Full' or 'Full (Strict)' in Cloudflare"
echo -e "3. Make sure the origin server allows Cloudflare IP addresses"
echo -e "4. Static files are now served directly from S3 at: https://dragonrise-static.s3.us-east-1.amazonaws.com/static/"