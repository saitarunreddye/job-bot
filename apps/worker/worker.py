"""
Background worker functions for Job Bot processing pipeline.
Implements the core job processing workflow with retry logic and error handling.
"""

import logging
import random
import time
from typing import List, Dict, Any, Optional
from uuid import UUID
from pathlib import Path

from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    retry_if_exception_type,
    before_sleep_log
)

from config.settings import settings
from db.db import get_connection, exec_query, exec_query_fetchall, exec_query_fetchone, transaction
from apps.worker.dao import insert_job
from apps.worker.sources import job_source_registry, scrape_all_sources, scrape_source
from apps.worker.location_parser import process_job_location_data
from apps.worker.followup_scheduler import process_due_followups

logger = logging.getLogger(__name__)


class WorkerError(Exception):
    """Base exception for worker errors."""
    pass


class JobProcessingError(WorkerError):
    """Exception raised during job processing."""
    pass


class ApplicationError(WorkerError):
    """Exception raised during application processing."""
    pass


class EmailError(WorkerError):
    """Exception raised during email operations."""
    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    retry=retry_if_exception_type((JobProcessingError, ConnectionError))
)
def ingest_jobs(
    source: str = "all",
    search_terms: Optional[List[str]] = None,
    location: Optional[str] = None,
    max_jobs: int = 50
) -> int:
    """
    Ingest jobs from external sources using the source registry.
    
    Scrapes job listings from various sources and stores them in the database.
    Implements deduplication and data validation.
    
    Args:
        source: Job source platform ("all", "greenhouse", "lever", "ashby", etc.)
        search_terms: Search keywords for job discovery (used for fallback sources)
        location: Geographic location filter (used for fallback sources)
        max_jobs: Maximum number of jobs to ingest
        
    Returns:
        int: Number of jobs successfully ingested
        
    Raises:
        JobProcessingError: If job ingestion fails
    """
    logger.info(f"Starting job ingestion: source={source}, max_jobs={max_jobs}")
    
    try:
        start_time = time.time()
        jobs_ingested = 0
        
        # Get available sources
        available_sources = job_source_registry.get_enabled_source_names()
        logger.info(f"Available sources: {available_sources}")
        
        if source.lower() == "all":
            # Scrape from all enabled sources
            logger.info("Scraping from all enabled sources")
            
            if not available_sources:
                logger.warning("No sources are enabled in the registry")
                return 0
            
            # Calculate max jobs per source
            max_jobs_per_source = max_jobs // len(available_sources) if available_sources else max_jobs
            
            all_scraped_jobs, jobs_per_source = scrape_all_sources(max_jobs_per_source)
            
            logger.info(f"Scraped jobs by source: {jobs_per_source}")
            
            # Limit total jobs if specified
            if max_jobs and len(all_scraped_jobs) > max_jobs:
                all_scraped_jobs = all_scraped_jobs[:max_jobs]
                logger.info(f"Limited to {max_jobs} jobs as requested")
            
            # Insert jobs using DAO
            for job_data in all_scraped_jobs:
                try:
                    # Map scraped data to our schema
                    job_record = {
                        'title': job_data.get('title'),
                        'company': job_data.get('company'),
                        'url': job_data.get('url'),
                        'location': job_data.get('location'),
                        'description': job_data.get('jd_text'),
                        'source': job_data.get('source'),
                        'job_type': 'full-time',  # Default assumption
                        'status': 'active',
                        'remote_allowed': 'remote' in job_data.get('location', '').lower()
                    }
                    
                    # Process location and visa information
                    job_record = process_job_location_data(job_record)
                    
                    # Insert job via DAO (handles upsert by URL)
                    job_id = insert_job(job_record)
                    jobs_ingested += 1
                    logger.debug(f"Job ingested via DAO: {job_id} - {job_record['title']}")
                    
                except Exception as e:
                    logger.error(f"Failed to insert job via DAO: {e}")
                    continue
        
        elif source.lower() in available_sources:
            # Scrape from specific source
            logger.info(f"Scraping from specific source: {source}")
            
            try:
                scraped_jobs = scrape_source(source.lower(), max_jobs)
                
                # Insert jobs using DAO
                for job_data in scraped_jobs:
                    try:
                        # Map scraped data to our schema
                        job_record = {
                            'title': job_data.get('title'),
                            'company': job_data.get('company'),
                            'url': job_data.get('url'),
                            'location': job_data.get('location'),
                            'description': job_data.get('jd_text'),
                            'source': job_data.get('source'),
                            'job_type': 'full-time',  # Default assumption
                            'status': 'active',
                            'remote_allowed': 'remote' in job_data.get('location', '').lower()
                        }
                        
                        # Process location and visa information
                        job_record = process_job_location_data(job_record)
                        
                        # Insert job via DAO (handles upsert by URL)
                        job_id = insert_job(job_record)
                        jobs_ingested += 1
                        logger.debug(f"Job ingested via DAO: {job_id} - {job_record['title']}")
                        
                    except Exception as e:
                        logger.error(f"Failed to insert job via DAO: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Failed to scrape from source {source}: {e}")
                raise JobProcessingError(f"Source scraping failed: {e}")
        
        else:
            # Fallback to stub implementation for unknown sources
            logger.info(f"Using stub implementation for unknown source: {source}")
            
            # Simulate job scraping with delays and processing
            search_keywords = search_terms or ["python", "software engineer"]
            logger.info(f"Searching for jobs with keywords: {search_keywords}")
            
            # Simulate scraping multiple job listings
            for i in range(min(max_jobs, 10)):  # Simulate up to 10 jobs for now
                try:
                    # Simulate processing time
                    time.sleep(0.5)
                    
                    # Simulate job data
                    job_data = {
                        "title": f"Software Engineer {i+1}",
                        "company": f"TechCorp {i+1}",
                        "url": f"https://{source}.com/jobs/{i+1}",
                        "location": location or "Remote",
                        "job_type": "full-time",
                        "experience_level": "mid",
                        "description": f"Job description for position {i+1}",
                        "requirements": "Python, FastAPI, PostgreSQL",
                        "source": source,
                        "status": "active"
                    }
                    
                    # Process location and visa information
                    job_data = process_job_location_data(job_data)
                    
                    # Insert job via DAO
                    job_id = insert_job(job_data)
                    jobs_ingested += 1
                    logger.debug(f"Stub job ingested: {job_id} - {job_data['title']}")
                    
                except Exception as e:
                    logger.error(f"Failed to ingest stub job {i+1}: {e}")
                    continue
        
        duration = time.time() - start_time
        logger.info(f"Job ingestion completed: {jobs_ingested} jobs in {duration:.2f}s")
        
        return jobs_ingested
        
    except Exception as e:
        logger.error(f"Job ingestion failed: {e}")
        raise JobProcessingError(f"Failed to ingest jobs from {source}: {e}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    retry=retry_if_exception_type((JobProcessingError, ConnectionError))
)
def score_all_jobs() -> None:
    """
    Score all unscored jobs based on candidate profile match.
    
    Analyzes job requirements against candidate skills and experience
    to generate compatibility scores (0-100).
    
    Raises:
        JobProcessingError: If scoring process fails
    """
    logger.info("Starting job scoring for all unscored jobs")
    
    try:
        start_time = time.time()
        
        # Get all unscored jobs
        with get_connection() as conn:
            unscored_jobs = exec_query_fetchall(
                conn,
                """
                SELECT id, title, company, description, requirements
                FROM jobs 
                WHERE score IS NULL AND status = 'active'
                ORDER BY date_posted DESC
                """
            )
        
        if not unscored_jobs:
            logger.info("No unscored jobs found")
            return
        
        logger.info(f"Found {len(unscored_jobs)} jobs to score")
        scored_count = 0
        
        for job in unscored_jobs:
            try:
                # TODO: Implement actual ML/AI scoring logic
                # This is a stub implementation
                
                # Simulate scoring algorithm
                score = _calculate_job_score(job)
                match_reasons = _generate_match_reasons(job, score)
                
                # Update job with score
                with transaction() as conn:
                    exec_query(
                        conn,
                        """
                        UPDATE jobs 
                        SET score = :score, 
                            match_reasons = :match_reasons,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :job_id
                        """,
                        score=score,
                        match_reasons=match_reasons,
                        job_id=job['id']
                    )
                
                scored_count += 1
                logger.debug(f"Job scored: {job['id']} - {score}/100")
                
                # Small delay to avoid overwhelming the system
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Failed to score job {job['id']}: {e}")
                continue
        
        duration = time.time() - start_time
        logger.info(f"Job scoring completed: {scored_count}/{len(unscored_jobs)} jobs in {duration:.2f}s")
        
    except Exception as e:
        logger.error(f"Job scoring failed: {e}")
        raise JobProcessingError(f"Failed to score jobs: {e}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    retry=retry_if_exception_type((JobProcessingError, ConnectionError))
)
def tailor_application_for_job(job_id: UUID) -> Dict[str, str]:
    """
    Generate tailored resume and cover letter for specific job.
    
    Creates customized application materials optimized for the job requirements
    and ATS compatibility.
    
    Args:
        job_id: UUID of the job to tailor application for
        
    Returns:
        Dict[str, str]: Dictionary with artifact file paths
        
    Raises:
        JobProcessingError: If tailoring fails
    """
    logger.info(f"Starting application tailoring for job: {job_id}")
    
    try:
        start_time = time.time()
        
        # Get job details
        with get_connection() as conn:
            job = exec_query_fetchone(
                conn,
                """
                SELECT job_id, title, company, jd_text, skills, score
                FROM jobs 
                WHERE job_id = :job_id
                """,
                job_id=job_id
            )
        
        if not job:
            raise JobProcessingError(f"Job not found: {job_id}")
        
        logger.info(f"Tailoring for: {job['company']} - {job['title']}")
        
        # Ensure artifacts directory exists
        artifacts_dir = Path(settings.artifact_dir)
        artifacts_dir.mkdir(exist_ok=True)
        
        # TODO: Implement actual resume/cover letter generation
        # This is a stub implementation
        
        # Generate tailored resume
        resume_path = artifacts_dir / f"resume_{job_id}.docx"
        _generate_tailored_resume(job, resume_path)
        
        # Generate tailored cover letter
        cover_letter_path = artifacts_dir / f"cover_letter_{job_id}.docx"
        _generate_tailored_cover_letter(job, cover_letter_path)
        
        artifacts = {
            "resume": str(resume_path),
            "cover_letter": str(cover_letter_path)
        }
        
        duration = time.time() - start_time
        logger.info(f"Application tailoring completed for {job_id} in {duration:.2f}s")
        
        return artifacts
        
    except Exception as e:
        logger.error(f"Application tailoring failed for {job_id}: {e}")
        raise JobProcessingError(f"Failed to tailor application for {job_id}: {e}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    retry=retry_if_exception_type((ApplicationError, ConnectionError))
)
def apply_to_job(job_id: UUID, method: str = "email") -> None:
    """
    Submit application for specific job and update status.
    
    Args:
        job_id: UUID of the job to apply to
        method: Application method (email, web_form, recruiter)
        
    Raises:
        ApplicationError: If application submission fails
    """
    logger.info(f"Starting job application: {job_id} via {method}")
    
    try:
        start_time = time.time()
        
        # Get job details
        with get_connection() as conn:
            job = exec_query_fetchone(
                conn,
                """
                SELECT job_id, title, company, url, score
                FROM jobs 
                WHERE job_id = :job_id
                """,
                job_id=job_id
            )
        
        if not job:
            raise ApplicationError(f"Job not found: {job_id}")
        
        # Check if already applied
        with get_connection() as conn:
            existing_application = exec_query_fetchone(
                conn,
                """
                SELECT app_id, status FROM applications 
                WHERE job_id = :job_id
                """,
                job_id=job_id
            )
        
        if existing_application:
            logger.warning(f"Application already exists for job {job_id}: {existing_application['status']}")
            return
        
        # TODO: Implement actual application submission logic
        # This is a stub implementation
        
        # Create application record
        with transaction() as conn:
            result = exec_query(
                conn,
                """
                INSERT INTO applications (
                    job_id, status, application_method, 
                    resume_version, cover_letter_version
                )
                VALUES (
                    :job_id, 'applied', :method,
                    :resume_version, :cover_letter_version
                )
                RETURNING id
                """,
                job_id=job_id,
                method=method,
                resume_version=f"resume_{job_id}.docx",
                cover_letter_version=f"cover_letter_{job_id}.docx"
            )
            
            application_id = result.scalar()
        
        duration = time.time() - start_time
        logger.info(f"Application submitted for {job_id} (ID: {application_id}) in {duration:.2f}s")
        
    except Exception as e:
        logger.error(f"Job application failed for {job_id}: {e}")
        raise ApplicationError(f"Failed to apply to job {job_id}: {e}")


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    retry=retry_if_exception_type((EmailError, ConnectionError))
)
def send_email_for_job(job_id: UUID, to_email: str, subject: Optional[str] = None) -> None:
    """
    Send application email via Gmail API.
    
    Args:
        job_id: UUID of the job being applied to
        to_email: Recipient email address
        subject: Email subject (optional, will be generated if not provided)
        
    Raises:
        EmailError: If email sending fails
    """
    logger.info(f"Sending application email for job {job_id} to {to_email}")
    
    try:
        start_time = time.time()
        
        # Get job details
        with get_connection() as conn:
            job = exec_query_fetchone(
                conn,
                """
                SELECT id, title, company, url
                FROM jobs 
                WHERE id = :job_id
                """,
                job_id=job_id
            )
        
        if not job:
            raise EmailError(f"Job not found: {job_id}")
        
        # Generate email subject if not provided
        if not subject:
            subject = f"Application for {job['title']} at {job['company']}"
        
        # TODO: Implement actual Gmail API integration
        # This is a stub implementation that prints instead of sending
        
        email_content = {
            "to": to_email,
            "subject": subject,
            "body": f"""
Dear Hiring Manager,

I am writing to express my interest in the {job['title']} position at {job['company']}.

Please find my resume and cover letter attached.

Best regards,
[Your Name]

Job URL: {job['url']}
            """.strip(),
            "attachments": [
                f"artifacts/resume_{job_id}.docx",
                f"artifacts/cover_letter_{job_id}.docx"
            ]
        }
        
        # Stub: Print email instead of sending
        print("=" * 60)
        print("EMAIL WOULD BE SENT:")
        print(f"To: {email_content['to']}")
        print(f"Subject: {email_content['subject']}")
        print(f"Body:\n{email_content['body']}")
        print(f"Attachments: {email_content['attachments']}")
        print("=" * 60)
        
        # Record email in outreach table (if we have contact info)
        # This would be implemented when we have actual contact management
        
        duration = time.time() - start_time
        logger.info(f"Email sent for job {job_id} in {duration:.2f}s")
        
    except Exception as e:
        logger.error(f"Email sending failed for job {job_id}: {e}")
        raise EmailError(f"Failed to send email for job {job_id}: {e}")


