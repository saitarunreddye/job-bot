"""
Data Access Object (DAO) for Job Bot database operations.
Provides helper functions using SQLAlchemy Core with bind parameters.
"""

import json
import logging
from typing import Dict, List, Optional, Any
from uuid import UUID

from sqlalchemy import text
from db.db import get_connection, exec_query, exec_query_fetchall, exec_query_fetchone, transaction

logger = logging.getLogger(__name__)


class JobDAOError(Exception):
    """Exception raised for job DAO operations."""
    pass


class ApplicationDAOError(Exception):
    """Exception raised for application DAO operations."""
    pass


def insert_job(job_data: Dict[str, Any]) -> int:
    """
    Insert or update a job record, upsert by URL.
    
    Args:
        job_data: Dictionary containing job information
        
    Returns:
        int: Job ID of the inserted/updated job
        
    Raises:
        JobDAOError: If job insertion fails
        
    Example:
        job_data = {
            'title': 'Software Engineer',
            'company': 'TechCorp',
            'url': 'https://example.com/job/123',
            'location': 'Remote',
            'description': 'Great opportunity...',
            'requirements': 'Python, FastAPI',
            'source': 'linkedin'
        }
        job_id = insert_job(job_data)
    """
    logger.debug(f"Inserting job: {job_data.get('title')} at {job_data.get('company')}")
    
    try:
        # Validate required fields
        required_fields = ['title', 'company', 'url']
        for field in required_fields:
            if field not in job_data or not job_data[field]:
                raise JobDAOError(f"Missing required field: {field}")
        
        with transaction() as conn:
            # Check if job already exists by URL
            existing_job = exec_query_fetchone(
                conn,
                "SELECT job_id FROM jobs WHERE url = :url",
                url=job_data.get('url')
            )
            
            if existing_job:
                # Update existing job
                job_id = existing_job['job_id']
                exec_query(
                    conn,
                    """
                        UPDATE jobs SET
                            title = :title,
                            company = :company,
                            location = :location,
                            source = :source,
                            jd_text = :jd_text,
                            skills = :skills,
                            status = COALESCE(:status, status)
                        WHERE url = :url
                    """,
                    title=job_data.get('title'),
                    company=job_data.get('company'),
                    location=job_data.get('location'),
                    source=job_data.get('source'),
                    jd_text=job_data.get('description'),
                    skills=job_data.get('requirements'),
                    status=job_data.get('status', 'new'),
                    url=job_data.get('url')
                )
            else:
                # Insert new job
                exec_query(
                    conn,
                    """
                        INSERT INTO jobs (
                            title, company, url, location, source, jd_text, skills, status, created_at
                        )
                        VALUES (
                            :title, :company, :url, :location, :source, :jd_text, :skills, :status, datetime('now')
                        )
                    """,
                    title=job_data.get('title'),
                    company=job_data.get('company'),
                    url=job_data.get('url'),
                    location=job_data.get('location'),
                    source=job_data.get('source'),
                    jd_text=job_data.get('description'),
                    skills=job_data.get('requirements'),
                    status=job_data.get('status', 'new')
                )
                
                # Get the inserted job_id
                result = exec_query_fetchone(
                    conn,
                    "SELECT job_id FROM jobs WHERE url = :url",
                    url=job_data.get('url')
                )
                
                job_id = result['job_id']
            
            logger.info(f"Job upserted successfully: {job_id}")
            return job_id
            
    except Exception as e:
        logger.error(f"Failed to insert job: {e}")
        raise JobDAOError(f"Job insertion failed: {e}")


