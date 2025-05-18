#!/bin/bash

# EC2 connection details
EC2_HOST="ec2-user@54.234.216.90"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Fixing AWS Bedrock credentials...${NC}"

# Use the credentials that worked in local test
# Get from test_bedrock.py output
AWS_ACCESS_KEY_ID="AKIAXIYNJBLPGS5JIJW6"
AWS_SECRET_ACCESS_KEY=$(grep -m 1 "AWS_SECRET_ACCESS_KEY" /Users/nat/Git/DragonRise/.env | cut -d '=' -f2)
AWS_REGION="us-east-1"

# Create a temporary script with the correct credential format
cat > /tmp/fix_aws_creds.sh << EOF
#!/bin/bash

# Create AWS config directory
mkdir -p ~/.aws

# Create AWS credentials file with exact format
cat > ~/.aws/credentials << 'CREDS'
[default]
aws_access_key_id=${AWS_ACCESS_KEY_ID}
aws_secret_access_key=${AWS_SECRET_ACCESS_KEY}
region=${AWS_REGION}
CREDS

# Create AWS config file
cat > ~/.aws/config << 'CONFIG'
[default]
region=${AWS_REGION}
output=json
CONFIG

# Set correct permissions
chmod 600 ~/.aws/credentials ~/.aws/config

# Update application .env file with fresh credentials
# Remove any existing AWS credentials first
sed -i '/AWS_ACCESS_KEY_ID/d' /home/ec2-user/DragonRise/.env
sed -i '/AWS_SECRET_ACCESS_KEY/d' /home/ec2-user/DragonRise/.env
sed -i '/AWS_REGION/d' /home/ec2-user/DragonRise/.env

# Add fresh credentials
echo "" >> /home/ec2-user/DragonRise/.env
echo "# AWS Bedrock Configuration" >> /home/ec2-user/DragonRise/.env
echo "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}" >> /home/ec2-user/DragonRise/.env
echo "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}" >> /home/ec2-user/DragonRise/.env
echo "AWS_REGION=${AWS_REGION}" >> /home/ec2-user/DragonRise/.env

echo "AWS credentials have been fixed"
EOF

# Make script executable
chmod +x /tmp/fix_aws_creds.sh

# Upload and run the script on EC2
scp -i "${PEM_KEY}" /tmp/fix_aws_creds.sh "${EC2_HOST}:/tmp/"
ssh -i "${PEM_KEY}" "${EC2_HOST}" "bash /tmp/fix_aws_creds.sh"

# Clean up local temp file
rm /tmp/fix_aws_creds.sh

# Restart the DragonRise service
ssh -i "${PEM_KEY}" "${EC2_HOST}" "sudo systemctl restart dragonrise"

echo -e "${GREEN}AWS credentials have been fixed and service restarted${NC}"
echo -e "${YELLOW}Try uploading an image again to test Bedrock functionality${NC}"