"""
API routes for Job Bot application.
Contains all v1 API endpoints for job processing pipeline.
"""

import logging
from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Query
from pydantic import BaseModel, Field

from apps.worker.queue import enqueue_job, get_queue_info
from apps.worker.worker import ingest, score_all, tailor_one, apply_one, send_email_for, process_followups
from apps.worker.dao import list_jobs, get_job
from db.db import get_connection, exec_query_fetchone, exec_query_scalar


def safe_format_datetime(dt_value) -> Optional[str]:
    """
    Safely format datetime values to ISO format string.
    
    Args:
        dt_value: Datetime value (could be datetime object, string, or None)
        
    Returns:
        Optional[str]: Formatted datetime string or None
    """
    if dt_value is None:
        return None
    
    if isinstance(dt_value, str):
        return dt_value
    
    if hasattr(dt_value, 'isoformat'):
        return dt_value.isoformat() + 'Z'
    
    return str(dt_value)

logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(tags=["Job Bot API v1"])


# Pydantic models for request/response schemas
class IngestRequest(BaseModel):
    """Request schema for job ingestion."""
    source: str = Field(..., description="Job source (linkedin, indeed, company_site, etc.)")
    url: Optional[str] = Field(None, description="Specific URL to scrape")
    search_terms: Optional[List[str]] = Field(None, description="Search terms for job discovery")
    location: Optional[str] = Field(None, description="Job location filter")
    max_jobs: int = Field(default=50, ge=1, le=1000, description="Maximum jobs to ingest")


class IngestResponse(BaseModel):
    """Response schema for job ingestion."""
    task_id: str = Field(..., description="Background task ID")
    message: str = Field(..., description="Status message")
    estimated_completion: str = Field(..., description="Estimated completion time")


class ScoreRequest(BaseModel):
    """Request schema for job scoring."""
    job_ids: Optional[List[UUID]] = Field(None, description="Specific job IDs to score (if empty, scores all unscored jobs)")
    rescore: bool = Field(default=False, description="Force re-scoring of already scored jobs")
    min_score_threshold: int = Field(default=60, ge=0, le=100, description="Minimum score threshold")


class ScoreResponse(BaseModel):
    """Response schema for job scoring."""
    task_id: str = Field(..., description="Background task ID")
    jobs_queued: int = Field(..., description="Number of jobs queued for scoring")
    message: str = Field(..., description="Status message")


class TailorResponse(BaseModel):
    """Response schema for resume/cover letter tailoring."""
    task_id: str = Field(..., description="Background task ID")
    job_id: UUID = Field(..., description="Job ID being tailored for")
    artifacts: Dict[str, str] = Field(..., description="Generated artifact file paths")
    message: str = Field(..., description="Status message")


class ApplyRequest(BaseModel):
    """Request schema for job application."""
    method: str = Field(..., description="Application method (auto, email, manual)")
    resume_version: Optional[str] = Field(None, description="Specific resume version to use")
    cover_letter_version: Optional[str] = Field(None, description="Specific cover letter version to use")
    custom_message: Optional[str] = Field(None, description="Custom application message")


class ApplyResponse(BaseModel):
    """Response schema for job application."""
    task_id: str = Field(..., description="Background task ID")
    job_id: UUID = Field(..., description="Job ID being applied to")
    application_method: str = Field(..., description="Application method used")
    message: str = Field(..., description="Status message")


class OutreachEmailRequest(BaseModel):
    """Request schema for outreach email."""
    job_id: UUID = Field(..., description="Related job ID")
    to: str = Field(..., description="Recipient email address")
    subject: Optional[str] = Field(None, description="Email subject (optional, will be generated if not provided)")
    template: Optional[str] = Field(None, description="Email template to use")
    personalization: Optional[Dict[str, str]] = Field(None, description="Personalization variables")
    send_immediately: bool = Field(default=False, description="Send immediately or queue for later")


