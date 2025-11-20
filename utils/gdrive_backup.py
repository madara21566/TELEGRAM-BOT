import os, time, zipfile
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.file']
SERVICE_ACCOUNT_FILE = "credentials.json"
FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")

def create_zip():
    path = f"data_backup_{int(time.time())}.zip"
    if os.path.exists(path): os.remove(path)

    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk('data'):
            for f in files:
                full_path = os.path.join(root, f)
                z.write(full_path, os.path.relpath(full_path, 'data'))
    return path

def upload_to_drive():
    creds = Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build('drive', 'v3', credentials=creds)

    file_path = create_zip()
    file_name = os.path.basename(file_path)

    file_metadata = {
        "name": file_name,
        "parents": [FOLDER_ID]
    }
    media = MediaFileUpload(file_path, mimetype='application/zip')

    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    print("Backup uploaded:", file.get("id"))
    return file_path
