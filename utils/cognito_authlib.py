from flask import redirect, url_for, session
from authlib.integrations.flask_client import OAuth
import os

def setup_oauth(app):
    """Initialize OAuth with Authlib for Cognito integration"""
    oauth = OAuth(app)
    
    oauth.register(
        name='oidc',
        authority=f'https://cognito-idp.{app.config["AWS_REGION"]}.amazonaws.com/{app.config["COGNITO_USER_POOL_ID"]}',
        client_id=app.config['COGNITO_CLIENT_ID'],
        client_secret=app.config['COGNITO_CLIENT_SECRET'],
        server_metadata_url=f'https://cognito-idp.{app.config["AWS_REGION"]}.amazonaws.com/{app.config["COGNITO_USER_POOL_ID"]}/.well-known/openid-configuration',
        client_kwargs={'scope': 'email openid profile'}
    )
    
    return oauth