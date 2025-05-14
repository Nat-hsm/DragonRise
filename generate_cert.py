from OpenSSL import crypto
import os

def generate_self_signed_cert(cert_file, key_file):
    # Create a key pair
    k = crypto.PKey()
    k.generate_key(crypto.TYPE_RSA, 2048)

    # Create a self-signed cert
    cert = crypto.X509()
    cert.get_subject().C = "US"
    cert.get_subject().ST = "State"
    cert.get_subject().L = "City"
    cert.get_subject().O = "DragonRise"
    cert.get_subject().OU = "Development"
    cert.get_subject().CN = "localhost"
    cert.set_serial_number(1000)
    cert.gmtime_adj_notBefore(0)
    cert.gmtime_adj_notAfter(365*24*60*60)  # Valid for a year
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(k)
    cert.sign(k, 'sha256')  # Use SHA-256 for signature

    # Write the certificate and key to files
    with open(cert_file, "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
    
    with open(key_file, "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
    
    print(f"Certificate created: {cert_file}")
    print(f"Private key created: {key_file}")

if __name__ == "__main__":
    # Create certificates directory if it doesn't exist
    os.makedirs("certificates", exist_ok=True)
    
    # Generate the certificate and key
    cert_file = os.path.join("certificates", "cert.pem")
    key_file = os.path.join("certificates", "key.pem")
    
    generate_self_signed_cert(cert_file, key_file)
    
    print("\nTo use these certificates, run your application with:")
    print("python run.py")
    print("\nNote: Your browser will show a security warning because these are self-signed certificates.")
    print("This is normal for development environments.")
    print("\nTLS 1.2 or higher will be enforced for secure connections.")