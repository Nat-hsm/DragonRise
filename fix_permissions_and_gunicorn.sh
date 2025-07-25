#!/bin/bash
# Script to fix static directory permissions and NGINX configuration

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Fixing DragonRise static directory permissions...${NC}"

# Check if PEM key exists
if [ ! -f "$PEM_KEY" ]; then
    echo -e "${RED}PEM key not found at $PEM_KEY${NC}"
    exit 1
fi

# Ensure PEM key has correct permissions
chmod 400 "$PEM_KEY"

# Create the fix script to run on the server
cat > /tmp/fix_static_permissions.sh << 'EOF'
#!/bin/bash
# Script to fix static directory permissions

echo "Fixing static directory ownership and permissions..."

# Create static directories with proper permissions
sudo mkdir -p /home/ec2-user/DragonRise/static/css
sudo mkdir -p /home/ec2-user/DragonRise/static/images/favicon

# Reset ownership to ec2-user (not nginx)
sudo chown -R ec2-user:ec2-user /home/ec2-user/DragonRise/static

# Set directory and file permissions
sudo chmod 755 /home/ec2-user/DragonRise/static
sudo chmod 755 /home/ec2-user/DragonRise/static/css
sudo chmod 755 /home/ec2-user/DragonRise/static/images
sudo chmod 755 /home/ec2-user/DragonRise/static/images/favicon

# Create CSS file
echo "Creating CSS file..."
cat > /home/ec2-user/DragonRise/static/css/style.css << 'CSS_FILE'
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
CSS_FILE

# Set file permissions
sudo chmod 644 /home/ec2-user/DragonRise/static/css/style.css

# Create favicon placeholders
echo "Creating favicon placeholders..."
touch /home/ec2-user/DragonRise/static/images/favicon/favicon-16x16.png
touch /home/ec2-user/DragonRise/static/images/favicon/favicon-32x32.png
touch /home/ec2-user/DragonRise/static/images/favicon/favicon.ico
touch /home/ec2-user/DragonRise/static/images/favicon/apple-touch-icon.png

# Set favicon permissions
sudo chmod 644 /home/ec2-user/DragonRise/static/images/favicon/favicon-16x16.png
sudo chmod 644 /home/ec2-user/DragonRise/static/images/favicon/favicon-32x32.png
sudo chmod 644 /home/ec2-user/DragonRise/static/images/favicon/favicon.ico
sudo chmod 644 /home/ec2-user/DragonRise/static/images/favicon/apple-touch-icon.png

# Create test page
echo "Creating test page..."
cat > /home/ec2-user/DragonRise/static/test.html << 'HTML_FILE'
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
    </div>
</body>
</html>
HTML_FILE

sudo chmod 644 /home/ec2-user/DragonRise/static/test.html

# Update nginx configuration for static files
echo "Updating Nginx configuration..."
cat > /tmp/nginx.conf << 'NGINX_CONF'
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

    # Serve static files directly from local directory first
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
NGINX_CONF

sudo mv /tmp/nginx.conf /etc/nginx/conf.d/dragonrise.conf

# Update wsgi.py with permissive CSP
echo "Updating WSGI file..."
cat > /home/ec2-user/DragonRise/wsgi.py << 'WSGI_FILE'
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
WSGI_FILE

# Update dragonrise.service to use config file
echo "Updating service file..."
cat > /tmp/dragonrise.service << 'SERVICE_FILE'
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
SERVICE_FILE

sudo mv /tmp/dragonrise.service /etc/systemd/system/dragonrise.service

# Update gunicorn config
echo "Updating gunicorn config..."
cat > /home/ec2-user/DragonRise/gunicorn.conf.py << 'GUNICORN_CONF'
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
GUNICORN_CONF

# Reload and restart services
echo "Restarting services..."
sudo systemctl daemon-reload
sudo systemctl restart dragonrise
sudo systemctl restart nginx

# Check service status
echo "Service status:"
echo "==== DragonRise Service ===="
sudo systemctl status dragonrise --no-pager
echo "==== Nginx Service ===="
sudo systemctl status nginx --no-pager

# Verify static file permissions
echo "==== Static directory permissions ===="
ls -la /home/ec2-user/DragonRise/static
ls -la /home/ec2-user/DragonRise/static/css
EOF

# Upload and execute the fix script
echo -e "${YELLOW}Uploading and executing the fix script...${NC}"
scp -i "$PEM_KEY" /tmp/fix_static_permissions.sh "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod +x /tmp/fix_static_permissions.sh && sudo /tmp/fix_static_permissions.sh"

echo -e "${GREEN}Fix applied! Static files should now work correctly.${NC}"
echo -e "${YELLOW}Try accessing the site at: https://dragonrise.pro${NC}"
echo -e "${YELLOW}Or test static files directly at: https://dragonrise.pro/static/test.html${NC}"
echo -e "${YELLOW}Remember to clear your browser cache or use incognito mode for testing.${NC}"