class OutreachEmailResponse(BaseModel):
    """Response schema for outreach email."""
    task_id: str = Field(..., description="Background task ID")
    job_id: UUID = Field(..., description="Related job ID")
    to: str = Field(..., description="Recipient email address")
    scheduled_time: Optional[str] = Field(None, description="Scheduled send time")
    message: str = Field(..., description="Status message")


class JobResponse(BaseModel):
    """Response schema for individual job."""
    id: str = Field(..., description="Job ID")
    title: str = Field(..., description="Job title")
    company: str = Field(..., description="Company name")
    url: str = Field(..., description="Job posting URL")
    location: Optional[str] = Field(None, description="Job location")
    job_type: Optional[str] = Field(None, description="Job type (full-time, part-time, etc.)")
    experience_level: Optional[str] = Field(None, description="Experience level required")
    salary_min: Optional[int] = Field(None, description="Minimum salary")
    salary_max: Optional[int] = Field(None, description="Maximum salary")
    currency: Optional[str] = Field(None, description="Salary currency")
    description: Optional[str] = Field(None, description="Job description")
    requirements: Optional[str] = Field(None, description="Job requirements")
    benefits: Optional[str] = Field(None, description="Job benefits")
    remote_allowed: Optional[bool] = Field(None, description="Remote work allowed")
    date_posted: Optional[str] = Field(None, description="Date posted")
    application_deadline: Optional[str] = Field(None, description="Application deadline")
    status: str = Field(..., description="Job status")
    source: Optional[str] = Field(None, description="Job source")
    score: Optional[int] = Field(None, description="Compatibility score (0-100)")
    match_reasons: Optional[List[str]] = Field(None, description="Matching reasons")
    # Visa and location fields
    visa_friendly: Optional[bool] = Field(None, description="Offers visa sponsorship")
    visa_keywords: Optional[List[str]] = Field(None, description="Detected visa keywords")
    country: Optional[str] = Field(None, description="Country code (US, CA, etc.)")
    state_province: Optional[str] = Field(None, description="State or province")
    city: Optional[str] = Field(None, description="City")
    is_remote: Optional[bool] = Field(None, description="Is remote position")
    remote_type: Optional[str] = Field(None, description="Remote type (full, hybrid, occasional)")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Update timestamp")
    scraped_at: Optional[str] = Field(None, description="Scraping timestamp")


class JobsListResponse(BaseModel):
    """Response schema for jobs list."""
    jobs: List[JobResponse] = Field(..., description="List of jobs")
    total_count: int = Field(..., description="Total jobs matching filters")
    page: int = Field(..., description="Current page")
    page_size: int = Field(..., description="Page size")
    has_next: bool = Field(..., description="Has next page")


class FollowupProcessResponse(BaseModel):
    """Response schema for follow-up processing."""
    task_id: str = Field(..., description="Background task ID")
    message: str = Field(..., description="Status message")
    stats: Optional[Dict[str, int]] = Field(None, description="Processing statistics")


class StatsResponse(BaseModel):
    """Response schema for application statistics."""
    total_jobs: int = Field(..., description="Total jobs ingested")
    scored_jobs: int = Field(..., description="Number of scored jobs")
    high_score_jobs: int = Field(..., description="Jobs with score >= 80")
    applications_submitted: int = Field(..., description="Total applications submitted")
    applications_pending: int = Field(..., description="Pending applications")
    applications_responded: int = Field(..., description="Applications with responses")
    outreach_sent: int = Field(..., description="Outreach messages sent")
    contacts_added: int = Field(..., description="Total contacts in database")
    last_activity: Optional[str] = Field(None, description="Last activity timestamp")
    # Enhanced stats with visa and location breakdowns
    visa_friendly_jobs: Optional[int] = Field(None, description="Jobs offering visa sponsorship")
    us_jobs: Optional[int] = Field(None, description="Jobs in the United States")
    remote_jobs: Optional[int] = Field(None, description="Remote jobs available")


# API Endpoints

@router.get("/jobs", response_model=JobsListResponse)
async def get_jobs(
    status: Optional[str] = Query(None, description="Job status filter (active, closed, expired)"),
    min_score: Optional[int] = Query(None, ge=0, le=100, description="Minimum compatibility score (0-100)"),
    visa_friendly: Optional[bool] = Query(None, description="Filter for visa sponsorship jobs"),
    country: Optional[str] = Query(None, description="Country filter (ISO code: US, CA, GB, etc.)"),
    state_province: Optional[str] = Query(None, description="State or province filter"),
    city: Optional[str] = Query(None, description="City filter"),
    is_remote: Optional[bool] = Query(None, description="Filter for remote jobs"),
    remote_type: Optional[str] = Query(None, description="Remote type filter (full, hybrid, occasional)"),
    company: Optional[str] = Query(None, description="Company name filter"),
    title: Optional[str] = Query(None, description="Job title search (partial match)"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    page_size: int = Query(20, ge=1, le=100, description="Number of jobs per page")
) -> JobsListResponse:
    """
    Get jobs with advanced filtering by visa, location, and other criteria.
    
    Provides comprehensive job search with filters for:
    - Visa sponsorship (H-1B, OPT, CPT, etc.)
    - Location (country, state, city, remote options)  
    - Job attributes (status, score, company, title)
    - Pagination support
    
    Args:
        Various query parameters for filtering and pagination
        
    Returns:
        JobsListResponse: Paginated list of jobs matching filters
        
    Example URLs:
        - GET /v1/jobs?visa_friendly=true&country=US&is_remote=true
        - GET /v1/jobs?min_score=80&state_province=CA&page=2
        - GET /v1/jobs?remote_type=full&company=Google
    """
    logger.info(f"Jobs requested: visa_friendly={visa_friendly}, country={country}, remote={is_remote}")
    
    try:
        # Calculate offset for pagination
        offset = (page - 1) * page_size
        
        # Get jobs with filters
        jobs_data = list_jobs(
            status=status,
            min_score=min_score,
            visa_friendly=visa_friendly,
            country=country,
            state_province=state_province,
            is_remote=is_remote,
            remote_type=remote_type,
            limit=page_size + 1,  # Get one extra to check if there's a next page
            offset=offset
        )
        
        # Check if there's a next page
        has_next = len(jobs_data) > page_size
        if has_next:
            jobs_data = jobs_data[:-1]  # Remove the extra job
        
        # Apply additional text-based filters
        if company:
            jobs_data = [job for job in jobs_data if company.lower() in (job.get('company') or '').lower()]
        
        if title:
            jobs_data = [job for job in jobs_data if title.lower() in (job.get('title') or '').lower()]
        
        # Get total count for this filter combination (approximate)
        total_count = len(jobs_data) + (page - 1) * page_size
        if has_next:
            total_count += 1  # Rough estimate
        
        # Convert to response format
        job_responses = []
        for job in jobs_data:
            # Parse visa_keywords from JSON if needed
            visa_keywords = job.get('visa_keywords')
            if isinstance(visa_keywords, str):
                try:
                    import json
                    visa_keywords = json.loads(visa_keywords) if visa_keywords else []
                except:
                    visa_keywords = []
            
            # Parse match_reasons from JSON if needed
            match_reasons = job.get('match_reasons')
            if isinstance(match_reasons, str):
                try:
                    import json
                    match_reasons = json.loads(match_reasons) if match_reasons else []
                except:
                    match_reasons = []
            
            job_response = JobResponse(
                id=str(job['id']),
                title=job['title'],
                company=job['company'],
                url=job['url'],
                location=job.get('location'),
                job_type=job.get('job_type'),
                experience_level=job.get('experience_level'),
                salary_min=job.get('salary_min'),
                salary_max=job.get('salary_max'),
                currency=job.get('currency'),
                description=job.get('description'),
                requirements=job.get('requirements'),
                benefits=job.get('benefits'),
                remote_allowed=job.get('remote_allowed'),
                date_posted=safe_format_datetime(job.get('date_posted')),
                application_deadline=safe_format_datetime(job.get('application_deadline')),
                status=job['status'],
                source=job.get('source'),
                score=job.get('score'),
                match_reasons=match_reasons,
                visa_friendly=job.get('visa_friendly'),
                visa_keywords=visa_keywords,
                country=job.get('country'),
                state_province=job.get('state_province'),
                city=job.get('city'),
                is_remote=job.get('is_remote'),
                remote_type=job.get('remote_type'),
                created_at=safe_format_datetime(job.get('created_at')),
                updated_at=safe_format_datetime(job.get('updated_at')),
                scraped_at=safe_format_datetime(job.get('scraped_at'))
            )
            job_responses.append(job_response)
        
        logger.debug(f"Retrieved {len(job_responses)} jobs for page {page}")
        
        return JobsListResponse(
            jobs=job_responses,
            total_count=total_count,
            page=page,
            page_size=page_size,
            has_next=has_next
        )
        
    except Exception as e:
        logger.error(f"Failed to retrieve jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve jobs: {str(e)}")


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job_by_id(job_id: UUID) -> JobResponse:
    """
    Get a specific job by ID with all details including visa and location information.
    
    Args:
        job_id: UUID of the job to retrieve
        
    Returns:
        JobResponse: Complete job details
        
    Raises:
        HTTPException: If job is not found
    """
    logger.info(f"Job details requested: {job_id}")
    
    try:
        job = get_job(job_id)
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        
        # Parse JSON fields
        visa_keywords = job.get('visa_keywords')
        if isinstance(visa_keywords, str):
            try:
                import json
                visa_keywords = json.loads(visa_keywords) if visa_keywords else []
            except:
                visa_keywords = []
        
        match_reasons = job.get('match_reasons')
        if isinstance(match_reasons, str):
            try:
                import json
                match_reasons = json.loads(match_reasons) if match_reasons else []
            except:
                match_reasons = []
        
        return JobResponse(
            id=str(job['id']),
            title=job['title'],
            company=job['company'],
            url=job['url'],
            location=job.get('location'),
            job_type=job.get('job_type'),
            experience_level=job.get('experience_level'),
            salary_min=job.get('salary_min'),
            salary_max=job.get('salary_max'),
            currency=job.get('currency'),
            description=job.get('description'),
            requirements=job.get('requirements'),
            benefits=job.get('benefits'),
            remote_allowed=job.get('remote_allowed'),
            date_posted=safe_format_datetime(job.get('date_posted')),
            application_deadline=safe_format_datetime(job.get('application_deadline')),
            status=job['status'],
            source=job.get('source'),
            score=job.get('score'),
            match_reasons=match_reasons,
            visa_friendly=job.get('visa_friendly'),
            visa_keywords=visa_keywords,
            country=job.get('country'),
            state_province=job.get('state_province'),
            city=job.get('city'),
            is_remote=job.get('is_remote'),
            remote_type=job.get('remote_type'),
            created_at=safe_format_datetime(job.get('created_at')),
            updated_at=safe_format_datetime(job.get('updated_at')),
            scraped_at=safe_format_datetime(job.get('scraped_at'))
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve job: {str(e)}")


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_jobs(request: IngestRequest) -> IngestResponse:
    """
    Ingest jobs from various sources.
    
    Initiates background job scraping from specified sources like LinkedIn, Indeed,
    or company websites. Returns immediately with a task ID for tracking progress.
    
    Args:
        request: Ingestion parameters including source, search terms, and filters
        
    Returns:
        IngestResponse with task ID and status information
        
    Raises:
        HTTPException: If request validation fails or source is unsupported
    """
    logger.info(f"Job ingestion requested: source={request.source}, max_jobs={request.max_jobs}")
    
    try:
        # Validate source
        valid_sources = ["linkedin", "indeed", "company_site", "glassdoor", "ziprecruiter"]
        if request.source not in valid_sources:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid source: {request.source}. Valid sources: {valid_sources}"
            )
        
        # Enqueue background job for ingestion
        job = enqueue_job(
            ingest,
            source=request.source,
            search_terms=request.search_terms,
            location=request.location,
            max_jobs=request.max_jobs,
            job_timeout=3600,  # 1 hour timeout
            description=f"Ingest jobs from {request.source}"
        )
        
        # Calculate estimated completion time (rough estimate based on max_jobs)
        estimated_minutes = max(5, request.max_jobs // 10)  # ~10 jobs per minute
        estimated_completion = safe_format_datetime(datetime.now() + timedelta(minutes=estimated_minutes))
        
        logger.info(f"Job ingestion queued: task_id={job.id}")
        
        return IngestResponse(
            task_id=job.id,
            message=f"Job ingestion queued for source: {request.source}",
            estimated_completion=estimated_completion
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to queue job ingestion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to queue job ingestion: {str(e)}")


@router.post("/score", response_model=ScoreResponse, status_code=status.HTTP_202_ACCEPTED)
async def score_jobs(request: ScoreRequest) -> ScoreResponse:
    """
    Score jobs based on candidate profile match.
    
    Analyzes job requirements against candidate skills and experience to generate
    compatibility scores. Processes jobs in background and updates database.
    
    Args:
        request: Scoring parameters including job filters and thresholds
        
    Returns:
        ScoreResponse with task ID and queue information
    """
    logger.info(f"Job scoring requested: job_ids={request.job_ids}, rescore={request.rescore}")
    
    try:
        # Count jobs to be scored
        if request.job_ids:
            # Validate that all job IDs exist
            jobs_queued = 0
            with get_connection() as conn:
                for job_id in request.job_ids:
                    exists = exec_query_scalar(
                        conn,
                        "SELECT COUNT(*) FROM jobs WHERE id = :job_id",
                        job_id=job_id
                    )
                    if exists:
                        jobs_queued += 1
                    else:
                        logger.warning(f"Job ID not found: {job_id}")
        else:
            # Count unscored jobs
            with get_connection() as conn:
                condition = "score IS NULL" if not request.rescore else "1=1"
                jobs_queued = exec_query_scalar(
                    conn,
                    f"SELECT COUNT(*) FROM jobs WHERE {condition} AND status = 'active'"
                )
        
        if jobs_queued == 0:
            return ScoreResponse(
                task_id="",
                jobs_queued=0,
                message="No jobs found to score"
            )
        
        # Enqueue background job for scoring
        job = enqueue_job(
            score_all,
            job_timeout=1800,  # 30 minutes timeout
            description=f"Score {jobs_queued} jobs"
        )
        
        logger.info(f"Job scoring queued: task_id={job.id}, jobs_count={jobs_queued}")
        
        return ScoreResponse(
            task_id=job.id,
            jobs_queued=jobs_queued,
            message=f"Scoring queued for {jobs_queued} jobs"
        )
        
    except Exception as e:
        logger.error(f"Failed to queue job scoring: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to queue job scoring: {str(e)}")


@router.post("/tailor/{job_id}", response_model=TailorResponse, status_code=status.HTTP_202_ACCEPTED)
async def tailor_application(job_id: UUID) -> TailorResponse:
    """
    Generate tailored resume and cover letter for specific job.
    
    Creates customized application materials optimized for the job requirements
    and ATS compatibility. Generated files are stored in artifacts directory.
    
    Args:
        job_id: UUID of the job to tailor application for
        
    Returns:
        TailorResponse with task ID and artifact information
        
    Raises:
        HTTPException: If job_id is not found or job is not scoreable
    """
    logger.info(f"Application tailoring requested for job: {job_id}")
    
    try:
        # Validate job exists and get details
        with get_connection() as conn:
            job = exec_query_fetchone(
                conn,
                """
                SELECT id, title, company, score, status
                FROM jobs 
                WHERE id = :job_id
                """,
                job_id=job_id
            )
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        
        if job['status'] != 'active':
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot tailor for inactive job: {job_id}"
            )
        
        # Check if job has a score (recommended but not required)
        if job['score'] is None:
            logger.warning(f"Tailoring job {job_id} without score")
        
        # Enqueue background job for tailoring
        job_task = enqueue_job(
            tailor_one,
            job_id=str(job_id),
            job_timeout=900,  # 15 minutes timeout
            description=f"Tailor application for {job['company']} - {job['title']}"
        )
        
        logger.info(f"Application tailoring queued: task_id={job_task.id}")
        
        return TailorResponse(
            task_id=job_task.id,
            job_id=job_id,
            artifacts={
                "resume": f"artifacts/resume_{job_id}.docx",
                "cover_letter": f"artifacts/cover_letter_{job_id}.docx"
            },
            message=f"Tailoring queued for {job['company']} - {job['title']}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to queue application tailoring: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to queue tailoring: {str(e)}")


@router.post("/apply/{job_id}", response_model=ApplyResponse, status_code=status.HTTP_202_ACCEPTED)
async def apply_to_job(job_id: UUID, request: ApplyRequest) -> ApplyResponse:
    """
    Submit application for specific job.
    
    Applies to the job using specified method (automated form submission,
    email application, or manual preparation). Tracks application status.
    
    Args:
        job_id: UUID of the job to apply to
        request: Application parameters including method and materials
        
    Returns:
        ApplyResponse with task ID and application details
        
    Raises:
        HTTPException: If job_id is not found or application materials missing
    """
    logger.info(f"Job application requested: job_id={job_id}, method={request.method}")
    
    try:
        # Validate job exists and get details
        with get_connection() as conn:
            job = exec_query_fetchone(
                conn,
                """
                SELECT id, title, company, status, url
                FROM jobs 
                WHERE id = :job_id
                """,
                job_id=job_id
            )
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        
        if job['status'] != 'active':
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot apply to inactive job: {job_id}"
            )
        
        # Check if already applied
        with get_connection() as conn:
            existing_application = exec_query_fetchone(
                conn,
                "SELECT id, status FROM applications WHERE job_id = :job_id",
                job_id=job_id
            )
        
        if existing_application:
            raise HTTPException(
                status_code=400,
                detail=f"Application already exists with status: {existing_application['status']}"
            )
        
        # Validate application method
        valid_methods = ["email", "web_form", "recruiter", "manual"]
        if request.method not in valid_methods:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid method: {request.method}. Valid methods: {valid_methods}"
            )
        
        # Enqueue background job for application
        job_task = enqueue_job(
            apply_one,
            job_id=str(job_id),
            method=request.method,
            job_timeout=1200,  # 20 minutes timeout
            description=f"Apply to {job['company']} - {job['title']} via {request.method}"
        )
        
        logger.info(f"Job application queued: task_id={job_task.id}")
        
        return ApplyResponse(
            task_id=job_task.id,
            job_id=job_id,
            application_method=request.method,
            message=f"Application queued for {job['company']} via {request.method}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to queue job application: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to queue application: {str(e)}")


