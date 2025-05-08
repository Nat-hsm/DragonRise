import json
import boto3
import logging

def check_bedrock_health():
    try:
        # First, list available models to find one we can use
        bedrock_client = boto3.client('bedrock')
        models_response = bedrock_client.list_foundation_models()
        available_models = [model['modelId'] for model in models_response['modelSummaries']]
        
        # Try to find a suitable Claude model that's enabled
        claude_models = [model for model in available_models if 'claude' in model.lower()]
        
        # If no Claude models are available, try any available model
        model_to_use = claude_models[0] if claude_models else available_models[0]
        
        logging.info(f"Attempting to use model: {model_to_use}")
        
        # Create the runtime client for invocation
        bedrock = boto3.client('bedrock-runtime')
        
        # Prepare the appropriate request body based on the model
        if 'claude' in model_to_use.lower():
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 5,
                "messages": [
                    {
                        "role": "user",
                        "content": "Test"
                    }
                ]
            })
        else:
            # Generic format for other models (adjust as needed)
            body = json.dumps({
                "prompt": "Test",
                "max_tokens": 5
            })
        
        # Try to invoke model with minimal prompt
        response = bedrock.invoke_model(
            modelId=model_to_use,
            contentType='application/json',
            accept='application/json',
            body=body
        )
        return True
    except Exception as e:
        logging.error(f"Bedrock health check failed: {str(e)}")
        return False