from app import app, init_db
from dotenv import load_dotenv

# Load environment variables before initializing the app
load_dotenv()

if __name__ == '__main__':
    init_db()
    app.run(debug=True)