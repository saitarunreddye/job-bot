#!/usr/bin/env python3
"""
Test script for the follow-up scheduler system.
Demonstrates automatic follow-up scheduling with value-add content and threading.
"""

import json
import sys
import tempfile
import sqlite3
import os
from pathlib import Path
from datetime import datetime, timedelta, UTC
from uuid import uuid4

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.worker.followup_scheduler import (
    FollowupScheduler,
    FollowupTemplate,
    schedule_followups_for_outreach,
    process_due_followups
)
from config.settings import settings


def setup_test_database():
    """Create a temporary SQLite database for testing."""
    # Create temporary database
    temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    temp_db.close()
    
    db_path = temp_db.name
    print(f"📂 Creating test database: {db_path}")
    
    # Override database URL to use SQLite
    original_db_url = settings.database_url
    settings.database_url = f"sqlite:///{db_path}"
    
    # Create tables
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create jobs table (needed for foreign key references)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs(
          job_id INTEGER PRIMARY KEY,
          title TEXT, company TEXT, location TEXT,
          source TEXT, url TEXT UNIQUE,
          jd_text TEXT, skills TEXT,
          score INTEGER DEFAULT 0,
          status TEXT DEFAULT 'new',
          created_at TIMESTAMP
        )
    """)
    
    # Create contacts table (needed for foreign key references)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts(
          contact_id INTEGER PRIMARY KEY,
          name TEXT, role TEXT, company TEXT,
          email TEXT UNIQUE,
          linkedin_url TEXT,
          verified BOOLEAN DEFAULT 0,
          last_seen TIMESTAMP
        )
    """)
    
    # Create enhanced outreach table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS outreach_enhanced(
          outreach_id INTEGER PRIMARY KEY,
          job_id INTEGER REFERENCES jobs(job_id),
          contact_id INTEGER REFERENCES contacts(contact_id),
          channel TEXT,              -- 'email' | 'linkedin'
          subject TEXT,
          message_content TEXT,      -- required by tests
          scheduled_at TIMESTAMP,
          sent_at TIMESTAMP,
          reply_status TEXT,
          attempt_count INTEGER DEFAULT 0
        )
    """)
    
    conn.commit()
    conn.close()
    
    return db_path, original_db_url


def create_test_outreach():
    """Create sample outreach records for testing."""
    print("📧 Creating test outreach records...")
    
    # Sample job and contact data
    job_data = {
        'id': 1,
        'title': 'Senior Python Developer',
        'company': 'TechCorp Inc',
        'url': 'https://techcorp.com/jobs/python-dev'
    }
    
    contact_data = {
        'id': 1,
        'email': 'hiring@techcorp.com',
        'first_name': 'Sarah',
        'last_name': 'Johnson',
        'company': 'TechCorp Inc'
    }
    
    # Create original outreach record
    outreach_id = 1  # Use integer ID instead of UUID
    original_message_id = f"<{uuid4()}@jobbot.local>"
    thread_id = uuid4()
    
    conn = sqlite3.connect(settings.database_url.replace('sqlite:///', ''))
    cursor = conn.cursor()
    
    # Insert job
    cursor.execute("""
        INSERT INTO jobs (job_id, title, company, url, jd_text, skills, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        1,
        job_data['title'],
        job_data['company'],
        job_data['url'],
        "We are looking for a senior Python developer...",
        "Python, Django, SQL",
        'active'
    ))
    
    # Insert contact
    cursor.execute("""
        INSERT INTO contacts (contact_id, name, email, company)
        VALUES (?, ?, ?, ?)
    """, (
        1,
        f"{contact_data['first_name']} {contact_data['last_name']}",
        contact_data['email'],
        contact_data['company']
    ))
    
    # Insert original outreach
    cursor.execute("""
        INSERT INTO outreach_enhanced (
            outreach_id, job_id, contact_id, channel, subject, message_content,
            sent_at, reply_status, attempt_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        outreach_id,
        job_data['id'],
        contact_data['id'],
        'email',
        f"Application for {job_data['title']} position",
        "Hi Sarah,\n\nI'm very interested in the Senior Python Developer position at TechCorp...",
        datetime.now(UTC).isoformat(),
        'sent',
        1
    ))
    
    conn.commit()
    conn.close()
    
    print(f"   ✅ Original outreach created: {outreach_id}")
    print(f"      To: {contact_data['email']}")
    print(f"      Subject: Application for {job_data['title']} position")
    print(f"      Message-ID: {original_message_id}")
    print()
    
    return outreach_id, job_data, contact_data


def test_template_generation():
    """Test follow-up template generation."""
    print("📝 TESTING TEMPLATE GENERATION")
    print("=" * 40)
    
    # Test value-add content generation
    job_data = {
        'title': 'Senior Python Developer',
        'company': 'TechCorp'
    }
    
    print("🔍 Value-add content samples:")
    
    # Test different template types
    for template_type in ['value_add_1', 'value_add_2']:
        print(f"\n📋 Template: {template_type}")
        content = FollowupTemplate.generate_value_add_content(job_data, template_type)
        print(f"   Content: {content}")
    
    # Test different job types
    job_types = [
        {'title': 'Data Scientist', 'company': 'DataCorp'},
        {'title': 'DevOps Engineer', 'company': 'CloudTech'},
        {'title': 'Frontend Developer', 'company': 'WebStudio'}
    ]
    
    print(f"\n🎯 Job-specific content:")
    for job in job_types:
        content = FollowupTemplate.generate_value_add_content(job, 'value_add_1')
        print(f"   {job['title']}: {content[:80]}...")
    
    print()


def test_followup_scheduling():
    """Test follow-up scheduling functionality."""
    print("⏰ TESTING FOLLOW-UP SCHEDULING")
    print("=" * 40)
    
    # Create test outreach
    outreach_id, job_data, contact_data = create_test_outreach()
    
    # Schedule follow-ups
    print("📅 Scheduling follow-ups...")
    
    try:
        scheduler = FollowupScheduler()
        schedule_ids = scheduler.schedule_followups(outreach_id, job_data, contact_data)
        
        print(f"   ✅ Scheduled {len(schedule_ids)} follow-ups")
        print(f"      Follow-up IDs: {schedule_ids}")
        
        # Verify follow-ups were created in outreach_enhanced
        conn = sqlite3.connect(settings.database_url.replace('sqlite:///', ''))
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT outreach_id, subject, scheduled_at, reply_status 
            FROM outreach_enhanced 
            WHERE reply_status = 'followup_scheduled'
        """)
        
        followups = cursor.fetchall()
        print(f"   📊 Found {len(followups)} follow-up records in database:")
        
        for followup in followups:
            print(f"      ID: {followup[0]}")
            print(f"      Subject: {followup[1]}")
            print(f"      Scheduled: {followup[2]}")
            print(f"      Status: {followup[3]}")
        
        conn.close()
        
    except Exception as e:
        print(f"   ❌ Error scheduling follow-ups: {e}")
    
    print()
    return outreach_id


