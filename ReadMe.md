# DragonRise

A secure web application for tracking stair climbing and standing activities.

## Security Features

- TLS 1.2+ for secure communications
- Input sanitization to prevent XSS attacks
- CSRF protection for all forms
- Secure password handling
- Rate limiting to prevent brute force attacks
- Security headers to prevent common web vulnerabilities
- Environment variables for sensitive configuration

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/DragonRise.git
   cd DragonRise
   ```

2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Create environment file:
   ```
   cp .env.example .env
   ```

5. Edit `.env` with your secure values:
   ```
   SECRET_KEY=your-secure-secret-key
   ADMIN_PASSWORD=your-secure-admin-password
   API_KEY=your-secure-api-key
   DEBUG=True  # Set to False in production
   ```

6. Generate SSL certificates for development:
   ```
   python generate_cert.py
   ```

7. Run the application:
   ```
   python run.py
   ```

8. Access the application:
   ```
   https://localhost:5000
   ```

## Security Notes

- **Certificates**: SSL certificates are generated locally and not included in the repository
- **Environment Variables**: Sensitive values are stored in `.env` which is not committed to the repository
- **Production Deployment**: Use proper SSL certificates from a trusted CA in production

## Development

- The application enforces TLS 1.2 or higher
- All user inputs are sanitized to prevent XSS attacks
- CSRF protection is enabled for all forms
- Rate limiting is applied to sensitive endpoints

## License

[MIT License](LICENSE)