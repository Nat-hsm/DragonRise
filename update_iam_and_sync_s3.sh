#!/bin/bash
# Update IAM user permissions and sync static files to S3

# Configuration
S3_BUCKET="dragonrise-static"
LOCAL_STATIC_DIR="/Users/nat/Git/DragonRise/static"
IAM_USER="dragonrise-bedrock-user"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Load AWS credentials from .env file
source /Users/nat/Git/DragonRise/.env

echo -e "${GREEN}Updating IAM user permissions and syncing static files to S3...${NC}"

# Verify AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}AWS CLI is not installed. Please install it first.${NC}"
    exit 1
fi

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

# Verify IAM credentials
echo -e "${YELLOW}Verifying IAM credentials...${NC}"
IAM_INFO=$(aws sts get-caller-identity)
USER_ARN=$(echo $IAM_INFO | jq -r '.Arn')
ACCOUNT_ID=$(echo $IAM_INFO | jq -r '.Account')

echo -e "${GREEN}Authenticated as: $USER_ARN${NC}"

# Create IAM policy document for S3 access
echo -e "${YELLOW}Creating S3 access policy...${NC}"
cat > /tmp/s3_policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:ListAllMyBuckets"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:ListBucket",
                "s3:GetBucketLocation",
                "s3:CreateBucket",
                "s3:PutBucketPolicy",
                "s3:PutBucketPublicAccessBlock"
            ],
            "Resource": "arn:aws:s3:::${S3_BUCKET}"
        },
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject",
                "s3:PutObjectAcl"
            ],
            "Resource": "arn:aws:s3:::${S3_BUCKET}/*"
        }
    ]
}
EOF

# Create the policy in AWS
POLICY_NAME="DragonRiseS3AccessPolicy"
echo -e "${YELLOW}Creating IAM policy: $POLICY_NAME...${NC}"

EXISTING_POLICY=$(aws iam list-policies --query "Policies[?PolicyName=='$POLICY_NAME'].Arn" --output text)

if [ -z "$EXISTING_POLICY" ]; then
    POLICY_ARN=$(aws iam create-policy --policy-name $POLICY_NAME --policy-document file:///tmp/s3_policy.json --query 'Policy.Arn' --output text)
    echo -e "${GREEN}Created policy: $POLICY_ARN${NC}"
else
    POLICY_ARN=$EXISTING_POLICY
    echo -e "${YELLOW}Policy already exists: $POLICY_ARN${NC}"
    
    # Update the existing policy
    aws iam create-policy-version --policy-arn $POLICY_ARN --policy-document file:///tmp/s3_policy.json --set-as-default
    echo -e "${GREEN}Updated policy: $POLICY_ARN${NC}"
fi

# Attach the policy to the IAM user
echo -e "${YELLOW}Attaching policy to IAM user: $IAM_USER...${NC}"
aws iam attach-user-policy --user-name $IAM_USER --policy-arn $POLICY_ARN
echo -e "${GREEN}Policy attached to user: $IAM_USER${NC}"

# Wait for permissions to propagate
echo -e "${YELLOW}Waiting 10 seconds for permissions to propagate...${NC}"
sleep 10

# Create the S3 bucket if it doesn't exist
echo -e "${YELLOW}Checking if bucket exists...${NC}"
if ! aws s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null; then
    echo -e "${YELLOW}Creating S3 bucket: $S3_BUCKET${NC}"
    
    # Create bucket in us-east-1 region (special case with no LocationConstraint)
    if [ "$AWS_REGION" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "$S3_BUCKET"
    else
        aws s3api create-bucket --bucket "$S3_BUCKET" --create-bucket-configuration LocationConstraint="$AWS_REGION"
    fi
    
    # Disable block public access settings to allow public read
    aws s3api put-public-access-block --bucket "$S3_BUCKET" --public-access-block-configuration "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"
    
    # Set bucket policy to allow public read access
    echo -e "${YELLOW}Setting bucket policy for public read access...${NC}"
    cat > /tmp/bucket-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "PublicReadGetObject",
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::$S3_BUCKET/*"
        }
    ]
}
EOF
    aws s3api put-bucket-policy --bucket "$S3_BUCKET" --policy file:///tmp/bucket-policy.json
fi

# Check if static directory exists
if [ ! -d "$LOCAL_STATIC_DIR" ]; then
    echo -e "${RED}Static directory not found at $LOCAL_STATIC_DIR${NC}"
    exit 1
fi

# Sync files to S3
echo -e "${YELLOW}Uploading files...${NC}"
aws s3 sync "$LOCAL_STATIC_DIR" "s3://$S3_BUCKET/static/" --acl public-read

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Successfully synced static files to S3!${NC}"
    echo -e "${YELLOW}Files are accessible at: https://$S3_BUCKET.s3.${AWS_REGION}.amazonaws.com/static/${NC}"
    
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

echo -e "${GREEN}S3 static website endpoint: http://$S3_BUCKET.s3-website-${AWS_REGION}.amazonaws.com/${NC}"
echo -e "${GREEN}S3 direct URL format: https://$S3_BUCKET.s3.${AWS_REGION}.amazonaws.com/static/css/style.css${NC}"

# Verify access
echo -e "${YELLOW}Testing access to a sample CSS file...${NC}"
curl -s -o /dev/null -w "%{http_code}" "https://$S3_BUCKET.s3.${AWS_REGION}.amazonaws.com/static/css/style.css"

echo -e "\n${GREEN}All done! Your static files are now hosted on S3.${NC}"
echo -e "${YELLOW}Make sure your app is configured to use: https://$S3_BUCKET.s3.${AWS_REGION}.amazonaws.com/static/${NC}"