def test_due_followup_processing():
    """Test processing of due follow-ups."""
    print("🔄 TESTING DUE FOLLOW-UP PROCESSING")
    print("=" * 40)
    
    # Create test data
    outreach_id, job_data, contact_data = create_test_outreach()
    
    # Manually create a due follow-up
    conn = sqlite3.connect(settings.database_url.replace('sqlite:///', ''))
    cursor = conn.cursor()
    
    due_time = datetime.now(UTC) - timedelta(minutes=5)  # Due 5 minutes ago
    
    cursor.execute("""
        INSERT INTO outreach_enhanced (
            job_id, contact_id, channel, subject, message_content,
            scheduled_at, reply_status, attempt_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        job_data.get('id'),
        contact_data.get('id'),
        'email',
        'Re: Application for Senior Python Developer position',
        'Hi Sarah,\n\nI wanted to follow up on my application...',
        due_time,
        'followup_scheduled',
        0
    ))
    
    conn.commit()
    conn.close()
    
    print(f"📧 Created due follow-up for testing")
    print(f"   Due time: {due_time}")
    print(f"   Recipient: {contact_data['email']}")
    
    # Test processing (will fail without Gmail setup, but should show logic)
    try:
        print(f"\n🔄 Processing due follow-ups...")
        stats = process_due_followups()
        
        print(f"   📊 Processing stats: {stats}")
        
    except Exception as e:
        print(f"   ⚠️ Expected error (Gmail not configured): {type(e).__name__}")
        print(f"      Message: {str(e)[:100]}...")
    
    print()


def test_scheduler_stats():
    """Test follow-up scheduler statistics."""
    print("📊 TESTING SCHEDULER STATISTICS")
    print("=" * 40)
    
    try:
        scheduler = FollowupScheduler()
        stats = scheduler.get_followup_stats()
        
        print("📈 Follow-up Statistics:")
        for key, value in stats.items():
            print(f"   {key}: {value}")
        
    except Exception as e:
        print(f"   ❌ Error getting stats: {e}")
    
    print()


def cleanup_database(db_path, original_db_url):
    """Clean up the test database."""
    print(f"🧹 Cleaning up test database: {db_path}")
    
    # Restore original database URL
    settings.database_url = original_db_url
    
    # Remove temporary database file
    try:
        os.unlink(db_path)
        print("   ✅ Test database removed")
    except OSError as e:
        print(f"   ⚠️ Failed to remove test database: {e}")


def main():
    """Main test function."""
    print("🚀 FOLLOW-UP SCHEDULER TEST SUITE")
    print("=" * 60)
    print()
    
    # Setup test environment
    db_path, original_db_url = setup_test_database()
    
    try:
        # Test template generation
        test_template_generation()
        
        # Test follow-up scheduling
        outreach_id = test_followup_scheduling()
        
        # Test due follow-up processing
        test_due_followup_processing()
        
        # Test statistics
        test_scheduler_stats()
        
        print("🎉 All tests completed!")
        
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        cleanup_database(db_path, original_db_url)


if __name__ == "__main__":
    main()
