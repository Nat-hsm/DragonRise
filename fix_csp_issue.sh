#!/bin/bash
# Script to fix CSP issue and S3 static file access on EC2 instance

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"
S3_BUCKET="dragonrise-static"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Fixing S3 static file issues comprehensively...${NC}"

# Check if PEM key exists
if [ ! -f "$PEM_KEY" ]; then
    echo -e "${RED}PEM key not found at $PEM_KEY${NC}"
    exit 1
fi

# Ensure PEM key has correct permissions
chmod 400 "$PEM_KEY"

# Create the comprehensive S3 fix
cat > /tmp/s3_fix.py << 'EOF'
#!/usr/bin/env python3
"""
Comprehensive script to fix S3 static file loading issues in app_fixed.py
"""
import re

def apply_comprehensive_fix():
    # Path to the app_fixed.py file
    app_fixed_path = "/home/ec2-user/DragonRise/app_fixed.py"
    
    # Read the current content of app_fixed.py
    with open(app_fixed_path, 'r') as f:
        content = f.read()
    
    # PART 1: Add or update security headers with enhanced CSP
    if "@app.after_request\ndef add_security_headers" in content:
        print("Updating existing security headers...")
        # Use regex to find and replace the security headers function
        security_pattern = r'@app\.after_request\s*def\s+add_security_headers.*?return\s+response'
        
        # New security headers function with updated CSP and referrer policy
        new_security_function = """@app.after_request
def add_security_headers(response):
    \"\"\"Add security headers to all responses\"\"\"
    # Update CSP to allow S3 bucket for static resources
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://dragonrise-static.s3.us-east-1.amazonaws.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://dragonrise-static.s3.us-east-1.amazonaws.com; "
        "font-src 'self' https://cdn.jsdelivr.net https://dragonrise-static.s3.us-east-1.amazonaws.com; "
        "img-src 'self' data: https://dragonrise-static.s3.us-east-1.amazonaws.com; "
        "connect-src 'self' https://dragonrise-static.s3.us-east-1.amazonaws.com; "
        "object-src 'none';"
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'origin'
    return response"""
        
        # Replace existing function
        content = re.sub(security_pattern, new_security_function, content, flags=re.DOTALL)
    else:
        print("Adding new security headers function...")
        # Find a good place to insert - after allowed_file function
        allowed_file_pattern = "def allowed_file(filename):"
        allowed_file_index = content.find(allowed_file_pattern)
        
        if allowed_file_index == -1:
            # If allowed_file function not found, try to find the end of signup function
            signup_pattern = "@app.route('/signup')"
            signup_index = content.find(signup_pattern)
            
            if signup_index != -1:
                # Find the end of the signup function
                function_end = content.find('\n\n', signup_index)
                if function_end == -1:
                    function_end = content.find('if __name__', signup_index)
                    if function_end == -1:
                        function_end = len(content)
            else:
                # Just add before __main__ check
                function_end = content.find('if __name__')
                if function_end == -1:
                    function_end = len(content)
        else:
            # Find the end of the allowed_file function
            function_end = content.find('\n\n', allowed_file_index)
            if function_end == -1:
                function_end = content.find('if __name__', allowed_file_index)
                if function_end == -1:
                    function_end = len(content)
        
        # Security headers function to add
        security_function = """

@app.after_request
def add_security_headers(response):
    \"\"\"Add security headers to all responses\"\"\"
    # Update CSP to allow S3 bucket for static resources
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://dragonrise-static.s3.us-east-1.amazonaws.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://dragonrise-static.s3.us-east-1.amazonaws.com; "
        "font-src 'self' https://cdn.jsdelivr.net https://dragonrise-static.s3.us-east-1.amazonaws.com; "
        "img-src 'self' data: https://dragonrise-static.s3.us-east-1.amazonaws.com; "
        "connect-src 'self' https://dragonrise-static.s3.us-east-1.amazonaws.com; "
        "object-src 'none';"
    )
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'origin'
    return response
"""
        # Insert security function
        content = content[:function_end] + '\n' + security_function + content[function_end:]
    
    # PART 2: Add or update the STATIC_URL configuration
    if "app.config['STATIC_URL']" not in content:
        print("Adding S3 static URL configuration...")
        # Find where to add the configuration - before the override_url_for function
        context_processor_index = content.find("@app.context_processor")
        
        if context_processor_index == -1:
            # If no context processor exists, add it before __main__
            insert_index = content.find('if __name__')
            if insert_index == -1:
                insert_index = len(content)
            
            # Add both STATIC_URL config and override_url_for function
            static_config = """
# Add S3 static file configuration
app.config['STATIC_URL'] = 'https://dragonrise-static.s3.us-east-1.amazonaws.com/static/'

# Create a custom template context processor to override url_for('static', ...)
@app.context_processor
def override_url_for():
    def url_for(endpoint, **kwargs):
        if endpoint == 'static':
            return app.config['STATIC_URL'] + kwargs.get('filename', '')
        # Use the original url_for for all other endpoints
        from flask import url_for as flask_url_for
        return flask_url_for(endpoint, **kwargs)
    return dict(url_for=url_for)
"""
            content = content[:insert_index] + static_config + content[insert_index:]
        else:
            # Add STATIC_URL config before context processor
            static_config = """
# Add S3 static file configuration
app.config['STATIC_URL'] = 'https://dragonrise-static.s3.us-east-1.amazonaws.com/static/'

"""
            content = content[:context_processor_index] + static_config + content[context_processor_index:]
    else:
        print("S3 static URL configuration already exists")
    
    # PART 3: Ensure override_url_for function exists and is correct
    if "@app.context_processor\ndef override_url_for" not in content:
        print("Adding override_url_for function...")
        # Find where to add the function
        insert_index = content.find('if __name__')
        if insert_index == -1:
            insert_index = len(content)
        
        # Add override_url_for function
        url_for_function = """
# Create a custom template context processor to override url_for('static', ...)
@app.context_processor
def override_url_for():
    def url_for(endpoint, **kwargs):
        if endpoint == 'static':
            return app.config['STATIC_URL'] + kwargs.get('filename', '')
        # Use the original url_for for all other endpoints
        from flask import url_for as flask_url_for
        return flask_url_for(endpoint, **kwargs)
    return dict(url_for=url_for)
"""
        content = content[:insert_index] + url_for_function + content[insert_index:]
    
    # PART 4: Make sure signup route exists
    if "@app.route('/signup')" not in content:
        print("Adding signup route...")
        # Find where to add the route
        insert_index = content.find('if __name__')
        if insert_index == -1:
            insert_index = len(content)
        
        # Add signup route
        signup_route = """
@app.route('/signup')
def signup():
    \"\"\"Route for signup - redirects to register page\"\"\"
    return redirect(url_for('register'))
"""
        content = content[:insert_index] + signup_route + content[insert_index:]
    
    # Write the updated content back to the file
    with open(app_fixed_path, 'w') as f:
        f.write(content)
    
    print("Successfully applied comprehensive S3 static file fixes to app_fixed.py")

