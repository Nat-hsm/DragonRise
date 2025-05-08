import boto3
import json
import base64
import os
from io import BytesIO
from PIL import Image
import logging
from datetime import datetime, timezone

class ImageAnalyzer:
    def __init__(self):
        """Initialize Bedrock client"""
        self.logger = logging.getLogger('bedrock_monitor')
        self.monitor = None  # For future monitoring implementation
        
        # Initialize Bedrock clients
        try:
            # First get a list of available models
            self.bedrock = boto3.client(
                'bedrock',
                region_name=os.getenv('AWS_REGION', 'us-east-1'),
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )
            
            # Initialize the runtime client for invocation
            self.client = boto3.client(
                'bedrock-runtime', 
                region_name=os.getenv('AWS_REGION', 'us-east-1'),
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
            )
            self.logger.info("Amazon Bedrock clients initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize Amazon Bedrock clients: {str(e)}")
            self.bedrock = None
            self.client = None
        
    def analyze_image(self, image_file):
        """
        Analyze a health app screenshot to extract flights climbed and timestamp
        
        Args:
            image_file: The uploaded image file
        
        Returns:
            dict: Analysis results with flights and timestamp
        """
        try:
            # Read and resize image to reduce size
            image = Image.open(image_file)
            
            # Resize image if it's too large (keep aspect ratio)
            max_size = 1600
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
                image = image.resize(new_size, Image.LANCZOS)
            
            # Convert to base64
            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # Prepare request for Claude
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": "This is a screenshot from a health tracking app showing stairs climbed. Extract the exact number of flights climbed and the timestamp when this activity occurred. Reply in JSON format with two fields: 'flights' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM). If you can't determine one of these values, set it to null."
                            }
                        ]
                    }
                ],
                "temperature": 0.2
            }
            
            # Get available models from Bedrock
            available_models = []
            try:
                if self.bedrock:
                    models_response = self.bedrock.list_foundation_models()
                    available_models = [model['modelId'] for model in models_response['modelSummaries']]
                    self.logger.info(f"Found {len(available_models)} available Bedrock models")
            except Exception as e:
                self.logger.error(f"Error listing Bedrock models: {str(e)}")
            
            # Limit to ONLY Claude 3.7 Sonnet as the preferred model
            preferred_model = "anthropic.claude-3-7-sonnet-20250219-v1:0"
            
            # Check if the preferred model is available
            if preferred_model in available_models:
                models_to_try = [preferred_model]
                self.logger.info(f"Using preferred model: {preferred_model}")
            else:
                self.logger.warning(f"Preferred model {preferred_model} not available")
                # Only use a fallback if absolutely necessary
                models_to_try = []
                
                # Add fallbacks only if our preferred model is unavailable
                if not models_to_try:
                    self.logger.info("Falling back to other Claude models")
                    claude_models = [m for m in available_models if 'claude' in m.lower()]
                    if claude_models:
                        models_to_try = claude_models[:1]  # Just the first Claude model
            
            # If no models are available, add the preferred model anyway
            # (it might become available later)
            if not models_to_try:
                self.logger.warning("No models available, using preferred model as fallback")
                models_to_try = [preferred_model]
            
            response = None
            model_used = None
            
            # Try each model until one works
            for model in models_to_try:
                try:
                    self.logger.info(f"Attempting to use model: {model}")
                    
                    # Adjust request body format based on model type
                    current_body = request_body.copy()
                    
                    # For non-Claude models (Amazon Titan etc), use a different format
                    if not model.startswith('anthropic.'):
                        # Format for Amazon Titan Image models
                        if 'image' in model.lower() or 'tg1' in model.lower():
                            prompt_text = "This is a screenshot from a health tracking app showing stairs climbed. Extract the exact number of flights climbed and the timestamp when this activity occurred. Reply in JSON format with two fields: 'flights' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM). If you can't determine one of these values, set it to null."
                            
                            current_body = {
                                "taskType": "TEXT_IMAGE_UNDERSTANDING",
                                "textImageUnderstandingConfig": {
                                    "inputText": prompt_text,
                                    "outputFormat": {"jsonFormat": {"structure": {"flights": "integer", "timestamp": "string"}}},
                                },
                                "imageData": [
                                    {"image": base64.b64encode(buffered.getvalue()).decode('utf-8')}
                                ]
                            }
                        else:
                            # Format for other Amazon models (text-only)
                            prompt_text = "This is a screenshot from a health tracking app showing stairs climbed. Extract the exact number of flights climbed and the timestamp when this activity occurred. Reply in JSON format with two fields: 'flights' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM). If you can't determine one of these values, set it to null."
                            
                            current_body = {
                                "inputText": prompt_text,
                                "textGenerationConfig": {
                                    "maxTokenCount": 500,
                                    "temperature": 0.2,
                                    "topP": 0.9
                                }
                            }
                    
                    response = self.client.invoke_model(
                        modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                        body=json.dumps(current_body)
                    )
                    model_used = model
                    self.logger.info(f"Successfully used model: {model}")
                    break  # Break out of loop if successful
                except Exception as model_error:
                    self.logger.warning(f"Error with model {model}: {str(model_error)}")
                    continue  # Try next model
            
            if not response:
                # No models worked - fall back to manual entry
                return {
                    'success': False,
                    'error': "Could not access any AWS Bedrock model. Please enter details manually.",
                    'fallback_required': True
                }
            
            # Parse response based on model type
            response_body = json.loads(response['body'].read())
            self.logger.info(f"Bedrock API Call: model={model_used}, status=success")
            
            # Extract text content differently based on model type
            if model_used.startswith('anthropic.'):
                # Claude models response format
                text_content = response_body['content'][0]['text']
            else:
                # Generic format for other models
                text_content = response_body.get('text', response_body.get('outputs', [{'text': ''}])[0].get('text', ''))
            
            # Try to extract JSON from the response text
            try:
                # Find JSON in the response (might be surrounded by other text)
                import re
                json_match = re.search(r'(\{.*?\})', text_content, re.DOTALL)
                if json_match:
                    result_json = json.loads(json_match.group(1))
                else:
                    # Try to directly parse if there's no clear JSON pattern
                    result_json = json.loads(text_content)
                
                # Validate the extracted data
                flights = int(result_json.get('flights', 0)) if result_json.get('flights') else None
                timestamp = result_json.get('timestamp')
                
                return {
                    'success': True,
                    'flights': flights,
                    'timestamp': timestamp,
                    'raw_response': text_content,
                    'model_used': model_used
                }
            
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.error(f"Error parsing Bedrock response: {e}")
                return {
                    'success': False,
                    'error': 'Could not parse response',
                    'raw_response': text_content
                }
                
        except Exception as e:
            self.logger.error(f"AWS Bedrock error: {str(e)}")
            # Return a response that indicates manual entry is needed
            return {
                'success': False,
                'error': "Could not process image with AWS Bedrock. Please enter details manually.",
                'fallback_required': True
            }

    def analyze_standing_image(self, image_file):
        """
        Analyze a health app screenshot to extract standing time
        
        Args:
            image_file: The uploaded image file
        
        Returns:
            dict: Analysis results with minutes and timestamp
        """
        try:
            # Read and resize image to reduce size
            image = Image.open(image_file)
            
            # Resize image if it's too large (keep aspect ratio)
            max_size = 1600
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
                image = image.resize(new_size, Image.LANCZOS)
            
            # Convert to base64
            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # Prepare request for Claude, with standing-specific prompt
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": "This is a screenshot from a health tracking app showing standing time. Extract the exact number of minutes stood and the timestamp when this activity occurred. Reply in JSON format with two fields: 'minutes' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM). If you can't determine one of these values, set it to null."
                            }
                        ]
                    }
                ],
                "temperature": 0.2
            }
            
            # Rest of the method is similar to analyze_image
            # Get available models
            available_models = []
            try:
                if self.bedrock:
                    models_response = self.bedrock.list_foundation_models()
                    available_models = [model['modelId'] for model in models_response['modelSummaries']]
                    self.logger.info(f"Found {len(available_models)} available Bedrock models")
            except Exception as e:
                self.logger.error(f"Error listing Bedrock models: {str(e)}")
            
            # Use same model selection logic
            preferred_model = "anthropic.claude-3-7-sonnet-20250219-v1:0"
            if preferred_model in available_models:
                models_to_try = [preferred_model]
            else:
                models_to_try = []
                claude_models = [m for m in available_models if 'claude' in m.lower()]
                if claude_models:
                    models_to_try = claude_models[:1]
            
            if not models_to_try:
                models_to_try = [preferred_model]
            
            response = None
            model_used = None
            
            # Process with selected model
            for model in models_to_try:
                try:
                    current_body = request_body.copy()
                    
                    # Format requests for non-Claude models
                    if not model.startswith('anthropic.'):
                        # Similar logic as in analyze_image but for standing time
                        if 'image' in model.lower() or 'tg1' in model.lower():
                            prompt_text = "This is a screenshot from a health tracking app showing standing time. Extract the exact number of minutes stood and the timestamp when this activity occurred. Reply in JSON format with two fields: 'minutes' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM)."
                            
                            current_body = {
                                "taskType": "TEXT_IMAGE_UNDERSTANDING",
                                "textImageUnderstandingConfig": {
                                    "inputText": prompt_text,
                                    "outputFormat": {"jsonFormat": {"structure": {"minutes": "integer", "timestamp": "string"}}},
                                },
                                "imageData": [
                                    {"image": base64.b64encode(buffered.getvalue()).decode('utf-8')}
                                ]
                            }
                        else:
                            prompt_text = "This is a screenshot from a health tracking app showing standing time. Extract the exact number of minutes stood and the timestamp when this activity occurred. Reply in JSON format with two fields: 'minutes' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM)."
                            
                            current_body = {
                                "inputText": prompt_text,
                                "textGenerationConfig": {
                                    "maxTokenCount": 500,
                                    "temperature": 0.2,
                                    "topP": 0.9
                                }
                            }
                    
                    response = self.client.invoke_model(
                        modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                        body=json.dumps(current_body)
                    )
                    model_used = model
                    self.logger.info(f"Successfully used model: {model}")
                    break
                except Exception as model_error:
                    self.logger.warning(f"Error with model {model}: {str(model_error)}")
                    continue
            
            if not response:
                return {
                    'success': False,
                    'error': "Could not access any AWS Bedrock model. Please enter details manually.",
                    'fallback_required': True
                }
            
            # Parse response and extract data
            response_body = json.loads(response['body'].read())
            
            if model_used.startswith('anthropic.'):
                text_content = response_body['content'][0]['text']
            else:
                text_content = response_body.get('text', response_body.get('outputs', [{'text': ''}])[0].get('text', ''))
            
            try:
                import re
                json_match = re.search(r'(\{.*?\})', text_content, re.DOTALL)
                if json_match:
                    result_json = json.loads(json_match.group(1))
                else:
                    result_json = json.loads(text_content)
                
                minutes = int(result_json.get('minutes', 0)) if result_json.get('minutes') else None
                timestamp = result_json.get('timestamp')
                
                return {
                    'success': True,
                    'minutes': minutes,
                    'timestamp': timestamp,
                    'raw_response': text_content,
                    'model_used': model_used
                }
            
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.error(f"Error parsing Bedrock response: {e}")
                return {
                    'success': False,
                    'error': 'Could not parse response',
                    'raw_response': text_content
                }
        
        except Exception as e:
            self.logger.error(f"AWS Bedrock error: {str(e)}")
            return {
                'success': False,
                'error': "Could not process image with AWS Bedrock. Please enter details manually.",
                'fallback_required': True
            }
    def analyze_steps_image(self, image_file):
        """
        Analyze a health app screenshot to extract step count and timestamp
        
        Args:
            image_file: The uploaded image file
        
        Returns:
            dict: Analysis results with steps and timestamp
        """
        try:
            # Read and resize image to reduce size
            image = Image.open(image_file)
            
            # Resize image if it's too large (keep aspect ratio)
            max_size = 1600
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
                image = image.resize(new_size, Image.LANCZOS)
            
            # Convert to base64
            buffered = BytesIO()
            image.save(buffered, format="JPEG")
            image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            # Prepare request for Claude, with steps-specific prompt
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": "This is a screenshot from a health tracking app showing step count. Extract the exact number of steps taken and the timestamp when this activity occurred. Reply in JSON format with two fields: 'steps' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM). If you can't determine one of these values, set it to null."
                            }
                        ]
                    }
                ],
                "temperature": 0.2
            }
            
            # Get available models from Bedrock
            available_models = []
            try:
                if self.bedrock:
                    models_response = self.bedrock.list_foundation_models()
                    available_models = [model['modelId'] for model in models_response['modelSummaries']]
                    self.logger.info(f"Found {len(available_models)} available Bedrock models")
            except Exception as e:
                self.logger.error(f"Error listing Bedrock models: {str(e)}")
            
            # Limit to ONLY Claude 3.7 Sonnet as the preferred model
            preferred_model = "anthropic.claude-3-7-sonnet-20250219-v1:0"
            
            # Check if the preferred model is available
            if preferred_model in available_models:
                models_to_try = [preferred_model]
                self.logger.info(f"Using preferred model: {preferred_model}")
            else:
                self.logger.warning(f"Preferred model {preferred_model} not available")
                # Only use a fallback if absolutely necessary
                models_to_try = []
                
                # Add fallbacks only if our preferred model is unavailable
                if not models_to_try:
                    self.logger.info("Falling back to other Claude models")
                    claude_models = [m for m in available_models if 'claude' in m.lower()]
                    if claude_models:
                        models_to_try = claude_models[:1]  # Just the first Claude model
            
            # If no models are available, add the preferred model anyway
            # (it might become available later)
            if not models_to_try:
                self.logger.warning("No models available, using preferred model as fallback")
                models_to_try = [preferred_model]
            
            response = None
            model_used = None
            
            # Try each model until one works
            for model in models_to_try:
                try:
                    self.logger.info(f"Attempting to use model: {model}")
                    
                    # Adjust request body format based on model type
                    current_body = request_body.copy()
                    
                    # For non-Claude models (Amazon Titan etc), use a different format
                    if not model.startswith('anthropic.'):
                        # Format for Amazon Titan Image models
                        if 'image' in model.lower() or 'tg1' in model.lower():
                            prompt_text = "This is a screenshot from a health tracking app showing step count. Extract the exact number of steps taken and the timestamp when this activity occurred. Reply in JSON format with two fields: 'steps' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM). If you can't determine one of these values, set it to null."
                            
                            current_body = {
                                "taskType": "TEXT_IMAGE_UNDERSTANDING",
                                "textImageUnderstandingConfig": {
                                    "inputText": prompt_text,
                                    "outputFormat": {"jsonFormat": {"structure": {"steps": "integer", "timestamp": "string"}}},
                                },
                                "imageData": [
                                    {"image": base64.b64encode(buffered.getvalue()).decode('utf-8')}
                                ]
                            }
                        else:
                            # Format for other Amazon models (text-only)
                            prompt_text = "This is a screenshot from a health tracking app showing step count. Extract the exact number of steps taken and the timestamp when this activity occurred. Reply in JSON format with two fields: 'steps' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM). If you can't determine one of these values, set it to null."
                            
                            current_body = {
                                "inputText": prompt_text,
                                "textGenerationConfig": {
                                    "maxTokenCount": 500,
                                    "temperature": 0.2,
                                    "topP": 0.9
                                }
                            }
                    
                    response = self.client.invoke_model(
                        modelId="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                        body=json.dumps(current_body)
                    )
                    model_used = model
                    self.logger.info(f"Successfully used model: {model}")
                    break  # Break out of loop if successful
                except Exception as model_error:
                    self.logger.warning(f"Error with model {model}: {str(model_error)}")
                    continue  # Try next model
            
            if not response:
                # No models worked - fall back to manual entry
                return {
                    'success': False,
                    'error': "Could not access any AWS Bedrock model. Please enter details manually.",
                    'fallback_required': True
                }
            
            # Parse response based on model type
            response_body = json.loads(response['body'].read())
            self.logger.info(f"Bedrock API Call: model={model_used}, status=success")
            
            # Extract text content differently based on model type
            if model_used.startswith('anthropic.'):
                # Claude models response format
                text_content = response_body['content'][0]['text']
            else:
                # Generic format for other models
                text_content = response_body.get('text', response_body.get('outputs', [{'text': ''}])[0].get('text', ''))
            
            # Try to extract JSON from the response text
            try:
                # Find JSON in the response (might be surrounded by other text)
                import re
                json_match = re.search(r'(\{.*?\})', text_content, re.DOTALL)
                if json_match:
                    result_json = json.loads(json_match.group(1))
                else:
                    # Try to directly parse if there's no clear JSON pattern
                    result_json = json.loads(text_content)
                
                # Validate the extracted data
                steps = int(result_json.get('steps', 0)) if result_json.get('steps') else None
                timestamp = result_json.get('timestamp')
                
                return {
                    'success': True,
                    'steps': steps,
                    'timestamp': timestamp,
                    'raw_response': text_content,
                    'model_used': model_used
                }
            
            except (json.JSONDecodeError, ValueError) as e:
                self.logger.error(f"Error parsing Bedrock response: {e}")
                return {
                    'success': False,
                    'error': 'Could not parse response',
                    'raw_response': text_content
                }
                
        except Exception as e:
            self.logger.error(f"AWS Bedrock error: {str(e)}")
            # Return a response that indicates manual entry is needed
            return {
                'success': False,
                'error': "Could not process image with AWS Bedrock. Please enter details manually.",
                'fallback_required': True
            }