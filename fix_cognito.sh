#!/bin/bash

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"
APP_DIR="/home/ec2-user/DragonRise"

# Create updated Cognito configuration
echo "Updating Cognito configuration..."
cat > /tmp/cognito.env << 'EOF'
# Cognito Configuration
COGNITO_USER_POOL_ID=us-east-1_4qwsylDo1
COGNITO_CLIENT_ID=3mn0rluusoslnjqa7dk2sriaec
COGNITO_CLIENT_SECRET=b1nnfg3irtrtt8eoi8lnddhue1fjn5snnch82d3demouvshkg82
COGNITO_DOMAIN=dragonrise.pro
COGNITO_REDIRECT_URI=https://dragonrise.pro/auth/callback
AWS_REGION=us-east-1
EOF

# Copy to the server
scp -i "$PEM_KEY" /tmp/cognito.env "$EC2_HOST:/tmp/"

# Append to .env file on the server and restart
ssh -i "$PEM_KEY" "$EC2_HOST" "cat /tmp/cognito.env >> $APP_DIR/.env && chmod 600 $APP_DIR/.env && sudo systemctl restart dragonrise"

echo "Cognito configuration updated and service restarted."