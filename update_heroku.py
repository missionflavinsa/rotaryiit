import os
import subprocess
import json
import base64

with open('serviceAccountKey.json', 'r') as f:
    data = f.read()

b64_data = base64.b64encode(data.encode('utf-8')).decode('utf-8')

print("Updating Heroku Config with Base64 Service Account...")
try:
    subprocess.run(["heroku.cmd", "config:set", f"FIREBASE_SERVICE_ACCOUNT={b64_data}", "-a", "rotary-iit-admin"], check=True)
    print("Successfully updated config!")
except Exception as e:
    subprocess.run(["C:\\Program Files\\heroku\\bin\\heroku.cmd", "config:set", f"FIREBASE_SERVICE_ACCOUNT={b64_data}", "-a", "rotary-iit-admin"], check=True)
    print("Successfully updated config using absolute path!")
