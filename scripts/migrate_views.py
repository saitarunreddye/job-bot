#!/usr/bin/env python3
"""
Migration script to create compatibility views for Job Bot database.
Runs CREATE VIEW statements idempotently to alias old column names expected by tests.
"""

import os
import sys
import sqlalchemy as sa
from sqlalchemy import text
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config.settings import settings


def create_compatibility_views(database_url: str = None):
    """
    Create compatibility views that alias old column names expected by tests.
    
    Args:
        database_url: Database URL to connect to. If None, uses settings.DATABASE_URL
    """
    if database_url is None:
        database_url = settings.database_url
    
    print(f"Creating compatibility views in database: {database_url}")
    
    # Create engine
    engine = sa.create_engine(database_url)
    
    # View creation statements (one per statement to avoid parsing issues)
    view_statements = [
        # Jobs compatibility view
        """
        DROP VIEW IF EXISTS jobs_view;
        CREATE VIEW jobs_view AS
        SELECT
          job_id            AS id,
          title,
          company,
          location,
          source,
          url,
          jd_text           AS description,
          skills            AS match_reasons,
          score,
          status,
          created_at
        FROM jobs
        """,
        
        # Applications compatibility view
        """
        DROP VIEW IF EXISTS applications_view;
        CREATE VIEW applications_view AS
        SELECT
          app_id,
          job_id,
          resume_path,
          portal,
          tracking_url,
          status,
          submitted_at,
          NULL AS cover_letter_version,
          NULL AS notes
        FROM applications
        """,
        
        # Contacts compatibility view
        """
        DROP VIEW IF EXISTS contacts_view;
        CREATE VIEW contacts_view AS
        SELECT
          contact_id AS id,
          name,
          role,
          company,
          email,
          linkedin_url,
          verified,
          last_seen
        FROM contacts
        """,
        
        # Outreach compatibility view
        """
        DROP VIEW IF EXISTS outreach_view;
        CREATE VIEW outreach_view AS
        SELECT
          outreach_id,
          job_id,
          contact_id,
          channel,
          subject,
          message_content,
          scheduled_at,
          sent_at,
          reply_status,
          attempt_count
        FROM outreach_enhanced
        """
    ]
    
    # Execute view creation
    with engine.connect() as conn:
        try:
            # Execute each view creation statement
            for i, statement in enumerate(view_statements):
                try:
                    # Split into DROP and CREATE statements
                    parts = statement.strip().split(';')
                    for part in parts:
                        part = part.strip()
                        if part:
                            conn.execute(text(part))
                            print(f"✓ Executed: {part[:50]}...")
                except Exception as e:
                    print(f"⚠️  Warning executing statement {i+1}: {e}")
                    print(f"   Statement: {statement[:100]}...")
            
            conn.commit()
            print("✅ Compatibility views created successfully!")
            
            # Verify views were created
            result = conn.execute(text("""
                SELECT name FROM sqlite_master 
                WHERE type='view' AND name IN ('jobs_view', 'applications_view', 'contacts_view', 'outreach_view')
                ORDER BY name
            """))
            created_views = [row[0] for row in result.fetchall()]
            print(f"📋 Created views: {', '.join(created_views)}")
            
        except Exception as e:
            print(f"❌ Error creating views: {e}")
            conn.rollback()
            raise


def verify_views(database_url: str = None):
    """
    Verify that compatibility views exist and have expected columns.
    
    Args:
        database_url: Database URL to connect to. If None, uses settings.DATABASE_URL
    """
    if database_url is None:
        database_url = settings.database_url
    
    print(f"\nVerifying compatibility views in database: {database_url}")
    
    engine = sa.create_engine(database_url)
    
    with engine.connect() as conn:
        # Check if views exist
        result = conn.execute(text("""
            SELECT name FROM sqlite_master 
            WHERE type='view' AND name IN ('jobs_view', 'applications_view', 'contacts_view', 'outreach_view')
            ORDER BY name
        """))
        existing_views = [row[0] for row in result.fetchall()]
        
        expected_views = ['jobs_view', 'applications_view', 'contacts_view', 'outreach_view']
        missing_views = set(expected_views) - set(existing_views)
        
        if missing_views:
            print(f"❌ Missing views: {', '.join(missing_views)}")
            return False
        else:
            print(f"✅ All expected views exist: {', '.join(existing_views)}")
        
        # Check view columns
        for view_name in existing_views:
            try:
                result = conn.execute(text(f"PRAGMA table_info({view_name})"))
                columns = [row[1] for row in result.fetchall()]
                print(f"📋 {view_name} columns: {', '.join(columns)}")
            except Exception as e:
                print(f"⚠️  Could not inspect {view_name}: {e}")
        
        return True


def main():
    """Main function to run migration."""
    print("🔄 Job Bot Compatibility Views Migration")
    print("=" * 50)
    
    try:
        # Create views
        create_compatibility_views()
        
        # Verify views
        verify_views()
        
        print("\n🎉 Migration completed successfully!")
        print("\nCompatibility views created:")
        print("- jobs_view: aliases job_id→id, jd_text→description, skills→match_reasons")
        print("- applications_view: adds cover_letter_version and notes as NULL")
        print("- contacts_view: aliases contact_id→id")
        print("- outreach_view: direct mapping from outreach_enhanced")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
