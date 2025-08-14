#!/usr/bin/env python3
"""
Database initialization script.
Executes schema.sql to create tables and initial setup.
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


def read_schema_file() -> str:
    """
    Read the schema.sql file content.
    
    Returns:
        str: SQL schema content
        
    Raises:
        FileNotFoundError: If schema.sql file is not found
    """
    schema_path = project_root / "db" / "schema.sql"
    
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    
    logger.info(f"Reading schema from: {schema_path}")
    
    with open(schema_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    logger.info(f"Schema file read successfully ({len(content)} characters)")
    return content


def execute_schema_sql(schema_content: str) -> None:
    """
    Execute the schema SQL content against the database.
    
    Args:
        schema_content: SQL schema content to execute
        
    Raises:
        Exception: If schema execution fails
    """
    logger.info("Starting schema execution...")
    
    try:
        with get_connection() as conn:
            # Split schema into individual statements
            # Handle potential issues with semicolons in function definitions
            statements = []
            current_statement = ""
            in_function = False
            
            for line in schema_content.split('\n'):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('--'):
                    continue
                
                current_statement += line + '\n'
                
                # Track if we're inside a function definition
                if 'CREATE OR REPLACE FUNCTION' in line.upper():
                    in_function = True
                elif in_function and line.endswith("language 'plpgsql';"):
                    in_function = False
                    statements.append(current_statement.strip())
                    current_statement = ""
                elif not in_function and line.endswith(';'):
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
                        logger.debug(f"Executing statement {i}: {statement[:100]}...")
                        exec_query(conn, statement)
                        logger.debug(f"Statement {i} executed successfully")
                    except Exception as e:
                        logger.error(f"Failed to execute statement {i}: {e}")
                        logger.error(f"Statement content: {statement}")
                        raise
            
            # Commit the transaction
            conn.commit()
            logger.info("Schema execution completed successfully")
            
    except Exception as e:
        logger.error(f"Schema execution failed: {e}")
        raise


def verify_tables_created() -> bool:
    """
    Verify that the expected tables were created.
    
    Returns:
        bool: True if all expected tables exist
    """
    expected_tables = ['jobs', 'applications', 'contacts', 'outreach']
    
    logger.info("Verifying table creation...")
    
    try:
        with get_connection() as conn:
            for table in expected_tables:
                result = exec_query(
                    conn,
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = :table_name
                    )
                    """,
                    table_name=table
                )
                
                exists = result.scalar()
                if exists:
                    logger.info(f"✓ Table '{table}' created successfully")
                else:
                    logger.error(f"✗ Table '{table}' was not created")
                    return False
        
        logger.info("All tables verified successfully")
        return True
        
    except Exception as e:
        logger.error(f"Table verification failed: {e}")
        return False


def main():
    """Main initialization function."""
    logger.info("=" * 60)
    logger.info("Job Bot Database Initialization")
    logger.info("=" * 60)
    logger.info(f"Database URL: {settings.database_url}")
    
    try:
        # Check database connection
        logger.info("Checking database connection...")
        if not check_connection():
            logger.error("Database connection failed")
            sys.exit(1)
        logger.info("Database connection successful")
        
        # Read schema file
        schema_content = read_schema_file()
        
        # Execute schema
        execute_schema_sql(schema_content)
        
        # Verify tables were created
        if verify_tables_created():
            logger.info("Database initialization completed successfully!")
        else:
            logger.error("Database initialization completed with errors")
            sys.exit(1)
            
    except FileNotFoundError as e:
        logger.error(f"Schema file error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
