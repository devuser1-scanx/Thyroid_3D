import requests
from flask import Flask, request, jsonify, render_template
import os
import sys
from datetime import datetime, timedelta
import pytz
from google.cloud import storage
from google.auth import default as google_auth_default
from google.auth import iam
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

# Add the db folder to the module search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'db')))
from db_connection import connect_to_db

# 🔹 Get absolute base directory of project
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

print(f"--- STARTING FLASK APP FROM: {__file__} ---")
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

@app.before_request
def log_request_info():
    print(f"Incoming Request: {request.method} {request.path}")

# 🔹 Google Cloud Storage setup with proper service account
BUCKET_NAME = "scanx-thyroid-3d"

# Store credentials globally for signing
_credentials = None
storage_client = None

def _build_storage_client():
    global _credentials, storage_client
    
    # Try to get from environment variable first
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    # Strip quotes if present (Windows issue)
    if credentials_path:
        credentials_path = credentials_path.strip('"').strip("'")
    
    # Fallback to hardcoded path if environment variable not set
    if not credentials_path or not os.path.exists(credentials_path):
        credentials_path = r"C:\Latitude_Projects\ScanX\google_thyroid_3d_storage_key.json"
    
    print(f"Using credentials from: {credentials_path}")
    print(f"File exists: {os.path.exists(credentials_path)}")
    
    if os.path.exists(credentials_path):
        try:
            _credentials = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            storage_client = storage.Client(credentials=_credentials)
            print(f"✅ Service account loaded successfully!")
            print(f"✅ Service account email: {_credentials.service_account_email}")
            return storage_client
        except Exception as e:
            print(f"❌ Error loading service account: {e}")
            raise
    
    print(f"❌ Service account file not found at: {credentials_path}")
    raise FileNotFoundError(f"Service account JSON file not found at: {credentials_path}")

storage_client = _build_storage_client()

# Function to generate signed URL for a given file in GCS
def generate_signed_url(file_path):
    """Generate a signed URL for the video file from GCS."""
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(file_path)

        # Check if file exists
        if not blob.exists():
            print(f"❌ File does not exist: {file_path}")
            return None

        # Generate signed URL using service account credentials
        url = blob.generate_signed_url(
            expiration=timedelta(hours=1),  # Extended to 1 hours
            method="GET",
            version="v4"
        )
        
        print(f"✅ Generated signed URL for: {file_path}")
        print(f"   URL (first 100 chars): {url[:100]}...")
        
        # Test the URL
        try:
            test_response = requests.head(url, timeout=5)
            print(f"   URL test status code: {test_response.status_code}")
            if test_response.status_code != 200:
                print(f"   ⚠️ URL returned non-200 status code")
        except Exception as test_error:
            print(f"   ⚠️ Could not test URL: {test_error}")
        
        return url

    except Exception as e:
        print(f"❌ Error generating signed URL for {file_path}: {e}")
        import traceback
        traceback.print_exc()
        return None

@app.route('/')
def index():
    return render_template('video_form.html')

@app.route('/video-player', methods=['GET', 'POST'])
def video_player():
    return render_template('video_player.html')

@app.route('/fetch-video', methods=['POST'])
def fetch_video():
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()

    first_name = data.get('firstName')
    last_name = data.get('lastName')
    apptdate = data.get('apptdate')

    if not first_name or not last_name or not apptdate:
        return jsonify({
            "success": False,
            "message": "All fields are required."
        }), 400

    # 🔹 Check user existence in the database
    conn = connect_to_db()
    if not conn:
        return jsonify({
            "success": False,
            "message": "Failed to connect to the database."
        }), 500

    try:
        cursor = conn.cursor()
        query = """
        SELECT * FROM appointment
        WHERE LOWER(first_name) = LOWER(%s) AND LOWER(last_name) = LOWER(%s) AND 
        appointment_datetime::DATE = %s;
        """
        print(f"Running query: {query}, Parameters: {first_name.strip()}, {last_name.strip()}, {apptdate}")
        cursor.execute(query, (first_name.strip(), last_name.strip(), apptdate.strip()))

        user = cursor.fetchone()
        print(f"User found: {user}")
        cursor.close()

        if not user:
            return jsonify({
                "success": False,
                "message": "User not found."
            }), 404

    except Exception as e:
        print(f"Database query error: {e}")
        return jsonify({
            "success": False,
            "message": "Error querying the database."
        }), 500
    finally:
        if conn:
            conn.close()

    # 🔹 Build the flexible folder path pattern
    folder_name_pattern = f"Thyroid_Videos/{first_name.strip()}_{last_name.strip()}_{apptdate.replace('-', '')}/"
    print(f"Searching for folder pattern: {folder_name_pattern}")

    try:
        # List all files in the folder
        bucket = storage_client.bucket(BUCKET_NAME)
        blobs = list(bucket.list_blobs(prefix=folder_name_pattern))
        
        print(f"Found {len(blobs)} files in folder")
        
        video_files = []
        for blob in blobs:
            print(f"Processing blob: {blob.name}")
            # Only process .mp4 files
            if blob.name.endswith('.mp4'):
                # Check blob metadata
                print(f"  Blob size: {blob.size} bytes")
                print(f"  Content type: {blob.content_type}")
                print(f"  Public: {blob.public_url if hasattr(blob, 'public_url') else 'N/A'}")
                
                url = generate_signed_url(blob.name)
                if url:
                    video_files.append({
                        "fileName": blob.name.split('/')[-1],
                        "url": url,
                        "size": blob.size,
                        "contentType": blob.content_type
                    })
                else:
                    print(f"⚠️ Failed to generate URL for: {blob.name}")

        # If no video files found, return error
        if not video_files:
            return jsonify({
                "success": False,
                "message": f"No videos found in folder: {folder_name_pattern}"
            }), 404

        print(f"✅ Successfully generated {len(video_files)} video URLs")
        
        # Return the response
        response_data = {
            "success": True,
            "message": "Videos found.",
            "videoUrls": video_files
        }
        print(f"Response data: {response_data}")
        
        return jsonify(response_data), 200

    except Exception as e:
        print(f"❌ Error fetching video files: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": f"Error fetching video files: {str(e)}"
        }), 500

# 🔹 Add a test endpoint to verify a signed URL
@app.route('/test-url', methods=['POST'])
def test_url():
    """Test if a signed URL is accessible"""
    data = request.get_json()
    url = data.get('url')
    
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    
    try:
        response = requests.get(url, timeout=10, stream=True)
        return jsonify({
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "accessible": response.status_code == 200
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "accessible": False
        }), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080, debug=True)