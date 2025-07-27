#!/bin/bash

# Configuration
EC2_HOST="ec2-user@3.82.153.50"
PEM_KEY="/Users/nat/Git/DragonRise/DragonRiseKey.pem"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Checking if test app is working...${NC}"
# Connect to the server and check test app
TEST_APP_WORKING=$(ssh -i "$PEM_KEY" "$EC2_HOST" "curl -s http://localhost:8000/ | grep -q 'WSGI Test Application' && echo 'yes' || echo 'no'")

if [ "$TEST_APP_WORKING" = "yes" ]; then
    echo -e "${GREEN}Test app is working! Proceeding to restore original app...${NC}"
    
    # Create server-side restoration script
    cat > /tmp/restore_original_app.sh << 'RESTORE_SCRIPT'
#!/bin/bash

echo "Updating service file to use original app..."
sudo sed -i 's/test_wsgi:app/wsgi:app/g' /etc/systemd/system/dragonrise.service

echo "Reloading systemd and restarting services..."
sudo systemctl daemon-reload
sudo systemctl restart dragonrise

echo "Waiting for app to start..."
sleep 10

echo "Checking if original app is working..."
if curl -s http://localhost:8000/ | grep -q "DragonRise"; then
    echo "SUCCESS: Original app is working correctly!"
else
    echo "WARNING: Original app is not responding properly."
    echo "Checking for errors..."
    sudo journalctl -u dragonrise -n 20
fi
RESTORE_SCRIPT
    
    # Upload and execute restoration script
    scp -i "$PEM_KEY" /tmp/restore_original_app.sh "$EC2_HOST:/tmp/"
    ssh -i "$PEM_KEY" "$EC2_HOST" "chmod +x /tmp/restore_original_app.sh && /tmp/restore_original_app.sh"
    
    echo -e "${YELLOW}Checking if website is accessible...${NC}"
    echo -e "${GREEN}Please visit https://dragonrise.pro in your browser to verify it works.${NC}"
    echo -e "${YELLOW}If the site is working, the fix was successful!${NC}"
else
    echo -e "${RED}Test app is not working. Additional debugging required.${NC}"
    echo -e "${YELLOW}Please check the server logs and configuration.${NC}"
    
    # Collect more detailed diagnostics
    ssh -i "$PEM_KEY" "$EC2_HOST" "sudo journalctl -u dragonrise -n 50"
    
    echo -e "${YELLOW}To resolve this issue, you may need to:${NC}"
    echo -e "1. Check if Gunicorn is running: ${BLUE}sudo systemctl status dragonrise${NC}"
    echo -e "2. Check Gunicorn logs: ${BLUE}sudo journalctl -u dragonrise${NC}"
    echo -e "3. Test the app manually: ${BLUE}cd /home/ec2-user/DragonRise && source venv/bin/activate && python test_wsgi.py${NC}"
fi
