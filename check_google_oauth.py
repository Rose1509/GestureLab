#!/usr/bin/env python3
"""
Test script to verify Google OAuth configuration
Run this before starting your app to check if credentials are properly set up
"""

import os
from pathlib import Path

def check_google_oauth_config():
    print("=" * 60)
    print("Google OAuth Configuration Check")
    print("=" * 60)
    
    # Check .env file
    env_file = Path(".env")
    if env_file.exists():
        print("✓ .env file found")
        
        # Load .env (without using load_dotenv to see actual values)
        with open(".env") as f:
            content = f.read()
            
        if "GOOGLE_CLIENT_SECRETS_FILE" in content:
            print("✓ GOOGLE_CLIENT_SECRETS_FILE is set")
            
            # Check if credentials file exists
            for line in content.split("\n"):
                if "GOOGLE_CLIENT_SECRETS_FILE=" in line:
                    creds_file = line.split("=")[1].strip()
                    if Path(creds_file).exists():
                        print(f"  ✓ Credentials file found: {creds_file}")
                    else:
                        print(f"  ✗ Credentials file NOT found: {creds_file}")
                        print(f"    Please download it from Google Cloud Console")
                    break
                    
        elif "GOOGLE_CLIENT_ID" in content and "GOOGLE_CLIENT_SECRET" in content:
            print("✓ GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set")
        else:
            print("✗ No Google OAuth credentials found in .env")
            print("  Please follow the GOOGLE_OAUTH_SETUP.md guide")
    else:
        print("✗ .env file not found")
        print("  Please create a .env file with Google OAuth credentials")
        print("  See .env.example or GOOGLE_OAUTH_SETUP.md for instructions")
    
    # Check credentials.json
    creds_json = Path("credentials.json")
    if creds_json.exists():
        print("✓ credentials.json file found")
    else:
        print("  (credentials.json not found - you may be using env variables instead)")
    
    # Check required packages
    print("\n" + "=" * 60)
    print("Required Packages Check")
    print("=" * 60)
    
    required_packages = [
        ("google_auth_oauthlib", "google-auth-oauthlib"),
        ("google.oauth2", "google-auth"),
        ("dotenv", "python-dotenv"),
    ]
    
    for module_name, package_name in required_packages:
        try:
            __import__(module_name)
            print(f"✓ {package_name} is installed")
        except ImportError:
            print(f"✗ {package_name} is NOT installed")
            print(f"  Run: pip install {package_name}")
    
    print("\n" + "=" * 60)
    print("Next Steps:")
    print("=" * 60)
    print("1. Ensure all checks above show ✓")
    print("2. Start your app: uvicorn app.main:app --reload")
    print("3. Visit http://127.0.0.1:8000/login")
    print("4. Click 'Sign up with Google' button")
    print("=" * 60)


if __name__ == "__main__":
    check_google_oauth_config()
