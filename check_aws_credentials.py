import os
import boto3
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_aws_credentials():
    """Verify AWS credentials are properly configured"""
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    access_key = os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    if not access_key:
        logger.error("AWS_ACCESS_KEY_ID not found in environment variables")
        return False
        
    if not secret_key:
        logger.error("AWS_SECRET_ACCESS_KEY not found in environment variables")
        return False
    
    # Mask the key for security in logs
    masked_key = access_key[:4] + '****' + access_key[-4:] if len(access_key) > 8 else '****'
    logger.info(f"Found AWS_ACCESS_KEY_ID: {masked_key}")
    logger.info(f"AWS_REGION: {region}")
    
    # Test AWS credentials
    try:
        sts = boto3.client(
            'sts',
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        identity = sts.get_caller_identity()
        logger.info(f"AWS credentials verified successfully. Account ID: {identity['Account']}")
        return True
    except Exception as e:
        logger.error(f"AWS credential verification failed: {str(e)}")
        return False
        
if __name__ == "__main__":
    check_aws_credentials()