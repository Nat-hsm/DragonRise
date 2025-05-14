from app import app, init_db
import os
import ssl
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_certificates():
    """Check if certificates exist and create directory if needed"""
    # Define paths to SSL certificate and key
    cert_path = os.path.join('certificates', 'cert.pem')
    key_path = os.path.join('certificates', 'key.pem')
    
    # Create certificates directory if it doesn't exist
    if not os.path.exists('certificates'):
        os.makedirs('certificates')
        logger.info("Created certificates directory")
    
    # Check if certificates exist
    if os.path.exists(cert_path) and os.path.exists(key_path):
        logger.info("SSL certificates found")
        return cert_path, key_path
    else:
        logger.warning("SSL certificates not found")
        return None, None

if __name__ == '__main__':
    init_db()
    
    # Check for certificates
    cert_path, key_path = check_certificates()
    
    # Check if certificates exist
    if cert_path and key_path:
        print("TLS/SSL enabled. Access the application at https://localhost:5000")
        
        # Create SSL context with modern security settings
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        
        # Set minimum TLS version to 1.2
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        
        # Set preferred ciphers (modern, secure ciphers)
        ssl_context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20')
        
        # Disable compression (CRIME attack mitigation)
        ssl_context.options |= ssl.OP_NO_COMPRESSION
        
        # Load certificate and key
        ssl_context.load_cert_chain(cert_path, key_path)
        
        # Use debug mode only in development
        debug_mode = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')
        
        # Run the application with the secure SSL context
        app.run(
            debug=debug_mode,
            ssl_context=ssl_context,
            host='0.0.0.0',  # Allow connections from other devices
            port=5001  # Changed from default 5000 to 5001
        )
    else:
        print("WARNING: SSL certificates not found. Running in insecure HTTP mode.")
        print("To enable HTTPS, run 'python generate_cert.py' first.")
        # Use debug mode only in development
        debug_mode = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 't')
        app.run(debug=debug_mode, port=5001)  # Changed from default 5000 to 5001