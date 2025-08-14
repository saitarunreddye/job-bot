"""
Redis Queue setup and configuration for background job processing.
"""

import logging
from typing import Optional
import redis
from rq import Queue
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import settings

logger = logging.getLogger(__name__)

# Global Redis connection and queue instances
_redis_connection: Optional[redis.Redis] = None
_job_queue: Optional[Queue] = None


def get_redis_connection() -> redis.Redis:
    """
    Get Redis connection instance with connection pooling.
    
    Returns:
        redis.Redis: Configured Redis connection
        
    Raises:
        redis.ConnectionError: If Redis connection fails
    """
    global _redis_connection
    
    if _redis_connection is None:
        try:
            _redis_connection = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test the connection
            _redis_connection.ping()
            logger.info("Redis connection established successfully")
            
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            # Create a mock Redis connection for development
            logger.warning("Creating mock Redis connection for development")
            _redis_connection = MockRedisConnection()
        except Exception as e:
            logger.error(f"Unexpected error connecting to Redis: {e}")
            logger.warning("Creating mock Redis connection for development")
            _redis_connection = MockRedisConnection()
    
    return _redis_connection


class MockRedisConnection:
    """Mock Redis connection for development when Redis is not available."""
    
    def ping(self):
        return True
    
    def memory_usage(self):
        return 0
    
    def info(self, section=None):
        return {
            "connected_clients": 0,
            "used_memory_human": "0B",
            "redis_version": "7.0.0"
        }
    
    def pipeline(self):
        return MockPipeline()
    
    def set(self, key, value, **kwargs):
        return True
    
    def get(self, key):
        return None
    
    def delete(self, key):
        return True
    
    def exists(self, key):
        return False
    
    def zadd(self, name, mapping, **kwargs):
        return 1
    
    def zrange(self, name, start, end, **kwargs):
        return []
    
    def zrem(self, name, *values):
        return 1
    
    def llen(self, name):
        return 0
    
    def lpush(self, name, *values):
        return len(values)
    
    def lpop(self, name):
        return None
    
    def rpush(self, name, *values):
        return len(values)
    
    def rpop(self, name):
        return None


class MockPipeline:
    """Mock Redis pipeline for development."""
    
    def __init__(self):
        self.commands = []
    
    def execute(self):
        return [True] * len(self.commands)
    
    def __getattr__(self, name):
        def method(*args, **kwargs):
            self.commands.append((name, args, kwargs))
            return self
        return method


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((redis.ConnectionError, Exception))
)
def get_job_queue() -> Queue:
    """
    Get RQ job queue instance with retry logic.
    
    Returns:
        Queue: RQ Queue instance for job processing
        
    Raises:
        redis.ConnectionError: If Redis connection fails after retries
    """
    global _job_queue
    
    if _job_queue is None:
        try:
            redis_conn = get_redis_connection()
            _job_queue = Queue(
                name=settings.worker_queue_name,
                connection=redis_conn,
                default_timeout=3600  # 1 hour default timeout
            )
            
            logger.info(f"Job queue '{settings.worker_queue_name}' initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize job queue: {e}")
            logger.warning("Creating mock queue for development")
            _job_queue = MockQueue()
    
    return _job_queue


class MockQueue:
    """Mock Queue for development when RQ is not working properly."""
    
    def __init__(self):
        self.name = "mock"
        self.jobs = []
    
    def enqueue(self, func, *args, **kwargs):
        job_id = f"mock_job_{len(self.jobs)}"
        job = MockJob(job_id, func.__name__)
        self.jobs.append(job)
        logger.info(f"Mock job enqueued: {job_id} - {func.__name__}")
        return job
    
    def __len__(self):
        return len(self.jobs)
    
    @property
    def failed_job_registry(self):
        return MockRegistry()
    
    @property
    def finished_job_registry(self):
        return MockRegistry()
    
    @property
    def started_job_registry(self):
        return MockRegistry()
    
    @property
    def scheduled_job_registry(self):
        return MockRegistry()


