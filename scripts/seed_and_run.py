#!/usr/bin/env python3
"""
Seed database with sample jobs and demonstrate the Job Bot pipeline.
Creates sample jobs, scores them, and generates tailored assets.
"""

import os
import sys
import json
import logging
from pathlib import Path
from uuid import UUID

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from apps.worker.dao import insert_job, list_jobs, get_job
from apps.worker.scorer import score_job_from_description, update_job_with_score
from apps.worker.tailor import build_tailored_assets
from apps.worker.worker import score_all_jobs
from config.settings import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_sample_jobs():
    """Create sample jobs for different tech stacks."""
    
    sample_jobs = [
        {
            'title': 'Senior Python Developer',
            'company': 'TechCorp Inc',
            'url': 'https://techcorp.com/jobs/senior-python-dev',
            'location': 'San Francisco, CA',
            'job_type': 'full-time',
            'experience_level': 'senior',
            'salary_min': 120000,
            'salary_max': 160000,
            'currency': 'USD',
            'description': '''
            We are seeking a Senior Python Developer to join our growing engineering team. 
            You will be responsible for developing scalable web applications using modern Python frameworks.
            
            Key Responsibilities:
            - Design and implement RESTful APIs using FastAPI or Django
            - Work with PostgreSQL databases and optimize query performance
            - Collaborate with frontend teams using React and JavaScript
            - Deploy applications using Docker and Kubernetes on AWS
            - Write comprehensive tests and maintain high code quality
            ''',
            'requirements': '''
            Required Skills:
            - 5+ years of Python development experience
            - Strong experience with Django or FastAPI frameworks
            - Proficiency with PostgreSQL and SQL optimization
            - Experience with Docker containerization
            - Knowledge of AWS services (EC2, RDS, S3)
            - Familiarity with React and JavaScript for API integration
            - Experience with Git version control and CI/CD pipelines
            
            Preferred Skills:
            - Experience with Kubernetes orchestration
            - Knowledge of Redis for caching
            - Testing frameworks like pytest
            - Agile development methodologies
            ''',
            'benefits': 'Health insurance, 401k matching, unlimited PTO, remote work options',
            'remote_allowed': True,
            'source': 'seed_script',
            'status': 'active'
        },
        {
            'title': 'ServiceNow Developer',
            'company': 'Enterprise Solutions LLC',
            'url': 'https://enterprise-solutions.com/jobs/servicenow-dev',
            'location': 'Chicago, IL',
            'job_type': 'full-time',
            'experience_level': 'mid',
            'salary_min': 85000,
            'salary_max': 110000,
            'currency': 'USD',
            'description': '''
            Join our IT Services team as a ServiceNow Developer! You'll be responsible for 
            developing and maintaining ServiceNow applications and workflows for our enterprise clients.
            
            Key Responsibilities:
            - Develop custom ServiceNow applications and workflows
            - Configure ITSM, ITOM, and HRSD modules
            - Create custom forms, business rules, and client scripts
            - Integrate ServiceNow with external systems via REST APIs
            - Provide technical support and troubleshooting
            ''',
            'requirements': '''
            Required Skills:
            - 3+ years of ServiceNow development experience
            - Strong knowledge of ServiceNow platform and modules (ITSM, ITOM, HRSD)
            - Experience with JavaScript and ServiceNow scripting
            - Understanding of REST API integrations
            - Knowledge of ServiceNow workflows and business rules
            - Experience with ServiceNow Studio and Update Sets
            
            Preferred Skills:
            - ServiceNow certifications (CSA, CAD)
            - Experience with LDAP integration
            - Knowledge of ITIL processes
            - SQL database knowledge
            ''',
            'benefits': 'Health insurance, dental, vision, 401k, professional development budget',
            'remote_allowed': False,
            'source': 'seed_script',
            'status': 'active'
        },
        {
            'title': '.NET Full Stack Developer',
            'company': 'Microsoft Partner Solutions',
            'url': 'https://mspartner.com/jobs/dotnet-fullstack',
            'location': 'Austin, TX',
            'job_type': 'full-time',
            'experience_level': 'mid',
            'salary_min': 95000,
            'salary_max': 125000,
            'currency': 'USD',
            'description': '''
            We're looking for a .NET Full Stack Developer to build modern web applications 
            using the latest Microsoft technologies. You'll work on both frontend and backend 
            development in a collaborative team environment.
            
            Key Responsibilities:
            - Develop web applications using .NET Core and ASP.NET
            - Build responsive frontend interfaces with Angular or React
            - Design and implement RESTful APIs and microservices
            - Work with SQL Server databases and Entity Framework
            - Deploy applications to Azure cloud platform
            ''',
            'requirements': '''
            Required Skills:
            - 4+ years of .NET development experience
            - Strong knowledge of C# and .NET Core/Framework
            - Experience with ASP.NET MVC and Web API
            - Proficiency with SQL Server and Entity Framework
            - Frontend development with Angular or React
            - Knowledge of HTML, CSS, and JavaScript/TypeScript
            - Experience with Azure cloud services
            
            Preferred Skills:
            - Azure DevOps and CI/CD pipelines
            - Docker containerization experience
            - Knowledge of microservices architecture
            - Experience with Azure Service Bus or similar messaging
            - Unit testing with xUnit or NUnit
            ''',
            'benefits': 'Comprehensive benefits package, stock options, flexible hours, learning budget',
            'remote_allowed': True,
            'source': 'seed_script',
            'status': 'active'
        }
    ]
    
    job_ids = []
    
    print("🌱 Seeding database with sample jobs...")
    print("=" * 50)
    
    for i, job_data in enumerate(sample_jobs, 1):
        try:
            job_id = insert_job(job_data)
            job_ids.append(job_id)
            print(f"✓ Job {i}: {job_data['title']} at {job_data['company']}")
            print(f"  ID: {job_id}")
            print(f"  URL: {job_data['url']}")
            print()
        except Exception as e:
            print(f"❌ Failed to insert job {i}: {e}")
            continue
    
    print(f"✅ Successfully created {len(job_ids)} sample jobs")
    return job_ids


