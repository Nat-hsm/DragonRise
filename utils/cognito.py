import boto3
import requests
import json
import time
import os
from jose import jwk, jwt
from jose.utils import base64url_decode
from flask import redirect, session, url_for, request, current_app
from urllib.parse import quote

class CognitoAuth:
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
            
    def init_app(self, app):
        self.region = app.config.get('AWS_REGION', 'us-east-1')
        self.user_pool_id = app.config.get('COGNITO_USER_POOL_ID')
        self.client_id = app.config.get('COGNITO_CLIENT_ID')
        self.client_secret = app.config.get('COGNITO_CLIENT_SECRET')
        self.redirect_uri = app.config.get('COGNITO_REDIRECT_URI')
        self.domain = app.config.get('COGNITO_DOMAIN')
        
        # Initialize Cognito client
        self.client = boto3.client('cognito-idp', region_name=self.region)
    
    def get_login_url(self, state=None):
        """Generate login URL for Cognito hosted UI"""
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'scope': 'email+openid+profile',
            'redirect_uri': self.redirect_uri
        }
        
        if state:
            params['state'] = state

        query_string = '&'.join([f"{k}={quote(v)}" for k, v in params.items()])
        # The domain format is correct - don't change it
        return f"https://{self.domain}.auth.{self.region}.amazoncognito.com/login?{query_string}"
    
    def get_token(self, code):
        """Exchange authorization code for tokens"""
        # Use the domain from config instead of hardcoding
        token_url = f"https://{self.domain}.auth.{self.region}.amazoncognito.com/oauth2/token"
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        # Include client credentials in the body (CLIENT_SECRET_POST method)
        body = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.redirect_uri
        }
        
        try:
            import logging
            from urllib.parse import urlencode
            
            # Log redacted request details
            debug_body = body.copy()
            debug_body['client_secret'] = '[REDACTED]'
            debug_body['code'] = f"{code[:8]}..." if code else "None"
            logging.info(f"Token exchange request to {token_url}")
            logging.info(f"Request params: {debug_body}")
            
            # Make the request with proper URL encoding
            response = requests.post(token_url, headers=headers, data=urlencode(body))
            
            logging.info(f"Token exchange response status: {response.status_code}")
            
            try:
                response_json = response.json()
                
                if 'error' in response_json:
                    error_msg = response_json.get('error')
                    error_desc = response_json.get('error_description', '')
                    
                    # Log specific error information
                    if error_msg == 'invalid_grant':
                        logging.error(f"Invalid grant: The authorization code is invalid/expired or has already been used. Details: {error_desc}")
                    else:
                        logging.error(f"Token exchange error: {response_json}")
                        
                    return None
                
                # Log successful token exchange
                logging.info("Token exchange successful")
                return response_json
                
            except ValueError:  # Not JSON
                logging.error(f"Non-JSON response: {response.text}")
                return None
                
        except Exception as e:
            logging.error(f"Token exchange exception: {str(e)}")
            return None
    
    def validate_token(self, token):
        """Validate ID token"""
        try:
            import logging
            import base64
            import json
            
            # Parse the token
            parts = token.split('.')
            if len(parts) != 3:
                raise Exception("Invalid token format")
            
            # Get the JWT payload
            payload = parts[1]
            # Add padding if needed
            payload += '=' * (4 - len(payload) % 4) if len(payload) % 4 else ''
            # Decode the payload
            claims = json.loads(base64.b64decode(payload).decode('utf-8'))
            
            # Basic validation
            now = int(time.time())
            if claims.get('exp', 0) < now:
                raise Exception("Token has expired")
                
            if claims.get('aud') != self.client_id:
                raise Exception("Token audience mismatch")
            
            if self.app and hasattr(self.app, 'logger'):
                self.app.logger.info("Token validated successfully")
            else:
                logging.info("Token validated successfully")
                
            return claims
        except Exception as e:
            if self.app and hasattr(self.app, 'logger'):
                self.app.logger.error(f"Token validation error: {str(e)}")
            else:
                logging.error(f"Token validation error: {str(e)}")
            return None
    
    def get_user_attributes(self, access_token):
        """Get user attributes using access token"""
        try:
            response = self.client.get_user(
                AccessToken=access_token
            )
            
            user_attributes = {}
            for attr in response['UserAttributes']:
                user_attributes[attr['Name']] = attr['Value']
                
            return user_attributes
        except Exception as e:
            current_app.logger.error(f"Error getting user attributes: {str(e)}")
            return None