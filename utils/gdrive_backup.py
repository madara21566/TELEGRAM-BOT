import os
import time
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive

def upload_to_drive(file_path):
    try:
        gauth = GoogleAuth()
        gauth.LoadCredentialsFile("data/google_credentials.json")

        if gauth.credentials is None:
            return False
        elif gauth.access_token_expired:
            gauth.Refresh()
        else:
            gauth.Authorize()

        drive = GoogleDrive(gauth)

        file = drive.CreateFile({
            'title': os.path.basename(file_path),
            'parents': [{'id': os.getenv("GDRIVE_FOLDER_ID")}]
        })
        file.SetContentFile(file_path)
        file.Upload()

        return True

    except Exception as e:
        print(f"GDrive Upload Error: {e}")
        return False
