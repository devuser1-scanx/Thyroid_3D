import psycopg2
import os

# Configure your Cloud SQL connection details
# DB_HOST = "/cloudsql/vernal-maker-473121-k4:us-central1:scanx-postgres-db"
DB_HOST = "35.192.117.171"
DB_NAME = "scanx_app"
DB_USER = "postgres"
DB_PASSWORD = "ScanX@2025"  # Replace with actual password securely

def connect_to_db():
    """Connect to the Cloud SQL PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None