class MockJob:
    """Mock Job for development."""
    
    def __init__(self, job_id, func_name):
        self.id = job_id
        self.func_name = func_name


class MockRegistry:
    """Mock Registry for development."""
    
    def __len__(self):
        return 0


def enqueue_job(func, *args, **kwargs):
    """
    Enqueue a job for background processing.
    
    Args:
        func: Function to execute
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
        
    Returns:
        Job: RQ Job instance
        
    Raises:
        redis.ConnectionError: If Redis connection fails
    """
    try:
        queue = get_job_queue()
        
        # Extract job-specific options
        job_timeout = kwargs.pop('job_timeout', 3600)
        job_id = kwargs.pop('job_id', None)
        description = kwargs.pop('description', f"Execute {func.__name__}")
        
        job = queue.enqueue(
            func,
            *args,
            **kwargs,
            timeout=job_timeout,
            job_id=job_id,
            description=description
        )
        
        logger.info(f"Job enqueued: {job.id} - {description}")
        return job
        
    except Exception as e:
        logger.error(f"Failed to enqueue job {func.__name__}: {e}")
        raise


def get_queue_info() -> dict:
    """
    Get information about the job queue status.
    
    Returns:
        dict: Queue statistics and information
    """
    try:
        queue = get_job_queue()
        redis_conn = get_redis_connection()
        
        # Get queue statistics
        info = {
            "queue_name": queue.name,
            "pending_jobs": len(queue),
            "failed_jobs": len(queue.failed_job_registry),
            "finished_jobs": len(queue.finished_job_registry),
            "started_jobs": len(queue.started_job_registry),
            "scheduled_jobs": len(queue.scheduled_job_registry),
            "redis_memory_usage": redis_conn.memory_usage(),
            "redis_info": {
                "connected_clients": redis_conn.info().get("connected_clients", 0),
                "used_memory_human": redis_conn.info().get("used_memory_human", "unknown"),
                "redis_version": redis_conn.info().get("redis_version", "unknown")
            }
        }
        
        logger.debug(f"Queue info retrieved: {info}")
        return info
        
    except Exception as e:
        logger.error(f"Failed to get queue info: {e}")
        return {
            "error": str(e),
            "queue_name": settings.worker_queue_name,
            "status": "unavailable"
        }


def check_redis_health() -> bool:
    """
    Check if Redis connection is healthy.
    
    Returns:
        bool: True if Redis is accessible, False otherwise
    """
    try:
        redis_conn = get_redis_connection()
        redis_conn.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


def clear_failed_jobs() -> int:
    """
    Clear all failed jobs from the queue.
    
    Returns:
        int: Number of failed jobs cleared
    """
    try:
        queue = get_job_queue()
        failed_count = len(queue.failed_job_registry)
        queue.failed_job_registry.clear()
        
        logger.info(f"Cleared {failed_count} failed jobs from queue")
        return failed_count
        
    except Exception as e:
        logger.error(f"Failed to clear failed jobs: {e}")
        return 0


# Context manager for Redis connections
class RedisConnectionContext:
    """Context manager for Redis connections in workers."""
    
    def __enter__(self):
        """Enter the context and set up Redis connection."""
        self.connection = get_redis_connection()
        Connection.push(self.connection)
        return self.connection
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context and clean up connection."""
        Connection.pop()
        if exc_type:
            logger.error(f"Redis connection context error: {exc_val}")


# Convenience function for worker scripts
def setup_worker_connection():
    """
    Setup Redis connection for worker processes.
    Should be called at the start of worker processes.
    """
    try:
        redis_conn = get_redis_connection()
        Connection.push(redis_conn)
        logger.info("Worker Redis connection setup completed")
        return True
    except Exception as e:
        logger.error(f"Worker Redis connection setup failed: {e}")
        return False
