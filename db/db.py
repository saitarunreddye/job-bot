"""
Database utilities and connection management.
Uses SQLAlchemy Core for database operations.
"""

import logging
from typing import Any, Dict, Optional, Union
from contextlib import contextmanager
from uuid import UUID
from sqlalchemy import create_engine, text, Engine, Connection
from sqlalchemy.exc import SQLAlchemyError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config.settings import settings

logger = logging.getLogger(__name__)

# Global engine instance
_engine: Optional[Engine] = None


def convert_params_for_sqlite(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert parameters to be compatible with SQLite.
    Converts UUID objects to strings.
    
    Args:
        params: Dictionary of parameters
        
    Returns:
        Dict[str, Any]: Converted parameters
    """
    converted = {}
    for key, value in params.items():
        if isinstance(value, UUID):
            converted[key] = str(value)
        else:
            converted[key] = value
    return converted


def create_engine_instance() -> Engine:
    """
    Create and configure SQLAlchemy engine.
    
    Returns:
        Engine: Configured SQLAlchemy engine instance
    """
    global _engine
    
    if _engine is None:
        try:
            _engine = create_engine(
                settings.database_url,
                echo=settings.api_debug,  # Log SQL queries in debug mode
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,  # Verify connections before use
                pool_recycle=3600,  # Recycle connections after 1 hour
            )
            logger.info("Database engine created successfully")
        except Exception as e:
            logger.error(f"Failed to create database engine: {e}")
            raise
    
    return _engine


def get_engine() -> Engine:
    """
    Get the database engine instance.
    
    Returns:
        Engine: SQLAlchemy engine instance
    """
    return create_engine_instance()


@contextmanager
def get_connection():
    """
    Context manager for database connections.
    
    Yields:
        Connection: SQLAlchemy connection instance
        
    Example:
        with get_connection() as conn:
            result = exec_query(conn, "SELECT * FROM jobs")
    """
    engine = get_engine()
    connection = None
    
    try:
        connection = engine.connect()
        yield connection
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        if connection:
            connection.rollback()
        raise
    finally:
        if connection:
            connection.close()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(SQLAlchemyError),
)
def exec_query(
    connection: Connection,
    query: str,
    **params: Any
) -> Any:
    """
    Execute a SQL query with retry logic and parameter binding.
    
    Args:
        connection: SQLAlchemy connection instance
        query: SQL query string
        **params: Query parameters for binding
        
    Returns:
        Query result (varies by query type)
        
    Raises:
        SQLAlchemyError: If query execution fails after retries
        
    Example:
        with get_connection() as conn:
            result = exec_query(
                conn, 
                "SELECT * FROM jobs WHERE company = :company",
                company="TechCorp"
            )
    """
    try:
        # Convert parameters for SQLite compatibility
        converted_params = convert_params_for_sqlite(params)
        
        # Handle both string and TextClause objects
        query_str = str(query)
        logger.debug(f"Executing query: {query_str[:100]}...")
        logger.debug(f"Parameters: {converted_params}")
        
        # If query is already a TextClause, use it directly; otherwise wrap in text()
        if hasattr(query, 'text'):
            result = connection.execute(query, converted_params)
        else:
            result = connection.execute(text(query), converted_params)
        
        logger.debug("Query executed successfully")
        return result
        
    except SQLAlchemyError as e:
        logger.error(f"Query execution failed: {e}")
        logger.error(f"Query: {query}")
        logger.error(f"Parameters: {params}")
        raise


def exec_query_fetchall(
    connection: Connection,
    query: str,
    **params: Any
) -> list[Dict[str, Any]]:
    """
    Execute a SELECT query and return all results as dictionaries.
    
    Args:
        connection: SQLAlchemy connection instance
        query: SQL SELECT query string
        **params: Query parameters for binding
        
    Returns:
        List of dictionaries representing rows
        
    Example:
        with get_connection() as conn:
            jobs = exec_query_fetchall(
                conn,
                "SELECT * FROM jobs WHERE score >= :min_score",
                min_score=80
            )
    """
    result = exec_query(connection, query, **params)
    return [dict(row._mapping) for row in result.fetchall()]


def exec_query_fetchone(
    connection: Connection,
    query: str,
    **params: Any
) -> Optional[Dict[str, Any]]:
    """
    Execute a SELECT query and return the first result as a dictionary.
    
    Args:
        connection: SQLAlchemy connection instance
        query: SQL SELECT query string
        **params: Query parameters for binding
        
    Returns:
        Dictionary representing the row, or None if no results
        
    Example:
        with get_connection() as conn:
            job = exec_query_fetchone(
                conn,
                "SELECT * FROM jobs WHERE id = :job_id",
                job_id="123e4567-e89b-12d3-a456-426614174000"
            )
    """
    result = exec_query(connection, query, **params)
    row = result.fetchone()
    return dict(row._mapping) if row else None


def exec_query_scalar(
    connection: Connection,
    query: str,
    **params: Any
) -> Any:
    """
    Execute a query and return a single scalar value.
    
    Args:
        connection: SQLAlchemy connection instance
        query: SQL query string
        **params: Query parameters for binding
        
    Returns:
        Single scalar value
        
    Example:
        with get_connection() as conn:
            count = exec_query_scalar(
                conn,
                "SELECT COUNT(*) FROM jobs WHERE status = :status",
                status="active"
            )
    """
    result = exec_query(connection, query, **params)
    return result.scalar()


@contextmanager
def transaction():
    """
    Context manager for database transactions.
    
    Automatically commits on success, rolls back on exception.
    
    Example:
        with transaction() as conn:
            exec_query(conn, "INSERT INTO jobs (...) VALUES (...)")
            exec_query(conn, "UPDATE applications SET ...")
    """
    with get_connection() as connection:
        trans = connection.begin()
        try:
            yield connection
            trans.commit()
            logger.debug("Transaction committed successfully")
        except Exception as e:
            trans.rollback()
            logger.error(f"Transaction rolled back due to error: {e}")
            raise


def check_connection() -> bool:
    """
    Check if database connection is working.
    
    Returns:
        bool: True if connection is successful, False otherwise
    """
    try:
        with get_connection() as conn:
            exec_query_scalar(conn, "SELECT 1")
        logger.info("Database connection check successful")
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False


# Convenience function for the exec utility as requested
def exec(query: str, **params: Any) -> Any:
    """
    Convenience function to execute a query with automatic connection management.
    
    Args:
        query: SQL query string
        **params: Query parameters for binding
        
    Returns:
        Query result
        
    Example:
        result = exec("SELECT * FROM jobs WHERE company = :company", company="TechCorp")
    """
    with get_connection() as conn:
        return exec_query(conn, query, **params)
