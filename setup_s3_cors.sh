#!/bin/bash
# Configure CORS for S3 bucket

# Configuration
S3_BUCKET="dragonrise-static"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Setting up CORS configuration for S3 bucket: $S3_BUCKET${NC}"

# Create CORS configuration file
cat > /tmp/cors.json << EOF
{
  "CORSRules": [
    {
      "AllowedOrigins": ["*"],
      "AllowedHeaders": ["*"],
      "AllowedMethods": ["GET", "HEAD"],
      "MaxAgeSeconds": 3000
    }
  ]
}
EOF

# Apply CORS configuration
aws s3api put-bucket-cors --bucket $S3_BUCKET --cors-configuration file:///tmp/cors.json

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Successfully configured CORS for S3 bucket!${NC}"
else
    echo -e "${RED}Failed to configure CORS. Check your AWS credentials and bucket permissions.${NC}"
    exit 1
fi

# Clean up
rm /tmp/cors.json

echo -e "${GREEN}Done!${NC}"