if __name__ == "__main__":
    apply_comprehensive_fix()
EOF

# Copy the fix script to EC2
scp -i "$PEM_KEY" /tmp/s3_fix.py "$EC2_HOST:$APP_DIR/"

# Execute the fix on EC2
echo -e "${YELLOW}Applying comprehensive S3 fixes on EC2...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "cd $APP_DIR && python3 s3_fix.py"

# Configure S3 bucket CORS
echo -e "${YELLOW}Configuring S3 bucket CORS...${NC}"
cat > /tmp/configure_s3_cors.sh << EOF
#!/bin/bash
# Configure CORS on S3 bucket

# Make sure AWS CLI is installed
command -v aws >/dev/null 2>&1 || { 
    echo "AWS CLI is required but not installed. Installing..."
    pip install awscli
}

# Create CORS configuration file
cat > /tmp/cors-config.json << 'EOCORS'
{
    "CORSRules": [
        {
            "AllowedHeaders": ["*"],
            "AllowedMethods": ["GET", "HEAD"],
            "AllowedOrigins": ["*"],
            "ExposeHeaders": ["ETag", "Content-Length", "Content-Type"],
            "MaxAgeSeconds": 3000
        }
    ]
}
EOCORS

# Apply CORS configuration to S3 bucket
aws s3api put-bucket-cors --bucket ${S3_BUCKET} --cors-configuration file:///tmp/cors-config.json

