#!/bin/bash
# Complete deployment script for DragonRise with all fixes incorporated
# Updated version: July 25, 2025

# Configuration
EC2_HOST="ec2-user@3.82.153.50"  # Updated IP address
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"
S3_BUCKET="dragonrise-static"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting DragonRise deployment...${NC}"
echo -e "${BLUE}This script includes all fixes for static files, permissions, and Gunicorn configuration${NC}"

# Check if PEM key exists
if [ ! -f "$PEM_KEY" ]; then
    echo -e "${RED}PEM key not found at $PEM_KEY${NC}"
    exit 1
fi

# Ensure PEM key has correct permissions
chmod 400 "$PEM_KEY"

# Stop services if they're running
echo -e "${YELLOW}Stopping any running services...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl stop dragonrise 2>/dev/null || true && sudo systemctl stop nginx 2>/dev/null || true"

# Install required system packages
echo -e "${GREEN}Installing system dependencies...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo yum update -y && sudo yum install -y python3 python3-pip python3-devel nginx gcc openssl-devel"

# Create application directory and setup structure
echo -e "${GREEN}Setting up application directory...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "mkdir -p $APP_DIR/logs $APP_DIR/certificates $APP_DIR/instance $APP_DIR/static/uploads $APP_DIR/static/css $APP_DIR/static/images/favicon /var/log/dragonrise"

# Fix permissions for logs directory
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo chown -R ec2-user:ec2-user /var/log/dragonrise"

# Copy application files
echo -e "${GREEN}Copying application files...${NC}"
rsync -avz --exclude 'venv/' --exclude '.git/' --exclude '__pycache__/' \
    --exclude '*.pyc' --exclude '.env.root' \
    -e "ssh -i $PEM_KEY" . "$EC2_HOST:$APP_DIR/"

# Fix requirements.txt to remove any problematic dependencies
echo -e "${GREEN}Fixing requirements.txt...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && sed -i '/patternomaly/d' requirements.txt"

# Set up Python virtual environment
echo -e "${GREEN}Setting up Python environment...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
    python3 -m venv venv && \
    source venv/bin/activate && \
    pip install --upgrade pip && \
    pip install pyOpenSSL gunicorn && \
    pip install -r requirements.txt"

# Create the .env file
echo -e "${GREEN}Setting up environment configuration...${NC}"
cat > /tmp/dragonrise.env << 'EOF'
SECRET_KEY=very-secured-key-for-dragon-rise-production
API_KEY=dragon-rise-production-api-key-2025
DATABASE_URL=mysql+pymysql://dragonrise_admin:Dragon2025!Rise@dragonrise-aurora.cluster-c05mciuw6fqu.us-east-1.rds.amazonaws.com:3306/dragonrise
DEBUG=False
EOF

# Copy AWS credentials to EC2
echo -e "${GREEN}Setting up AWS credentials...${NC}"
if [ -f ".env.aws" ]; then
    scp -i "$PEM_KEY" ".env.aws" "$EC2_HOST:$APP_DIR/"
    ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && cat .env.aws >> /tmp/dragonrise.env"
    echo -e "${GREEN}AWS credentials configured!${NC}"
else
    echo -e "${YELLOW}Warning: .env.aws file not found. AWS services may not work properly.${NC}"
fi

scp -i "$PEM_KEY" /tmp/dragonrise.env "$EC2_HOST:$APP_DIR/.env"

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

# Create optimized WSGI file with CSP fixes
echo -e "${GREEN}Creating optimized WSGI file...${NC}"
cat > /tmp/wsgi.py << 'EOF'
"""
WSGI file with permissive CSP for S3 static files
"""
from flask import Flask
from app_fixed import app as original_app

