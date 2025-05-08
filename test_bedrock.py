import os
import boto3
import json
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def test_bedrock_access():
    """Test AWS Bedrock access and permissions"""
    
    # Print AWS credentials (partially masked)
    access_key = os.getenv('AWS_ACCESS_KEY_ID', '')
    secret_key = os.getenv('AWS_SECRET_ACCESS_KEY', '')
    region = os.getenv('AWS_REGION', 'us-east-1')
    
    if access_key and secret_key:
        print(f"Using AWS Access Key: {access_key[:5]}...{access_key[-3:]}")
        print(f"Secret Key length: {len(secret_key)} characters")
        print(f"Region: {region}")
    else:
        print("❌ AWS credentials not found in environment variables")
        return
    
    # Test bedrock client for listing models
    try:
        print("\nTesting bedrock client...")
        bedrock = boto3.client('bedrock', 
                              region_name=region,
                              aws_access_key_id=access_key,
                              aws_secret_access_key=secret_key)
        
        response = bedrock.list_foundation_models()
        print("✅ Successfully listed foundation models\n")
        
        # Print available models
        print("Available models:")
        for model in response['modelSummaries']:
            print(f"- {model['modelId']}")
        
    except Exception as e:
        print(f"❌ Error listing models: {str(e)}")
        return
    
    # Test bedrock-runtime client for invoking a model
    try:
        print("\nTesting bedrock-runtime client...")
        bedrock_runtime = boto3.client('bedrock-runtime',
                                      region_name=region,
                                      aws_access_key_id=access_key,
                                      aws_secret_access_key=secret_key)
        
        # Try to find a suitable model to test
        available_models = [model['modelId'] for model in response['modelSummaries']]
        
        # Only use Claude 3.7 Sonnet model for testing
        preferred_model = "anthropic.claude-3-7-sonnet-20250219-v1:0"
        
        print(f"Limiting test to only use model: {preferred_model}")
        
        # Check if preferred model is available
        if preferred_model in available_models:
            test_model = preferred_model
            print(f"✅ Preferred model {preferred_model} is available")
        else:
            print(f"❌ Preferred model {preferred_model} is not available")
            print("Available models:")
            for model in response['modelSummaries']:
                print(f"- {model['modelId']}")
            print("\nExiting test since the required model is not available")
            return
        
        # Check model status
        model_info = bedrock.get_foundation_model(modelIdentifier=test_model)
        print(f"\nChecking model access...")
        print(f"Model status: {model_info.get('modelLifecycle', {}).get('status', 'UNKNOWN')}")
        
        # Try the model
        print(f"Selected model for testing: {test_model}")

        # Prepare request body for Claude 3.7 Sonnet
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 10,
            "messages": [
                {
                    "role": "user",
                    "content": "Hello"
                }
            ]
        })
        
        # Try to invoke the model
        response = bedrock_runtime.invoke_model(
            modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            contentType='application/json',
            accept='application/json',
            body=body
        )
        
        print(f"✅ Successfully invoked model: {test_model}")
        
    except Exception as e:
        print(f"❌ Error invoking model: {str(e)}")
        print("\nThis is an access denied error. Possible causes:")
        print("1. The IAM policy doesn't have the correct permissions")
        print("2. There's an explicit deny somewhere in your account")
        print("3. The model hasn't been enabled in Bedrock Model access")
        print("4. The model ID is incorrect")

if __name__ == "__main__":
    test_bedrock_access()