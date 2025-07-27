#!/bin/bash
# Check if Cognito callback URL is properly registered in AWS

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"

echo "Checking Cognito app client configuration in AWS..."

# Create a script to check Cognito app client settings
cat > /tmp/check_cognito_aws.sh << 'EOF'
#!/bin/bash
# Check if the Cognito app client has the correct callback URL

# Get credentials from .env file
ENV_FILE="/home/ec2-user/DragonRise/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: .env file not found!"
    exit 1
fi

# Extract Cognito configuration
USER_POOL_ID=$(grep "COGNITO_USER_POOL_ID" "$ENV_FILE" | cut -d'=' -f2)
CLIENT_ID=$(grep "COGNITO_CLIENT_ID" "$ENV_FILE" | cut -d'=' -f2)
REDIRECT_URI=$(grep "COGNITO_REDIRECT_URI" "$ENV_FILE" | cut -d'=' -f2)

echo "Cognito User Pool ID: $USER_POOL_ID"
echo "Client ID: $CLIENT_ID"
echo "Current redirect URI in .env: $REDIRECT_URI"

# Print information on how to update the app client in AWS
echo ""
echo "==================================================================="
echo "IMPORTANT: The AWS CLI commands to update the app client configuration"
echo "might fail due to permission issues. You need to manually update the"
echo "Cognito app client settings in AWS."
echo ""
echo "Please follow these steps:"
echo ""
echo "1. Log in to the AWS console: https://console.aws.amazon.com/"
echo "2. Go to Amazon Cognito service"
echo "3. Click on 'User Pools' in the left navigation"
echo "4. Select your user pool: $USER_POOL_ID"
echo "5. Go to 'App integration' tab"
echo "6. Scroll down to 'App client list' and select the app client: $CLIENT_ID"
echo "7. Under 'Hosted UI', make sure the following settings are configured:"
echo "   - Allowed callback URLs: $REDIRECT_URI"
echo "   - Allowed sign-out URLs: https://dragonrise.pro/"
echo "   - Identity providers: Cognito user pool"
echo "   - OAuth 2.0 grant types: Authorization code grant"
echo "   - OpenID Connect scopes: email, openid, profile"
echo "8. Save changes"
echo ""
echo "After updating these settings, clear your browser cache and try again."
echo "==================================================================="

# Create instructions for adding a domain name if needed
echo ""
echo "If the app client doesn't have a domain name configured:"
echo "1. Go to 'App integration' tab"
echo "2. Under 'Domain', check if there is a domain name configured"
echo "3. If not, click 'Create Cognito domain'"
echo "4. Enter 'us-east-14qwsyldo1' as the domain prefix"
echo "5. Click 'Create Cognito domain'"
EOF

# Upload and run the script on the server
scp -i "$PEM_KEY" /tmp/check_cognito_aws.sh "$EC2_HOST:/tmp/"
ssh -i "$PEM_KEY" "$EC2_HOST" "chmod +x /tmp/check_cognito_aws.sh && /tmp/check_cognito_aws.sh"

# Clean up
rm /tmp/check_cognito_aws.sh

echo "
=================================================================
NEXT STEPS:

1. Follow the instructions above to manually update the Cognito app client 
   settings in the AWS console

2. After updating the settings, clear your browser cache completely:
   - For Chrome: Settings > Privacy and security > Clear browsing data
   - Select 'Cookies and other site data' and 'Cached images and files'
   - Click 'Clear data'

3. Try logging in again at https://dragonrise.pro/

If the issue persists, it might be related to how the Cognito app client 
is configured in AWS, which requires manual intervention through the AWS console.
=================================================================
"