@router.post("/outreach/email", response_model=OutreachEmailResponse, status_code=status.HTTP_202_ACCEPTED)
async def send_outreach_email(request: OutreachEmailRequest) -> OutreachEmailResponse:
    """
    Send outreach email for job application.
    
    Sends application email to specified recipient for a job.
    Expects JSON with job_id and to email address.
    
    Args:
        request: Outreach parameters with job_id and recipient email
        
    Returns:
        OutreachEmailResponse with task ID and email details
        
    Raises:
        HTTPException: If job_id is not found or email is invalid
    """
    logger.info(f"Outreach email requested: job_id={request.job_id}, to={request.to}")
    
    try:
        # Validate job exists and get details
        with get_connection() as conn:
            job = exec_query_fetchone(
                conn,
                """
                SELECT id, title, company, status, url
                FROM jobs 
                WHERE id = :job_id
                """,
                job_id=request.job_id
            )
        
        if not job:
            raise HTTPException(status_code=404, detail=f"Job not found: {request.job_id}")
        
        # Basic email validation
        if not request.to or "@" not in request.to:
            raise HTTPException(status_code=400, detail="Invalid email address")
        
        # Determine if immediate or scheduled
        scheduled_time = None
        if not request.send_immediately:
            # Schedule for later (e.g., next business day at 9 AM)
            scheduled_time = safe_format_datetime((datetime.now() + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            ))
        
        # Enqueue background job for email sending
        job_task = enqueue_job(
            send_email_for,
            job_id=request.job_id,
            to=request.to,
            subject=request.subject,
            job_timeout=300,  # 5 minutes timeout
            description=f"Send email for {job['company']} - {job['title']} to {request.to}"
        )
        
        logger.info(f"Outreach email queued: task_id={job_task.id}")
        
        return OutreachEmailResponse(
            task_id=job_task.id,
            job_id=request.job_id,
            to=request.to,
            scheduled_time=scheduled_time,
            message=f"Email queued for {job['company']} - {job['title']}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to queue outreach email: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to queue email: {str(e)}")


