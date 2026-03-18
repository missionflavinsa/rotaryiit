import firebase_admin
from firebase_admin import credentials, firestore
import os

# Path to the service account key
# In production (Heroku), we might use environment variables, 
# but for now, we use the local file.
service_key_path = os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json')

if not firebase_admin._apps:
    if os.path.exists(service_key_path):
        cred = credentials.Certificate(service_key_path)
        firebase_admin.initialize_app(cred)
    else:
        # Fallback for environment variables if needed
        # cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CONFIG')))
        # firebase_admin.initialize_app(cred)
        raise FileNotFoundError("serviceAccountKey.json not found in root directory!")

db = firestore.client()

def get_db():
    return db
