#!/bin/bash
# Deployment script for DragonRise with S3 static assets

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"
S3_BUCKET="dragonrise-static"
S3_URL="https://$S3_BUCKET.s3.us-east-1.amazonaws.com/static/"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting DragonRise deployment with S3 integration...${NC}"

# Check if PEM key exists
if [ ! -f "$PEM_KEY" ]; then
    echo -e "${RED}PEM key not found at $PEM_KEY${NC}"
    exit 1
fi

# Ensure PEM key has correct permissions
chmod 400 "$PEM_KEY"

# Copy application files to EC2 (excluding static directory)
echo -e "${GREEN}Copying application files...${NC}"
rsync -avz --exclude 'venv/' --exclude '.git/' --exclude '__pycache__/' \
    --exclude '*.pyc' --exclude '.env.root' --exclude 'dragonrise.db.*' \
    --exclude 'static/' \
    -e "ssh -i $PEM_KEY" . "$EC2_HOST:$APP_DIR/"

# Update the .env file on EC2 with S3 URL
echo -e "${GREEN}Updating .env file with S3 configuration...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    # Add S3 URL to .env if not already present
    if ! grep -q 'STATIC_URL' $APP_DIR/.env; then
        echo '' >> $APP_DIR/.env
        echo '# S3 Static Files Configuration' >> $APP_DIR/.env
        echo 'STATIC_URL=$S3_URL' >> $APP_DIR/.env
    else
        # Update existing STATIC_URL
        sed -i 's|STATIC_URL=.*|STATIC_URL=$S3_URL|g' $APP_DIR/.env
    fi
"

# Create a simplified Nginx configuration that redirects static requests to S3
echo -e "${GREEN}Updating Nginx configuration...${NC}"
cat > /tmp/nginx-s3-config.conf << EOF
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
    real_ip_header CF-Connecting-IP;
    
    # Main application proxy
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    # Redirect static requests to S3
    location /static/ {
        return 301 $S3_URL\$request_uri;
    }
}
EOF

# Upload and apply the new Nginx configuration
scp -i "$PEM_KEY" /tmp/nginx-s3-config.conf "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    sudo mv /tmp/nginx-s3-config.conf /etc/nginx/conf.d/dragonrise.conf
    sudo nginx -t && sudo systemctl restart nginx
"

# Restart the application
echo -e "${GREEN}Restarting application...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    sudo systemctl restart dragonrise
"

# Verify deployment
echo -e "${GREEN}Verifying deployment...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    sudo systemctl status nginx --no-pager
    sudo systemctl status dragonrise --no-pager
    sudo tail -n 10 /var/log/dragonrise/error.log
"

echo -e "${GREEN}Deployment completed!${NC}"
echo -e "${YELLOW}Important notes:${NC}"
echo -e "1. Static files are now served from: $S3_URL"
echo -e "2. Verify that your application is working correctly at: https://dragonrise.pro"
echo -e "3. Check that Cloudflare is properly configured to work with S3"
echo -e "4. If you make changes to static files, use sync_static_to_s3.sh to update them"