import firebase_admin
from firebase_admin import credentials, firestore
import os

# Path to the service account key
# In production (Heroku), we might use environment variables, 
# but for now, we use the local file.
service_key_path = os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json')

if not firebase_admin._apps:
    service_account_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if service_account_json:
        # Load credentials from environment variable JSON string
        import json
        import base64
        
        # Check if it's base64 encoded by trying to decode it
        try:
            if not service_account_json.strip().startswith('{'):
                service_account_json = base64.b64decode(service_account_json).decode('utf-8')
        except Exception:
            pass
            
        cred_info = json.loads(service_account_json)
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
    elif os.path.exists(service_key_path):
        # Fallback to local file if it exists
        cred = credentials.Certificate(service_key_path)
        firebase_admin.initialize_app(cred)
    else:
        raise FileNotFoundError("Neither FIREBASE_SERVICE_ACCOUNT env var nor serviceAccountKey.json found!")

db = firestore.client()

def get_db():
    return db