def score_all_sample_jobs():
    """Score all unscored jobs in the database."""
    print("\n📊 Scoring all jobs...")
    print("=" * 50)
    
    try:
        # Use the worker function to score all jobs
        score_all_jobs()
        print("✅ Job scoring completed successfully")
        
        # Display scored jobs
        scored_jobs = list_jobs()
        for job in scored_jobs:
            if job.get('score') is not None:
                print(f"✓ {job['title']}: {job['score']}/100")
                if job.get('match_reasons'):
                    try:
                        reasons = json.loads(job['match_reasons']) if isinstance(job['match_reasons'], str) else job['match_reasons']
                        for reason in reasons[:2]:  # Show first 2 reasons
                            print(f"  - {reason}")
                    except:
                        pass
                print()
        
    except Exception as e:
        print(f"❌ Failed to score jobs: {e}")
        return False
    
    return True


def tailor_application_for_first_job(job_ids):
    """Generate tailored application materials for the first job."""
    if not job_ids:
        print("❌ No jobs available for tailoring")
        return None
    
    first_job_id = job_ids[0]
    
    print(f"\n✂️ Tailoring application for first job...")
    print("=" * 50)
    
    try:
        # Get the job details
        job = get_job(first_job_id)
        if not job:
            print(f"❌ Could not retrieve job {first_job_id}")
            return None
        
        print(f"📋 Job: {job['title']} at {job['company']}")
        print(f"🎯 Score: {job.get('score', 'Not scored')}/100")
        
        # Prepare job data for tailoring
        job_data = dict(job)
        
        # Add extracted skills if we have them (from scoring)
        if job.get('match_reasons'):
            try:
                match_reasons = json.loads(job['match_reasons']) if isinstance(job['match_reasons'], str) else job['match_reasons']
                job_data['match_reasons'] = match_reasons
            except:
                job_data['match_reasons'] = []
        
        # Extract skills from job description for tailoring
        from apps.worker.scorer import extract_skills
        description_text = (job.get('description', '') + ' ' + job.get('requirements', '')).strip()
        if description_text:
            extracted_skills = extract_skills(description_text)
            job_data['skills'] = extracted_skills
            print(f"🔧 Extracted skills: {', '.join(extracted_skills[:5])}{'...' if len(extracted_skills) > 5 else ''}")
        
        # Create output directory
        artifacts_dir = Path(settings.artifact_dir) if hasattr(settings, 'artifact_dir') else Path('artifacts')
        artifacts_dir.mkdir(exist_ok=True)
        
        # Generate tailored assets
        assets = build_tailored_assets(first_job_id, job_data, artifacts_dir)
        
        print(f"\n📁 Generated tailored assets:")
        for asset_type, file_path in assets.items():
            print(f"  {asset_type}: {file_path}")
            if file_path.exists():
                file_size = file_path.stat().st_size
                print(f"    ✓ Created ({file_size} bytes)")
            else:
                print(f"    ❌ File not found")
        
        return assets
        
    except Exception as e:
        print(f"❌ Failed to tailor application: {e}")
        import traceback
        traceback.print_exc()
        return None


