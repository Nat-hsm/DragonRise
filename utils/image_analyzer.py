import boto3
import json
import base64
import os
import re
from io import BytesIO
from PIL import Image
import logging
from datetime import datetime, timezone

class ImageAnalyzer:
    def __init__(self):
        """Initialize Bedrock client"""
        self.logger = logging.getLogger('bedrock_monitor')
        self.monitor = None  # For future monitoring implementation
        self.model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"  # Consistent model ID
        
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
        """Analyze a health app screenshot to extract flights climbed and timestamp"""
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
            
            # Use the specific model directly without fallbacks
            response = None
            try:
                self.logger.info(f"Using model: {self.model_id}")
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(request_body)
                )
                self.logger.info(f"Successfully used model: {self.model_id}")
            except Exception as e:
                self.logger.error(f"Error with model {self.model_id}: {str(e)}")
                return {
                    'success': False,
                    'error': f"Could not access AWS Bedrock model. Error: {str(e)}",
                    'fallback_required': True
                }
            
            if not response:
                return {
                    'success': False,
                    'error': "Could not access AWS Bedrock model. Please enter details manually.",
                    'fallback_required': True
                }
            
            # Parse response
            response_body = json.loads(response['body'].read())
            self.logger.info(f"Bedrock API Call: model={self.model_id}, status=success")
            
            # Extract text content from Claude response
            text_content = response_body['content'][0]['text']
            
            # Try to extract JSON from the response text
            try:
                # Find JSON in the response (might be surrounded by other text)
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
                    'model_used': self.model_id
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
        """Analyze a health app screenshot to extract standing time"""
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
                                "text": "This is a screenshot from a health tracking app showing standing time. Extract the exact number of minutes stood and the timestamp when this activity occurred. Reply in JSON format with two fields: 'minutes' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM). If you can't determine one of these values, set it to null."
                            }
                        ]
                    }
                ],
                "temperature": 0.2
            }
            
            # Use the specific model directly without fallbacks
            response = None
            try:
                self.logger.info(f"Using model: {self.model_id}")
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(request_body)
                )
                self.logger.info(f"Successfully used model: {self.model_id}")
            except Exception as e:
                self.logger.error(f"Error with model {self.model_id}: {str(e)}")
                return {
                    'success': False,
                    'error': f"Could not access AWS Bedrock model. Error: {str(e)}",
                    'fallback_required': True
                }
            
            if not response:
                return {
                    'success': False,
                    'error': "Could not access AWS Bedrock model. Please enter details manually.",
                    'fallback_required': True
                }
            
            # Parse response
            response_body = json.loads(response['body'].read())
            
            # Extract text content from Claude response
            text_content = response_body['content'][0]['text']
            
            try:
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
                    'model_used': self.model_id
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
        """Analyze a health app screenshot to extract step count"""
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
                                "text": "This is a screenshot from a health tracking app showing step count. Extract the exact number of steps taken and the timestamp when this activity occurred. Reply in JSON format with two fields: 'steps' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM). If you can't determine one of these values, set it to null."
                            }
                        ]
                    }
                ],
                "temperature": 0.2
            }
            
            # Use the specific model directly without fallbacks
            response = None
            try:
                self.logger.info(f"Using model: {self.model_id}")
                response = self.client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(request_body)
                )
                self.logger.info(f"Successfully used model: {self.model_id}")
            except Exception as e:
                self.logger.error(f"Error with model {self.model_id}: {str(e)}")
                return {
                    'success': False,
                    'error': f"Could not access AWS Bedrock model. Error: {str(e)}",
                    'fallback_required': True
                }
            
            if not response:
                return {
                    'success': False,
                    'error': "Could not access AWS Bedrock model. Please enter details manually.",
                    'fallback_required': True
                }
            
            # Parse response
            response_body = json.loads(response['body'].read())
            
            # Extract text content from Claude response
            text_content = response_body['content'][0]['text']
            
            try:
                json_match = re.search(r'(\{.*?\})', text_content, re.DOTALL)
                if json_match:
                    result_json = json.loads(json_match.group(1))
                else:
                    result_json = json.loads(text_content)
                
                steps = int(result_json.get('steps', 0)) if result_json.get('steps') else None
                timestamp = result_json.get('timestamp')
                
                return {
                    'success': True,
                    'steps': steps,
                    'timestamp': timestamp,
                    'raw_response': text_content,
                    'model_used': self.model_id
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