#!/usr/bin/env python3
"""
Gmail API setup script.
Helps users set up Gmail OAuth2 authentication for the job bot.
"""

import logging
import sys
from pathlib import Path

# Add the project root to the path so we can import our modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from apps.worker.emailer import setup_gmail, get_quota_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Main setup function for Gmail API."""
    print("=" * 60)
    print("Gmail API Setup for Job Bot")
    print("=" * 60)
    
    print("\n1. Setting up Gmail API authentication...")
    print("   This will open a browser window for OAuth2 authentication.")
    print("   Please make sure you have:")
    print("   - Downloaded OAuth2 credentials from Google Cloud Console")
print("   - Saved them as 'config/configgmail_credentials.json'")
    print("   - Enabled Gmail API in your Google Cloud project")
    
    input("\nPress Enter to continue...")
    
    try:
        # Attempt to set up Gmail
        success = setup_gmail()
        
        if success:
            print("\n✅ Gmail API setup successful!")
            
            # Check quota status
            print("\n2. Checking email quota status...")
            quota_status = get_quota_status()
            print(f"   Daily limit: {quota_status['daily_limit']}")
            print(f"   Used today: {quota_status['sent_count']}")
            print(f"   Remaining: {quota_status['remaining']}")
            
            print("\n🎉 Setup complete! You can now send emails via the job bot.")
            print("\nNext steps:")
            print("1. Start the API server: python -m uvicorn apps.api.main:app --reload")
            print("2. Start the worker: python -m rq worker")
            print("3. Use POST /v1/outreach/email to send application emails")
            
        else:
            print("\n❌ Gmail API setup failed!")
            return 1
            
    except Exception as e:
        print(f"\n❌ Error during setup: {e}")
        logger.error(f"Setup failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
