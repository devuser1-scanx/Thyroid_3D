from flask import Flask, request, jsonify, render_template
from google.cloud import storage
from datetime import timedelta
import os

# 🔹 Get absolute base directory of project
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

# 🔹 Configure your bucket name here
BUCKET_NAME = "your-bucket-name"


@app.route('/')
def index():
    return render_template('video_form.html')


def generate_signed_video_url(first_name, last_name):
    """
    Generates a secure signed URL for a patient video.
    File format assumed: FIRSTNAME_LASTNAME.mp4
    """

    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)

        # 🔹 Normalize filename (optional but recommended)
        file_name = f"{first_name.strip().title()}_{last_name.strip().title()}.mp4"

        blob = bucket.blob(file_name)

        if not blob.exists():
            return None

        url = blob.generate_signed_url(
            expiration=timedelta(hours=1),
            method="GET"
        )

        return url

    except Exception as e:
        print("Error generating signed URL:", str(e))
        return None

# Required format for the video file name: FIRSTNAME_LASTNAME_YYYYMMDD.mp4

@app.route('/fetch-video', methods=['POST'])
def fetch_video():
    data = request.get_json()

    first_name = data.get('firstName')
    last_name = data.get('lastName')
    dob = data.get('dob')

    if not first_name or not last_name or not dob:
        return jsonify({
            "success": False,
            "message": "All fields are required."
        }), 400

    # 🔹 Generate signed URL
    def generate_signed_video_url(first_name, last_name, dob):
        try:
            client = storage.Client()
            bucket = client.bucket(BUCKET_NAME)

            # Convert DOB from yyyy-mm-dd → yyyymmdd
            dob_clean = dob.replace("-", "")

            file_name = f"{first_name.strip().title()}_{last_name.strip().title()}_{dob_clean}.mp4"

            blob = bucket.blob(file_name)

            if not blob.exists():
                return None

            url = blob.generate_signed_url(
                expiration=timedelta(hours=1),
                method="GET"
            )

            return url

        except Exception as e:
            print("Error generating signed URL:", str(e))
            return None



if __name__ == '__main__':
    # Cloud Run requires 0.0.0.0 and port 8080
    app.run(host="0.0.0.0", port=8080)
