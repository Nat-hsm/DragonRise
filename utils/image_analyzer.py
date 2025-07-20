import boto3
import json
import base64
import os
import re
import logging
from io import BytesIO
from PIL import Image
from datetime import datetime, timezone

class ImageAnalyzer:
    def __init__(self):
        """Initialize Bedrock client"""
        self.logger = logging.getLogger('bedrock_monitor')
        self.monitor = None
        self.model_id = "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
        
        # Get credentials directly from environment
        access_key = os.getenv('AWS_ACCESS_KEY_ID')
        secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        region = os.getenv('AWS_REGION', 'us-east-1')
        
        # Initialize Bedrock clients with explicit credentials
        try:
            if not access_key or not secret_key:
                self.logger.warning("AWS credentials not available in environment")
                self.bedrock = None
                self.client = None
                self.has_valid_credentials = False
                return
                
            # Create clients with explicit credentials
            self.bedrock = boto3.client(
                'bedrock',
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key
            )
            
            self.client = boto3.client(
                'bedrock-runtime', 
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key
            )
            
            # Verify credentials work by making a simple call
            self.bedrock.list_foundation_models(maxResults=1)
            
            self.logger.info("Amazon Bedrock clients initialized successfully")
            self.has_valid_credentials = True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize Amazon Bedrock clients: {str(e)}")
            self.bedrock = None
            self.client = None
            self.has_valid_credentials = False
    
    def _verify_credentials(self):
        """Verify if AWS credentials are valid without relying on env vars"""
        try:
            # Try to list models as a simple credential verification
            self.bedrock.list_foundation_models(maxResults=1)
            return True
        except Exception as e:
            self.logger.error(f"AWS credential verification failed: {str(e)}")
            return False
            
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
                                "text": """This is a screenshot from a health tracking app showing flights of stairs climbed.

Analyze the image and extract the flights climbed information:

1. Check if this shows a SPECIFIC DAY'S total flights climbed - it may be labeled as "TOTAL" with a specific date
2. Extract the exact number of flights climbed for that specific day
3. Extract the date if visible

Only accept the image if:
- It shows data for a specific single day (not an average)
- The date is clearly visible

IMPORTANT: 
- Images showing "TOTAL" with a specific date and flights (like "TOTAL 17 floors" with date "12 Jul 2025") ARE valid and should be accepted
- Images showing "AVERAGE" with a date range (like "AVERAGE 6 floors 6-12 Jul 2025") should be REJECTED
- Images without a visible date should be REJECTED

Format your response as a JSON with these keys:
- "valid_data" (boolean): true only if it shows a specific day's flights with a date
- "flights" (integer): the number of flights climbed
- "date" (string): the date in YYYY-MM-DD format if possible
- "error" (string): description of why the data is invalid, only if valid_data is false
- "view_type" (string): "daily" or "weekly" or "monthly"
"""
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
                    
                    # Check if this is valid flight data for a specific day
                    if result_json.get('valid_data', False):
                        flights = int(result_json.get('flights', 0))
                        date = result_json.get('date')
                        
                        self.logger.info(f"Successfully extracted flights: {flights} for date: {date}")
                        return {
                            'success': True,
                            'flights': flights,
                            'timestamp': date if date else datetime.now(timezone.utc).isoformat(),
                            'raw_response': text_content,
                            'model_used': self.model_id
                        }
                    else:
                        # Reject with specific reason
                        error_msg = result_json.get('error', 'Invalid flight data')
                        view_type = result_json.get('view_type', 'unknown')
                        
                        if view_type == "weekly" or view_type == "monthly":
                            reject_reason = f"Screenshot shows {view_type} average. Please upload a daily view."
                        else:
                            reject_reason = error_msg
                            
                        self.logger.info(f"Rejected flight image: {reject_reason}")
                        return {
                            'success': False,
                            'error': reject_reason
                        }
                else:
                    # Fallback to regex extraction if JSON parsing fails
                    # Look for "TOTAL X floors" with a date
                    total_match = re.search(r'TOTAL\s+(\d+)\s+floors', text_content, re.IGNORECASE)
                    date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', text_content)
                    
                    # Check for AVERAGE indicator (reject)
                    average_match = re.search(r'AVERAGE', text_content, re.IGNORECASE)
                    
                    if average_match:
                        self.logger.info("Rejected: Image shows weekly/monthly average")
                        return {
                            'success': False,
                            'error': "Please upload an image showing daily floors climbed, not a weekly or monthly average."
                        }
                    
                    if not date_match:
                        self.logger.info("Rejected: No date found in the image")
                        return {
                            'success': False,
                            'error': "Please upload an image with a visible date."
                        }
                    
                    if total_match and date_match:
                        flights = int(total_match.group(1))
                        date_str = date_match.group(0)
                        
                        self.logger.info(f"Extracted flights with regex: {flights}, date: {date_str}")
                        return {
                            'success': True,
                            'flights': flights,
                            'timestamp': date_str,
                            'raw_response': text_content,
                        }
                
                # If we get here, we couldn't extract the data
                return {
                    'success': False,
                    'error': "Could not extract flight data from the image. Please ensure it shows daily flights with a clear date.",
                    'raw_response': text_content
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
        Analyze an image from the health app showing standing time
        
        Args:
            image_file: File object containing the image
            
        Returns:
            dict: Analysis result with minutes count and success status
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
            
            # Use AWS Bedrock if configured and credentials are valid
            if self.client and self.has_valid_credentials:
                try:
                    # Prepare request body with specific prompt for standing minutes
                    request_body = {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 1000,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": """This is a screenshot from a health app showing standing time.

Analyze the image and extract stand time information:

1. Check if this shows a SPECIFIC DAY'S stand time - it may be labeled as "TOTAL" with a specific date
2. Check if the stand time is shown in MINUTES (not hours)
3. Extract the exact number of stand minutes for the specific day
4. Extract the date if visible

Only accept the image if:
- It shows data for a specific single day (not an average)
- The data is shown in minutes (not hours)

IMPORTANT: Images showing "TOTAL" with a specific date and minutes (like "TOTAL 63 min") ARE valid and should be accepted.

Format your response as a JSON with these keys:
- "valid_data" (boolean): true only if it shows a specific day's stand minutes
- "minutes" (integer): the number of stand minutes (not hours)
- "date" (string): the date in YYYY-MM-DD format if visible, otherwise null
- "error" (string): description of why the data is invalid, only if valid_data is false
- "units" (string): "minutes" or "hours"
- "view_type" (string): "daily" or "weekly" or "monthly"

Examples of rejections:
- Weekly average data should be rejected
- Stand hours (not minutes) should be rejected"""
                                    },
                                    {
                                        "type": "image",
                                        "source": {
                                            "type": "base64",
                                            "media_type": "image/jpeg",
                                            "data": image_base64
                                        }
                                    }
                                ]
                            }
                        ],
                        "temperature": 0.2
                    }
                    
                    # Call Claude model
                    response = self.client.invoke_model(
                        modelId=self.model_id,
                        body=json.dumps(request_body)
                    )
                    
                    # Parse response
                    response_body = json.loads(response['body'].read())
                    text_content = response_body['content'][0]['text']
                    
                    # Extract JSON from response
                    json_match = re.search(r'(\{.*?\})', text_content, re.DOTALL)
                    if json_match:
                        result_json = json.loads(json_match.group(1))
                        
                        # Check if this is valid daily stand minutes
                        if result_json.get('valid_data', False):
                            minutes = int(result_json.get('minutes', 0))
                            date = result_json.get('date')
                            
                            self.logger.info(f"Successfully extracted stand minutes: {minutes} for date: {date}")
                            return {
                                'success': True,
                                'minutes': minutes,
                                'timestamp': date if date else datetime.now(timezone.utc).isoformat()
                            }
                        else:
                            # Reject with specific reason
                            error_msg = result_json.get('error', 'Invalid standing data')
                            units = result_json.get('units', 'unknown')
                            view_type = result_json.get('view_type', 'unknown')
                            
                            if units == "hours":
                                reject_reason = "Screenshot shows standing hours. Please upload an image showing standing minutes."
                            elif view_type == "weekly" or view_type == "monthly":
                                reject_reason = f"Screenshot shows {view_type} average. Please upload a daily view."
                            else:
                                reject_reason = error_msg
                                
                            self.logger.info(f"Rejected stand image: {reject_reason}")
                            return {
                                'success': False,
                                'error': reject_reason
                            }
                    else:
                        # Enhanced fallback to detect "TOTAL" minutes pattern (as shown in IMG_0350)
                        total_minutes_match = re.search(r'TOTAL[\s:]*(\d+)\s*min', text_content, re.IGNORECASE)
                        specific_date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', text_content)
                        
                        # Detect if this is an "hours" image (reject)
                        hours_match = re.search(r'(\d+)\s*hr', text_content, re.IGNORECASE)
                        average_match = re.search(r'AVERAGE', text_content, re.IGNORECASE)
                        
                        if hours_match and not total_minutes_match:
                            self.logger.info("Rejected: Image shows hours instead of minutes")
                            return {
                                'success': False,
                                'error': "Please upload an image showing stand minutes, not hours."
                            }
                        
                        if average_match and not total_minutes_match:
                            self.logger.info("Rejected: Image shows weekly/monthly average")
                            return {
                                'success': False, 
                                'error': "Please upload an image showing daily stand minutes, not a weekly or monthly average."
                            }
                        
                        if total_minutes_match:
                            minutes = int(total_minutes_match.group(1))
                            date_str = specific_date_match.group(1) if specific_date_match else None
                            
                            self.logger.info(f"Extracted stand minutes with regex: {minutes} minutes, date: {date_str}")
                            return {
                                'success': True,
                                'minutes': minutes,
                                'timestamp': date_str if date_str else datetime.now(timezone.utc).isoformat()
                            }
                        
                        # Last resort - look for any minutes mention
                        minutes_match = re.search(r'(\d+)\s*minutes?', text_content, re.IGNORECASE)
                        if minutes_match:
                            minutes = int(minutes_match.group(1))
                            self.logger.info(f"Extracted stand minutes with generic regex: {minutes} minutes")
                            return {
                                'success': True,
                                'minutes': minutes,
                                'timestamp': datetime.now(timezone.utc).isoformat()
                            }
                except Exception as e:
                    self.logger.error(f"Bedrock error analyzing standing time: {str(e)}")
            
            # Reject screenshot with clear message
            self.logger.info("Stand image analysis failed, rejecting screenshot")
            return {
                'success': False,
                'error': 'Unable to analyze screenshot. Please upload a daily view showing stand minutes (not hours).'
            }
                
        except Exception as e:
            self.logger.error(f"Standing image analysis error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def analyze_steps_image(self, image_file):
        """
        Analyze an image from the health app showing steps count
    
        Args:
            image_file: File object containing the image
            
        Returns:
            dict: Analysis result with steps count and success status
        """
        try:
            # Read and resize image
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
        
            # Use AWS Bedrock if configured
            if hasattr(self, 'client') and self.client:
                try:
                    # Updated request body to improve steps analysis
                    request_body = {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 1000,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": """This is a screenshot from a health app showing step count.
                                
Analyze the image and extract the step count information:

1. If this shows a SPECIFIC DAY'S total steps (even if displayed within a weekly view), extract:
   - The exact number of steps for that day
   - The specific date (if visible)

2. Only reject the image if:
   - It shows ONLY weekly or monthly averages with no specific day highlighted
   - The step count for a specific day cannot be clearly determined

Format your response as a JSON with keys:
- "valid_data" (boolean): true if a specific day's step count is clearly visible
- "steps" (integer): the number of steps for the specific day (remove any commas)
- "date" (string): the date in YYYY-MM-DD format if visible, otherwise null
- "error" (string): description of why the data is invalid, only if valid_data is false"""
                                    },
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
                                        "text": "This is a screenshot from a health tracking app showing steps count. Extract the exact number of steps and the timestamp when this activity occurred. Reply in JSON format with two fields: 'steps' (integer) and 'timestamp' (string in format YYYY-MM-DD HH:MM). If you can't determine one of these values, set it to null."
                                    }
                                ]
                            }
                        ],
                        "temperature": 0.2
                    }
            
                    # Call Claude model
                    response = self.client.invoke_model(
                        modelId=self.model_id,
                        body=json.dumps(request_body)
                    )
            
                    # Parse response
                    response_body = json.loads(response['body'].read())
                    text_content = response_body['content'][0]['text']
            
                    # Extract JSON from response
                    json_match = re.search(r'(\{.*?\})', text_content, re.DOTALL)
                    if json_match:
                        result_json = json.loads(json_match.group(1))
                
                        # Check if this contains valid data for a specific day
                        if result_json.get('valid_data', False):
                            steps = int(result_json.get('steps', 0))
                            date = result_json.get('date')
                
                            self.logger.info(f"Successfully extracted steps: {steps} for date: {date}")
                            return {
                                'success': True,
                                'steps': steps,
                                'timestamp': date if date else datetime.now(timezone.utc).isoformat()
                            }
                        else:
                            error_msg = result_json.get('error', 'Please upload an image showing a specific day\'s step count')
                            self.logger.info(f"Rejected image: {error_msg}")
                            return {
                                'success': False,
                                'error': error_msg
                            }
                    else:
                        # Fallback to simple regex extraction if JSON parsing fails
                        self.logger.warning("Couldn't parse JSON from response, using fallback")
                
                        # Look for specific day data formats like "TOTAL: X steps" or "X steps" with a date
                        total_steps_match = re.search(r'TOTAL[:\s]*([0-9,]+)\s*steps', text_content, re.IGNORECASE)
                        date_match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', text_content)
                        
                        if total_steps_match:
                            steps_str = total_steps_match.group(1).replace(',', '')
                            steps = int(steps_str)
                            date_str = date_match.group(1) if date_match else None
                            
                            self.logger.info(f"Extracted steps with regex: {steps}, date: {date_str}")
                            return {
                                'success': True,
                                'steps': steps,
                                'timestamp': date_str if date_str else datetime.now(timezone.utc).isoformat()
                            }
                        
                        # General steps pattern as last resort
                        steps_match = re.search(r'(\d{1,3}(?:,\d{3})*|\d+)\s*steps?', text_content, re.IGNORECASE)
                        if steps_match:
                            steps_str = steps_match.group(1).replace(',', '')
                            steps = int(steps_str)
                            self.logger.info(f"Extracted steps with generic regex: {steps}")
                            return {
                                'success': True,
                                'steps': steps,
                                'timestamp': datetime.now(timezone.utc).isoformat()
                            }
                except Exception as e:
                        self.logger.error(f"Bedrock error analyzing steps: {str(e)}")
                
                # Fallback method if AWS Bedrock is not available
                self.logger.info("Image analysis not available, rejecting screenshot")
                return {
                    'success': False,
                    'error': 'Could not analyze screenshot. Please try again with a clearer image of your steps.'
                }
        except Exception as e:
            self.logger.error(f"Steps image analysis error: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }