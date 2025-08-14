"""
Gmail API emailer with OAuth2 authentication and rate limiting.
Handles the complete email sending workflow with quota management.
"""

import base64
import logging
import mimetypes
import os
import json
from datetime import date, datetime, UTC
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Optional, Dict, Any
from uuid import UUID

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    before_sleep_log,
    retry_if_exception_type
)

from config.settings import settings
from db.db import get_connection, exec_query, exec_query_fetchone, transaction

logger = logging.getLogger(__name__)

# Gmail API scopes for sending emails
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Rate limiting defaults
DEFAULT_DAILY_LIMIT = 30  # Respectful daily limit
QUOTA_WARNING_THRESHOLD = 0.8  # Warn when 80% of quota is used
MIN_SEND_INTERVAL_MINUTES = 2  # Minimum 2 minutes between emails


class EmailError(Exception):
    """Base exception for email operations."""
    pass


class QuotaExceededError(EmailError):
    """Raised when daily email quota is exceeded."""
    pass


class AuthenticationError(EmailError):
    """Raised when Gmail authentication fails."""
    pass


class DoNotContactError(EmailError):
    """Raised when attempting to email an address on the do-not-contact list."""
    pass


class RateLimitError(EmailError):
    """Raised when email sending is rate limited."""
    pass


