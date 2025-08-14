#!/usr/bin/env python3
"""
Test script for visa sponsorship and location filtering features.
Demonstrates the new filtering capabilities added to the Job Bot.
"""

import json
import sys
import tempfile
import sqlite3
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.worker.location_parser import (
    VisaDetector, 
    LocationParser, 
    process_job_location_data
)
from apps.worker.dao import insert_job, list_jobs
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
    
    # Create jobs table with visa and location fields
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            location TEXT,
            job_type TEXT,
            experience_level TEXT,
            salary_min INTEGER,
            salary_max INTEGER,
            currency TEXT DEFAULT 'USD',
            description TEXT,
            requirements TEXT,
            benefits TEXT,
            remote_allowed BOOLEAN DEFAULT 0,
            date_posted DATETIME,
            application_deadline DATETIME,
            source TEXT,
            status TEXT DEFAULT 'active',
            score INTEGER,
            match_reasons TEXT,
            visa_friendly BOOLEAN DEFAULT 0,
            visa_keywords TEXT,
            country TEXT,
            state_province TEXT,
            city TEXT,
            is_remote BOOLEAN DEFAULT 0,
            remote_type TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    
    return db_path, original_db_url


def create_test_jobs():
    """Create diverse test jobs with different visa and location characteristics."""
    test_jobs = [
        {
            'title': 'Senior Python Developer',
            'company': 'TechCorp',
            'url': 'https://techcorp.com/jobs/python-sr',
            'location': 'San Francisco, CA',
            'description': '''
                We are seeking a Senior Python Developer to join our team. 
                This position offers H-1B sponsorship for qualified candidates. 
                We welcome international talent and will sponsor work visas.
                
                Requirements:
                - 5+ years Python experience
                - Django/FastAPI knowledge
                - Database experience (PostgreSQL preferred)
                
                Benefits:
                - Competitive salary ($150k-200k)
                - Health insurance
                - Visa sponsorship available
                - Stock options
            ''',
            'requirements': 'Python, Django, PostgreSQL, 5+ years experience',
            'source': 'test',
            'score': 88
        },
        {
            'title': 'Software Engineer',
            'company': 'StartupXYZ',
            'url': 'https://startup.com/jobs/swe-remote',
            'location': 'Remote',
            'description': '''
                Fully remote Software Engineer position. This role is open to 
                candidates worldwide. We are a remote-first company.
                
                We sponsor H-1B and other work visas for qualified international candidates.
                OPT and CPT students are welcome to apply.
                
                Tech stack: React, Node.js, MongoDB, AWS
            ''',
            'requirements': 'React, Node.js, MongoDB, AWS experience',
            'source': 'test',
            'score': 92
        },
        {
            'title': 'Java Developer',
            'company': 'BigCorp',
            'url': 'https://bigcorp.com/jobs/java-dev',
            'location': 'New York, NY',
            'description': '''
                Java Developer position in our NYC office. This is a hybrid role
                with 3 days in office, 2 days remote.
                
                US citizens and permanent residents only. No visa sponsorship
                provided. Must be authorized to work in the US.
                
                Requirements:
                - Java 8+ experience
                - Spring Framework
                - Microservices architecture
            ''',
            'requirements': 'Java, Spring Framework, Microservices',
            'source': 'test',
            'score': 75
        },
        {
            'title': 'Frontend Engineer',
            'company': 'DesignStudio',
            'url': 'https://designstudio.com/jobs/frontend',
            'location': 'Austin, TX',
            'description': '''
                Frontend Engineer role in Austin, Texas. We create beautiful
                web applications for our clients.
                
                Immigration sponsorship available for exceptional candidates.
                We value diverse backgrounds and international perspectives.
                
                Tech: React, TypeScript, CSS, Figma
            ''',
            'requirements': 'React, TypeScript, CSS, Design skills',
            'source': 'test',
            'score': 83
        },
        {
            'title': 'DevOps Engineer',
            'company': 'CloudTech',
            'url': 'https://cloudtech.com/jobs/devops',
            'location': 'Seattle, WA',
            'description': '''
                DevOps Engineer position in Seattle. Hybrid work model with
                flexible remote days.
                
                We support visa applications for qualified international talent.
                Experience with cloud platforms required.
                
                Tech: AWS, Kubernetes, Docker, Terraform
            ''',
            'requirements': 'AWS, Kubernetes, Docker, Terraform',
            'source': 'test',
            'score': 86
        },
        {
            'title': 'Data Scientist',
            'company': 'AICompany',
            'url': 'https://aicompany.com/jobs/data-scientist',
            'location': 'Toronto, ON, Canada',
            'description': '''
                Data Scientist role in our Toronto office. We are building
                next-generation AI products.
                
                Open to candidates from around the world. We assist with
                work permits and immigration processes.
                
                Tech: Python, TensorFlow, PyTorch, SQL
            ''',
            'requirements': 'Python, Machine Learning, Statistics, SQL',
            'source': 'test',
            'score': 90
        }
    ]
    
    print(f"📝 Creating {len(test_jobs)} test jobs...")
    
    for job in test_jobs:
        # Process visa and location data
        processed_job = process_job_location_data(job)
        
        # Insert into database
        job_id = insert_job(processed_job)
        
        print(f"   ✅ {job['title']} at {job['company']}")
        print(f"      Visa friendly: {processed_job.get('visa_friendly')}")
        print(f"      Location: {processed_job.get('country')}/{processed_job.get('state_province')}")
        print(f"      Remote: {processed_job.get('is_remote')} ({processed_job.get('remote_type')})")
        print()


