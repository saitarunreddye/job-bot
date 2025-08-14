"""
Enhanced logging system with JSON formatting, job tracing, and event tracking.
Provides structured logging with database event recording and network retry decorators.
"""

import json
import logging
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, UTC
from functools import wraps
from typing import Any, Dict, Optional, Union, Callable
from uuid import UUID

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    after_log,
    retry_if_exception_type,
    RetryError
)

from db.db import get_connection, exec_query

# Job ID context variable for tracing
_job_context = {}


class JobBotJSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""
    
    def format(self, record):
        """Format log record as JSON."""
        log_entry = {
            'timestamp': datetime.now(UTC).isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add job_id if available in context
        job_id = get_current_job_id()
        if job_id:
            log_entry['job_id'] = str(job_id)
        
        # Add extra fields if present
        if hasattr(record, 'job_id'):
            log_entry['job_id'] = str(record.job_id)
        
        if hasattr(record, 'stage'):
            log_entry['stage'] = record.stage
            
        if hasattr(record, 'duration_ms'):
            log_entry['duration_ms'] = record.duration_ms
            
        if hasattr(record, 'context'):
            log_entry['context'] = record.context
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': ''.join(traceback.format_exception(*record.exc_info))
            }
        
        return json.dumps(log_entry, default=str)


class JobBotLogger:
    """Enhanced logger with job tracing and event recording."""
    
    def __init__(self, name: str):
        """
        Initialize JobBot logger.
        
        Args:
            name: Logger name (usually module name)
        """
        self.logger = logging.getLogger(name)
        self.name = name
        
        # Configure JSON formatter if not already configured
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(JobBotJSONFormatter())
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def _log_event(
        self,
        level: str,
        message: str,
        stage: Optional[str] = None,
        job_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None
    ):
        """
        Log event both to logger and events table.
        
        Args:
            level: Log level (info, warning, error, debug)
            message: Log message
            stage: Pipeline stage (ingest, score, tailor, apply, email)
            job_id: Associated job ID
            context: Additional structured data
            duration_ms: Operation duration in milliseconds
        """
        # Get job_id from context if not provided
        if not job_id:
            job_id = get_current_job_id()
        
        # Log to standard logger
        log_level = getattr(logging, level.upper())
        extra = {
            'stage': stage,
            'job_id': job_id,
            'context': context,
            'duration_ms': duration_ms
        }
        self.logger.log(log_level, message, extra=extra)
        
        # Log to events table (non-blocking)
        try:
            self._record_event(
                job_id=job_id,
                stage=stage or 'unknown',
                level=level,
                message=message,
                context=context,
                duration_ms=duration_ms
            )
        except Exception as e:
            # Don't let event recording failures break the application
            self.logger.warning(f"Failed to record event: {e}")
    
    def _record_event(
        self,
        job_id: Optional[UUID],
        stage: str,
        level: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None
    ):
        """Record event in database table."""
        try:
            with get_connection() as conn:
                exec_query(
                    conn,
                    """
                    INSERT INTO events (job_id, stage, level, message, context, source, duration_ms)
                    VALUES (:job_id, :stage, :level, :message, :context, :source, :duration_ms)
                    """,
                    job_id=job_id,
                    stage=stage,
                    level=level,
                    message=message,
                    context=json.dumps(context) if context else None,
                    source=self.name,
                    duration_ms=duration_ms
                )
        except Exception as e:
            # Silent failure - don't break application for logging issues
            pass
    
    def info(
        self,
        message: str,
        stage: Optional[str] = None,
        job_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None
    ):
        """Log info message."""
        self._log_event('info', message, stage, job_id, context, duration_ms)
    
    def warning(
        self,
        message: str,
        stage: Optional[str] = None,
        job_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None
    ):
        """Log warning message."""
        self._log_event('warning', message, stage, job_id, context, duration_ms)
    
    def error(
        self,
        message: str,
        stage: Optional[str] = None,
        job_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        exc_info: bool = False
    ):
        """Log error message."""
        if exc_info:
            # Include exception information
            import sys
            exc_type, exc_value, exc_tb = sys.exc_info()
            if exc_type:
                if not context:
                    context = {}
                context['exception'] = {
                    'type': exc_type.__name__,
                    'message': str(exc_value)
                }
        
        self._log_event('error', message, stage, job_id, context, duration_ms)
    
    def debug(
        self,
        message: str,
        stage: Optional[str] = None,
        job_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None
    ):
        """Log debug message."""
        self._log_event('debug', message, stage, job_id, context, duration_ms)


