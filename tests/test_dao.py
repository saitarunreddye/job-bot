"""
Tests for DAO (Data Access Object) functions.
Tests job insertion, updates, deduplication by URL, and application management.
"""

import pytest
from uuid import UUID, uuid4
from datetime import datetime

from apps.worker.dao import (
    insert_job, list_jobs, get_job, create_application, 
    mark_applied, get_unscored_jobs, update_job_score,
    get_application_by_job, get_contacts_by_company,
    ApplicationDAOError
)
from db.db import get_connection, exec_query
from sqlalchemy import text


class TestJobDAO:
    """Test job-related DAO operations."""
    
    def test_insert_job_success(self, sample_job_data):
        """Test successful job insertion."""
        # Insert job
        job_id = insert_job(sample_job_data)
        
        # Verify job was inserted
        assert isinstance(job_id, int)
        
        # Verify job data in database
        job = get_job(job_id)
        assert job is not None
        assert job['title'] == sample_job_data['title']
        assert job['company'] == sample_job_data['company']
        assert job['url'] == sample_job_data['url']
        assert job['source'] == sample_job_data['source']
        assert job['status'] == sample_job_data['status']
    
    def test_insert_job_dedupe_by_url(self, sample_job_data):
        """Test job deduplication by URL."""
        # Insert job first time
        job_id_1 = insert_job(sample_job_data)
        
        # Modify data but keep same URL
        modified_data = sample_job_data.copy()
        modified_data['title'] = 'Updated Title'
        modified_data['company'] = 'Updated Company'
        
        # Insert again with same URL - should update existing
        job_id_2 = insert_job(modified_data)
        
        # Should return same job ID (upsert behavior)
        assert job_id_1 == job_id_2
        
        # Verify updated data
        job = get_job(job_id_1)
        assert job['title'] == 'Updated Title'
        assert job['company'] == 'Updated Company'
        assert job['url'] == sample_job_data['url']  # URL unchanged
        
        # Verify only one job exists
        with get_connection() as conn:
            count = exec_query(conn, "SELECT COUNT(*) FROM jobs").scalar()
            assert count == 1
    
    def test_insert_multiple_different_jobs(self, sample_job_data, sample_job_data_2):
        """Test inserting multiple jobs with different URLs."""
        # Insert two different jobs
        job_id_1 = insert_job(sample_job_data)
        job_id_2 = insert_job(sample_job_data_2)
        
        # Should be different IDs
        assert job_id_1 != job_id_2
        
        # Both should exist
        job_1 = get_job(job_id_1)
        job_2 = get_job(job_id_2)
        
        assert job_1['url'] == sample_job_data['url']
        assert job_2['url'] == sample_job_data_2['url']
        
        # Verify count
        with get_connection() as conn:
            count = exec_query(conn, "SELECT COUNT(*) FROM jobs").scalar()
            assert count == 2
    
    def test_list_jobs_all(self, sample_job_data, sample_job_data_2):
        """Test listing all jobs."""
        # Insert test jobs
        insert_job(sample_job_data)
        insert_job(sample_job_data_2)
        
        # List all jobs
        jobs = list_jobs()
        
        assert len(jobs) == 2
        job_urls = [job['url'] for job in jobs]
        assert sample_job_data['url'] in job_urls
        assert sample_job_data_2['url'] in job_urls
    
    def test_list_jobs_by_status(self, sample_job_data, sample_job_data_2):
        """Test listing jobs filtered by status."""
        # Insert jobs with different statuses
        sample_job_data['status'] = 'active'
        sample_job_data_2['status'] = 'closed'
        
        insert_job(sample_job_data)
        insert_job(sample_job_data_2)
        
        # Filter by status
        active_jobs = list_jobs(status='active')
        closed_jobs = list_jobs(status='closed')
        
        assert len(active_jobs) == 1
        assert len(closed_jobs) == 1
        assert active_jobs[0]['status'] == 'active'
        assert closed_jobs[0]['status'] == 'closed'
    
    def test_list_jobs_by_min_score(self, sample_job_data, sample_job_data_2):
        """Test listing jobs filtered by minimum score."""
        # Insert jobs and set scores
        job_id_1 = insert_job(sample_job_data)
        job_id_2 = insert_job(sample_job_data_2)
        
        # Update scores
        update_job_score(job_id_1, 85, ['Strong Python match'])
        update_job_score(job_id_2, 65, ['Basic React match'])
        
        # Filter by minimum score
        high_score_jobs = list_jobs(min_score=80)
        low_score_jobs = list_jobs(min_score=60)
        
        assert len(high_score_jobs) == 1
        assert len(low_score_jobs) == 2
        assert high_score_jobs[0]['score'] == 85
    
    def test_get_job_not_found(self):
        """Test getting non-existent job."""
        fake_id = uuid4()
        job = get_job(fake_id)
        assert job is None
    
    def test_get_unscored_jobs(self, sample_job_data, sample_job_data_2):
        """Test getting jobs that need scoring."""
        # Insert jobs
        job_id_1 = insert_job(sample_job_data)
        job_id_2 = insert_job(sample_job_data_2)
        
        # Initially both should be unscored
        unscored = get_unscored_jobs()
        assert len(unscored) == 2
        
        # Score one job
        update_job_score(job_id_1, 85, ['Good match'])
        
        # Now only one should be unscored
        unscored = get_unscored_jobs()
        assert len(unscored) == 1
        assert unscored[0]['id'] == job_id_2
    
    def test_update_job_score(self, sample_job_data):
        """Test updating job score and match reasons."""
        # Insert job
        job_id = insert_job(sample_job_data)
        
        # Update score
        match_reasons = ['Strong Python experience', 'React proficiency']
        update_job_score(job_id, 87, match_reasons)
        
        # Verify update
        job = get_job(job_id)
        assert job['score'] == 87
        # Note: Now stored as CSV string in match_reasons
        assert job['match_reasons'] == ', '.join(match_reasons)


