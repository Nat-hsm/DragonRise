from app import app, init_db
import os
import ssl
import logging
from dotenv import load_dotenv

# Load environment variables before initializing the app
load_dotenv()

if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Check if we're in development mode
    is_dev = os.getenv('FLASK_ENV', 'development') == 'development'
    
    if is_dev:
        # Run without SSL in development mode
        print("Starting server in development mode without TLS")
        print("Access your application at http://localhost:5001")
        app.run(debug=True, host='0.0.0.0', port=5001)
    else:
        # Get certificate paths for production
        cert_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certificates')
        cert_path = os.path.join(cert_dir, 'cert.pem')
        key_path = os.path.join(cert_dir, 'key.pem')
        
        # Check if certificates exist
        if not os.path.exists(cert_path) or not os.path.exists(key_path):
            print("Error: SSL certificates not found. Please run generate_cert.py first.")
            print("Run: python generate_cert.py")
            exit(1)
        
        # Configure SSL context to use TLS 1.3
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        context.load_cert_chain(cert_path, key_path)
        
        # Run the app with TLS 1.3
        print("Starting server with TLS 1.3 enabled")
        print("Access your application at https://localhost:5001")
        print("Note: You may see a browser security warning because the certificate is self-signed.")
        app.run(
            debug=True,
            ssl_context=context,
            host='0.0.0.0',
            port=5001
        )