# Helper functions

def _calculate_job_score(job: Dict[str, Any]) -> int:
    """
    Calculate compatibility score for a job (stub implementation).
    
    Args:
        job: Job dictionary with details
        
    Returns:
        int: Score between 0-100
    """
    # TODO: Implement actual scoring algorithm based on:
    # - Skills match
    # - Experience level match
    # - Location preferences
    # - Company preferences
    # - Salary expectations
    
    # Stub scoring logic
    score = 75  # Base score
    
    # Adjust based on job characteristics
    if "python" in job.get("requirements", "").lower():
        score += 10
    if "remote" in job.get("location", "").lower():
        score += 5
    if "senior" in job.get("title", "").lower():
        score += 5
    
    return min(100, max(0, score))


def _generate_match_reasons(job: Dict[str, Any], score: int) -> List[str]:
    """
    Generate reasons for job match score (stub implementation).
    
    Args:
        job: Job dictionary with details
        score: Calculated score
        
    Returns:
        List[str]: List of match reasons
    """
    reasons = []
    
    if score >= 80:
        reasons.append("Strong technical skills match")
        reasons.append("Company culture alignment")
    elif score >= 60:
        reasons.append("Good skills overlap")
        reasons.append("Relevant experience")
    else:
        reasons.append("Partial skills match")
    
    return reasons


def _generate_tailored_resume(job: Dict[str, Any], output_path: Path) -> None:
    """
    Generate tailored resume for specific job (stub implementation).
    
    Args:
        job: Job dictionary with details
        output_path: Path to save the generated resume
    """
    # TODO: Implement actual resume generation using templates
    # This is a stub that creates a placeholder file
    
    with open(output_path, 'w') as f:
        f.write(f"TAILORED RESUME FOR: {job['company']} - {job['title']}\n")
        f.write("=" * 50 + "\n")
        f.write("This would be a properly formatted resume document.\n")
    
    logger.debug(f"Resume generated: {output_path}")


def _generate_tailored_cover_letter(job: Dict[str, Any], output_path: Path) -> None:
    """
    Generate tailored cover letter for specific job (stub implementation).
    
    Args:
        job: Job dictionary with details
        output_path: Path to save the generated cover letter
    """
    # TODO: Implement actual cover letter generation using templates
    # This is a stub that creates a placeholder file
    
    with open(output_path, 'w') as f:
        f.write(f"TAILORED COVER LETTER FOR: {job['company']} - {job['title']}\n")
        f.write("=" * 50 + "\n")
        f.write("This would be a properly formatted cover letter document.\n")
    
    logger.debug(f"Cover letter generated: {output_path}")