# Job context management
def set_job_context(job_id: UUID, stage: Optional[str] = None):
    """Set current job context for tracing."""
    import threading
    thread_id = threading.get_ident()
    _job_context[thread_id] = {
        'job_id': job_id,
        'stage': stage
    }


def get_current_job_id() -> Optional[UUID]:
    """Get current job ID from context."""
    import threading
    thread_id = threading.get_ident()
    context = _job_context.get(thread_id, {})
    return context.get('job_id')


def get_current_stage() -> Optional[str]:
    """Get current stage from context."""
    import threading
    thread_id = threading.get_ident()
    context = _job_context.get(thread_id, {})
    return context.get('stage')


def clear_job_context():
    """Clear current job context."""
    import threading
    thread_id = threading.get_ident()
    _job_context.pop(thread_id, None)


@contextmanager
def job_context(job_id: UUID, stage: Optional[str] = None):
    """Context manager for job tracing."""
    set_job_context(job_id, stage)
    try:
        yield
    finally:
        clear_job_context()


# Network retry decorators
def network_retry(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    exponential_base: float = 2,
    exceptions: tuple = (httpx.RequestError, httpx.HTTPStatusError, ConnectionError, TimeoutError)
):
    """
    Decorator for network operations with retry logic.
    
    Args:
        max_attempts: Maximum number of retry attempts
        min_wait: Minimum wait time between retries
        max_wait: Maximum wait time between retries
        exponential_base: Base for exponential backoff
        exceptions: Exception types to retry on
    """
    def decorator(func):
        logger = get_logger(func.__module__)
        
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=min_wait, min=min_wait, max=max_wait, exp_base=exponential_base),
            retry=retry_if_exception_type(exceptions),
            before_sleep=before_sleep_log(logger.logger, logging.WARNING),
            after=after_log(logger.logger, logging.INFO)
        )
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            job_id = get_current_job_id()
            stage = get_current_stage() or 'network'
            
            try:
                result = func(*args, **kwargs)
                duration_ms = int((time.time() - start_time) * 1000)
                
                logger.info(
                    f"Network operation succeeded: {func.__name__}",
                    stage=stage,
                    job_id=job_id,
                    duration_ms=duration_ms,
                    context={
                        'function': func.__name__,
                        'module': func.__module__,
                        'success': True
                    }
                )
                
                return result
                
            except RetryError as e:
                duration_ms = int((time.time() - start_time) * 1000)
                
                logger.error(
                    f"Network operation failed after {max_attempts} attempts: {func.__name__}",
                    stage=stage,
                    job_id=job_id,
                    duration_ms=duration_ms,
                    context={
                        'function': func.__name__,
                        'module': func.__module__,
                        'max_attempts': max_attempts,
                        'final_exception': str(e.last_attempt.exception()),
                        'success': False
                    },
                    exc_info=True
                )
                raise
            
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                
                logger.error(
                    f"Network operation failed: {func.__name__}",
                    stage=stage,
                    job_id=job_id,
                    duration_ms=duration_ms,
                    context={
                        'function': func.__name__,
                        'module': func.__module__,
                        'exception': str(e),
                        'success': False
                    },
                    exc_info=True
                )
                raise
        
        return wrapper
    return decorator


# HTTP client with retry
class HTTPClient:
    """HTTP client with built-in retry logic and logging."""
    
    def __init__(self, timeout: float = 30.0, max_retries: int = 3):
        """
        Initialize HTTP client.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries
        """
        self.client = httpx.AsyncClient(timeout=timeout)
        self.max_retries = max_retries
        self.logger = get_logger(__name__)
    
    @network_retry(max_attempts=3)
    async def get(self, url: str, **kwargs) -> httpx.Response:
        """GET request with retry logic."""
        job_id = get_current_job_id()
        stage = get_current_stage() or 'http'
        
        self.logger.info(
            f"HTTP GET: {url}",
            stage=stage,
            job_id=job_id,
            context={'url': url, 'method': 'GET'}
        )
        
        response = await self.client.get(url, **kwargs)
        response.raise_for_status()
        return response
    
    @network_retry(max_attempts=3)
    async def post(self, url: str, **kwargs) -> httpx.Response:
        """POST request with retry logic."""
        job_id = get_current_job_id()
        stage = get_current_stage() or 'http'
        
        self.logger.info(
            f"HTTP POST: {url}",
            stage=stage,
            job_id=job_id,
            context={'url': url, 'method': 'POST'}
        )
        
        response = await self.client.post(url, **kwargs)
        response.raise_for_status()
        return response
    
    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


