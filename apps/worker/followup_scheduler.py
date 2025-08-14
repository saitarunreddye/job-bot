"""
Follow-up Scheduler for automated outreach follow-ups.
Manages scheduling and sending of value-add follow-up emails at +4 and +10 days.
Uses outreach_enhanced table for all operations.
"""

import logging
import uuid
from datetime import datetime, timedelta, UTC
from typing import Dict, List, Optional, Any
from uuid import UUID

from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from db.db import get_connection, exec_query, exec_query_fetchone, exec_query_fetchall, transaction
from apps.worker.emailer import GmailEmailer, DoNotContactError, RateLimitError

logger = logging.getLogger(__name__)


class FollowupSchedulerError(Exception):
    """Base exception for follow-up scheduler errors."""
    pass


class FollowupTemplate:
    """Container for follow-up email templates with value-add content."""
    
    TEMPLATES = {
        'value_add_1': {
            'subject_prefix': 'Re: ',
            'delay_days': 4,
            'content': '''Hi {first_name},

I wanted to follow up on my previous message about the {job_title} position at {company}.

I came across this recent {industry_trend} article that might interest your team: {article_link}

{value_add_content}

I'd still love to learn more about {company}'s {specific_focus} initiatives and how my {relevant_skill} experience could contribute.

Would you have 15 minutes for a brief call this week?

Best regards,
{sender_name}'''
        },
        
        'value_add_2': {
            'subject_prefix': 'Re: ',
            'delay_days': 10,
            'content': '''Hi {first_name},

I hope you're doing well. I wanted to share something that might be valuable for {company}'s {technical_area} work.

{value_add_content}

I noticed {company} is {recent_company_news}. Given my experience with {relevant_experience}, I believe I could help {specific_contribution}.

Would you be open to a brief conversation about the {job_title} role?

Thanks for your time,
{sender_name}'''
        },
        
        'technical_insight': {
            'subject_prefix': 'Re: ',
            'delay_days': 4,
            'content': '''Hi {first_name},

Following up on the {job_title} position - I wanted to share a quick technical insight that might be relevant.

{technical_insight}

This approach has helped reduce {metric} by {percentage} in my previous projects. I'd love to discuss how similar optimizations could benefit {company}.

Are you available for a 15-minute call this week?

Best,
{sender_name}'''
        }
    }
    
    VALUE_ADD_CONTENT = {
        'industry_trends': [
            "The latest developments in AI/ML are creating new opportunities for automation.",
            "Recent studies show that companies using modern data pipelines see 40% faster insights.",
            "The shift to cloud-native architectures is accelerating digital transformation.",
            "New security frameworks are becoming essential for modern applications.",
            "DevOps practices are evolving with container orchestration and GitOps."
        ],
        
        'technical_insights': [
            "Implementing proper database indexing strategies can improve query performance by 60-80%.",
            "Using async/await patterns in Python can significantly improve I/O-bound application performance.",
            "Microservices architecture with proper API gateways reduces system coupling and improves scalability.",
            "Implementing CI/CD pipelines with automated testing reduces deployment risks by 70%.",
            "Container orchestration with Kubernetes enables better resource utilization and deployment flexibility."
        ],
        
        'industry_resources': [
            "https://github.com/awesome-python/awesome-python",
            "https://martinfowler.com/articles/microservices.html",
            "https://12factor.net/",
            "https://cloudnative.cncf.io/",
            "https://dzone.com/articles/category/devops"
        ]
    }
    
    @classmethod
    def get_template(cls, template_type: str) -> Dict[str, Any]:
        """Get a follow-up template by type."""
        if template_type not in cls.TEMPLATES:
            raise ValueError(f"Unknown template type: {template_type}")
        return cls.TEMPLATES[template_type].copy()
    
    @classmethod
    def generate_value_add_content(cls, job_data: Dict[str, Any], template_type: str) -> str:
        """Generate contextual value-add content based on job and template type."""
        import random
        
        job_title = job_data.get('title', '').lower()
        company = job_data.get('company', '')
        
        # Determine content type based on job and template
        if 'engineer' in job_title or 'developer' in job_title:
            if template_type == 'value_add_1':
                insight = random.choice(cls.VALUE_ADD_CONTENT['industry_trends'])
                return f"I've been following the latest trends in software development, and {insight.lower()}"
            else:
                insight = random.choice(cls.VALUE_ADD_CONTENT['technical_insights'])
                return f"Here's a technical insight from my recent work: {insight}"
        
        elif 'data' in job_title or 'analytics' in job_title:
            if template_type == 'value_add_1':
                return "I've been exploring new data processing frameworks that could significantly improve pipeline efficiency."
            else:
                return "I recently optimized a data pipeline that reduced processing time by 50% using modern streaming architectures."
        
        elif 'devops' in job_title or 'cloud' in job_title:
            if template_type == 'value_add_1':
                return "The latest developments in cloud-native technologies are creating exciting opportunities for infrastructure optimization."
            else:
                return "I recently implemented a Kubernetes deployment strategy that improved system reliability by 90%."
        
        else:
            # Generic value-add content
            if template_type == 'value_add_1':
                return "I've been researching industry best practices that could bring value to your team."
            else:
                return "I recently worked on a project that delivered significant improvements in efficiency and scalability."


