#!/bin/bash
# Complete deployment script for DragonRise with error handling

# Configuration
EC2_HOST="ec2-user@54.234.216.90"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting DragonRise deployment...${NC}"

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
ssh -i "$PEM_KEY" "$EC2_HOST" "mkdir -p $APP_DIR/logs $APP_DIR/certificates $APP_DIR/instance $APP_DIR/static/uploads /var/log/dragonrise"

# Fix permissions for logs directory
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo chown -R ec2-user:ec2-user /var/log/dragonrise"

# Copy application files
echo -e "${GREEN}Copying application files...${NC}"
rsync -avz --exclude 'venv/' --exclude '.git/' --exclude '__pycache__/' \
    --exclude '*.pyc' --exclude '.env.root' \
    -e "ssh -i $PEM_KEY" . "$EC2_HOST:$APP_DIR/"

# Fix requirements.txt to remove patternomaly (it's a JavaScript library, not Python)
echo -e "${GREEN}Fixing requirements.txt...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && sed -i '/patternomaly/d' requirements.txt"

# Set up Python virtual environment (with explicit Python version)
echo -e "${GREEN}Setting up Python environment...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
    python3 -m venv venv && \
    source venv/bin/activate && \
    pip install --upgrade pip && \
    pip install pyOpenSSL && \
    pip install -r requirements.txt"

# Create the .env file
echo -e "${GREEN}Setting up environment configuration...${NC}"
cat > /tmp/dragonrise.env << 'EOF'
SECRET_KEY=very-secured-key-for-dragon-rise-production
API_KEY=dragon-rise-production-api-key-2025
DATABASE_URL=mysql+pymysql://dragonrise_admin:Dragon2025!Rise@dragonrise-aurora.cluster-c05mciuw6fqu.us-east-1.rds.amazonaws.com:3306/dragonrise
DEBUG=False
EOF

# Update this file:
# filepath: /Users/nat/Git/DragonRise/deploy.sh

# Add these lines to your deployment script where environment files are copied:

# Copy AWS credentials to EC2
echo -e "${GREEN}Setting up AWS credentials...${NC}"
if [ -f ".env.aws" ]; then
    scp -i "$PEM_KEY" ".env.aws" "$EC2_HOST:$APP_DIR/"
    ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && cat .env.aws >> .env"
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
    cert.get_subject().CN = 'dragonrise.example.com'
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

# Create WSGI file
echo -e "${GREEN}Creating WSGI file...${NC}"
cat > /tmp/wsgi.py << 'EOF'
from app_fixed import app

if __name__ == "__main__":
    app.run()
EOF

scp -i "$PEM_KEY" /tmp/wsgi.py "$EC2_HOST:$APP_DIR/"

# Configure Nginx
echo -e "${GREEN}Configuring Nginx...${NC}"
cat > /tmp/dragonrise-nginx.conf << 'EOF'
server {
    listen 80;
    server_name 54.234.216.90;
    
    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl;
    server_name 54.234.216.90;

    ssl_certificate /home/ec2-user/DragonRise/certificates/cert.pem;
    ssl_certificate_key /home/ec2-user/DragonRise/certificates/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /home/ec2-user/DragonRise/static/;
        expires 30d;
    }
}
EOF

scp -i "$PEM_KEY" /tmp/dragonrise-nginx.conf "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo mv /tmp/dragonrise-nginx.conf /etc/nginx/conf.d/dragonrise.conf"

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

# Set correct permissions
echo -e "${GREEN}Setting permissions...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod -R 755 $APP_DIR/static/ && \
                               chmod -R 755 $APP_DIR/templates/ && \
                               chmod -R 700 $APP_DIR/certificates/"

# Initialize database
echo -e "${GREEN}Initializing database...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && \
                               source venv/bin/activate && \
                               python -c 'from app import init_db; init_db()'"

# Start services
echo -e "${GREEN}Starting services...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl daemon-reload && \
                               sudo systemctl enable nginx && \
                               sudo systemctl restart nginx && \
                               sudo systemctl enable dragonrise && \
                               sudo systemctl restart dragonrise"

# Verify deployment
echo -e "${GREEN}Verifying deployment...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl status nginx && \
                               sudo systemctl status dragonrise"

echo -e "${GREEN}Deployment completed! Application should be accessible at https://54.234.216.90${NC}"