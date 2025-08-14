#!/usr/bin/env python3
"""
Simple test runner to demonstrate the new functionality.
Tests DAO, scorer, and tailor modules with basic SQLite setup.
"""

import os
import tempfile
import sqlite3
import json
from pathlib import Path
from uuid import uuid4, UUID

def setup_test_database(db_path: str):
    """Create a simple SQLite database for testing."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create jobs table (matching the actual schema)
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
    
    # Create applications table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications(
          app_id INTEGER PRIMARY KEY,
          job_id INTEGER REFERENCES jobs(job_id),
          resume_path TEXT,
          portal TEXT,
          tracking_url TEXT,
          status TEXT DEFAULT 'prepared',
          submitted_at TIMESTAMP
        )
    """)
    
    # Create contacts table
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
    
    # Create outreach_enhanced table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS outreach_enhanced(
          outreach_id INTEGER PRIMARY KEY,
          job_id INTEGER REFERENCES jobs(job_id),
          contact_id INTEGER REFERENCES contacts(contact_id),
          channel TEXT,
          subject TEXT,
          message_content TEXT,
          scheduled_at TIMESTAMP,
          sent_at TIMESTAMP,
          reply_status TEXT,
          attempt_count INTEGER DEFAULT 0
        )
    """)
    
    # Create compatibility views
    cursor.execute("DROP VIEW IF EXISTS jobs_view")
    cursor.execute("""
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
    """)
    
    cursor.execute("DROP VIEW IF EXISTS applications_view")
    cursor.execute("""
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
    """)
    
    cursor.execute("DROP VIEW IF EXISTS contacts_view")
    cursor.execute("""
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
    """)
    
    cursor.execute("DROP VIEW IF EXISTS outreach_view")
    cursor.execute("""
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
    """)
    
    conn.commit()
    conn.close()
    print(f"✓ Test database created at {db_path}")


def test_dao_functions():
    """Test DAO insert/update and dedupe functionality."""
    print("\n=== Testing DAO Functions ===")

    # Create temporary database
    fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    try:
        setup_test_database(db_path)

        # Set environment variable for database URL
        original_db_url = os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'

        # Import DAO functions after setting environment
        from apps.worker.dao import insert_job, get_job, list_jobs, update_job_score
        
        # Clean database before test
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM applications")
        cursor.execute("DELETE FROM jobs")
        cursor.execute("DELETE FROM contacts")
        conn.commit()
        conn.close()
        
        # Test 1: Insert job
        job_data = {
            'title': 'Senior Python Developer',
            'company': 'TechCorp Inc',
            'url': 'https://example.com/jobs/python-dev',
            'location': 'San Francisco, CA',
            'description': 'Looking for Python expert with React experience',
            'requirements': 'Python, React, SQL, Docker required',
            'source': 'test'
        }
        
        job_id = insert_job(job_data)
        print(f"✓ Job inserted with ID: {job_id}")
        
        # Test 2: Get job
        retrieved_job = get_job(job_id)
        assert retrieved_job is not None
        assert retrieved_job['title'] == job_data['title']
        assert retrieved_job['company'] == job_data['company']
        print("✓ Job retrieval successful")
        
        # Test 3: Dedupe by URL (upsert)
        modified_data = job_data.copy()
        modified_data['title'] = 'Updated Python Developer'
        job_id_2 = insert_job(modified_data)
        
        # Should be same ID due to URL uniqueness
        assert str(job_id) == str(job_id_2)
        
        # Verify update
        updated_job = get_job(job_id)
        assert updated_job['title'] == 'Updated Python Developer'
        print("✓ URL deduplication working correctly")
        
        # Test 4: List jobs
        all_jobs = list_jobs()
        assert len(all_jobs) == 1
        print("✓ Job listing successful")
        
        # Test 5: Update job score
        match_reasons = ['Strong Python experience', 'React knowledge']
        update_job_score(job_id, 85, match_reasons)
        
        scored_job = get_job(job_id)
        assert scored_job['score'] == 85
        assert scored_job['match_reasons'] == ', '.join(match_reasons)
        print("✓ Job scoring update successful")
        
        print("✅ All DAO tests passed!")
        
    finally:
        # Cleanup
        if original_db_url:
            os.environ['DATABASE_URL'] = original_db_url
        else:
            os.environ.pop('DATABASE_URL', None)
        
        try:
            os.unlink(db_path)
        except OSError:
            pass


def test_scorer_functions():
    """Test skill extraction and job scoring."""
    print("\n=== Testing Scorer Functions ===")
    
    from apps.worker.scorer import extract_skills, score_job, score_job_from_description
    
    # Test 1: Skill extraction
    job_text = """
    We are looking for a Senior Python Developer with strong React experience.
    Must have experience with SQL databases, Docker containerization, and AWS.
    Knowledge of JavaScript and TypeScript is required.
    """
    
    extracted_skills = extract_skills(job_text)
    expected_skills = {'python', 'react', 'sql', 'docker', 'aws', 'javascript', 'typescript'}
    
    assert set(extracted_skills).issuperset({'python', 'react', 'sql', 'docker', 'aws'})
    print(f"✓ Skills extracted: {extracted_skills}")
    
    # Test 2: Job scoring
    job_skills = ['python', 'react', 'sql', 'docker']
    candidate_skills = ['python', 'react', 'javascript', 'git', 'linux']
    must_haves = {'python'}
    
    score = score_job(job_skills, candidate_skills, must_haves)
    assert 0 <= score <= 100
    print(f"✓ Job scored: {score}/100")
    
    # Test 3: End-to-end scoring
    result = score_job_from_description(job_text)
    assert 'score' in result
    assert 'extracted_skills' in result
    assert 'analysis' in result
    assert 'match_reasons' in result
    print(f"✓ End-to-end scoring: {result['score']}/100 with {len(result['extracted_skills'])} skills")
    
    print("✅ All scorer tests passed!")


def test_tailor_functions():
    """Test tailored asset generation."""
    print("\n=== Testing Tailor Functions ===")
    
    from apps.worker.tailor import build_tailored_assets, FileManager
    
    # Create temporary output directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Test data
        job_id = uuid4()
        job_data = {
            'title': 'Senior Python Developer',
            'company': 'TechCorp Inc',
            'url': 'https://techcorp.com/jobs/python-dev',
            'location': 'San Francisco, CA',
            'description': 'Looking for Python expert with React experience',
            'requirements': 'Python, React, SQL, Docker required',
            'skills': ['python', 'react', 'sql', 'docker'],
            'score': 85,
            'match_reasons': ['Strong Python background', 'React experience']
        }
        
        # Test 1: Build tailored assets
        assets = build_tailored_assets(job_id, job_data, temp_path)
        
        expected_assets = ['resume_docx', 'resume_txt', 'cover_email', 'linkedin_msg', 'meta_json']
        for asset_type in expected_assets:
            assert asset_type in assets
            assert assets[asset_type].exists()
            assert assets[asset_type].stat().st_size > 0
        
        print(f"✓ Created {len(assets)} tailored assets")
        
        # Test 2: Verify content quality (no fabrication)
        resume_content = assets['resume_txt'].read_text().lower()
        
        # Should mention relevant skills
        assert 'python' in resume_content
        print("✓ Resume mentions relevant skills")
        
        # Should not fabricate years of experience
        fabricated_patterns = ['10 years', '15 years', '20 years']
        for pattern in fabricated_patterns:
            assert pattern not in resume_content
        print("✓ No fabricated experience claims found")
        
        # Test 3: FileManager compatibility
        file_manager = FileManager(temp_path)
        resume_path = file_manager.create_resume_txt(job_id, job_data)
        assert resume_path.exists()
        print("✓ FileManager compatibility confirmed")
        
        # Test 4: Check metadata
        meta_content = assets['meta_json'].read_text()
        meta_data = json.loads(meta_content)
        
        assert meta_data['job']['id'] == str(job_id)
        assert meta_data['job']['title'] == job_data['title']
        assert 'no_fabrication' in meta_data['guidelines']
        assert meta_data['guidelines']['no_fabrication'] == True
        print("✓ Metadata includes anti-fabrication guidelines")
        
        print("✅ All tailor tests passed!")


def main():
    """Run all tests."""
    print("🧪 Running Job Bot Tests")
    print("=" * 50)
    
    try:
        test_dao_functions()
        test_scorer_functions()
        test_tailor_functions()
        
        print("\n" + "=" * 50)
        print("🎉 All tests passed successfully!")
        print("\nKey features tested:")
        print("✓ DAO insert/update with URL deduplication")
        print("✓ Skill extraction from job descriptions")
        print("✓ Job compatibility scoring")
        print("✓ Tailored asset generation without fabrication")
        print("✓ Temporary SQLite database configuration")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
