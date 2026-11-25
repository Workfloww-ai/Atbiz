"""
Google OAuth Login Script for AT BiZ
Enables you to connect Google Drive using your personal Google ID.
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CLIENT_SECRETS_FILE = "credentials.json"
TOKEN_FILE = "token.json"

def login_with_google_account():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print("=" * 60)
        print("STEP 1: GET YOUR OAUTH CLIENT ID")
        print("=" * 60)
        print("1. Go to Google Cloud Console: https://console.cloud.google.com/apis/credentials")
        print("2. Click '+ CREATE CREDENTIALS' -> 'OAuth client ID'")
        print("3. Application type: Choose 'Desktop app'")
        print("4. Click 'Create', then click 'DOWNLOAD JSON'")
        print("5. Save the downloaded file as 'credentials.json' in 'atbiz-backend/'")
        print("=" * 60)
        return

    print("Opening browser for Google Login...")
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    # Save credentials for subsequent runs
    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())

    print("\nSUCCESS! Successfully logged in with your Google Account.")
    print(f"Token saved to: {TOKEN_FILE}")
    print("AT BiZ can now directly access your Google Drive using your Google ID!")

if __name__ == "__main__":
    login_with_google_account()