echo "CORS configuration applied to S3 bucket: ${S3_BUCKET}"
EOF

# Copy and run S3 CORS configuration script
scp -i "$PEM_KEY" /tmp/configure_s3_cors.sh "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod +x /tmp/configure_s3_cors.sh && /tmp/configure_s3_cors.sh"

# Update Nginx configuration for better CORS handling
echo -e "${YELLOW}Updating Nginx configuration...${NC}"
cat > /tmp/nginx-s3-config.conf << 'EOF'
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
    
    # Global CORS headers
    add_header 'Access-Control-Allow-Origin' '*' always;
    add_header 'Access-Control-Allow-Methods' 'GET, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Content-Type, Origin, Referer' always;
    add_header 'Referrer-Policy' 'origin' always;
    
    # Main application proxy
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Redirect static requests to S3
    location /static/ {
        # Handle OPTIONS requests for CORS preflight
        if ($request_method = OPTIONS) {
            add_header 'Access-Control-Allow-Origin' '*';
            add_header 'Access-Control-Allow-Methods' 'GET, OPTIONS';
            add_header 'Access-Control-Allow-Headers' 'Content-Type, Origin, Referer';
            add_header 'Access-Control-Max-Age' '3000';
            add_header 'Content-Type' 'text/plain charset=UTF-8';
            add_header 'Content-Length' '0';
            return 204;
        }
        
        # For regular requests, redirect to S3
        return 301 https://dragonrise-static.s3.us-east-1.amazonaws.com$request_uri;
    }
}
EOF

# Upload and apply the new Nginx configuration
scp -i "$PEM_KEY" /tmp/nginx-s3-config.conf "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo mv /tmp/nginx-s3-config.conf /etc/nginx/conf.d/dragonrise.conf && sudo nginx -t && sudo systemctl restart nginx"

# Create a simple test page to verify static file loading
echo -e "${YELLOW}Creating test page...${NC}"
cat > /tmp/test.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>S3 Static Files Test</title>
    <link rel="stylesheet" href="https://dragonrise-static.s3.us-east-1.amazonaws.com/static/css/style.css">
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        .success { color: green; font-weight: bold; }
        .error { color: red; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>S3 Static Files Test</h1>
        <p>This page tests if S3 static files are loading properly.</p>
        
        <div id="status">Checking CSS loading...</div>
        
        <div class="box house-card" style="margin-top: 20px;">
            If this box has styling from S3, the static files are working!
        </div>
    </div>
    
    <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Check if CSS loaded
            const styleSheets = Array.from(document.styleSheets);
            const s3StyleSheet = styleSheets.find(sheet => 
                sheet.href && sheet.href.includes('dragonrise-static.s3'));
            
            const statusDiv = document.getElementById('status');
            if (s3StyleSheet) {
                statusDiv.textContent = '✅ SUCCESS: S3 CSS file loaded successfully!';
                statusDiv.className = 'success';
            } else {
                statusDiv.textContent = '❌ ERROR: S3 CSS file failed to load';
                statusDiv.className = 'error';
                console.error('S3 stylesheet not found among:', styleSheets.map(s => s.href));
            }
        });
    </script>
</body>
</html>
EOF

# Upload the test page
scp -i "$PEM_KEY" /tmp/test.html "$EC2_HOST:$APP_DIR/static/s3test.html"

# Restart the application
echo -e "${YELLOW}Restarting application...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl restart dragonrise"

# Check the application status
echo -e "${YELLOW}Checking service status...${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl status dragonrise --no-pager && sudo systemctl status nginx --no-pager"

echo -e "${GREEN}All fixes have been applied!${NC}"
echo -e "${YELLOW}Try accessing your application now at https://dragonrise.pro${NC}"
echo -e "${YELLOW}You can also test S3 static file loading directly at: https://dragonrise.pro/static/s3test.html${NC}"
echo -e "${YELLOW}Remember to clear your browser cache or use incognito mode for testing.${NC}"