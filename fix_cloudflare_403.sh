#!/bin/bash
# Fix Cloudflare 403 error for static files

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"

echo "Fixing Cloudflare 403 Forbidden error for static files..."

# 1. Fix permissions on the server side with more aggressive approach
ssh -i "$PEM_KEY" "$EC2_HOST" "
    echo 'Setting proper permissions for all static files...'
    # Ensure everyone can read the static directory and all its contents
    sudo chmod -R 755 $APP_DIR/static
    sudo find $APP_DIR/static -type f -exec chmod 644 {} \;
    
    # Ensure Nginx user can access the files
    sudo chown -R ec2-user:ec2-user $APP_DIR/static
    
    # Double-check the CSS file specifically
    echo 'Verifying style.css permissions:'
    ls -la $APP_DIR/static/css/style.css
    
    # Make sure style.css has proper permissions
    chmod 644 $APP_DIR/static/css/style.css
    
    # Make sure the parent directories are accessible
    chmod 755 $APP_DIR/static/css
    chmod 755 $APP_DIR/static
    
    # Show the final state
    echo 'Directory structure permissions:'
    ls -la $APP_DIR/static
    ls -la $APP_DIR/static/css
"

# 2. Update Nginx configuration for better Cloudflare compatibility
cat > /tmp/cloudflare-nginx-fix.conf << 'EOF'
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
    
    # Main application proxy
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Static files with simplified configuration
    location /static/ {
        root /home/ec2-user/DragonRise;
        autoindex off;
        try_files $uri =404;
        add_header Access-Control-Allow-Origin "*";
        expires 7d;
    }
}
EOF

# Upload and apply the new Nginx configuration
scp -i "$PEM_KEY" /tmp/cloudflare-nginx-fix.conf "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "
    sudo mv /tmp/cloudflare-nginx-fix.conf /etc/nginx/conf.d/dragonrise.conf
    
    # Test the Nginx configuration
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

# 3. Cloudflare cache purge instructions
echo "
========================================
IMPORTANT CLOUDFLARE STEPS
========================================
1. Log in to your Cloudflare account
2. Go to your dragonrise.pro domain
3. Go to 'Caching' > 'Configuration'
4. Click on 'Purge Cache' > 'Purge Everything'
5. Check your Cloudflare SSL/TLS settings:
   - Set SSL/TLS encryption mode to 'Full'
   - Enable 'Always Use HTTPS'

If you're still experiencing issues, you might need to temporarily:
1. Set Cloudflare to 'Development Mode' in the 'Overview' section
2. This will bypass Cloudflare's cache for 3 hours
"

echo "The changes have been applied. After following the Cloudflare steps above, try accessing https://dragonrise.pro/static/css/style.css again."