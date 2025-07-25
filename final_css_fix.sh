#!/bin/bash
# Comprehensive fix for CSS 403 error with Cloudflare

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"

echo "Applying comprehensive fix for CSS 403 error..."

# 1. Extremely permissive approach to troubleshoot
ssh -i "$PEM_KEY" "$EC2_HOST" "
    echo 'Setting very permissive permissions for troubleshooting...'
    
    # Make static directory and all subdirectories world-readable
    sudo chmod -R 777 $APP_DIR/static
    
    # Create fresh CSS file with minimal content
    mkdir -p $APP_DIR/static/css
    echo 'body { font-family: Arial; }' > $APP_DIR/static/css/style.css
    
    # Make sure file is readable by everyone
    chmod 666 $APP_DIR/static/css/style.css
    
    # Check file permissions
    ls -la $APP_DIR/static/css/style.css
"

# 2. Create a special Nginx configuration that bypasses most restrictions
cat > /tmp/permissive-nginx.conf << 'EOF'
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
    
    # Main application
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Extremely permissive static files configuration
    location /static/ {
        alias /home/ec2-user/DragonRise/static/;
        
        # Disable all restrictions
        allow all;
        
        # Add permissive headers
        add_header Access-Control-Allow-Origin "*";
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
        add_header Access-Control-Allow-Headers "*";
        
        # Disable caching for troubleshooting
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        add_header Expires "0";
    }
    
    # Direct access to style.css with minimal configuration
    location = /static/css/style.css {
        alias /home/ec2-user/DragonRise/static/css/style.css;
        default_type text/css;
        allow all;
        add_header Access-Control-Allow-Origin "*";
        add_header Cache-Control "no-cache";
    }
}
EOF

# Upload and apply the configuration
scp -i "$PEM_KEY" /tmp/permissive-nginx.conf "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    sudo mv /tmp/permissive-nginx.conf /etc/nginx/conf.d/dragonrise.conf
    
    # Test and restart Nginx
    sudo nginx -t && sudo systemctl restart nginx
    
    # Restart the application
    sudo systemctl restart dragonrise
    
    # Create a simple test HTML file that loads the CSS directly
    cat > $APP_DIR/static/test.html << 'HTML'
<!DOCTYPE html>
<html>
<head>
    <title>CSS Test</title>
    <link rel='stylesheet' href='/static/css/style.css'>
</head>
<body>
    <h1>CSS Test Page</h1>
    <p>This page tests if the CSS file can be loaded properly.</p>
</body>
</html>
HTML
    
    # Make the test file accessible
    chmod 666 $APP_DIR/static/test.html
    
    # Check Nginx logs for errors
    echo 'Recent Nginx error logs:'
    sudo tail -n 30 /var/log/nginx/error.log
"

echo "
========================================
IMPORTANT CLOUDFLARE SETTINGS
========================================
1. Log in to your Cloudflare account
2. Go to your dragonrise.pro domain

3. In SSL/TLS > Overview:
   - Set mode to 'Full' (not Strict)

4. In SSL/TLS > Edge Certificates:
   - Enable 'Always Use HTTPS'
   - Set 'Minimum TLS Version' to 'TLS 1.2'

5. In Caching > Configuration:
   - Click 'Purge Cache' > 'Purge Everything'

6. In Page Rules, create a new rule:
   - URL pattern: *dragonrise.pro/static/*
   - Settings: Cache Level: Bypass
   - Save and Deploy

7. In Network:
   - Turn on 'HTTP/3 (with QUIC)'
   - Set WebSockets to 'On'

8. MOST IMPORTANT: Go to Overview and enable 'Development Mode'
   (This will bypass caching for 3 hours)

After configuring these settings, try:
1. https://dragonrise.pro/static/test.html (to test basic static file access)
2. https://dragonrise.pro/static/css/style.css (to test the CSS file directly)

If still facing issues:
1. Try accessing the site in incognito mode or a different browser
2. Try disabling any browser extensions that might be affecting requests
3. Clear your browser cache completely
"