# Certificate Security in DragonRise

I've updated your codebase to ensure that SSL/TLS certificates are not pushed to GitHub. This is an important security practice to prevent sensitive cryptographic material from being exposed in your repository.

## Changes Made

1. **Updated `.gitignore`**:
   - Added comprehensive rules for certificate files
   - Included all common certificate extensions (`.pem`, `.key`, `.crt`, etc.)
   - Excluded the entire `certificates/` directory from Git tracking

2. **Added `.gitkeep` file**:
   - Created `certificates/.gitkeep` to ensure the directory structure is maintained
   - Added a comment explaining that certificate files should not be committed

3. **Updated `run.py`**:
   - Added code to create the certificates directory if it doesn't exist
   - Improved certificate checking and error handling
   - Added logging for certificate-related operations

## Why This Matters

Keeping certificates out of your Git repository is crucial for several reasons:

1. **Security**: Private keys should never be shared or stored in version control
2. **Environment-Specific**: Certificates are often specific to deployment environments
3. **Best Practice**: Following security best practices for sensitive cryptographic material

## How to Work with Certificates

### Development

For development, generate certificates locally:

```
python generate_cert.py
```

These certificates will be created in the `certificates/` directory but won't be committed to Git.

### Production

For production deployment:

1. Obtain proper certificates from a trusted Certificate Authority
2. Install them securely on your production server
3. Configure your application to use these certificates
4. Never commit production certificates to version control

## Verification

You can verify that certificates won't be committed to Git by:

1. Running `git status` after generating certificates
2. The certificate files should not appear in the list of tracked files

This setup ensures that your application can use TLS for secure communications while maintaining proper security practices for the certificate files themselves.