# Sync HTTP client
def get_sync_http_client() -> httpx.Client:
    """Get synchronous HTTP client with retry logic."""
    return httpx.Client(timeout=30.0)


@network_retry(max_attempts=3)
def http_get_sync(url: str, client: Optional[httpx.Client] = None, **kwargs) -> httpx.Response:
    """Synchronous GET request with retry logic."""
    job_id = get_current_job_id()
    stage = get_current_stage() or 'http'
    logger = get_logger(__name__)
    
    logger.info(
        f"HTTP GET (sync): {url}",
        stage=stage,
        job_id=job_id,
        context={'url': url, 'method': 'GET'}
    )
    
    if client is None:
        client = get_sync_http_client()
    
    response = client.get(url, **kwargs)
    response.raise_for_status()
    return response


@network_retry(max_attempts=3)
def http_post_sync(url: str, client: Optional[httpx.Client] = None, **kwargs) -> httpx.Response:
    """Synchronous POST request with retry logic."""
    job_id = get_current_job_id()
    stage = get_current_stage() or 'http'
    logger = get_logger(__name__)
    
    logger.info(
        f"HTTP POST (sync): {url}",
        stage=stage,
        job_id=job_id,
        context={'url': url, 'method': 'POST'}
    )
    
    if client is None:
        client = get_sync_http_client()
    
    response = client.post(url, **kwargs)
    response.raise_for_status()
    return response


# Performance monitoring decorator
def monitor_performance(stage: Optional[str] = None):
    """
    Decorator to monitor function performance.
    
    Args:
        stage: Pipeline stage name
    """
    def decorator(func):
        logger = get_logger(func.__module__)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            job_id = get_current_job_id()
            func_stage = stage or func.__name__
            
            try:
                result = func(*args, **kwargs)
                duration_ms = int((time.time() - start_time) * 1000)
                
                logger.info(
                    f"Function completed: {func.__name__}",
                    stage=func_stage,
                    job_id=job_id,
                    duration_ms=duration_ms,
                    context={
                        'function': func.__name__,
                        'module': func.__module__,
                        'success': True
                    }
                )
                
                return result
                
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                
                logger.error(
                    f"Function failed: {func.__name__}",
                    stage=func_stage,
                    job_id=job_id,
                    duration_ms=duration_ms,
                    context={
                        'function': func.__name__,
                        'module': func.__module__,
                        'exception': str(e),
                        'success': False
                    },
                    exc_info=True
                )
                raise
        
        return wrapper
    return decorator


# Logger factory
def get_logger(name: str) -> JobBotLogger:
    """
    Get or create a JobBot logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        JobBotLogger: Configured logger instance
    """
    return JobBotLogger(name)


# Event query utilities
def get_events_for_job(job_id: UUID, limit: int = 100) -> list:
    """Get events for a specific job."""
    try:
        with get_connection() as conn:
            events = exec_query(
                conn,
                """
                SELECT id, stage, level, message, context, source, duration_ms, created_at
                FROM events 
                WHERE job_id = :job_id 
                ORDER BY created_at DESC 
                LIMIT :limit
                """,
                job_id=job_id,
                limit=limit
            ).fetchall()
        
        return [dict(event) for event in events]
    except Exception:
        return []


def get_events_by_stage(stage: str, level: Optional[str] = None, limit: int = 100) -> list:
    """Get events by pipeline stage."""
    try:
        with get_connection() as conn:
            if level:
                events = exec_query(
                    conn,
                    """
                    SELECT id, job_id, stage, level, message, context, source, duration_ms, created_at
                    FROM events 
                    WHERE stage = :stage AND level = :level
                    ORDER BY created_at DESC 
                    LIMIT :limit
                    """,
                    stage=stage,
                    level=level,
                    limit=limit
                ).fetchall()
            else:
                events = exec_query(
                    conn,
                    """
                    SELECT id, job_id, stage, level, message, context, source, duration_ms, created_at
                    FROM events 
                    WHERE stage = :stage
                    ORDER BY created_at DESC 
                    LIMIT :limit
                    """,
                    stage=stage,
                    limit=limit
                ).fetchall()
        
        return [dict(event) for event in events]
    except Exception:
        return []


def get_error_events(limit: int = 50) -> list:
    """Get recent error events."""
    try:
        with get_connection() as conn:
            events = exec_query(
                conn,
                """
                SELECT id, job_id, stage, level, message, context, source, duration_ms, created_at
                FROM events 
                WHERE level = 'error'
                ORDER BY created_at DESC 
                LIMIT :limit
                """,
                limit=limit
            ).fetchall()
        
        return [dict(event) for event in events]
    except Exception:
        return []