class FollowupScheduler:
    """Manages automated follow-up email scheduling and execution using outreach_enhanced table."""
    
    def __init__(self):
        self.emailer = GmailEmailer()
    
    def schedule_followups(self, outreach_id: UUID, job_data: Dict[str, Any], 
                          contact_data: Dict[str, Any]) -> List[int]:
        """
        Schedule follow-up emails for an outreach message.
        
        Args:
            outreach_id: ID of the original outreach message
            job_data: Job information for personalization
            contact_data: Contact information
            
        Returns:
            List of follow-up outreach IDs created
        """
        logger.info(f"Scheduling follow-ups for outreach: {outreach_id}")
        
        try:
            # Check if follow-ups already scheduled
            with get_connection() as conn:
                existing = exec_query_fetchone(
                    conn,
                    "SELECT COUNT(*) as count FROM outreach_enhanced WHERE reply_status = 'followup_scheduled' AND job_id = :job_id AND contact_id = :contact_id",
                    job_id=job_data.get('id'),
                    contact_id=contact_data.get('id')
                )
                
                if existing and existing['count'] > 0:
                    logger.warning(f"Follow-ups already scheduled for outreach {outreach_id}")
                    return []
            
            # Create follow-up entries in outreach_enhanced
            followup_ids = []
            current_time = datetime.now(UTC)
            
            # Schedule +4 day follow-up
            followup_1_time = current_time + timedelta(days=4)
            followup_id_1 = self._create_followup_outreach(
                outreach_id, job_data, contact_data, 1, followup_1_time, 'value_add_1'
            )
            followup_ids.append(followup_id_1)
            
            # Schedule +10 day follow-up  
            followup_2_time = current_time + timedelta(days=10)
            followup_id_2 = self._create_followup_outreach(
                outreach_id, job_data, contact_data, 2, followup_2_time, 'value_add_2'
            )
            followup_ids.append(followup_id_2)
            
            logger.info(f"Scheduled {len(followup_ids)} follow-ups for outreach {outreach_id}")
            return followup_ids
            
        except Exception as e:
            logger.error(f"Failed to schedule follow-ups for outreach {outreach_id}: {e}")
            raise FollowupSchedulerError(f"Follow-up scheduling failed: {e}")
    
    def _create_followup_outreach(self, parent_outreach_id: UUID, job_data: Dict[str, Any],
                                contact_data: Dict[str, Any], sequence: int, 
                                scheduled_time: datetime, template_type: str) -> int:
        """Create a single follow-up outreach entry in outreach_enhanced."""
        
        # Generate follow-up content
        email_content = self._generate_followup_content(job_data, contact_data, template_type)
        
        with transaction() as conn:
            result = exec_query(
                conn,
                """
                    INSERT INTO outreach_enhanced (
                        job_id, contact_id, channel, subject, message_content,
                        scheduled_at, reply_status, attempt_count
                    ) VALUES (
                        :job_id, :contact_id, :channel, :subject, :message_content,
                        :scheduled_at, :reply_status, :attempt_count
                    )
                """,
                job_id=job_data.get('id'),
                contact_id=contact_data.get('id'),
                channel='email',
                subject=email_content['subject'],
                message_content=email_content['body'],
                scheduled_at=scheduled_time,
                reply_status='followup_scheduled',
                attempt_count=0
            )
            
            # Get the inserted outreach_id
            followup_id = exec_query_fetchone(
                conn,
                "SELECT last_insert_rowid() as id"
            )['id']
        
        return followup_id
    
    @retry(
        stop=stop_after_attempt(3), 
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((Exception,)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retrying follow-up processing after error: {retry_state.outcome.exception()}. "
            f"Attempt {retry_state.attempt_number}/3"
        )
    )
    def process_due_followups(self) -> Dict[str, int]:
        """
        Process all follow-ups that are due to be sent.
        
        Returns:
            Dict with counts of processed, sent, skipped follow-ups
        """
        logger.info("Processing due follow-ups...")
        
        stats = {
            'processed': 0,
            'sent': 0,
            'skipped': 0,
            'errors': 0
        }
        
        try:
            # Get due follow-ups
            due_followups = self._get_due_followups()
            stats['processed'] = len(due_followups)
            
            logger.info(f"Found {len(due_followups)} due follow-ups")
            
            for followup in due_followups:
                try:
                    if self._should_send_followup(followup):
                        self._send_followup(followup)
                        stats['sent'] += 1
                    else:
                        self._mark_followup_skipped(followup['outreach_id'], "Recipient responded or unsubscribed")
                        stats['skipped'] += 1
                        
                except (DoNotContactError, RateLimitError) as e:
                    logger.warning(f"Skipping follow-up {followup['outreach_id']}: {e}")
                    self._mark_followup_skipped(followup['outreach_id'], str(e))
                    stats['skipped'] += 1
                    
                except Exception as e:
                    logger.error(f"Error sending follow-up {followup['outreach_id']}: {e}")
                    stats['errors'] += 1
            
            logger.info(f"Follow-up processing completed: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to process due follow-ups: {e}")
            raise FollowupSchedulerError(f"Follow-up processing failed: {e}")
    
    def _get_due_followups(self) -> List[Dict[str, Any]]:
        """Get all follow-ups that are due to be sent."""
        with get_connection() as conn:
            return exec_query_fetchall(
                conn,
                """
                    SELECT 
                        outreach_id, job_id, contact_id, subject, message_content
                    FROM outreach_enhanced
                    WHERE sent_at IS NULL 
                      AND scheduled_at <= :now
                      AND reply_status = 'followup_scheduled'
                    ORDER BY scheduled_at ASC
                """,
                now=datetime.now(UTC)
            )
    
    def _should_send_followup(self, followup: Dict[str, Any]) -> bool:
        """
        Check if a follow-up should be sent based on response status and do-not-contact list.
        """
        # Check if recipient is on do-not-contact list
        try:
            # Get contact email for do-not-contact check
            with get_connection() as conn:
                contact = exec_query_fetchone(
                    conn,
                    "SELECT email FROM contacts WHERE contact_id = :contact_id",
                    contact_id=followup['contact_id']
                )
                if contact:
                    self.emailer.check_do_not_contact(contact['email'])
        except DoNotContactError:
            return False
        
        # Check if original thread received a response
        with get_connection() as conn:
            response_check = exec_query_fetchone(
                conn,
                """
                    SELECT COUNT(*) as response_count
                    FROM outreach_enhanced 
                    WHERE job_id = :job_id 
                      AND contact_id = :contact_id
                      AND reply_status = 'replied'
                """,
                job_id=followup['job_id'],
                contact_id=followup['contact_id']
            )
            
            if response_check and response_check['response_count'] > 0:
                logger.info(f"Skipping follow-up {followup['outreach_id']}: recipient already responded")
                return False
        
        return True
    
    def _send_followup(self, followup: Dict[str, Any]) -> None:
        """Send a follow-up email and update outreach record."""
        logger.info(f"Sending follow-up {followup['outreach_id']}")
        
        try:
            # Get contact email
            with get_connection() as conn:
                contact = exec_query_fetchone(
                    conn,
                    "SELECT email FROM contacts WHERE contact_id = :contact_id",
                    contact_id=followup['contact_id']
                )
                
                if not contact:
                    raise FollowupSchedulerError(f"Contact not found for follow-up {followup['outreach_id']}")
                
                to_address = contact['email']
            
            # Send email
            self.emailer.send_email(
                to=to_address,
                subject=followup['subject'],
                body=followup['message_content']
            )
            
            # Update outreach record as sent
            self._mark_followup_sent(followup['outreach_id'])
            
            logger.info(f"Follow-up sent successfully: {followup['outreach_id']}")
            
        except Exception as e:
            logger.error(f"Failed to send follow-up {followup['outreach_id']}: {e}")
            raise
    
    def _generate_followup_content(self, job_data: Dict[str, Any], contact_data: Dict[str, Any], 
                                 template_type: str) -> Dict[str, str]:
        """Generate personalized follow-up email content."""
        template = FollowupTemplate.get_template(template_type)
        
        # Extract personalization data
        first_name = contact_data.get('first_name', 'there')
        job_title = job_data.get('title', 'position')
        company = job_data.get('company', 'your company')
        
        # Generate value-add content
        value_add = FollowupTemplate.generate_value_add_content(job_data, template_type)
        
        # Build subject (threaded)
        subject = f"Re: Application for {job_title} position at {company}"
        
        # Build email body
        body = template['content'].format(
            first_name=first_name,
            job_title=job_title,
            company=company,
            value_add_content=value_add,
            sender_name="[Your Name]",  # TODO: Make configurable
            industry_trend="industry",
            article_link="[relevant link]",
            specific_focus="technical",
            relevant_skill="software development",
            technical_area="engineering",
            recent_company_news="expanding their technical team",
            relevant_experience="similar technologies",
            specific_contribution="drive innovation and efficiency",
            metric="processing time",
            percentage="40%"
        )
        
        return {
            'subject': subject,
            'body': body
        }
    
    def _mark_followup_sent(self, outreach_id: int):
        """Mark a follow-up as sent with sent_at timestamp and increment attempt_count."""
        with transaction() as conn:
            exec_query(
                conn,
                """
                    UPDATE outreach_enhanced 
                    SET sent_at = :now, 
                        attempt_count = attempt_count + 1,
                        reply_status = 'sent'
                    WHERE outreach_id = :id
                """,
                id=outreach_id,
                now=datetime.now(UTC)
            )
    
    def _mark_followup_skipped(self, outreach_id: int, reason: str):
        """Mark a follow-up as skipped."""
        with transaction() as conn:
            exec_query(
                conn,
                """
                    UPDATE outreach_enhanced 
                    SET reply_status = 'skipped',
                        sent_at = :now
                    WHERE outreach_id = :id
                """,
                id=outreach_id,
                now=datetime.now(UTC)
            )
    
    def cancel_followups(self, job_id: int, contact_id: int, reason: str = "Cancelled by user") -> int:
        """
        Cancel all scheduled follow-ups for a job/contact combination.
        
        Args:
            job_id: ID of the job
            contact_id: ID of the contact
            reason: Reason for cancellation
            
        Returns:
            Number of follow-ups cancelled
        """
        logger.info(f"Cancelling follow-ups for job {job_id}, contact {contact_id}")
        
        with transaction() as conn:
            result = exec_query(
                conn,
                """
                    UPDATE outreach_enhanced 
                    SET reply_status = 'cancelled',
                        sent_at = :now
                    WHERE job_id = :job_id 
                      AND contact_id = :contact_id 
                      AND reply_status = 'followup_scheduled'
                """,
                job_id=job_id,
                contact_id=contact_id,
                now=datetime.now(UTC)
            )
            
            cancelled_count = result.rowcount if hasattr(result, 'rowcount') else 0
            logger.info(f"Cancelled {cancelled_count} follow-ups for job {job_id}, contact {contact_id}")
            return cancelled_count
    
    def get_followup_stats(self) -> Dict[str, Any]:
        """Get follow-up scheduler statistics."""
        with get_connection() as conn:
            stats = exec_query_fetchone(
                conn,
                """
                    SELECT 
                        COUNT(*) as total_scheduled,
                        COUNT(CASE WHEN reply_status = 'followup_scheduled' THEN 1 END) as pending,
                        COUNT(CASE WHEN reply_status = 'sent' THEN 1 END) as sent,
                        COUNT(CASE WHEN reply_status = 'skipped' THEN 1 END) as skipped,
                        COUNT(CASE WHEN reply_status = 'cancelled' THEN 1 END) as cancelled,
                        COUNT(CASE WHEN scheduled_at <= :now AND reply_status = 'followup_scheduled' THEN 1 END) as overdue
                    FROM outreach_enhanced
                    WHERE reply_status IN ('followup_scheduled', 'sent', 'skipped', 'cancelled')
                """,
                now=datetime.now(UTC)
            )
        
        return dict(stats) if stats else {}


# Global scheduler instance
followup_scheduler = FollowupScheduler()


# Convenience functions
def schedule_followups_for_outreach(outreach_id: UUID, job_data: Dict[str, Any], 
                                  contact_data: Dict[str, Any]) -> List[int]:
    """Schedule follow-ups for an outreach message."""
    return followup_scheduler.schedule_followups(outreach_id, job_data, contact_data)


def process_due_followups() -> Dict[str, int]:
    """Process all due follow-ups."""
    return followup_scheduler.process_due_followups()


def cancel_followups_for_job_contact(job_id: int, contact_id: int, reason: str = "Cancelled") -> int:
    """Cancel follow-ups for a job/contact combination."""
    return followup_scheduler.cancel_followups(job_id, contact_id, reason)
