"""
Test utilities for Job Bot testing.
Provides database setup and helper functions.
"""

import sqlalchemy as sa
from sqlalchemy import text
from pathlib import Path


def create_test_database(database_url: str):
    """
    Create test database with schema.
    
    Args:
        database_url: SQLite database URL
    """
    # Create engine
    engine = sa.create_engine(database_url)
    
    # Create SQLite-specific schema (simplified)
    sqlite_schema = """
    -- JOBS
    CREATE TABLE IF NOT EXISTS jobs(
      job_id INTEGER PRIMARY KEY,
      title TEXT, company TEXT, location TEXT,
      source TEXT, url TEXT UNIQUE,
      jd_text TEXT, skills TEXT,
      score INTEGER DEFAULT 0,
      status TEXT DEFAULT 'new',
      created_at TIMESTAMP
    );

    -- APPLICATIONS
    CREATE TABLE IF NOT EXISTS applications(
      app_id INTEGER PRIMARY KEY,
      job_id INTEGER REFERENCES jobs(job_id),
      resume_path TEXT,
      portal TEXT,
      tracking_url TEXT,
      status TEXT DEFAULT 'prepared',
      submitted_at TIMESTAMP
    );

    -- CONTACTS (email unique)
    CREATE TABLE IF NOT EXISTS contacts(
      contact_id INTEGER PRIMARY KEY,
      name TEXT, role TEXT, company TEXT,
      email TEXT UNIQUE,
      linkedin_url TEXT,
      verified BOOLEAN DEFAULT 0,
      last_seen TIMESTAMP
    );

    -- OUTREACH_ENHANCED (NOTE: message_content column)
    CREATE TABLE IF NOT EXISTS outreach_enhanced(
      outreach_id INTEGER PRIMARY KEY,
      job_id INTEGER REFERENCES jobs(job_id),
      contact_id INTEGER REFERENCES contacts(contact_id),
      channel TEXT,              -- 'email' | 'linkedin'
      subject TEXT,
      message_content TEXT,      -- required by tests
      scheduled_at TIMESTAMP,
      sent_at TIMESTAMP,
      reply_status TEXT,
      attempt_count INTEGER DEFAULT 0
    );

    -- optional: events table for logging
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY,
      job_id INTEGER,
      stage TEXT, level TEXT,
      message TEXT,
      created_at TIMESTAMP
    );
    """
    
    # Execute schema
    with engine.connect() as conn:
        # Execute each CREATE TABLE statement individually
        create_jobs = """
        CREATE TABLE IF NOT EXISTS jobs(
          job_id INTEGER PRIMARY KEY,
          title TEXT, company TEXT, location TEXT,
          source TEXT, url TEXT UNIQUE,
          jd_text TEXT, skills TEXT,
          score INTEGER DEFAULT 0,
          status TEXT DEFAULT 'new',
          created_at TIMESTAMP
        )
        """
        
        create_applications = """
        CREATE TABLE IF NOT EXISTS applications(
          app_id INTEGER PRIMARY KEY,
          job_id INTEGER REFERENCES jobs(job_id),
          resume_path TEXT,
          portal TEXT,
          tracking_url TEXT,
          status TEXT DEFAULT 'prepared',
          submitted_at TIMESTAMP
        )
        """
        
        create_contacts = """
        CREATE TABLE IF NOT EXISTS contacts(
          contact_id INTEGER PRIMARY KEY,
          name TEXT, role TEXT, company TEXT,
          email TEXT UNIQUE,
          linkedin_url TEXT,
          verified BOOLEAN DEFAULT 0,
          last_seen TIMESTAMP
        )
        """
        
        create_outreach = """
        CREATE TABLE IF NOT EXISTS outreach_enhanced(
          outreach_id INTEGER PRIMARY KEY,
          job_id INTEGER REFERENCES jobs(job_id),
          contact_id INTEGER REFERENCES contacts(contact_id),
          channel TEXT,
          subject TEXT,
          message_content TEXT,
          scheduled_at TIMESTAMP,
          sent_at TIMESTAMP,
          reply_status TEXT,
          attempt_count INTEGER DEFAULT 0
        )
        """
        
        # Execute each statement
        conn.execute(text(create_jobs))
        conn.execute(text(create_applications))
        conn.execute(text(create_contacts))
        conn.execute(text(create_outreach))
        
        # Create compatibility views
        conn.execute(text("DROP VIEW IF EXISTS jobs_view"))
        conn.execute(text("""
            CREATE VIEW jobs_view AS
            SELECT
              job_id            AS id,
              title,
              company,
              location,
              source,
              url,
              jd_text           AS description,
              skills            AS match_reasons,
              score,
              status,
              created_at
            FROM jobs
        """))
        
        conn.execute(text("DROP VIEW IF EXISTS applications_view"))
        conn.execute(text("""
            CREATE VIEW applications_view AS
            SELECT
              app_id,
              job_id,
              resume_path,
              portal,
              tracking_url,
              status,
              submitted_at,
              NULL AS cover_letter_version,
              NULL AS notes
            FROM applications
        """))
        
        conn.execute(text("DROP VIEW IF EXISTS contacts_view"))
        conn.execute(text("""
            CREATE VIEW contacts_view AS
            SELECT
              contact_id AS id,
              name,
              role,
              company,
              email,
              linkedin_url,
              verified,
              last_seen
            FROM contacts
        """))
        
        conn.execute(text("DROP VIEW IF EXISTS outreach_view"))
        conn.execute(text("""
            CREATE VIEW outreach_view AS
            SELECT
              outreach_id,
              job_id,
              contact_id,
              channel,
              subject,
              message_content,
              scheduled_at,
              sent_at,
              reply_status,
              attempt_count
            FROM outreach_enhanced
        """))
        
        conn.commit()


