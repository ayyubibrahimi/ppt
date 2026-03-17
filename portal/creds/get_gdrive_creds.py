"""
One-time script to get Google Drive OAuth tokens for manual database insertion.
Run this once to get your tokens, then paste them into Supabase.
"""
import os
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import json

# If modifying these scopes, delete the token file.
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_google_drive_tokens():
    """
    Get Google Drive OAuth tokens through browser flow.
    Returns tokens that can be stored in Supabase.
    """
    
    print("🔐 Google Drive OAuth Token Generator")
    print("=" * 60)
    print()
    print("Prerequisites:")
    print("1. Go to https://console.cloud.google.com/")
    print("2. Create a project (or use existing)")
    print("3. Enable Google Drive API")
    print("4. Create OAuth 2.0 credentials (Desktop app)")
    print("5. Download the credentials JSON file")
    print()
    
    # Check for credentials file
    creds_file = input("Enter path to your credentials JSON file (or press Enter for 'credentials.json'): ").strip()
    if not creds_file:
        creds_file = 'credentials.json'
    
    if not os.path.exists(creds_file):
        print(f"❌ Error: {creds_file} not found!")
        print()
        print("Please download OAuth credentials from Google Cloud Console:")
        print("https://console.cloud.google.com/apis/credentials")
        return None
    
    try:
        # Create flow from client secrets file
        flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
        
        # Run the OAuth flow - this will open a browser
        print("\n🌐 Opening browser for Google authentication...")
        print("Please sign in and authorize the application.")
        print()
        
        creds = flow.run_local_server(port=0)
        
        # Extract token information
        token_data = {
            'access_token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': creds.scopes,
            'expiry': creds.expiry.isoformat() if creds.expiry else None
        }
        
        print("✅ Successfully obtained tokens!")
        print("=" * 60)
        print()
        print("📋 COPY THESE VALUES TO YOUR SUPABASE USER RECORD:")
        print("=" * 60)
        print()
        print(f"google_drive_enabled: true")
        print(f"google_drive_refresh_token: {creds.refresh_token}")
        print(f"google_drive_access_token: {creds.token}")
        print(f"google_drive_token_expiry: {creds.expiry.isoformat() if creds.expiry else 'NULL'}")
        print()
        print("=" * 60)
        print()
        print("💡 To update your user record in Supabase:")
        print("1. Go to your Supabase dashboard")
        print("2. Open the 'users' table")
        print("3. Find your user record")
        print("4. Update the columns with the values above")
        print()
        print("📝 Full token data saved to 'google_drive_tokens.json' (for backup)")
        
        # Save to file for reference
        with open('google_drive_tokens.json', 'w') as f:
            json.dump(token_data, f, indent=2, default=str)
        
        return token_data
        
    except Exception as e:
        print(f"❌ Error obtaining tokens: {str(e)}")
        return None


if __name__ == '__main__':
    get_google_drive_tokens()