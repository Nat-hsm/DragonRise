#!/bin/bash
# Script to sync static files to S3 and deploy app to EC2

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting complete deployment process...${NC}"

# Step 1: Sync static files to S3
echo -e "${YELLOW}Syncing static files to S3...${NC}"
./sync_static_to_s3.sh
if [ $? -ne 0 ]; then
    echo -e "${RED}S3 sync failed. Aborting deployment.${NC}"
    exit 1
fi

# Step 2: Deploy application to EC2
echo -e "${YELLOW}Deploying application to EC2...${NC}"
./deploy_with_s3.sh
if [ $? -ne 0 ]; then
    echo -e "${RED}EC2 deployment failed.${NC}"
    exit 1
fi

echo -e "${GREEN}Complete deployment process finished successfully!${NC}"
echo -e "${YELLOW}Your application should now be accessible at https://dragonrise.pro${NC}"
echo -e "${YELLOW}Static files are being served from S3 at: https://dragonrise-static.s3.us-east-1.amazonaws.com/static/${NC}"