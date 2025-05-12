#!/bin/bash
# Script to verify DragonRise deployment

# Configuration
EC2_HOST="ec2-user@54.234.216.90"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Verifying DragonRise deployment...${NC}"

# Check service status
echo -e "${YELLOW}Service status:${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl status dragonrise | grep Active"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo systemctl status nginx | grep Active"

# Check application logs
echo -e "${YELLOW}Application logs:${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo tail -n 20 /var/log/dragonrise/error.log || echo 'No log file yet'"

# Check Nginx logs
echo -e "${YELLOW}Nginx logs:${NC}"
ssh -i "$PEM_KEY" "$EC2_HOST" "sudo tail -n 10 /var/log/nginx/error.log || echo 'No nginx error log yet'"

# Test HTTPS response
echo -e "${YELLOW}HTTPS accessibility:${NC}"
curl -k -I https://54.234.216.90

echo -e "${GREEN}Verification complete${NC}"