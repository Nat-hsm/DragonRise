#!/bin/bash
# Bypass Cloudflare for static files to troubleshoot 403 error

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"

echo "Setting up direct access to static files bypassing Cloudflare..."

# 1. Ensure static files exist and have maximally permissive permissions
ssh -i "$PEM_KEY" "$EC2_HOST" "
    echo 'Setting up static files with max permissions...'
    
    # Create directory structure
    mkdir -p $APP_DIR/static/css
    
    # Create CSS file with basic styling
    cat > $APP_DIR/static/css/style.css << 'CSSEOF'
/* Basic styling for DragonRise */
body {
    font-family: Arial, sans-serif;
    background-color: #f4f4f4;
    margin: 0;
    padding: 0;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

header {
    background-color: #333;
    color: white;
    padding: 10px 0;
}

footer {
    background-color: #333;
    color: white;
    text-align: center;
    padding: 10px 0;
    position: fixed;
    bottom: 0;
    width: 100%;
}

.btn {
    display: inline-block;
    padding: 8px 16px;
    background-color: #4CAF50;
    color: white;
    text-decoration: none;
    border-radius: 4px;
}
CSSEOF
    
    # Make static directory and all its contents universally accessible
    sudo chmod -R 777 $APP_DIR/static
    
    # Ensure CSS file is readable by everyone
    chmod 666 $APP_DIR/static/css/style.css
    
    # Verify file permissions
    ls -la $APP_DIR/static/css/style.css
"

# 2. Set up a separate server block in Nginx to serve static files directly
cat > /tmp/split-static-server.conf << 'EOF'
# Main application server
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
}

# Separate server block for static files - listening on port 8080
server {
    listen 8080;
    
    # Root directory for static files
    root /home/ec2-user/DragonRise;
    
    # Enable directory listing for debugging
    autoindex on;
    
    # Serve static files with permissive headers
    location /static/ {
        # Add permissive headers
        add_header Access-Control-Allow-Origin "*";
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
        add_header Access-Control-Allow-Headers "*";
        
        # Disable caching for troubleshooting
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        add_header Expires "0";
    }
    
    # Special configuration for CSS files
    location ~ \.css$ {
        add_header Content-Type text/css;
        add_header Access-Control-Allow-Origin "*";
    }
}
EOF

# Upload and apply the configuration
scp -i "$PEM_KEY" /tmp/split-static-server.conf "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    sudo mv /tmp/split-static-server.conf /etc/nginx/conf.d/dragonrise.conf
    
    # Open port 8080 in the firewall
    sudo iptables -I INPUT -p tcp --dport 8080 -j ACCEPT
    sudo service iptables save 2>/dev/null || echo 'Iptables service not available, port may need to be opened in AWS console'
    
    # Test and restart Nginx
    sudo nginx -t && sudo systemctl restart nginx
    
    # Create a test HTML file to verify setup
    cat > $APP_DIR/static/direct-test.html << 'HTML'
<!DOCTYPE html>
<html>
<head>
    <title>Direct CSS Test</title>
    <style>
        body { background-color: lightblue; }
        h1 { color: navy; }
    </style>
</head>
<body>
    <h1>Direct Static File Access Test</h1>
    <p>This page should be accessible directly via port 8080.</p>
    <p>The CSS file should be accessible at: http://3.82.153.50:8080/static/css/style.css</p>
</body>
</html>
HTML
    
    chmod 666 $APP_DIR/static/direct-test.html
    
    # Check Nginx error logs
    echo 'Recent Nginx error logs:'
    sudo tail -n 20 /var/log/nginx/error.log
"

echo "
========================================
INSTRUCTIONS FOR TESTING STATIC FILES DIRECTLY
========================================

The script has set up a direct access method for static files that bypasses Cloudflare completely.
You can now access static files directly on port 8080:

1. Test the direct static file access page:
   http://3.82.153.50:8080/static/direct-test.html

2. Test the CSS file directly:
   http://3.82.153.50:8080/static/css/style.css

3. Check directory listing (should show all static files):
   http://3.82.153.50:8080/static/

IMPORTANT: Make sure to update your Security Group in AWS console to allow inbound traffic on port 8080!

If the direct access works but Cloudflare access doesn't:
1. Go to your Cloudflare dashboard
2. Go to the 'DNS' section
3. Find your A record for dragonrise.pro
4. Click the cloud icon to turn it grey (DNS only, not proxied)
5. Save changes

This will bypass Cloudflare's proxy completely for your domain while you troubleshoot.
Once everything works, you can re-enable the Cloudflare proxy.
"