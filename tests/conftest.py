import os
import pytest
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, text

# Set environment variables before importing any modules
os.environ["JOBBOT_DISABLE_SEED"] = "1"

from tests.test_utils import create_test_database


@pytest.fixture(scope="session")
def test_database_url(tmp_path_factory):
    """Create a temporary database URL for testing."""
    dbfile = tmp_path_factory.mktemp("db") / "test.sqlite"
    return f"sqlite:///{dbfile}"


@pytest.fixture(scope="session")
def test_database(test_database_url):
    """Create and set up the test database."""
    # Set environment variables
    os.environ["DATABASE_URL"] = test_database_url
    
    # Create the database
    create_test_database(test_database_url)
    
    yield test_database_url


@pytest.fixture(autouse=True)
def override_database_url(test_database):
    """Override the database URL for all tests."""
    # Clear the global engine to force recreation
    from db import db as dbmod
    if hasattr(dbmod, '_engine'):
        dbmod._engine = None
    
    original_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_database
    
    yield
    
    if original_url:
        os.environ["DATABASE_URL"] = original_url
    else:
        os.environ.pop("DATABASE_URL", None)


@pytest.fixture(autouse=True)
def clean_database(test_database):
    """Clean the database before each test."""
    engine = create_engine(test_database)
    
    with engine.connect() as conn:
        # Clear data from tables in reverse dependency order
        tables = [
            'events',
            'outreach_enhanced', 
            'applications',
            'contacts',
            'jobs'
        ]
        for table in tables:
            try:
                conn.execute(text(f"DELETE FROM {table}"))
            except Exception:
                pass
        conn.commit()


@pytest.fixture
def sample_job_data():
    """Sample job data for testing."""
    return {
        'title': 'Senior Software Engineer',
        'company': 'TechCorp Inc',
        'location': 'San Francisco, CA',
        'url': 'https://example.com/jobs/senior-engineer',
        'description': 'We are looking for a senior software engineer with Python and React experience. Must have 5+ years of experience with web development.',
        'requirements': 'Requirements: Python, React, JavaScript, SQL, Docker, AWS. Experience with microservices and REST APIs required.',
        'source': 'Greenhouse',
        'status': 'active'
    }

@pytest.fixture  
def sample_job_data_2():
    """Second sample job for testing duplicates."""
    return {
        'title': 'Frontend Developer',
        'company': 'WebCorp',
        'location': 'Austin, TX', 
        'url': 'https://example.com/jobs/frontend-dev',
        'description': 'Frontend developer position requiring React, TypeScript, and CSS skills.',
        'requirements': 'React, TypeScript, CSS, HTML, JavaScript, Jest',
        'source': 'Lever',
        'status': 'active'
    }

@pytest.fixture
def temp_artifacts_dir():
    """Temporary directory for artifacts during testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Override ARTIFACT_DIR setting
        original_dir = os.environ.get('ARTIFACT_DIR')
        os.environ['ARTIFACT_DIR'] = temp_dir
        
        yield Path(temp_dir)
        
        # Restore original
        if original_dir:
            os.environ['ARTIFACT_DIR'] = original_dir
        else:
            os.environ.pop('ARTIFACT_DIR', None)