class TestApplicationDAO:
    """Test application-related DAO operations."""
    
    def test_create_application_success(self, sample_job_data):
        """Test successful application creation."""
        # Insert job first
        job_id = insert_job(sample_job_data)
        
        # Create application
        app_id = create_application(
            job_id=job_id,
            resume_path='artifacts/resume.docx',
            portal='email',
            cover_letter_path='artifacts/cover.txt',
            custom_message='Looking forward to hearing from you'
        )
        
        assert isinstance(app_id, int)
        
        # Verify application in database
        application = get_application_by_job(job_id)
        assert application is not None
        assert application['job_id'] == job_id
        assert application['portal'] == 'email'
        assert application['resume_path'] == 'artifacts/resume.docx'
        assert application['status'] == 'prepared'
    
    def test_create_application_duplicate_error(self, sample_job_data):
        """Test creating duplicate application raises error."""
        # Insert job
        job_id = insert_job(sample_job_data)
        
        # Create first application
        create_application(job_id, 'resume.docx', 'email')
        
        # Try to create duplicate - should raise error
        with pytest.raises(ApplicationDAOError, match="Application already exists"):
            create_application(job_id, 'resume2.docx', 'web_form')
    
    def test_create_application_job_not_found(self):
        """Test creating application for non-existent job."""
        fake_job_id = 99999  # Non-existent integer ID
        
        with pytest.raises(ApplicationDAOError, match="Job not found"):
            create_application(fake_job_id, 'resume.docx', 'email')
    
    def test_mark_applied_success(self, sample_job_data):
        """Test marking application as applied."""
        # Setup
        job_id = insert_job(sample_job_data)
        app_id = create_application(job_id, 'resume.docx', 'email')
        
        # Mark as applied
        mark_applied(job_id, confirmation_number='CONF123')
        
        # Verify status update
        application = get_application_by_job(job_id)
        assert application['status'] == 'submitted'
        assert application['tracking_url'] == 'CONF123'
        assert application['submitted_at'] is not None
    
    def test_get_application_by_job_not_found(self, sample_job_data):
        """Test getting application for job without application."""
        job_id = insert_job(sample_job_data)
        
        application = get_application_by_job(job_id)
        assert application is None


class TestContactDAO:
    """Test contact-related DAO operations."""
    
    def test_get_contacts_by_company(self):
        """Test getting contacts by company name."""
        # Insert test contacts
        with get_connection() as conn:
            # Insert contacts for same company
            exec_query(conn, """
                INSERT INTO contacts (contact_id, name, role, company, email, linkedin_url)
                VALUES 
                    (1, 'John Doe', 'recruiter', 'TechCorp Inc', 'john@techcorp.com', 'linkedin.com/in/johndoe'),
                    (2, 'Jane Smith', 'hiring_manager', 'TechCorp Inc', 'jane@techcorp.com', 'linkedin.com/in/janesmith'),
                    (3, 'Bob Wilson', 'engineer', 'OtherCorp', 'bob@othercorp.com', NULL)
            """)
            conn.commit()
        
        # Get contacts for TechCorp
        contacts = get_contacts_by_company('TechCorp Inc')
        
        assert len(contacts) == 2
        contact_names = [c['name'] for c in contacts]
        assert 'John Doe' in contact_names
        assert 'Jane Smith' in contact_names
        
        # Get contacts for non-existent company
        no_contacts = get_contacts_by_company('NonExistent Corp')
        assert len(no_contacts) == 0


class TestDAOErrorHandling:
    """Test DAO error handling and edge cases."""
    
    def test_insert_job_invalid_data(self):
        """Test inserting job with missing required fields."""
        invalid_data = {'title': 'Test Job'}  # Missing required fields
        
        # Should handle gracefully (depending on implementation)
        with pytest.raises(Exception):  # Could be various database errors
            insert_job(invalid_data)
    
    def test_database_connection_handling(self, sample_job_data):
        """Test DAO functions handle database connections properly."""
        # This test ensures connections are properly managed
        # Insert multiple jobs to test connection reuse
        job_ids = []
        for i in range(5):
            data = sample_job_data.copy()
            data['url'] = f"https://example.com/job-{i}"
            data['title'] = f"Job {i}"
            job_ids.append(insert_job(data))
        
        # All should be inserted successfully
        assert len(job_ids) == 5
        
        # All should be retrievable
        for job_id in job_ids:
            job = get_job(job_id)
            assert job is not None
    
    def test_transaction_rollback(self, sample_job_data):
        """Test that failed operations don't leave partial data."""
        # Insert valid job
        job_id = insert_job(sample_job_data)
        
        # Try to create application with invalid data
        try:
            # This should fail but shouldn't leave partial data
            with get_connection() as conn:
                exec_query(conn, """
                    INSERT INTO applications (job_id, status, application_method, resume_version)
                    VALUES (:job_id, :status, :method, :resume)
                """, {
                    'job_id': str(job_id),
                    'status': 'pending',
                    'method': 'email',
                    'resume': None  # This might cause an issue
                })
                
                # Force an error
                exec_query(conn, "INSERT INTO nonexistent_table VALUES (1)")
                conn.commit()
        except Exception:
            pass  # Expected to fail
        
        # Verify job still exists but no partial application data
        job = get_job(job_id)
        assert job is not None
        
        application = get_application_by_job(job_id)
        # Should be None if transaction was properly rolled back
        assert application is None