def adapt_schema_for_sqlite(postgres_sql: str) -> str:
    """
    Adapt PostgreSQL schema for SQLite.
    
    Args:
        postgres_sql: PostgreSQL schema SQL
        
    Returns:
        str: Adapted SQL for SQLite
    """
    # Replace PostgreSQL-specific syntax with SQLite equivalents
    sqlite_sql = postgres_sql
    
    # Remove PostgreSQL extensions
    sqlite_sql = sqlite_sql.replace('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";', '')
    
    # Replace UUID generation with simple text UUIDs for testing
    sqlite_sql = sqlite_sql.replace('uuid_generate_v4()', "'test-uuid-' || hex(randomblob(16))")
    sqlite_sql = sqlite_sql.replace('UUID PRIMARY KEY DEFAULT uuid_generate_v4()', 'TEXT PRIMARY KEY DEFAULT (\'test-uuid-\' || hex(randomblob(16)))')
    sqlite_sql = sqlite_sql.replace('UUID PRIMARY KEY', 'TEXT PRIMARY KEY')
    sqlite_sql = sqlite_sql.replace('UUID NOT NULL', 'TEXT NOT NULL')
    sqlite_sql = sqlite_sql.replace('UUID REFERENCES', 'TEXT REFERENCES')
    sqlite_sql = sqlite_sql.replace('UUID', 'TEXT')
    
    # Replace TIMESTAMP WITH TIME ZONE with DATETIME
    sqlite_sql = sqlite_sql.replace('TIMESTAMP WITH TIME ZONE', 'DATETIME')
    
    # Replace CURRENT_TIMESTAMP with datetime('now')
    sqlite_sql = sqlite_sql.replace('DEFAULT CURRENT_TIMESTAMP', "DEFAULT (datetime('now'))")
    
    # Replace TEXT[] arrays with JSON (SQLite doesn't have arrays)
    sqlite_sql = sqlite_sql.replace('TEXT[]', 'TEXT')
    sqlite_sql = sqlite_sql.replace('skills TEXT,', 'skills TEXT, -- JSON array')
    sqlite_sql = sqlite_sql.replace('match_reasons TEXT,', 'match_reasons TEXT, -- JSON array')
    
    # Replace JSONB with TEXT (SQLite doesn't have JSONB)
    sqlite_sql = sqlite_sql.replace('JSONB', 'TEXT')
    
    # Remove PostgreSQL-specific function syntax
    lines = sqlite_sql.split('\n')
    filtered_lines = []
    skip_block = False
    trigger_block = False
    
    for line in lines:
        # Skip PostgreSQL function definitions
        if 'CREATE OR REPLACE FUNCTION' in line:
            skip_block = True
            continue
        elif skip_block and line.strip().endswith("$$ language 'plpgsql';"):
            skip_block = False
            continue
        elif skip_block:
            continue
        
        # Skip PostgreSQL trigger syntax
        elif 'CREATE TRIGGER' in line and 'EXECUTE FUNCTION' in line:
            trigger_block = True
            continue
        elif trigger_block and ';' in line:
            trigger_block = False
            continue
        elif trigger_block:
            continue
        
        # Skip index creation on non-existent tables (will fail in setup)
        elif 'CREATE INDEX' in line:
            # Skip for now - we'll create these after tables exist
            continue
        
        elif not skip_block and not trigger_block:
            filtered_lines.append(line)
    
    sqlite_sql = '\n'.join(filtered_lines)
    
    # Clean up extra whitespace
    sqlite_sql = '\n'.join(line for line in sqlite_sql.split('\n') if line.strip())
    
    return sqlite_sql


