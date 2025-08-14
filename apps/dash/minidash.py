"""
Mini Dashboard for Job Bot.
Provides a simple web interface for monitoring job application pipeline status.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional
from uuid import UUID

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from db.db import get_connection, exec_query_fetchall, exec_query_fetchone, exec_query_scalar

logger = logging.getLogger(__name__)

# Dashboard models
class JobSummary(BaseModel):
    """Summary information for a job."""
    id: str = Field(..., description="Job ID")
    title: str = Field(..., description="Job title")
    company: str = Field(..., description="Company name")
    score: Optional[int] = Field(None, description="Compatibility score")
    status: str = Field(..., description="Job status")
    source: Optional[str] = Field(None, description="Job source")
    created_at: str = Field(..., description="Creation timestamp")
    application_status: Optional[str] = Field(None, description="Application status")
    needs_action: bool = Field(False, description="Whether job needs action")


class DashboardStats(BaseModel):
    """Complete dashboard statistics."""
    # Job counts by status
    total_jobs: int = Field(..., description="Total jobs in system")
    active_jobs: int = Field(..., description="Active jobs")
    scored_jobs: int = Field(..., description="Jobs with scores")
    high_score_jobs: int = Field(..., description="Jobs with score >= 80")
    
    # Today's activity
    todays_new_jobs: int = Field(..., description="New jobs today")
    todays_applications: int = Field(..., description="Applications submitted today")
    todays_emails: int = Field(..., description="Emails sent today")
    
    # Application pipeline
    applications_submitted: int = Field(..., description="Total applications submitted")
    applications_pending: int = Field(..., description="Pending applications")
    applications_needs_manual: int = Field(..., description="Applications needing manual action")
    
    # LinkedIn drafts and outreach
    pending_linkedin_drafts: List[JobSummary] = Field(..., description="Jobs with pending LinkedIn drafts")
    pending_linkedin_count: int = Field(..., description="Count of pending LinkedIn drafts")
    
    # Top jobs needing action
    top_jobs_needing_action: List[JobSummary] = Field(..., description="Top jobs requiring action")
    
    # Email quota
    email_quota_used: int = Field(0, description="Email quota used today")
    email_quota_limit: int = Field(100, description="Daily email limit")
    email_quota_remaining: int = Field(100, description="Remaining email quota")
    
    # System health
    last_ingestion: Optional[str] = Field(None, description="Last job ingestion time")
    last_application: Optional[str] = Field(None, description="Last application submission")
    pipeline_health: str = Field("unknown", description="Overall pipeline health status")


class DashboardManager:
    """Manages dashboard data and statistics."""
    
    def __init__(self):
        """Initialize dashboard manager."""
        logger.debug("DashboardManager initialized")
    
    def get_dashboard_stats(self) -> DashboardStats:
        """
        Get comprehensive dashboard statistics.
        
        Returns:
            DashboardStats: Complete dashboard data
        """
        logger.info("Generating dashboard statistics")
        
        try:
            with get_connection() as conn:
                # Job counts by status
                total_jobs = self._get_job_count(conn, None)
                active_jobs = self._get_job_count(conn, "active")
                scored_jobs = self._get_scored_job_count(conn)
                high_score_jobs = self._get_high_score_job_count(conn)
                
                # Today's activity
                today = date.today()
                todays_new_jobs = self._get_todays_new_jobs(conn, today)
                todays_applications = self._get_todays_applications(conn, today)
                todays_emails = self._get_todays_emails(conn, today)
                
                # Application pipeline
                applications_submitted = self._get_application_count(conn, "applied")
                applications_pending = self._get_application_count(conn, "pending")
                applications_needs_manual = self._get_application_count(conn, "needs_manual")
                
                # LinkedIn drafts (jobs with scores but no applications)
                pending_linkedin = self._get_pending_linkedin_drafts(conn)
                
                # Top jobs needing action
                top_jobs_action = self._get_top_jobs_needing_action(conn)
                
                # Email quota
                email_quota = self._get_email_quota_status(conn, today)
                
                # System health
                last_ingestion = self._get_last_ingestion_time(conn)
                last_application = self._get_last_application_time(conn)
                pipeline_health = self._assess_pipeline_health(conn)
                
                return DashboardStats(
                    # Job counts
                    total_jobs=total_jobs,
                    active_jobs=active_jobs,
                    scored_jobs=scored_jobs,
                    high_score_jobs=high_score_jobs,
                    
                    # Today's activity
                    todays_new_jobs=todays_new_jobs,
                    todays_applications=todays_applications,
                    todays_emails=todays_emails,
                    
                    # Application pipeline
                    applications_submitted=applications_submitted,
                    applications_pending=applications_pending,
                    applications_needs_manual=applications_needs_manual,
                    
                    # LinkedIn drafts
                    pending_linkedin_drafts=pending_linkedin,
                    pending_linkedin_count=len(pending_linkedin),
                    
                    # Top jobs needing action
                    top_jobs_needing_action=top_jobs_action,
                    
                    # Email quota
                    email_quota_used=email_quota['used'],
                    email_quota_limit=email_quota['limit'],
                    email_quota_remaining=email_quota['remaining'],
                    
                    # System health
                    last_ingestion=last_ingestion,
                    last_application=last_application,
                    pipeline_health=pipeline_health
                )
                
        except Exception as e:
            logger.error(f"Failed to generate dashboard stats: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get dashboard stats: {e}")
    
    def _get_job_count(self, conn, status: Optional[str] = None) -> int:
        """Get job count by status."""
        if status:
            return exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM jobs WHERE status = :status",
                status=status
            ) or 0
        else:
            return exec_query_scalar(conn, "SELECT COUNT(*) FROM jobs") or 0
    
    def _get_scored_job_count(self, conn) -> int:
        """Get count of jobs with scores."""
        return exec_query_scalar(
            conn,
            "SELECT COUNT(*) FROM jobs WHERE score IS NOT NULL"
        ) or 0
    
    def _get_high_score_job_count(self, conn) -> int:
        """Get count of high-scoring jobs."""
        return exec_query_scalar(
            conn,
            "SELECT COUNT(*) FROM jobs WHERE score >= 80"
        ) or 0
    
    def _get_todays_new_jobs(self, conn, today: date) -> int:
        """Get count of jobs created today."""
        return exec_query_scalar(
            conn,
            "SELECT COUNT(*) FROM jobs WHERE DATE(created_at) = :today",
            today=today
        ) or 0
    
    def _get_todays_applications(self, conn, today: date) -> int:
        """Get count of applications submitted today."""
        return exec_query_scalar(
            conn,
            "SELECT COUNT(*) FROM applications WHERE DATE(applied_at) = :today",
            today=today
        ) or 0
    
    def _get_todays_emails(self, conn, today: date) -> int:
        """Get count of emails sent today."""
        return exec_query_scalar(
            conn,
            "SELECT sent_count FROM send_quota WHERE date = :today",
            today=today
        ) or 0
    
    def _get_application_count(self, conn, status: str) -> int:
        """Get application count by status."""
        return exec_query_scalar(
            conn,
            "SELECT COUNT(*) FROM applications WHERE status = :status",
            status=status
        ) or 0
    
    def _get_pending_linkedin_drafts(self, conn) -> List[JobSummary]:
        """Get jobs that need LinkedIn outreach."""
        jobs = exec_query_fetchall(
            conn,
            """
            SELECT j.id, j.title, j.company, j.score, j.status, j.source, j.created_at
            FROM jobs j
            LEFT JOIN applications a ON j.id = a.job_id
            WHERE j.score >= 70 
              AND j.status = 'active'
              AND (a.id IS NULL OR a.status IN ('pending', 'needs_manual'))
            ORDER BY j.score DESC, j.created_at DESC
            LIMIT 10
            """
        )
        
        return [
            JobSummary(
                id=str(job['id']),
                title=job['title'],
                company=job['company'],
                score=job['score'],
                status=job['status'],
                source=job.get('source'),
                created_at=job['created_at'].isoformat() if job['created_at'] else '',
                needs_action=True
            )
            for job in jobs
        ]
    
    def _get_top_jobs_needing_action(self, conn) -> List[JobSummary]:
        """Get top 20 jobs that need action."""
        jobs = exec_query_fetchall(
            conn,
            """
            SELECT j.id, j.title, j.company, j.score, j.status, j.source, 
                   j.created_at, a.status as application_status
            FROM jobs j
            LEFT JOIN applications a ON j.id = a.job_id
            WHERE j.status = 'active'
              AND (
                (j.score IS NULL) OR  -- Needs scoring
                (j.score >= 70 AND a.id IS NULL) OR  -- High score, no application
                (a.status = 'needs_manual') OR  -- Needs manual application
                (a.status = 'pending')  -- Application pending
              )
            ORDER BY 
              CASE 
                WHEN j.score IS NULL THEN 1  -- Unscored jobs first
                WHEN j.score >= 80 THEN 2    -- High score jobs
                WHEN a.status = 'needs_manual' THEN 3  -- Manual action needed
                ELSE 4
              END,
              j.score DESC NULLS LAST,
              j.created_at DESC
            LIMIT 20
            """
        )
        
        return [
            JobSummary(
                id=str(job['id']),
                title=job['title'],
                company=job['company'],
                score=job['score'],
                status=job['status'],
                source=job.get('source'),
                created_at=job['created_at'].isoformat() if job['created_at'] else '',
                application_status=job.get('application_status'),
                needs_action=True
            )
            for job in jobs
        ]
    
    def _get_email_quota_status(self, conn, today: date) -> Dict[str, int]:
        """Get email quota status for today."""
        quota_record = exec_query_fetchone(
            conn,
            "SELECT sent_count, daily_limit FROM send_quota WHERE date = :today",
            today=today
        )
        
        if quota_record:
            used = quota_record['sent_count']
            limit = quota_record['daily_limit']
        else:
            used = 0
            limit = 100
        
        return {
            'used': used,
            'limit': limit,
            'remaining': limit - used
        }
    
    def _get_last_ingestion_time(self, conn) -> Optional[str]:
        """Get timestamp of last job ingestion."""
        result = exec_query_fetchone(
            conn,
            "SELECT MAX(created_at) as last_time FROM jobs WHERE created_at >= :since",
            since=datetime.now() - timedelta(days=7)
        )
        
        if result and result['last_time']:
            return result['last_time'].isoformat() + 'Z'
        return None
    
    def _get_last_application_time(self, conn) -> Optional[str]:
        """Get timestamp of last application submission."""
        result = exec_query_fetchone(
            conn,
            "SELECT MAX(applied_at) as last_time FROM applications WHERE applied_at >= :since",
            since=datetime.now() - timedelta(days=7)
        )
        
        if result and result['last_time']:
            return result['last_time'].isoformat() + 'Z'
        return None
    
    def _assess_pipeline_health(self, conn) -> str:
        """Assess overall pipeline health."""
        try:
            # Check for recent activity
            recent_jobs = exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM jobs WHERE created_at >= :since",
                since=datetime.now() - timedelta(hours=24)
            ) or 0
            
            recent_applications = exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM applications WHERE applied_at >= :since",
                since=datetime.now() - timedelta(hours=24)
            ) or 0
            
            # Check for stuck jobs
            stuck_jobs = exec_query_scalar(
                conn,
                """
                SELECT COUNT(*) FROM jobs 
                WHERE status = 'active' 
                  AND score IS NULL 
                  AND created_at < :cutoff
                """,
                cutoff=datetime.now() - timedelta(hours=6)
            ) or 0
            
            # Assess health
            if recent_jobs > 0 and recent_applications > 0:
                return "healthy"
            elif recent_jobs > 0 or recent_applications > 0:
                return "moderate"
            elif stuck_jobs > 10:
                return "issues"
            else:
                return "idle"
                
        except Exception as e:
            logger.error(f"Failed to assess pipeline health: {e}")
            return "unknown"


# Global dashboard manager instance
dashboard_manager = DashboardManager()


# Convenience functions
def get_dashboard_stats() -> DashboardStats:
    """Get dashboard statistics."""
    return dashboard_manager.get_dashboard_stats()


def get_linkedin_tos_banner() -> str:
    """Get LinkedIn Terms of Service banner content."""
    return """
    <div class="alert alert-warning border-warning" style="background-color: #fff3cd; border: 1px solid #ffeaa7; border-radius: 8px; padding: 16px; margin: 16px 0;">
        <h5 class="alert-heading" style="color: #856404; margin-bottom: 12px;">
            ⚠️ LinkedIn Usage Notice - Draft Only
        </h5>
        <p style="color: #856404; margin-bottom: 8px;">
            <strong>LinkedIn messages are provided for drafting purposes only.</strong> This system does NOT automatically send LinkedIn messages.
        </p>
        <hr style="border-color: #ffeaa7; margin: 12px 0;">
        <div style="color: #856404; font-size: 14px;">
            <p><strong>Important:</strong></p>
            <ul style="margin-bottom: 8px;">
                <li>LinkedIn prohibits automated messaging through their platform</li>
                <li>All LinkedIn outreach must be done manually by the user</li>
                <li>Generated messages are drafts to help you craft personalized outreach</li>
                <li>Always review and customize messages before sending</li>
                <li>Respect LinkedIn's Terms of Service and professional etiquette</li>
            </ul>
            <p style="margin-bottom: 0;">
                <strong>Use LinkedIn messages responsibly:</strong> Personalize each message, respect connection limits, 
                and maintain professional communication standards.
            </p>
        </div>
    </div>
    """


def get_dashboard_html() -> str:
    """Generate complete dashboard HTML with LinkedIn ToS banner."""
    banner = get_linkedin_tos_banner()
    
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Job Bot Dashboard</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            .metric-card {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border-radius: 10px;
                padding: 1.5rem;
                margin-bottom: 1rem;
            }}
            .metric-number {{
                font-size: 2.5rem;
                font-weight: bold;
                margin-bottom: 0.5rem;
            }}
            .metric-label {{
                font-size: 0.9rem;
                opacity: 0.8;
            }}
            .health-healthy {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }}
            .health-moderate {{ background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }}
            .health-issues {{ background: linear-gradient(135deg, #ff758c 0%, #ff7eb3 100%); }}
            .health-idle {{ background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); }}
        </style>
    </head>
    <body class="bg-light">
        <div class="container-fluid py-4">
            <h1 class="mb-4">🤖 Job Bot Dashboard</h1>
            
            {banner}
            
            <div class="row" id="dashboard-content">
                <div class="col-12">
                    <div class="card">
                        <div class="card-body">
                            <h5 class="card-title">Loading Dashboard...</h5>
                            <div class="spinner-border" role="status">
                                <span class="visually-hidden">Loading...</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            // Auto-refresh dashboard every 30 seconds
            async function loadDashboard() {{
                try {{
                    const response = await fetch('/api/stats');
                    const stats = await response.json();
                    updateDashboard(stats);
                }} catch (error) {{
                    console.error('Failed to load dashboard:', error);
                }}
            }}
            
            function updateDashboard(stats) {{
                const content = document.getElementById('dashboard-content');
                content.innerHTML = `
                    <div class="row">
                        <div class="col-md-3">
                            <div class="metric-card">
                                <div class="metric-number">${{stats.total_jobs}}</div>
                                <div class="metric-label">Total Jobs</div>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="metric-card">
                                <div class="metric-number">${{stats.high_score_jobs}}</div>
                                <div class="metric-label">High Score Jobs (≥80)</div>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="metric-card">
                                <div class="metric-number">${{stats.applications_submitted}}</div>
                                <div class="metric-label">Applications Submitted</div>
                            </div>
                        </div>
                        <div class="col-md-3">
                            <div class="metric-card health-${{stats.pipeline_health}}">
                                <div class="metric-number">${{stats.pipeline_health.toUpperCase()}}</div>
                                <div class="metric-label">Pipeline Health</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="row mt-4">
                        <div class="col-md-6">
                            <div class="card">
                                <div class="card-header">
                                    <h5>📋 LinkedIn Drafts Available (Manual Only)</h5>
                                </div>
                                <div class="card-body">
                                    <p class="text-muted">High-scoring jobs with LinkedIn message drafts ready for manual outreach:</p>
                                    ${{stats.pending_linkedin_drafts.map(job => `
                                        <div class="border-bottom py-2">
                                            <strong>${{job.title}}</strong> at ${{job.company}}
                                            <span class="badge bg-primary ms-2">Score: ${{job.score}}</span>
                                        </div>
                                    `).join('')}}
                                    ${{stats.pending_linkedin_count === 0 ? '<p class="text-muted">No LinkedIn drafts pending</p>' : ''}}
                                </div>
                            </div>
                        </div>
                        
                        <div class="col-md-6">
                            <div class="card">
                                <div class="card-header">
                                    <h5>📧 Email Status</h5>
                                </div>
                                <div class="card-body">
                                    <div class="progress mb-2">
                                        <div class="progress-bar" style="width: ${{(stats.email_quota_used / stats.email_quota_limit) * 100}}%">
                                            ${{stats.email_quota_used}}/${{stats.email_quota_limit}}
                                        </div>
                                    </div>
                                    <small class="text-muted">Daily email quota: ${{stats.email_quota_remaining}} remaining</small>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
            }}
            
            // Load dashboard on page load and set up auto-refresh
            loadDashboard();
            setInterval(loadDashboard, 30000); // Refresh every 30 seconds
        </script>
    </body>
    </html>
    """
    
    return html_template