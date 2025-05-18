#!/bin/bash
# Comprehensive fix for DragonRise 502 errors

# Configuration
EC2_HOST="ec2-user@54.234.216.90"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting DragonRise server fix...${NC}"

# Check if PEM key exists
if [ ! -f "$PEM_KEY" ]; then
    echo -e "${RED}PEM key not found at $PEM_KEY${NC}"
    exit 1
fi

# Ensure PEM key has correct permissions
chmod 400 "$PEM_KEY"

# Copy the key files
echo -e "${GREEN}Copying key files...${NC}"
scp -i "$PEM_KEY" wsgi.py "$EC2_HOST:$APP_DIR/"
scp -i "$PEM_KEY" dragonrise.service "$EC2_HOST:/tmp/"
scp -i "$PEM_KEY" gunicorn.conf.py "$EC2_HOST:$APP_DIR/"

# Check if deployment was successful
echo -e "${GREEN}Checking server status and reconfiguring services...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" << 'EOF'
# Check server status
echo "Checking if Gunicorn is installed..."
if ! pip list | grep -q gunicorn; then
    echo "Gunicorn not found, installing..."
    pip install gunicorn
fi

# Move service file to proper location
sudo mv /tmp/dragonrise.service /etc/systemd/system/dragonrise.service

# Ensure logs directory exists
sudo mkdir -p /var/log/dragonrise
sudo chown -R ec2-user:ec2-user /var/log/dragonrise

# Make sure the app directory has the right permissions
sudo chmod -R 755 /home/ec2-user/DragonRise

# Reload daemon and restart services
sudo systemctl daemon-reload
sudo systemctl restart dragonrise
sudo systemctl restart nginx

# Check service status
echo "Service status:"
sudo systemctl status dragonrise --no-pager
sudo systemctl status nginx --no-pager

# Check logs
echo "Latest logs:"
tail -n 20 /var/log/dragonrise/error.log
EOF

echo -e "${YELLOW}Important: If you're using a custom domain with Cloudflare:${NC}"
echo -e "1. Verify your Cloudflare DNS settings are pointing to 54.234.216.90"
echo -e "2. Set SSL/TLS encryption mode to 'Full' or 'Full (Strict)' in Cloudflare"
echo -e "3. Make sure the origin server allows Cloudflare IP addresses"

echo -e "${GREEN}Fix completed! Clear your browser cache and try accessing the site again.${NC}"