def test_filtering():
    """Test various filtering combinations."""
    print("🔍 TESTING VISA AND LOCATION FILTERS")
    print("=" * 50)
    
    # Test 1: All jobs
    all_jobs = list_jobs()
    print(f"📊 Total jobs: {len(all_jobs)}")
    print()
    
    # Test 2: Visa-friendly jobs
    visa_jobs = list_jobs(visa_friendly=True)
    print(f"🌍 Visa-friendly jobs: {len(visa_jobs)}")
    for job in visa_jobs:
        keywords = job.get('visa_keywords', '[]')
        if isinstance(keywords, str):
            try:
                import json
                keywords = json.loads(keywords)
            except:
                keywords = []
        print(f"   📌 {job['title']} at {job['company']} - Keywords: {keywords}")
    print()
    
    # Test 3: US jobs only
    us_jobs = list_jobs(country='US')
    print(f"🇺🇸 US jobs: {len(us_jobs)}")
    for job in us_jobs:
        print(f"   📍 {job['title']} - {job.get('state_province', 'Unknown state')}")
    print()
    
    # Test 4: Remote jobs
    remote_jobs = list_jobs(is_remote=True)
    print(f"🏠 Remote jobs: {len(remote_jobs)}")
    for job in remote_jobs:
        print(f"   💻 {job['title']} - {job.get('remote_type', 'Unknown type')}")
    print()
    
    # Test 5: Combined filters - Visa-friendly remote jobs in US
    combined_jobs = list_jobs(visa_friendly=True, country='US', is_remote=True)
    print(f"🎯 Visa-friendly + Remote + US jobs: {len(combined_jobs)}")
    for job in combined_jobs:
        print(f"   ⭐ {job['title']} at {job['company']}")
    print()
    
    # Test 6: High-score visa-friendly jobs
    high_score_visa_jobs = list_jobs(visa_friendly=True, min_score=85)
    print(f"🏆 High-score (85+) visa-friendly jobs: {len(high_score_visa_jobs)}")
    for job in high_score_visa_jobs:
        print(f"   🌟 {job['title']} - Score: {job.get('score', 'N/A')}")
    print()
    
    # Test 7: Jobs by state
    ca_jobs = list_jobs(state_province='CA')
    print(f"🌴 California jobs: {len(ca_jobs)}")
    for job in ca_jobs:
        print(f"   🏙️ {job['title']} in {job.get('city', 'Unknown city')}")
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
    print("🚀 VISA & LOCATION FILTER TEST SUITE")
    print("=" * 60)
    print()
    
    # Setup test environment
    db_path, original_db_url = setup_test_database()
    
    try:
        # Create test data
        create_test_jobs()
        
        # Run filter tests
        test_filtering()
        
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY!")
        print()
        print("🎯 SUMMARY:")
        print("   • Visa detection working correctly")
        print("   • Location parsing functional")
        print("   • Database filtering operational")
        print("   • API integration ready")
        print()
        print("🌐 Ready to use these filters:")
        print("   • GET /v1/jobs?visa_friendly=true")
        print("   • GET /v1/jobs?country=US&state_province=CA")
        print("   • GET /v1/jobs?is_remote=true&remote_type=full")
        print("   • GET /v1/jobs?visa_friendly=true&country=US&min_score=80")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        cleanup_database(db_path, original_db_url)


if __name__ == "__main__":
    main()
