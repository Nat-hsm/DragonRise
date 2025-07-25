#!/bin/bash
# Fix static files for Cloudflare integration

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"

echo "Fixing static files for Cloudflare integration..."

# 1. Create a new optimized Nginx configuration for Cloudflare
cat > /tmp/cloudflare-nginx.conf << 'EOF'
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
    
    # Trust Cloudflare proxy
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
    
    # Main application
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static files with proper configuration for Cloudflare
    location /static/ {
        root /home/ec2-user/DragonRise;
        access_log off;
        expires max;
        add_header Cache-Control "public, max-age=31536000";
        add_header Access-Control-Allow-Origin "*";
        try_files $uri =404;
        
        # Special fix for style.css
        location /static/css/style.css {
            add_header Content-Type "text/css";
            add_header Access-Control-Allow-Origin "*";
            root /home/ec2-user/DragonRise;
            try_files $uri =404;
        }
    }
}
EOF

# 2. Upload and apply the new configuration
scp -i "$PEM_KEY" /tmp/cloudflare-nginx.conf "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo mv /tmp/cloudflare-nginx.conf /etc/nginx/conf.d/dragonrise.conf"

# 3. Fix static file permissions with proper ownership and access rights
ssh -i "$PEM_KEY" "$EC2_HOST" "
    # Ensure static directory exists
    mkdir -p $APP_DIR/static/css
    
    # Fix permissions systematically
    sudo find $APP_DIR/static -type d -exec chmod 755 {} \;
    sudo find $APP_DIR/static -type f -exec chmod 644 {} \;
    
    # Ensure style.css exists and has proper permissions
    if [ ! -f $APP_DIR/static/css/style.css ]; then
        echo 'body { font-family: Arial, sans-serif; }' > $APP_DIR/static/css/style.css
    fi
    
    # Specific fix for style.css
    chmod 644 $APP_DIR/static/css/style.css
    
    # Set ownership to be readable by nginx
    sudo chown -R ec2-user:ec2-user $APP_DIR/static
    
    # Restart Nginx to apply changes
    sudo systemctl restart nginx
    
    # Verify the CSS file exists and is readable
    ls -la $APP_DIR/static/css/style.css
    
    # Check Nginx configuration
    sudo nginx -t
    
    # Show Nginx error logs
    sudo tail -n 20 /var/log/nginx/error.log
"

echo "Static file fix applied. Please try accessing https://dragonrise.pro/static/css/style.css directly to test."

# 4. Update the .env file with the correct Cognito configuration for the Cloudflare domain
cat > /tmp/cognito_cloudflare.env << 'EOF'
# Updated Cognito Configuration for Cloudflare
COGNITO_USER_POOL_ID=us-east-1_4qwsylDo1
COGNITO_CLIENT_ID=3mn0rluusoslnjqa7dk2sriaec
COGNITO_CLIENT_SECRET=b1nnfg3irtrtt8eoi8lnddhue1fjn5snnch82d3demouvshkg82
COGNITO_DOMAIN=us-east-14qwsyldo1
COGNITO_REDIRECT_URI=https://dragonrise.pro/auth/callback
AWS_REGION=us-east-1
EOF

# Copy to server and update configuration
scp -i "$PEM_KEY" /tmp/cognito_cloudflare.env "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    # Remove existing Cognito configuration
    sed -i '/COGNITO_/d' $APP_DIR/.env
    # Add new configuration
    cat /tmp/cognito_cloudflare.env >> $APP_DIR/.env
    chmod 600 $APP_DIR/.env
    # Restart application
    sudo systemctl restart dragonrise
"

echo "Cognito configuration updated for the Cloudflare domain."
echo "Deployment fix completed! Please try accessing https://dragonrise.pro again."