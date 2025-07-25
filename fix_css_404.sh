#!/bin/bash
# Fix CSS 404 error for DragonRise

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"

echo "Diagnosing and fixing CSS 404 error..."

# 1. First, check if the CSS file actually exists on the server
ssh -i "$PEM_KEY" "$EC2_HOST" "
    echo 'Checking if style.css exists:'
    ls -la $APP_DIR/static/css/style.css || echo 'File not found'
    
    # If directory doesn't exist, create it
    if [ ! -d $APP_DIR/static/css ]; then
        echo 'Creating CSS directory...'
        mkdir -p $APP_DIR/static/css
    fi
    
    # Create a simple style.css file if it doesn't exist
    if [ ! -f $APP_DIR/static/css/style.css ]; then
        echo 'Creating a new style.css file...'
        cat > $APP_DIR/static/css/style.css << 'CSSEOF'
:root {
    --black-house: #333333;
    --blue-house: #0066cc;
    --green-house: #009933;
    --white-house: #f8f9fa;
    --gold-house: #ffcc00;
    --purple-house: #660099;
}

body {
    background-color: #f4f4f4;
    font-family: 'Arial', sans-serif;
}

.navbar-brand {
    font-size: 1.5rem;
    font-weight: bold;
}

.house-card {
    padding: 20px;
    margin: 0;
    border-radius: 10px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    transition: transform 0.3s ease;
    height: 100%;
    display: flex;
    flex-direction: column;
    position: relative;
    overflow: hidden;
}
CSSEOF
    fi
    
    # Set proper permissions
    chmod 644 $APP_DIR/static/css/style.css
    
    echo 'After fix:'
    ls -la $APP_DIR/static/css/style.css
"

# 2. Fix the Nginx configuration - this is likely where the problem is
cat > /tmp/nginx-static-fix.conf << 'EOF'
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

    # CRITICAL FIX: Static files configuration - the 'root' directive was causing the issue
    # Using 'alias' directive instead which is correct for location blocks with a path prefix
    location /static/ {
        alias /home/ec2-user/DragonRise/static/;
        access_log off;
        expires max;
        add_header Cache-Control "public, max-age=31536000";
        add_header Access-Control-Allow-Origin "*";
    }
    
    # Add a specific location for style.css to ensure it's properly served
    location = /static/css/style.css {
        alias /home/ec2-user/DragonRise/static/css/style.css;
        add_header Content-Type "text/css";
        access_log off;
        expires max;
        add_header Cache-Control "public, max-age=31536000";
        add_header Access-Control-Allow-Origin "*";
    }
}
EOF

# Upload and apply the fixed Nginx configuration
scp -i "$PEM_KEY" /tmp/nginx-static-fix.conf "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    sudo mv /tmp/nginx-static-fix.conf /etc/nginx/conf.d/dragonrise.conf
    
    # Test Nginx configuration
    echo 'Testing Nginx configuration...'
    sudo nginx -t
    
    # Restart Nginx to apply changes
    echo 'Restarting Nginx...'
    sudo systemctl restart nginx
    
    # Check Nginx status
    echo 'Nginx status:'
    sudo systemctl status nginx --no-pager
    
    # Check Nginx logs
    echo 'Recent Nginx error logs:'
    sudo tail -n 20 /var/log/nginx/error.log
"

echo "The CSS file issue should now be fixed. Please try accessing https://dragonrise.pro/static/css/style.css again."
echo "If you still encounter issues, please check the Cloudflare settings to ensure they are not caching the 404 response."
echo "You may need to purge the Cloudflare cache for your domain."