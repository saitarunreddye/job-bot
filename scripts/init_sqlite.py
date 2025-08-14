#!/usr/bin/env python3
"""
SQLite Database initialization script.
Creates tables for Job Bot application.
"""

import sys
import os
import logging
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.db import get_connection, exec_query, check_connection
from config.settings import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def read_sqlite_schema() -> str:
    """
    Read the SQLite schema file content.
    
    Returns:
        str: SQL schema content
        
    Raises:
        FileNotFoundError: If schema file is not found
    """
    schema_path = project_root / "db" / "schema_sqlite.sql"
    
    if not schema_path.exists():
        raise FileNotFoundError(f"SQLite schema file not found: {schema_path}")
    
    logger.info(f"Reading SQLite schema from: {schema_path}")
    
    with open(schema_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    logger.info(f"Schema file read successfully ({len(content)} characters)")
    return content


def execute_schema_sql(schema_content: str) -> None:
    """
    Execute the schema SQL content against the SQLite database.
    
    Args:
        schema_content: SQL schema content to execute
        
    Raises:
        Exception: If schema execution fails
    """
    logger.info("Starting SQLite schema execution...")
    
    try:
        with get_connection() as conn:
            # Split schema into individual statements
            statements = []
            current_statement = ""
            
            for line in schema_content.split('\n'):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('--'):
                    continue
                
                current_statement += line + '\n'
                
                # End statement on semicolon
                if line.endswith(';'):
                    statements.append(current_statement.strip())
                    current_statement = ""
            
            # Add any remaining statement
            if current_statement.strip():
                statements.append(current_statement.strip())
            
            logger.info(f"Executing {len(statements)} SQL statements...")
            
            # Execute each statement
            for i, statement in enumerate(statements, 1):
                if statement:
                    try:
                        exec_query(conn, statement)
                        logger.debug(f"Executed statement {i}/{len(statements)}")
                    except Exception as e:
                        logger.error(f"Failed to execute statement {i}: {e}")
                        logger.error(f"Statement content: {statement}")
                        raise
            
            logger.info("All SQL statements executed successfully")
            
    except Exception as e:
        logger.error(f"Schema execution failed: {e}")
        raise


def verify_tables_created() -> bool:
    """
    Verify that all required tables were created.
    
    Returns:
        bool: True if all tables exist, False otherwise
    """
    logger.info("Verifying tables were created...")
    
    required_tables = [
        'jobs', 'applications', 'contacts', 'outreach',
        'do_not_contact', 'email_rate_limits', 'outreach_enhanced', 'followup_schedule'
    ]
    
    try:
        with get_connection() as conn:
            for table in required_tables:
                result = exec_query(conn, f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                if not result.fetchone():
                    logger.error(f"Table '{table}' was not created")
                    return False
                logger.debug(f"✓ Table '{table}' exists")
            
            logger.info("All required tables verified successfully")
            return True
            
    except Exception as e:
        logger.error(f"Table verification failed: {e}")
        return False


def main():
    """
    Main function to initialize the SQLite database.
    """
    logger.info("=" * 60)
    logger.info("Job Bot SQLite Database Initialization")
    logger.info("=" * 60)
    
    logger.info(f"Database URL: {settings.database_url}")
    
    # Check database connection
    logger.info("Checking database connection...")
    if not check_connection():
        logger.error("Database connection failed")
        return False
    
    logger.info("Database connection successful")
    
    try:
        # Read and execute schema
        schema_content = read_sqlite_schema()
        execute_schema_sql(schema_content)
        
        # Verify tables were created
        if not verify_tables_created():
            logger.error("Database initialization failed: Tables not created")
            return False
        
        logger.info("=" * 60)
        logger.info("✅ SQLite Database initialization completed successfully!")
        logger.info("=" * 60)
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
