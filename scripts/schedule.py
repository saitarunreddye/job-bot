#!/usr/bin/env python3
"""
Job Bot Automated Pipeline Scheduler.
Orchestrates the complete job application workflow: ingest → score → tailor → apply → email.
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, UTC
from pathlib import Path
from typing import List, Dict, Any, Optional
from uuid import UUID

# Add the project root to the path so we can import our modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from apps.worker.queue import enqueue_job, get_queue_info
from apps.worker.worker import ingest, score_all, tailor_one, apply_one, send_email_for
from db.db import get_connection, exec_query_fetchall, exec_query_fetchone
from config.settings import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('schedule.log')
    ]
)
logger = logging.getLogger(__name__)


class SchedulerError(Exception):
    """Base exception for scheduler operations."""
    pass


class JobBotScheduler:
    """Orchestrates the automated job application pipeline."""
    
    def __init__(
        self, 
        min_score: int = 70,
        max_jobs_per_run: int = 10,
        email_contacts_only: bool = True,
        dry_run: bool = False
    ):
        """
        Initialize the scheduler.
        
        Args:
            min_score: Minimum job score to process (default: 70)
            max_jobs_per_run: Maximum jobs to process per run (default: 10)
            email_contacts_only: Only send emails if contacts exist (default: True)
            dry_run: Log actions without executing them (default: False)
        """
        self.min_score = min_score
        self.max_jobs_per_run = max_jobs_per_run
        self.email_contacts_only = email_contacts_only
        self.dry_run = dry_run
        
        logger.info(f"JobBotScheduler initialized: min_score={min_score}, max_jobs={max_jobs_per_run}, dry_run={dry_run}")
    
    def run_pipeline(
        self, 
        sources: Optional[List[str]] = None,
        max_ingest_jobs: int = 50
    ) -> Dict[str, Any]:
        """
        Run the complete job application pipeline.
        
        Args:
            sources: List of job sources to ingest (default: all enabled sources)
            max_ingest_jobs: Maximum jobs to ingest (default: 50)
            
        Returns:
            Dict with pipeline execution results
        """
        logger.info("=" * 60)
        logger.info("Starting Job Bot Automated Pipeline")
        logger.info("=" * 60)
        
        start_time = time.time()
        results = {
            'started_at': datetime.now(UTC).isoformat() + 'Z',
            'steps': {},
            'jobs_processed': [],
            'errors': [],
            'summary': {}
        }
        
        try:
            # Step 1: Job Ingestion
            logger.info("Step 1: Job Ingestion")
            ingest_result = self._run_ingestion(sources or ["all"], max_ingest_jobs)
            results['steps']['ingest'] = ingest_result
            
            # Step 2: Job Scoring
            logger.info("Step 2: Job Scoring")
            scoring_result = self._run_scoring()
            results['steps']['score'] = scoring_result
            
            # Step 3: Get Top Jobs
            logger.info(f"Step 3: Finding top jobs (score >= {self.min_score})")
            top_jobs = self._get_top_jobs()
            results['steps']['top_jobs'] = {
                'count': len(top_jobs),
                'jobs': [{'id': str(job['id']), 'score': job['score'], 'company': job['company'], 'title': job['title']} for job in top_jobs]
            }
            
            if not top_jobs:
                logger.warning(f"No jobs found with score >= {self.min_score}")
                results['summary'] = {
                    'total_processed': 0,
                    'applications_submitted': 0,
                    'emails_sent': 0,
                    'status': 'completed_no_jobs'
                }
                return results
            
            # Step 4: Process Top Jobs
            logger.info(f"Step 4: Processing {len(top_jobs)} top jobs")
            processing_results = self._process_top_jobs(top_jobs)
            results['steps']['processing'] = processing_results
            results['jobs_processed'] = processing_results['jobs']
            
            # Generate summary
            summary = self._generate_summary(results)
            results['summary'] = summary
            
            duration = time.time() - start_time
            logger.info(f"Pipeline completed in {duration:.2f}s")
            logger.info(f"Summary: {summary}")
            
            return results
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            results['errors'].append(f"Pipeline failure: {e}")
            results['summary'] = {
                'status': 'failed',
                'error': str(e)
            }
            raise SchedulerError(f"Pipeline execution failed: {e}")
    
    def _run_ingestion(self, sources: List[str], max_jobs: int) -> Dict[str, Any]:
        """Run job ingestion step."""
        logger.info(f"Ingesting jobs from sources: {sources}")
        
        if self.dry_run:
            logger.info(f"DRY RUN: Would ingest {max_jobs} jobs from {sources}")
            return {
                'status': 'dry_run',
                'sources': sources,
                'max_jobs': max_jobs
            }
        
        try:
            total_ingested = 0
            source_results = {}
            
            for source in sources:
                logger.info(f"Ingesting from source: {source}")
                
                # Enqueue ingestion job
                job = enqueue_job(
                    ingest,
                    source=source,
                    max_jobs=max_jobs // len(sources) if len(sources) > 1 else max_jobs,
                    job_timeout=1800,  # 30 minutes
                    description=f"Scheduled ingestion from {source}"
                )
                
                # Wait for job completion (with timeout)
                result = self._wait_for_job(job.id, timeout=1800)
                
                if result['status'] == 'finished':
                    jobs_count = result.get('return_value', 0)
                    total_ingested += jobs_count
                    source_results[source] = jobs_count
                    logger.info(f"Ingested {jobs_count} jobs from {source}")
                else:
                    logger.error(f"Ingestion failed for {source}: {result.get('error', 'Unknown error')}")
                    source_results[source] = 0
            
            return {
                'status': 'completed',
                'total_ingested': total_ingested,
                'source_results': source_results
            }
            
        except Exception as e:
            logger.error(f"Ingestion step failed: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _run_scoring(self) -> Dict[str, Any]:
        """Run job scoring step."""
        logger.info("Scoring all unscored jobs")
        
        if self.dry_run:
            logger.info("DRY RUN: Would score all unscored jobs")
            return {'status': 'dry_run'}
        
        try:
            # Enqueue scoring job
            job = enqueue_job(
                score_all,
                job_timeout=3600,  # 1 hour
                description="Scheduled job scoring"
            )
            
            # Wait for job completion
            result = self._wait_for_job(job.id, timeout=3600)
            
            if result['status'] == 'finished':
                logger.info("Job scoring completed successfully")
                return {
                    'status': 'completed',
                    'job_id': job.id
                }
            else:
                logger.error(f"Job scoring failed: {result.get('error', 'Unknown error')}")
                return {
                    'status': 'failed',
                    'error': result.get('error', 'Unknown error')
                }
            
        except Exception as e:
            logger.error(f"Scoring step failed: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _get_top_jobs(self) -> List[Dict[str, Any]]:
        """Get top-scoring jobs that haven't been processed yet."""
        try:
            with get_connection() as conn:
                jobs = exec_query_fetchall(
                    conn,
                    """
                    SELECT j.id, j.title, j.company, j.url, j.score, j.source, j.status
                    FROM jobs j
                    LEFT JOIN applications a ON j.id = a.job_id
                    WHERE j.score >= :min_score 
                      AND j.status = 'active'
                      AND a.id IS NULL  -- No application exists yet
                    ORDER BY j.score DESC, j.created_at DESC
                    LIMIT :max_jobs
                    """,
                    min_score=self.min_score,
                    max_jobs=self.max_jobs_per_run
                )
            
            return [dict(job) for job in jobs]
            
        except Exception as e:
            logger.error(f"Failed to get top jobs: {e}")
            return []
    
    def _process_top_jobs(self, jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process each top job through the pipeline."""
        processing_results = {
            'jobs': [],
            'successful_applications': 0,
            'failed_applications': 0,
            'emails_sent': 0,
            'emails_failed': 0
        }
        
        for i, job in enumerate(jobs, 1):
            job_id = UUID(str(job['id']))
            logger.info(f"Processing job {i}/{len(jobs)}: {job['company']} - {job['title']} (Score: {job['score']})")
            
            job_result = {
                'job_id': str(job_id),
                'company': job['company'],
                'title': job['title'],
                'score': job['score'],
                'source': job.get('source'),
                'steps': {}
            }
            
            try:
                # Step A: Tailor application
                tailor_result = self._run_tailoring(job_id, job)
                job_result['steps']['tailor'] = tailor_result
                
                if tailor_result['status'] != 'completed':
                    logger.warning(f"Skipping application for {job_id} due to tailoring failure")
                    processing_results['jobs'].append(job_result)
                    continue
                
                # Step B: Submit application
                apply_result = self._run_application(job_id, job)
                job_result['steps']['apply'] = apply_result
                
                if apply_result['status'] == 'completed':
                    processing_results['successful_applications'] += 1
                    
                    # Step C: Send email if contacts exist
                    email_result = self._run_email_outreach(job_id, job)
                    job_result['steps']['email'] = email_result
                    
                    if email_result['status'] == 'completed':
                        processing_results['emails_sent'] += 1
                    elif email_result['status'] == 'failed':
                        processing_results['emails_failed'] += 1
                        
                else:
                    processing_results['failed_applications'] += 1
                
            except Exception as e:
                logger.error(f"Error processing job {job_id}: {e}")
                job_result['error'] = str(e)
                processing_results['failed_applications'] += 1
            
            processing_results['jobs'].append(job_result)
            
            # Small delay between jobs to avoid overwhelming the system
            time.sleep(2)
        
        return processing_results
    
    def _run_tailoring(self, job_id: UUID, job: Dict[str, Any]) -> Dict[str, Any]:
        """Run application tailoring for a job."""
        logger.info(f"Tailoring application for {job_id}")
        
        if self.dry_run:
            logger.info(f"DRY RUN: Would tailor application for {job_id}")
            return {'status': 'dry_run'}
        
        try:
            # Enqueue tailoring job
            tailor_job = enqueue_job(
                tailor_one,
                job_id=job_id,
                job_timeout=300,  # 5 minutes
                description=f"Scheduled tailoring for {job['company']} - {job['title']}"
            )
            
            # Wait for completion
            result = self._wait_for_job(tailor_job.id, timeout=300)
            
            if result['status'] == 'finished':
                logger.info(f"Tailoring completed for {job_id}")
                return {
                    'status': 'completed',
                    'job_id': tailor_job.id
                }
            else:
                logger.error(f"Tailoring failed for {job_id}: {result.get('error', 'Unknown error')}")
                return {
                    'status': 'failed',
                    'error': result.get('error', 'Unknown error')
                }
            
        except Exception as e:
            logger.error(f"Tailoring step failed for {job_id}: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _run_application(self, job_id: UUID, job: Dict[str, Any]) -> Dict[str, Any]:
        """Run job application submission."""
        logger.info(f"Submitting application for {job_id}")
        
        if self.dry_run:
            logger.info(f"DRY RUN: Would submit application for {job_id}")
            return {'status': 'dry_run'}
        
        try:
            # Determine application method based on source
            method = "web_form" if job.get('source', '').lower() == 'greenhouse' else "email"
            
            # Enqueue application job
            apply_job = enqueue_job(
                apply_one,
                job_id=job_id,
                method=method,
                job_timeout=600,  # 10 minutes (allows time for browser automation)
                description=f"Scheduled application for {job['company']} - {job['title']}"
            )
            
            # Wait for completion
            result = self._wait_for_job(apply_job.id, timeout=600)
            
            if result['status'] == 'finished':
                logger.info(f"Application submitted for {job_id}")
                return {
                    'status': 'completed',
                    'method': method,
                    'job_id': apply_job.id
                }
            else:
                logger.error(f"Application failed for {job_id}: {result.get('error', 'Unknown error')}")
                return {
                    'status': 'failed',
                    'method': method,
                    'error': result.get('error', 'Unknown error')
                }
            
        except Exception as e:
            logger.error(f"Application step failed for {job_id}: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _run_email_outreach(self, job_id: UUID, job: Dict[str, Any]) -> Dict[str, Any]:
        """Run email outreach if contacts exist."""
        logger.info(f"Checking email outreach for {job_id}")
        
        if self.dry_run:
            logger.info(f"DRY RUN: Would check email outreach for {job_id}")
            return {'status': 'dry_run'}
        
        try:
            # Check if contacts exist for this company
            contacts = self._find_company_contacts(job['company'])
            
            if not contacts:
                logger.info(f"No contacts found for {job['company']}, skipping email outreach")
                return {
                    'status': 'skipped',
                    'reason': 'no_contacts_found'
                }
            
            if self.email_contacts_only and not contacts:
                logger.info(f"Email contacts only mode - no contacts for {job['company']}")
                return {
                    'status': 'skipped',
                    'reason': 'email_contacts_only_no_contacts'
                }
            
            # Use the first contact with an email
            target_contact = None
            for contact in contacts:
                if contact.get('email'):
                    target_contact = contact
                    break
            
            if not target_contact:
                logger.info(f"No email addresses found for {job['company']} contacts")
                return {
                    'status': 'skipped',
                    'reason': 'no_email_addresses'
                }
            
            # Enqueue email job
            email_job = enqueue_job(
                send_email_for,
                job_id=job_id,
                to_email=target_contact['email'],
                job_timeout=300,  # 5 minutes
                description=f"Scheduled email for {job['company']} - {job['title']}"
            )
            
            # Wait for completion
            result = self._wait_for_job(email_job.id, timeout=300)
            
            if result['status'] == 'finished':
                logger.info(f"Email sent for {job_id} to {target_contact['email']}")
                return {
                    'status': 'completed',
                    'contact_email': target_contact['email'],
                    'contact_name': f"{target_contact.get('first_name', '')} {target_contact.get('last_name', '')}".strip(),
                    'job_id': email_job.id
                }
            else:
                logger.error(f"Email failed for {job_id}: {result.get('error', 'Unknown error')}")
                return {
                    'status': 'failed',
                    'error': result.get('error', 'Unknown error')
                }
            
        except Exception as e:
            logger.error(f"Email outreach step failed for {job_id}: {e}")
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _find_company_contacts(self, company: str) -> List[Dict[str, Any]]:
        """Find contacts for a specific company."""
        try:
            with get_connection() as conn:
                contacts = exec_query_fetchall(
                    conn,
                    """
                    SELECT id, first_name, last_name, email, contact_type
                    FROM contacts 
                    WHERE LOWER(company) = LOWER(:company)
                      AND email IS NOT NULL
                    ORDER BY 
                        CASE contact_type 
                            WHEN 'recruiter' THEN 1
                            WHEN 'hiring_manager' THEN 2  
                            WHEN 'employee' THEN 3
                            ELSE 4
                        END,
                        relationship_strength DESC NULLS LAST
                    LIMIT 5
                    """,
                    company=company
                )
            
            return [dict(contact) for contact in contacts]
            
        except Exception as e:
            logger.error(f"Failed to find contacts for {company}: {e}")
            return []
    
    def _wait_for_job(self, job_id: str, timeout: int = 300) -> Dict[str, Any]:
        """Wait for a queued job to complete."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                # Check job status using RQ
                from rq import Queue
                import redis
                
                redis_conn = redis.from_url(settings.redis_url)
                queue = Queue(connection=redis_conn)
                
                job = queue.fetch_job(job_id)
                if not job:
                    return {'status': 'not_found'}
                
                if job.is_finished:
                    return {
                        'status': 'finished',
                        'return_value': job.return_value
                    }
                elif job.is_failed:
                    return {
                        'status': 'failed',
                        'error': str(job.exc_info) if job.exc_info else 'Job failed'
                    }
                
                # Job is still running, wait a bit
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error checking job status: {e}")
                time.sleep(10)
        
        return {'status': 'timeout'}
    
    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate execution summary."""
        processing = results.get('steps', {}).get('processing', {})
        
        return {
            'status': 'completed',
            'total_jobs_processed': len(processing.get('jobs', [])),
            'successful_applications': processing.get('successful_applications', 0),
            'failed_applications': processing.get('failed_applications', 0),
            'emails_sent': processing.get('emails_sent', 0),
            'emails_failed': processing.get('emails_failed', 0),
            'execution_time': results.get('started_at'),
            'min_score_threshold': self.min_score
        }


def main():
    """Main entry point for the scheduler."""
    parser = argparse.ArgumentParser(description="Job Bot Automated Pipeline Scheduler")
    
    parser.add_argument(
        '--min-score', 
        type=int, 
        default=70,
        help='Minimum job score to process (default: 70)'
    )
    parser.add_argument(
        '--max-jobs', 
        type=int, 
        default=10,
        help='Maximum jobs to process per run (default: 10)'
    )
    parser.add_argument(
        '--max-ingest', 
        type=int, 
        default=50,
        help='Maximum jobs to ingest (default: 50)'
    )
    parser.add_argument(
        '--sources', 
        nargs='+', 
        default=['all'],
        help='Job sources to ingest (default: all)'
    )
    parser.add_argument(
        '--no-email-contacts-only', 
        action='store_true',
        help='Send emails even if no contacts exist'
    )
    parser.add_argument(
        '--dry-run', 
        action='store_true',
        help='Log actions without executing them'
    )
    parser.add_argument(
        '--verbose', 
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        # Initialize scheduler
        scheduler = JobBotScheduler(
            min_score=args.min_score,
            max_jobs_per_run=args.max_jobs,
            email_contacts_only=not args.no_email_contacts_only,
            dry_run=args.dry_run
        )
        
        # Run pipeline
        results = scheduler.run_pipeline(
            sources=args.sources,
            max_ingest_jobs=args.max_ingest
        )
        
        # Print final summary
        print("\n" + "=" * 60)
        print("PIPELINE EXECUTION SUMMARY")
        print("=" * 60)
        summary = results.get('summary', {})
        print(f"Status: {summary.get('status', 'unknown')}")
        print(f"Jobs Processed: {summary.get('total_jobs_processed', 0)}")
        print(f"Applications Submitted: {summary.get('successful_applications', 0)}")
        print(f"Application Failures: {summary.get('failed_applications', 0)}")
        print(f"Emails Sent: {summary.get('emails_sent', 0)}")
        print(f"Email Failures: {summary.get('emails_failed', 0)}")
        print(f"Score Threshold: >= {summary.get('min_score_threshold', args.min_score)}")
        
        if args.dry_run:
            print("\n⚠️  DRY RUN MODE - No actual actions were performed")
        
        return 0
        
    except Exception as e:
        logger.error(f"Scheduler execution failed: {e}")
        print(f"\n❌ Pipeline failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