def display_summary(job_ids, assets):
    """Display a summary of the seeding and processing results."""
    print("\n" + "=" * 60)
    print("🎉 SEED AND RUN COMPLETE")
    print("=" * 60)
    
    print(f"📊 Jobs Created: {len(job_ids)}")
    
    # Show job statistics
    all_jobs = list_jobs()
    scored_jobs = [j for j in all_jobs if j.get('score') is not None]
    print(f"📈 Jobs Scored: {len(scored_jobs)}/{len(all_jobs)}")
    
    if scored_jobs:
        avg_score = sum(j['score'] for j in scored_jobs) / len(scored_jobs)
        print(f"📊 Average Score: {avg_score:.1f}/100")
    
    print(f"📁 Assets Generated: {len(assets) if assets else 0}")
    
    if assets:
        print(f"\n📂 Artifact Paths:")
        for asset_type, path in assets.items():
            print(f"  {asset_type}: {path}")
    
    print(f"\n🗂️ Next Steps:")
    print(f"  1. Review generated assets in the artifacts directory")
    print(f"  2. Start the API server: uvicorn apps.api.main:app --reload")
    print(f"  3. Start the worker: rq worker -u redis://localhost:6379/0 jobs")
    print(f"  4. Test API endpoints with curl commands")


def setup_database():
    """Set up database connection, falling back to SQLite if PostgreSQL unavailable."""
    try:
        # Try to connect to the configured database
        from db.db import check_connection
        if check_connection():
            print(f"✓ Connected to database: {settings.database_url}")
            return True
    except Exception as e:
        print(f"⚠️ PostgreSQL not available: {e}")
        
    # Fall back to SQLite for demonstration
    print("🔄 Setting up SQLite database for demonstration...")
    
    import tempfile
    import sqlite3
    
    # Create temporary SQLite database
    fd, db_path = tempfile.mkstemp(suffix='.db', prefix='jobbot_demo_')
    os.close(fd)
    
    # Set up the database schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create jobs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            location TEXT,
            job_type TEXT,
            experience_level TEXT,
            salary_min INTEGER,
            salary_max INTEGER,
            currency TEXT DEFAULT 'USD',
            description TEXT,
            requirements TEXT,
            benefits TEXT,
            remote_allowed BOOLEAN DEFAULT 0,
            date_posted DATETIME,
            application_deadline DATETIME,
            source TEXT,
            status TEXT DEFAULT 'active',
            score INTEGER,
            match_reasons TEXT,
            -- Visa and location fields
            visa_friendly BOOLEAN DEFAULT 0,
            visa_keywords TEXT,
            country TEXT,
            state_province TEXT,
            city TEXT,
            is_remote BOOLEAN DEFAULT 0,
            remote_type TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    
    # Override the database URL environment variable
    sqlite_url = f'sqlite:///{db_path}'
    os.environ['DATABASE_URL'] = sqlite_url
    
    # Also update settings if it has a mutable database_url
    try:
        if hasattr(settings, '__dict__'):
            settings.__dict__['database_url'] = sqlite_url
        elif hasattr(settings, '_values'):
            settings._values['database_url'] = sqlite_url
    except:
        pass
    
    print(f"✓ Created SQLite database: {sqlite_url}")
    return True


def main():
    """Main function to run the seed and demonstration script."""
    print("🤖 Job Bot - Seed and Run Demo")
    print("=" * 60)
    
    # Set up database connection
    if not setup_database():
        print("❌ Failed to set up database connection")
        return 1
    
    print(f"Database URL: {os.getenv('DATABASE_URL', settings.database_url)}")
    print(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    print()
    
    try:
        # Step 1: Create sample jobs
        job_ids = create_sample_jobs()
        
        if not job_ids:
            print("❌ No jobs were created. Exiting.")
            return 1
        
        # Step 2: Score all jobs
        if not score_all_sample_jobs():
            print("⚠️ Job scoring failed, but continuing with tailoring...")
        
        # Step 3: Tailor application for first job
        assets = tailor_application_for_first_job(job_ids)
        
        # Step 4: Display summary
        display_summary(job_ids, assets)
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️ Process interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
