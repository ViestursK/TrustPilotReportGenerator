#!/usr/bin/env python3
"""
Google Sheets Authentication Setup
Run this once to set up OAuth authentication
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive.file'
]

def setup_oauth():
    """Set up OAuth authentication"""
    print("\n" + "="*70)
    print("GOOGLE SHEETS AUTHENTICATION SETUP")
    print("="*70 + "\n")
    
    # Check for credentials.json
    if not os.path.exists('credentials.json'):
        print("[ERROR] credentials.json not found!")
        print("\nTo get credentials.json:")
        print("1. Go to: https://console.cloud.google.com/")
        print("2. Create a new project (or select existing)")
        print("3. Enable Google Sheets API")
        print("4. Go to Credentials → Create Credentials → OAuth Client ID")
        print("5. Application type: Desktop app")
        print("6. Download JSON and save as 'credentials.json'")
        print("\nThen run this script again.")
        return False
    
    creds = None
    
    # Check if token already exists
    if os.path.exists('token.json'):
        print("[INFO] Existing token found, refreshing...")
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If no valid credentials, do OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[INFO] Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("[INFO] Starting OAuth flow...")
            print("[INFO] Your browser will open for authentication")
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
        
        print("[SUCCESS] Authentication complete!")
        print("[SUCCESS] token.json saved")
    else:
        print("[SUCCESS] Existing token is valid")
    
    print("\n" + "="*70)
    print("[COMPLETE] You can now run generate_sheets_report.py")
    print("="*70 + "\n")
    
    return True

if __name__ == "__main__":
    setup_oauth()