def list_jobs(
    status: Optional[str] = None, 
    min_score: Optional[int] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    List jobs with optional filtering by status, score, visa, and location.
    
    Args:
        status: Optional job status filter ('active', 'closed', 'expired')
        min_score: Optional minimum score filter (0-100)
        visa_friendly: Optional visa sponsorship filter
        country: Optional country filter (ISO code like 'US', 'CA')
        state_province: Optional state/province filter
        is_remote: Optional remote work filter
        remote_type: Optional remote type filter ('full', 'hybrid', 'occasional')
        limit: Optional limit for results
        offset: Optional offset for pagination
        
    Returns:
        List[Dict]: List of job dictionaries
        
    Example:
        # Get visa-friendly remote jobs in the US
        jobs = list_jobs(visa_friendly=True, country='US', is_remote=True)
        
        # Get all active jobs with score >= 70 in California
        jobs = list_jobs(status='active', min_score=70, state_province='CA')
    """
    logger.debug(f"Listing jobs: status={status}, min_score={min_score}")
    
    try:
        # Build dynamic WHERE clause
        where_conditions = []
        params = {}
        
        if status:
            where_conditions.append("status = :status")
            params['status'] = status
            
        if min_score is not None:
            where_conditions.append("score >= :min_score")
            params['min_score'] = min_score
            

        
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        query = f"""
            SELECT 
                id, title, company, url, location, source, 
                description, match_reasons, score, status, created_at
            FROM jobs_view 
            {where_clause}
            ORDER BY 
                CASE WHEN score IS NOT NULL THEN score ELSE 0 END DESC,
                created_at DESC
        """
        
        # Add LIMIT and OFFSET
        if limit:
            query += f" LIMIT {limit}"
        if offset:
            query += f" OFFSET {offset}"
        
        with get_connection() as conn:
            jobs = exec_query_fetchall(conn, query, **params)
        
        logger.debug(f"Retrieved {len(jobs)} jobs")
        return jobs
        
    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise JobDAOError(f"Job listing failed: {e}")


def get_job(job_id: int | str) -> Optional[Dict[str, Any]]:
    """
    Get a single job by ID.
    
    Args:
        job_id: Integer or string ID of the job to retrieve
        
    Returns:
        Optional[Dict]: Job dictionary if found, None otherwise
        
    Example:
        job = get_job(123)
        if job:
            print(f"Found: {job['title']} at {job['company']}")
    """
    logger.debug(f"Getting job: {job_id}")
    
    try:
        with get_connection() as conn:
            job = exec_query_fetchone(
                conn,
                """
                    SELECT 
                        id, title, company, url, location, source, 
                        description, match_reasons, score, status, created_at
                    FROM jobs_view 
                    WHERE id = :job_id
                """,
                job_id=job_id
            )
        
        if job:
            logger.debug(f"Job found: {job['title']} at {job['company']}")
        else:
            logger.debug(f"Job not found: {job_id}")
            
        return job
        
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}")
        raise JobDAOError(f"Job retrieval failed: {e}")


def create_application(
    job_id: int, 
    resume_path: str, 
    portal: str,
    cover_letter_path: Optional[str] = None,
    custom_message: Optional[str] = None
) -> int:
    """
    Create a new application record for a job.
    
    Args:
        job_id: Integer ID of the job being applied to
        resume_path: Path to the resume file used
        portal: Application method/portal (email, web_form, recruiter, etc.)
        cover_letter_path: Optional path to cover letter file
        custom_message: Optional custom application message
        
    Returns:
        int: Application ID of the created application
        
    Raises:
        ApplicationDAOError: If application creation fails
        
    Example:
        app_id = create_application(
            job_id=UUID('123e4567-e89b-12d3-a456-426614174000'),
            resume_path='artifacts/resume_tailored.docx',
            portal='email',
            cover_letter_path='artifacts/cover_letter.docx'
        )
    """
    logger.debug(f"Creating application for job {job_id} via {portal}")
    
    try:
        # Validate job exists
        job = get_job(job_id)
        if not job:
            raise ApplicationDAOError(f"Job not found: {job_id}")
        
        # Check for existing application
        with get_connection() as conn:
            existing = exec_query_fetchone(
                conn,
                "SELECT app_id, status FROM applications WHERE job_id = :job_id",
                job_id=job_id
            )
        
        if existing:
            raise ApplicationDAOError(
                f"Application already exists for job {job_id} with status: {existing['status']}"
            )
        
        with transaction() as conn:
            exec_query(
                conn,
                """
                    INSERT INTO applications (
                        job_id, status, portal, resume_path
                    )
                    VALUES (
                        :job_id, :status, :portal, :resume_path
                    )
                """,
                job_id=job_id,
                status='prepared',
                portal=portal,
                resume_path=resume_path
            )
            
            # Get the inserted app_id
            result = exec_query_fetchone(
                conn,
                "SELECT app_id FROM applications WHERE job_id = :job_id",
                job_id=job_id
            )
            
            application_id = result['app_id']
            logger.info(f"Application created: {application_id} for job {job_id}")
            return application_id
            
    except ApplicationDAOError:
        raise
    except Exception as e:
        logger.error(f"Failed to create application for job {job_id}: {e}")
        raise ApplicationDAOError(f"Application creation failed: {e}")


def mark_applied(job_id: int, confirmation_number: Optional[str] = None, notes: Optional[str] = None) -> bool:
    """
    Mark a job application as applied/submitted.
    
    Args:
        job_id: Integer ID of the job that was applied to
        confirmation_number: Optional confirmation number from application
        notes: Optional notes about the application
        
    Returns:
        bool: True if application was successfully marked as applied
        
    Raises:
        ApplicationDAOError: If marking application fails
        
    Example:
        success = mark_applied(
            job_id=UUID('123e4567-e89b-12d3-a456-426614174000'),
            confirmation_number='APP-2025-001234'
        )
    """
    logger.debug(f"Marking job {job_id} as applied")
    
    try:
        with transaction() as conn:
            # Check if application exists
            existing = exec_query_fetchone(
                conn,
                "SELECT app_id, status FROM applications WHERE job_id = :job_id",
                job_id=job_id
            )
            
            if not existing:
                raise ApplicationDAOError(f"No application found for job {job_id}")
            
            if existing['status'] == 'applied':
                logger.warning(f"Application for job {job_id} already marked as applied")
                return True
            
            # Update application status
            exec_query(
                conn,
                """
                    UPDATE applications 
                    SET status = :status,
                        submitted_at = datetime('now'),
                        tracking_url = :confirmation_number
                    WHERE job_id = :job_id
                """,
                status='submitted',
                confirmation_number=confirmation_number,
                job_id=job_id
            )
            
            logger.info(f"Application marked as submitted for job {job_id}")
            return True
            
    except ApplicationDAOError:
        raise
    except Exception as e:
        logger.error(f"Failed to mark job {job_id} as applied: {e}")
        raise ApplicationDAOError(f"Failed to mark application as applied: {e}")


# Additional helper functions for common queries

def get_unscored_jobs(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get jobs that haven't been scored yet.
    
    Args:
        limit: Optional limit on number of jobs to return
        
    Returns:
        List[Dict]: List of unscored job dictionaries
    """
    logger.debug(f"Getting unscored jobs (limit: {limit})")
    
    try:
        limit_clause = ""
        params = {}
        
        if limit:
            limit_clause = "LIMIT :limit"
            params['limit'] = limit
        
        query = f"""
            SELECT 
                id, title, company, url, description, match_reasons,
                source, created_at
            FROM jobs_view 
            WHERE score = 0
            ORDER BY created_at DESC
            {limit_clause}
        """
        
        with get_connection() as conn:
            jobs = exec_query_fetchall(conn, query, **params)
        
        logger.debug(f"Retrieved {len(jobs)} unscored jobs")
        return jobs
        
    except Exception as e:
        logger.error(f"Failed to get unscored jobs: {e}")
        raise JobDAOError(f"Failed to get unscored jobs: {e}")


def update_job_score(job_id: int, score: int, match_reasons: Optional[List[str]] = None) -> bool:
    """
    Update a job's score and match reasons.
    
    Args:
        job_id: UUID of the job to update
        score: Compatibility score (0-100)
        match_reasons: Optional list of match reasoning
        
    Returns:
        bool: True if update was successful
    """
    logger.debug(f"Updating job score: {job_id} -> {score}")
    
    try:
        if not (0 <= score <= 100):
            raise JobDAOError(f"Invalid score: {score}. Must be between 0 and 100")
        
        with transaction() as conn:
            # First check if job exists
            existing_job = exec_query_fetchone(
                conn,
                "SELECT job_id FROM jobs WHERE job_id = :job_id",
                job_id=job_id
            )
            
            if not existing_job:
                raise JobDAOError(f"Job not found: {job_id}")
            
            exec_query(
                conn,
                """
                    UPDATE jobs 
                    SET score = :score,
                        skills = :match_reasons
                    WHERE job_id = :job_id
                """,
                score=score,
                match_reasons=', '.join(match_reasons) if match_reasons else None,
                job_id=job_id
            )
            
            logger.info(f"Job score updated: {job_id} -> {score}")
            return True
            
    except JobDAOError:
        raise
    except Exception as e:
        logger.error(f"Failed to update job score for {job_id}: {e}")
        raise JobDAOError(f"Failed to update job score: {e}")


def get_contacts_by_company(company: str) -> List[Dict[str, Any]]:
    """
    Get contacts for a specific company.
    
    Args:
        company: Company name to search for
        
    Returns:
        List[Dict]: List of contact dictionaries
    """
    logger.debug(f"Getting contacts for company: {company}")
    
    try:
        with get_connection() as conn:
            contacts = exec_query_fetchall(
                conn,
                """
                    SELECT 
                        id, name, email, linkedin_url,
                        company, role, verified, last_seen
                    FROM contacts_view 
                    WHERE company = :company
                    ORDER BY last_seen DESC
                """,
                company=company
            )
        
        # Add full_name field for convenience (use name field)
        for contact in contacts:
            contact['full_name'] = contact.get('name', '')
        
        logger.debug(f"Retrieved {len(contacts)} contacts for {company}")
        return contacts
        
    except Exception as e:
        logger.error(f"Failed to get contacts for company {company}: {e}")
        raise JobDAOError(f"Failed to get contacts: {e}")


def get_application_by_job(job_id: int) -> Optional[Dict[str, Any]]:
    """
    Get application record for a specific job.
    
    Args:
        job_id: UUID of the job
        
    Returns:
        Optional[Dict]: Application dictionary if found, None otherwise
    """
    logger.debug(f"Getting application for job: {job_id}")
    
    try:
        with get_connection() as conn:
            application = exec_query_fetchone(
                conn,
                """
                    SELECT 
                        app_id, job_id, status, portal,
                        resume_path, tracking_url, submitted_at,
                        cover_letter_version, notes
                    FROM applications_view 
                    WHERE job_id = :job_id
                """,
                job_id=job_id
            )
        
        return application
        
    except Exception as e:
        logger.error(f"Failed to get application for job {job_id}: {e}")
        raise ApplicationDAOError(f"Failed to get application: {e}")