class GmailEmailer:
    """Gmail API emailer with OAuth2 authentication and rate limiting."""
    
    def __init__(self, credentials_file: Optional[str] = None, token_file: Optional[str] = None):
        """
        Initialize Gmail emailer.
        
        Args:
            credentials_file: Path to Gmail credentials JSON file
            token_file: Path to store OAuth token
        """
        self.credentials_file = credentials_file or settings.gmail_credentials_file
        self.token_file = token_file or "config/gmail_token.json"
        self.service = None
        self.credentials = None
        
        # Ensure config directory exists
        Path(self.token_file).parent.mkdir(exist_ok=True)
        
        logger.debug(f"GmailEmailer initialized with credentials: {self.credentials_file}")
    
    def setup_gmail(self) -> bool:
        """
        Set up Gmail API authentication using OAuth2 flow.
        
        Loads existing token or initiates OAuth flow to get new credentials.
        Stores refresh token for future use.
        
        Returns:
            bool: True if authentication successful
            
        Raises:
            AuthenticationError: If authentication setup fails
        """
        logger.info("Setting up Gmail API authentication...")
        
        try:
            # Check if token file exists and load existing credentials
            if Path(self.token_file).exists():
                logger.debug(f"Loading existing token from: {self.token_file}")
                self.credentials = Credentials.from_authorized_user_file(
                    self.token_file, SCOPES
                )
            
            # If there are no valid credentials, initiate OAuth flow
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    logger.info("Refreshing expired credentials...")
                    self.credentials.refresh(Request())
                else:
                    logger.info("Starting OAuth2 flow for new credentials...")
                    
                    # Check if credentials file exists
                    if not Path(self.credentials_file).exists():
                        raise AuthenticationError(
                            f"Gmail credentials file not found: {self.credentials_file}. "
                            f"Please download OAuth2 credentials from Google Cloud Console."
                        )
                    
                    # Run OAuth flow
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_file, SCOPES
                    )
                    self.credentials = flow.run_local_server(port=0)
                
                # Save credentials for future use
                with open(self.token_file, 'w') as token:
                    token.write(self.credentials.to_json())
                    logger.info(f"Credentials saved to: {self.token_file}")
            
            # Build Gmail service
            self.service = build('gmail', 'v1', credentials=self.credentials)
            
            # Test the connection
            profile = self.service.users().getProfile(userId='me').execute()
            email_address = profile.get('emailAddress')
            
            logger.info(f"Gmail API setup successful for: {email_address}")
            return True
            
        except Exception as e:
            logger.error(f"Gmail setup failed: {e}")
            raise AuthenticationError(f"Failed to setup Gmail API: {e}")
    
    def check_do_not_contact(self, email: str) -> Dict[str, Any]:
        """
        Check if an email address is on the do-not-contact list.
        
        Args:
            email: Email address to check
            
        Returns:
            Dict with check results
            
        Raises:
            DoNotContactError: If email is on do-not-contact list
        """
        try:
            with get_connection() as conn:
                dnc_record = exec_query_fetchone(
                    conn,
                    """
                    SELECT email, reason, added_at, notes, permanent
                    FROM do_not_contact 
                    WHERE LOWER(email) = LOWER(:email)
                    """,
                    email=email
                )
            
            if dnc_record:
                reason = dnc_record['reason']
                added_at = dnc_record['added_at']
                notes = dnc_record.get('notes', '')
                permanent = dnc_record['permanent']
                
                logger.warning(f"Email {email} is on do-not-contact list: {reason}")
                
                raise DoNotContactError(
                    f"Email {email} is on do-not-contact list. "
                    f"Reason: {reason}, Added: {added_at}, "
                    f"Permanent: {permanent}, Notes: {notes}"
                )
            
            return {
                'email': email,
                'allowed': True,
                'checked_at': datetime.now(UTC).isoformat()
            }
            
        except DoNotContactError:
            raise
        except Exception as e:
            logger.error(f"Do-not-contact check failed for {email}: {e}")
            # Default to allowing if check fails (but log the error)
            return {
                'email': email,
                'allowed': True,
                'checked_at': datetime.now(UTC).isoformat(),
                'error': str(e)
            }
    
    def add_to_do_not_contact(self, email: str, reason: str, notes: str = "", 
                              source: str = "manual", permanent: bool = True) -> bool:
        """
        Add an email address to the do-not-contact list.
        
        Args:
            email: Email address to add
            reason: Reason for adding (unsubscribed, complained, etc.)
            notes: Additional notes
            source: Source of the request
            permanent: Whether this is a permanent block
            
        Returns:
            bool: True if successfully added
        """
        try:
            with transaction() as conn:
                exec_query(
                    conn,
                    """
                    INSERT INTO do_not_contact (email, reason, notes, source, permanent, added_by)
                    VALUES (:email, :reason, :notes, :source, :permanent, 'system')
                    ON CONFLICT (email) 
                    DO UPDATE SET 
                        reason = :reason,
                        notes = :notes,
                        source = :source,
                        permanent = :permanent,
                        added_at = CURRENT_TIMESTAMP
                    """,
                    email=email.lower(),
                    reason=reason,
                    notes=notes,
                    source=source,
                    permanent=permanent
                )
            
            logger.info(f"Added {email} to do-not-contact list: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add {email} to do-not-contact list: {e}")
            return False
    
    def check_rate_limit(self) -> Dict[str, Any]:
        """
        Check if enough time has passed since last email (respectful delays).
        
        Returns:
            Dict with rate limit information
            
        Raises:
            RateLimitError: If sending too soon after last email
        """
        try:
            with get_connection() as conn:
                last_sent = exec_query_fetchone(
                    conn,
                    """
                    SELECT last_email_sent_at, next_allowed_send_at
                    FROM email_rate_limits 
                    WHERE date = CURRENT_DATE
                    """,
                )
            
            if not last_sent or not last_sent['last_email_sent_at']:
                return {
                    'can_send': True,
                    'last_sent': None,
                    'next_allowed': None,
                    'wait_seconds': 0
                }
            
            last_sent_at = last_sent['last_email_sent_at']
            next_allowed = last_sent['next_allowed_send_at']
            now = datetime.now(UTC)
            
            if next_allowed and now < next_allowed.replace(tzinfo=None):
                wait_seconds = (next_allowed.replace(tzinfo=None) - now).total_seconds()
                
                raise RateLimitError(
                    f"Rate limit active. Must wait {wait_seconds:.0f} seconds "
                    f"before sending next email (respectful delay)"
                )
            
            return {
                'can_send': True,
                'last_sent': last_sent_at.isoformat() if last_sent_at else None,
                'next_allowed': next_allowed.isoformat() if next_allowed else None,
                'wait_seconds': 0
            }
            
        except RateLimitError:
            raise
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # Default to allowing if check fails
            return {
                'can_send': True,
                'last_sent': None,
                'next_allowed': None,
                'wait_seconds': 0,
                'error': str(e)
            }
    
    def update_rate_limit(self) -> None:
        """Update rate limit tracking after sending an email."""
        try:
            from datetime import timedelta
            
            now = datetime.now(UTC)
            next_allowed = now + timedelta(minutes=MIN_SEND_INTERVAL_MINUTES)
            
            with transaction() as conn:
                exec_query(
                    conn,
                    """
                    INSERT INTO email_rate_limits (date, emails_sent, last_email_sent_at, next_allowed_send_at)
                    VALUES (CURRENT_DATE, 1, :now, :next_allowed)
                    ON CONFLICT (date)
                    DO UPDATE SET
                        emails_sent = email_rate_limits.emails_sent + 1,
                        last_email_sent_at = :now,
                        next_allowed_send_at = :next_allowed,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    now=now,
                    next_allowed=next_allowed
                )
            
            logger.debug(f"Rate limit updated. Next email allowed at: {next_allowed}")
            
        except Exception as e:
            logger.error(f"Failed to update rate limit: {e}")
            # Don't raise here - email was already sent successfully

    def check_quota(self, required_count: int = 1) -> Dict[str, Any]:
        """
        Check daily email quota and validate if sending is allowed.
        
        Args:
            required_count: Number of emails to be sent
            
        Returns:
            Dict with quota information
            
        Raises:
            QuotaExceededError: If quota would be exceeded
        """
        today = date.today()
        
        try:
            with get_connection() as conn:
                quota_record = exec_query_fetchone(
                    conn,
                    "SELECT sent_count, daily_limit FROM send_quota WHERE date = :date",
                    date=today
                )
            
            if quota_record:
                sent_count = quota_record['sent_count']
                daily_limit = quota_record['daily_limit']
            else:
                sent_count = 0
                daily_limit = DEFAULT_DAILY_LIMIT
            
            remaining = daily_limit - sent_count
            usage_percent = (sent_count / daily_limit) * 100
            
            quota_info = {
                'date': str(today),
                'sent_count': sent_count,
                'daily_limit': daily_limit,
                'remaining': remaining,
                'usage_percent': round(usage_percent, 1),
                'can_send': remaining >= required_count
            }
            
            logger.debug(f"Quota check: {sent_count}/{daily_limit} used ({usage_percent:.1f}%)")
            
            # Check if quota would be exceeded
            if remaining < required_count:
                raise QuotaExceededError(
                    f"Daily email quota exceeded. "
                    f"Sent: {sent_count}/{daily_limit}, "
                    f"Requested: {required_count}, "
                    f"Remaining: {remaining}"
                )
            
            # Warn if approaching quota limit
            if usage_percent >= (QUOTA_WARNING_THRESHOLD * 100):
                logger.warning(f"Approaching daily quota limit: {usage_percent:.1f}% used")
            
            return quota_info
            
        except QuotaExceededError:
            raise
        except Exception as e:
            logger.error(f"Quota check failed: {e}")
            # Default to allowing if quota check fails
            return {
                'date': str(today),
                'sent_count': 0,
                'daily_limit': DEFAULT_DAILY_LIMIT,
                'remaining': DEFAULT_DAILY_LIMIT,
                'usage_percent': 0.0,
                'can_send': True,
                'error': str(e)
            }
    
    def increment_quota(self) -> int:
        """
        Increment the daily sent email count.
        
        Returns:
            int: New sent count for today
        """
        today = date.today()
        
        try:
            with transaction() as conn:
                # Use UPSERT to handle first email of the day
                result = exec_query(
                    conn,
                    """
                    INSERT INTO send_quota (date, sent_count, daily_limit)
                    VALUES (:date, 1, :daily_limit)
                    ON CONFLICT (date) 
                    DO UPDATE SET 
                        sent_count = send_quota.sent_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING sent_count
                    """,
                    date=today,
                    daily_limit=DEFAULT_DAILY_LIMIT
                )
                
                new_count = result.scalar()
                logger.debug(f"Quota incremented: {new_count} emails sent today")
                return new_count
                
        except Exception as e:
            logger.error(f"Failed to increment quota: {e}")
            raise EmailError(f"Failed to update email quota: {e}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        retry=retry_if_exception_type((HttpError, EmailError))
    )
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: Optional[List[str]] = None,
        from_name: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Send email via Gmail API with optional attachments and threading support.
        
        Args:
            to: Recipient email address
            subject: Email subject line
            body: Email body content (plain text or HTML)
            attachments: List of file paths to attach
            from_name: Optional sender name (default: authenticated user)
            headers: Optional dict of email headers for threading (In-Reply-To, References, etc.)
            
        Returns:
            Dict with send result information
            
        Raises:
            EmailError: If email sending fails
            QuotaExceededError: If daily quota exceeded
        """
        logger.info(f"Sending email to: {to}, subject: {subject[:50]}...")
        
        try:
            # Check authentication
            if not self.service:
                self.setup_gmail()
            
            # Check do-not-contact list first
            self.check_do_not_contact(to)
            
            # Check rate limiting (respectful delays)
            self.check_rate_limit()
            
            # Check quota before sending
            quota_info = self.check_quota(1)
            
            # Create message
            message = self._create_message(to, subject, body, attachments, from_name, headers)
            
            # Send via Gmail API
            result = self.service.users().messages().send(
                userId='me', 
                body=message
            ).execute()
            
            # Update rate limiting and quota tracking
            self.update_rate_limit()
            new_count = self.increment_quota()
            
            send_result = {
                'message_id': result.get('id'),
                'thread_id': result.get('threadId'),
                'to': to,
                'subject': subject,
                'sent_at': datetime.now(UTC).isoformat() + 'Z',
                'attachments_count': len(attachments) if attachments else 0,
                'quota_used': new_count,
                'quota_remaining': quota_info['daily_limit'] - new_count
            }
            
            logger.info(f"Email sent successfully: {result.get('id')}")
            logger.debug(f"Send result: {send_result}")
            
            return send_result
            
        except (QuotaExceededError, DoNotContactError, RateLimitError):
            raise
        except HttpError as e:
            error_details = e.error_details[0] if e.error_details else {}
            error_message = error_details.get('message', str(e))
            logger.error(f"Gmail API error: {error_message}")
            raise EmailError(f"Gmail API error: {error_message}")
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            raise EmailError(f"Failed to send email: {e}")
    
    def _create_message(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: Optional[List[str]] = None,
        from_name: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        Create email message in Gmail API format.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Email body content
            attachments: List of file paths to attach
            from_name: Optional sender name
            
        Returns:
            Dict: Gmail API message format
        """
        # Create multipart message
        message = MIMEMultipart()
        message['to'] = to
        message['subject'] = subject
        
        # Set from field with optional name
        if from_name:
            profile = self.service.users().getProfile(userId='me').execute()
            sender_email = profile.get('emailAddress')
            message['from'] = f"{from_name} <{sender_email}>"
        
        # Add threading headers for email conversations
        if headers:
            for header_name, header_value in headers.items():
                if header_value:  # Only add non-empty headers
                    message[header_name] = header_value
        
        # Add body (detect if HTML or plain text)
        if body.strip().startswith('<') and body.strip().endswith('>'):
            message.attach(MIMEText(body, 'html'))
        else:
            message.attach(MIMEText(body, 'plain'))
        
        # Add attachments
        if attachments:
            for file_path in attachments:
                self._add_attachment(message, file_path)
        
        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
        
        return {'raw': raw_message}
    
    def _add_attachment(self, message: MIMEMultipart, file_path: str) -> None:
        """
        Add file attachment to email message.
        
        Args:
            message: MIMEMultipart message object
            file_path: Path to file to attach
        """
        try:
            file_path = Path(file_path)
            
            if not file_path.exists():
                logger.warning(f"Attachment file not found: {file_path}")
                return
            
            # Determine content type
            content_type, encoding = mimetypes.guess_type(str(file_path))
            if content_type is None or encoding is not None:
                content_type = 'application/octet-stream'
            
            main_type, sub_type = content_type.split('/', 1)
            
            # Read file content
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # Create attachment
            attachment = MIMEApplication(file_data, _subtype=sub_type)
            attachment.add_header(
                'Content-Disposition', 
                'attachment', 
                filename=file_path.name
            )
            
            message.attach(attachment)
            logger.debug(f"Added attachment: {file_path.name} ({len(file_data)} bytes)")
            
        except Exception as e:
            logger.error(f"Failed to add attachment {file_path}: {e}")
            # Don't raise here - continue sending email without this attachment
    
    def get_quota_status(self) -> Dict[str, Any]:
        """
        Get current quota status without checking limits.
        
        Returns:
            Dict with quota information
        """
        today = date.today()
        
        try:
            with get_connection() as conn:
                quota_record = exec_query_fetchone(
                    conn,
                    "SELECT sent_count, daily_limit FROM send_quota WHERE date = :date",
                    date=today
                )
            
            if quota_record:
                sent_count = quota_record['sent_count']
                daily_limit = quota_record['daily_limit']
            else:
                sent_count = 0
                daily_limit = DEFAULT_DAILY_LIMIT
            
            return {
                'date': str(today),
                'sent_count': sent_count,
                'daily_limit': daily_limit,
                'remaining': daily_limit - sent_count,
                'usage_percent': round((sent_count / daily_limit) * 100, 1)
            }
            
        except Exception as e:
            logger.error(f"Failed to get quota status: {e}")
            return {
                'date': str(today),
                'sent_count': 0,
                'daily_limit': DEFAULT_DAILY_LIMIT,
                'remaining': DEFAULT_DAILY_LIMIT,
                'usage_percent': 0.0,
                'error': str(e)
            }
    
    def update_daily_limit(self, new_limit: int) -> bool:
        """
        Update daily email sending limit.
        
        Args:
            new_limit: New daily limit
            
        Returns:
            bool: True if update successful
        """
        today = date.today()
        
        try:
            with transaction() as conn:
                exec_query(
                    conn,
                    """
                    INSERT INTO send_quota (date, sent_count, daily_limit)
                    VALUES (:date, 0, :daily_limit)
                    ON CONFLICT (date) 
                    DO UPDATE SET 
                        daily_limit = :daily_limit,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    date=today,
                    daily_limit=new_limit
                )
            
            logger.info(f"Daily email limit updated to: {new_limit}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update daily limit: {e}")
            return False


# Global emailer instance
gmail_emailer = GmailEmailer()


# Convenience functions for easy import

def setup_gmail() -> bool:
    """Set up Gmail API authentication."""
    return gmail_emailer.setup_gmail()


def send_email(
    to: str,
    subject: str,
    body: str,
    attachments: Optional[List[str]] = None,
    from_name: Optional[str] = None
) -> Dict[str, Any]:
    """Send email with optional attachments."""
    return gmail_emailer.send_email(to, subject, body, attachments, from_name)


def get_quota_status() -> Dict[str, Any]:
    """Get current email quota status."""
    return gmail_emailer.get_quota_status()


def update_daily_limit(new_limit: int) -> bool:
    """Update daily email sending limit."""
    return gmail_emailer.update_daily_limit(new_limit)


def check_quota(required_count: int = 1) -> Dict[str, Any]:
    """Check if sending emails is within quota."""
    return gmail_emailer.check_quota(required_count)