class CSPApp(Flask):
    def __call__(self, environ, start_response):
        def custom_start_response(status, headers, exc_info=None):
            new_headers = []
            
            # Replace or add headers
            for name, value in headers:
                if name.lower() == 'content-security-policy':
                    # Use permissive CSP
                    new_headers.append((name, "default-src * data: blob: 'unsafe-inline' 'unsafe-eval';"))
                elif name.lower() == 'referrer-policy':
                    new_headers.append((name, "origin"))
                else:
                    new_headers.append((name, value))
            
            # Add CSP if not present
            if not any(name.lower() == 'content-security-policy' for name, _ in headers):
                new_headers.append(('Content-Security-Policy', 
                                  "default-src * data: blob: 'unsafe-inline' 'unsafe-eval';"))
            
            # Add CORS headers
            if not any(name.lower() == 'access-control-allow-origin' for name, _ in headers):
                new_headers.append(('Access-Control-Allow-Origin', '*'))
                
            return start_response(status, new_headers, exc_info)
        
        return original_app(environ, custom_start_response)

app = CSPApp(__name__)
application = app

if __name__ == "__main__":
    application.run()
EOF

scp -i "$PEM_KEY" /tmp/wsgi.py "$EC2_HOST:$APP_DIR/"

# Configure optimized Nginx with S3 integration
echo -e "${GREEN}Configuring Nginx with S3 integration...${NC}"
cat > /tmp/dragonrise-nginx.conf << 'EOF'
server {
    listen 80;
    server_name dragonrise.pro;
    
    location / {
        return 301 https://$host$request_uri;
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
    real_ip_header CF-Connecting-IP;
    
    # Global headers
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' '*' always;
    add_header 'Referrer-Policy' 'origin' always;
    
    # Remove restrictive CSP headers in Nginx
    add_header 'Content-Security-Policy' "default-src * data: blob: 'unsafe-inline' 'unsafe-eval';" always;
    
    # Main application proxy with increased timeouts
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Increase timeouts to prevent 502 errors
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Serve static files with fallback system
    location /static/ {
        # Try to serve local file first
        root /home/ec2-user/DragonRise;
        try_files $uri @s3;
        
        # Cache settings
        expires 30d;
        add_header Cache-Control "public, max-age=2592000";
    }
    
    # S3 fallback location
    location @s3 {
        proxy_pass https://dragonrise-static.s3.us-east-1.amazonaws.com/static/$request_uri;
        proxy_set_header Host dragonrise-static.s3.us-east-1.amazonaws.com;
        proxy_ssl_name dragonrise-static.s3.us-east-1.amazonaws.com;
        proxy_ssl_server_name on;
    }
}
EOF

scp -i "$PEM_KEY" /tmp/dragonrise-nginx.conf "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo mv /tmp/dragonrise-nginx.conf /etc/nginx/conf.d/dragonrise.conf"

# Create optimized Gunicorn config
echo -e "${GREEN}Creating optimized Gunicorn config...${NC}"
cat > /tmp/gunicorn.conf.py << 'EOF'
"""Gunicorn configuration file"""

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Worker processes
workers = 2  # Reduced for stability
worker_class = 'sync'
worker_connections = 1000
timeout = 60  # Increased timeout
keepalive = 2

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

# Prevent worker timeouts
graceful_timeout = 60
max_requests = 100
max_requests_jitter = 20
EOF

scp -i "$PEM_KEY" /tmp/gunicorn.conf.py "$EC2_HOST:$APP_DIR/"

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
ExecStart=/home/ec2-user/DragonRise/venv/bin/gunicorn --config /home/ec2-user/DragonRise/gunicorn.conf.py wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

scp -i "$PEM_KEY" /tmp/dragonrise.service "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo mv /tmp/dragonrise.service /etc/systemd/system/dragonrise.service"

# Create backup static files
echo -e "${GREEN}Creating backup static files...${NC}"
cat > /tmp/style.css << 'EOF'
/* Backup style.css */
body {
    font-family: Arial, sans-serif;
    line-height: 1.6;
    color: #333;
    background-color: #f4f4f4;
    margin: 0;
    padding: 0;
}

.container {
    width: 80%;
    margin: auto;
    overflow: hidden;
}

.stats-card {
    background: #fff;
    padding: 15px;
    margin-bottom: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
}

.house-card {
    border-radius: 5px;
    padding: 10px;
    margin: 10px 0;
    color: #fff;
    text-align: center;
}

.house-card.Black { background-color: #333; }
.house-card.Blue { background-color: #0066cc; }
.house-card.Green { background-color: #009933; }
.house-card.White { background-color: #f8f9fa; color: #333; }
.house-card.Gold { background-color: #ffcc00; color: #333; }
.house-card.Purple { background-color: #660099; }
EOF

scp -i "$PEM_KEY" /tmp/style.css "$EC2_HOST:$APP_DIR/static/css/"

# Create test page for verification
echo -e "${GREEN}Creating test page...${NC}"
cat > /tmp/test.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>DragonRise Static Test</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <style>
        body { padding: 20px; }
        .test-container { max-width: 800px; margin: 0 auto; }
        .success { color: green; font-weight: bold; }
    </style>
</head>
<body>
    <div class="test-container">
        <h1>DragonRise Static Test</h1>
        <p class="success">If you can see this page with styling, static files are working!</p>
        
        <div class="house-card Blue">
            <h2>Blue House</h2>
            <p>This should have blue background and white text</p>
        </div>
        
        <div class="house-card Green">
            <h2>Green House</h2>
            <p>This should have green background and white text</p>
        </div>
        
        <div style="margin-top: 20px;">
            <h3>Test Links:</h3>
            <ul>
                <li><a href="/" target="_blank">Home Page</a></li>
                <li><a href="/login" target="_blank">Login Page</a></li>
                <li><a href="/register" target="_blank">Register Page</a></li>
            </ul>
        </div>
    </div>
</body>
</html>
EOF

scp -i "$PEM_KEY" /tmp/test.html "$EC2_HOST:$APP_DIR/static/test.html"

# Set correct permissions
echo -e "${GREEN}Setting permissions...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
    sudo chown -R ec2-user:ec2-user . && \
    chmod -R 755 static/ && \
    chmod -R 644 static/css/style.css && \
    chmod -R 644 static/test.html && \
    chmod -R 700 certificates/"

# Create placeholder favicon files
echo -e "${GREEN}Creating favicon placeholders...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
    touch static/images/favicon/favicon-16x16.png && \
    touch static/images/favicon/favicon-32x32.png && \
    touch static/images/favicon/favicon.ico && \
    touch static/images/favicon/apple-touch-icon.png && \
    chmod 644 static/images/favicon/*"

# Initialize database
echo -e "${GREEN}Initializing database...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
    source venv/bin/activate && \
    python -c 'from app_fixed import init_db; init_db()'"

# Start services
echo -e "${GREEN}Starting services...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl daemon-reload && \
                               sudo systemctl enable nginx && \
                               sudo systemctl restart nginx && \
                               sudo systemctl enable dragonrise && \
                               sudo systemctl restart dragonrise"

# Verify deployment
echo -e "${GREEN}Verifying deployment...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl status nginx --no-pager && \
                               sudo systemctl status dragonrise --no-pager && \
                               ls -la $APP_DIR/static && \
                               ls -la $APP_DIR/static/css"

echo -e "${GREEN}Deployment completed! Application is now accessible at https://dragonrise.pro${NC}"
echo -e "${YELLOW}Important notes:${NC}"
echo -e "1. Static files are configured with local fallback and S3 integration"
echo -e "2. SSL/TLS is properly configured with self-signed certificates"
echo -e "3. CSP headers are set to permissive mode to allow all resources"
echo -e "4. CORS is properly configured for cross-origin requests"
echo -e "5. Test the application at: ${BLUE}https://dragonrise.pro/static/test.html${NC}"
echo -e "6. Remember to clear your browser cache or use incognito mode for testing"