# Convenience functions for the worker API

def ingest(source: str = "linkedin", **kwargs) -> int:
    """Convenience wrapper for ingest_jobs."""
    return ingest_jobs(source=source, **kwargs)


def score_all() -> None:
    """Convenience wrapper for score_all_jobs."""
    return score_all_jobs()


def tailor_one(job_id: UUID) -> Dict[str, str]:
    """Convenience wrapper for tailor_application_for_job."""
    return tailor_application_for_job(job_id)


def apply_one(job_id: UUID, method: str = "email") -> None:
    """Convenience wrapper for apply_to_job."""
    return apply_to_job(job_id, method)


def send_email_for(job_id: UUID, to: str, subject: Optional[str] = None) -> None:
    """Convenience wrapper for send_email_for_job."""
    return send_email_for_job(job_id, to, subject)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    retry=retry_if_exception_type(WorkerError)
)
def process_followups() -> Dict[str, int]:
    """
    Process all due follow-up emails.
    
    This function should be called periodically (e.g., every hour) to:
    1. Check for follow-ups that are due to be sent
    2. Verify recipients haven't responded or unsubscribed  
    3. Send value-add follow-up emails with proper threading
    4. Respect do-not-contact list and rate limits
    
    Returns:
        Dict with processing statistics (sent, skipped, errors)
        
    Raises:
        WorkerError: If follow-up processing fails
    """
    logger.info("Starting follow-up processing...")
    
    try:
        # Process due follow-ups
        stats = process_due_followups()
        
        logger.info(f"Follow-up processing completed: {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"Follow-up processing failed: {e}")
        raise WorkerError(f"Follow-up processing error: {e}")