def cleanup_test_database(database_url: str):
    """
    Clean up test database.
    
    Args:
        database_url: Database URL to clean up
    """
    try:
        engine = sa.create_engine(database_url)
        with engine.connect() as conn:
            # Drop all tables in reverse dependency order
            tables = [
                'events',
                'outreach_enhanced',
                'applications', 
                'contacts', 
                'jobs'
            ]
            for table in tables:
                try:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                except Exception:
                    pass
            conn.commit()
    except Exception:
        pass


def insert_test_job(conn, job_data: dict) -> str:
    """
    Insert a test job and return its ID.
    
    Args:
        conn: Database connection
        job_data: Job data dictionary
        
    Returns:
        str: Job ID
    """
    from uuid import uuid4
    job_id = str(uuid4())
    
    result = conn.execute(text("""
        INSERT INTO jobs (id, title, company, location, url, description, requirements, source, status)
        VALUES (:id, :title, :company, :location, :url, :description, :requirements, :source, :status)
    """), {
        'id': job_id,
        **job_data
    })
    
    conn.commit()
    return job_id


def get_job_by_url(conn, url: str) -> dict:
    """
    Get job by URL.
    
    Args:
        conn: Database connection
        url: Job URL
        
    Returns:
        dict: Job data or None
    """
    result = conn.execute(text("""
        SELECT * FROM jobs WHERE url = :url
    """), {'url': url})
    
    row = result.fetchone()
    return dict(row) if row else None


def count_jobs(conn) -> int:
    """
    Count total jobs in database.
    
    Args:
        conn: Database connection
        
    Returns:
        int: Job count
    """
    result = conn.execute(text("SELECT COUNT(*) FROM jobs"))
    return result.scalar()


def create_test_skills_data():
    """Create test data for skill extraction."""
    return {
        'skill_bank': {
            'python', 'javascript', 'react', 'angular', 'vue', 'node.js', 'express',
            'sql', 'postgresql', 'mysql', 'mongodb', 'redis', 'docker', 'kubernetes',
            'aws', 'azure', 'gcp', 'jenkins', 'git', 'html', 'css', 'typescript',
            'java', 'c++', 'go', 'rust', 'scala', 'kotlin', 'swift', 'php',
            'django', 'flask', 'fastapi', 'spring', 'hibernate', 'rest', 'graphql',
            'microservices', 'api', 'json', 'xml', 'yaml', 'linux', 'bash',
            'testing', 'junit', 'pytest', 'jest', 'selenium', 'ci/cd', 'devops'
        },
        'synonym_map': {
            'js': 'javascript',
            'ts': 'typescript', 
            'node': 'node.js',
            'postgres': 'postgresql',
            'k8s': 'kubernetes',
            'eks': 'aws',
            'ec2': 'aws',
            's3': 'aws'
        }
    }