@router.post("/followups/process", response_model=FollowupProcessResponse, status_code=status.HTTP_202_ACCEPTED)
async def process_due_followups() -> FollowupProcessResponse:
    """
    Process all due follow-up emails.
    
    Checks for follow-ups scheduled to be sent and processes them:
    - Verifies recipients haven't responded or unsubscribed
    - Sends value-add follow-up emails with proper threading
    - Respects do-not-contact list and rate limits
    - Updates follow-up schedules and tracking
    
    This endpoint is typically called by a scheduled job or cron task.
    
    Returns:
        FollowupProcessResponse with task ID and processing statistics
    """
    logger.info("Follow-up processing requested via API")
    
    try:
        # Enqueue background job for follow-up processing
        job = enqueue_job(
            process_followups,
            job_timeout=1800,  # 30 minutes timeout
            description="Process due follow-up emails"
        )
        
        logger.info(f"Follow-up processing queued: task_id={job.id}")
        
        return FollowupProcessResponse(
            task_id=job.id,
            message="Follow-up processing queued successfully",
            stats=None  # Will be available after processing completes
        )
        
    except Exception as e:
        logger.error(f"Failed to queue follow-up processing: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to queue follow-up processing: {str(e)}")


@router.get("/stats", response_model=StatsResponse)
async def get_application_stats() -> StatsResponse:
    """
    Get application pipeline statistics and metrics.
    
    Provides overview of job ingestion, scoring, applications, and outreach
    activities. Useful for monitoring progress and system health.
    
    Returns:
        StatsResponse with comprehensive application metrics
    """
    logger.info("Application statistics requested")
    
    try:
        with get_connection() as conn:
            # Get job statistics
            total_jobs = exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM jobs"
            ) or 0
            
            scored_jobs = exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM jobs WHERE score IS NOT NULL"
            ) or 0
            
            high_score_jobs = exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM jobs WHERE score >= 80"
            ) or 0
            
            # Get application statistics
            applications_submitted = exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM applications WHERE status = 'applied'"
            ) or 0
            
            applications_pending = exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM applications WHERE status IN ('pending', 'submitted')"
            ) or 0
            
            applications_responded = exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM applications WHERE status IN ('interviewed', 'offered', 'rejected')"
            ) or 0
            
            # Get outreach statistics
            outreach_sent = exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM outreach WHERE sent_at IS NOT NULL"
            ) or 0
            
            contacts_added = exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM contacts"
            ) or 0
            
            # Get last activity timestamp
            last_activity_result = exec_query_scalar(
                conn,
                """
                SELECT MAX(activity_time) FROM (
                    SELECT MAX(updated_at) as activity_time FROM jobs
                    UNION ALL
                    SELECT MAX(updated_at) as activity_time FROM applications
                    UNION ALL
                    SELECT MAX(sent_at) as activity_time FROM outreach
                ) activities
                """
            )
            
            last_activity = safe_format_datetime(last_activity_result)
        
        logger.debug("Application statistics retrieved successfully")
        
        return StatsResponse(
            total_jobs=total_jobs,
            scored_jobs=scored_jobs,
            high_score_jobs=high_score_jobs,
            applications_submitted=applications_submitted,
            applications_pending=applications_pending,
            applications_responded=applications_responded,
            outreach_sent=outreach_sent,
            contacts_added=contacts_added,
            last_activity=last_activity
        )
        
    except Exception as e:
        logger.error(f"Failed to retrieve application statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve statistics: {str(e)}")
