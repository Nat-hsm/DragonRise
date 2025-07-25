#!/bin/bash
# Simple S3 sync script without ACL flags

# Configuration
S3_BUCKET="dragonrise-static"
LOCAL_STATIC_DIR="/Users/nat/Git/DragonRise/static"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Load AWS credentials from .env file
source /Users/nat/Git/DragonRise/.env

echo -e "${GREEN}Syncing static files to S3...${NC}"

# Create temporary AWS config files to ensure the CLI uses our credentials
mkdir -p ~/.aws
cat > ~/.aws/credentials << EOF
[default]
aws_access_key_id = $AWS_ACCESS_KEY_ID
aws_secret_access_key = $AWS_SECRET_ACCESS_KEY
EOF

cat > ~/.aws/config << EOF
[default]
region = ${AWS_REGION:-us-east-1}
output = json
EOF

chmod 600 ~/.aws/credentials ~/.aws/config

# Check if static directory exists
if [ ! -d "$LOCAL_STATIC_DIR" ]; then
    echo -e "${RED}Static directory not found at $LOCAL_STATIC_DIR${NC}"
    exit 1
fi

# Sync files to S3 (without ACL flag)
echo -e "${YELLOW}Uploading files...${NC}"
aws s3 sync "$LOCAL_STATIC_DIR" "s3://$S3_BUCKET/static/"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Successfully synced static files to S3!${NC}"
    echo -e "${YELLOW}Files are accessible at: https://$S3_BUCKET.s3.us-east-1.amazonaws.com/static/${NC}"
    
    # List files in the S3 bucket
    echo -e "${YELLOW}Files in S3 bucket:${NC}"
    aws s3 ls "s3://$S3_BUCKET/static/" --recursive --human-readable --summarize
else
    echo -e "${RED}Failed to sync files to S3. Check AWS logs for more details.${NC}"
    exit 1
fi

# Configure S3 bucket for static website hosting
echo -e "${YELLOW}Configuring S3 bucket for static website hosting...${NC}"
aws s3 website "s3://$S3_BUCKET" --index-document index.html --error-document error.html

echo -e "${GREEN}S3 static website endpoint: http://$S3_BUCKET.s3-website-us-east-1.amazonaws.com/${NC}"
echo -e "${GREEN}S3 direct URL format: https://$S3_BUCKET.s3.us-east-1.amazonaws.com/static/css/style.css${NC}"

# Verify access
echo -e "${YELLOW}Testing access to a sample CSS file...${NC}"
curl -s -o /dev/null -w "%{http_code}" "https://$S3_BUCKET.s3.us-east-1.amazonaws.com/static/css/style.css"

echo -e "\n${GREEN}All done! Your static files are now hosted on S3.${NC}"
echo -e "${YELLOW}Make sure your app is configured to use: https://$S3_BUCKET.s3.us-east-1.amazonaws.com/static/${NC}"