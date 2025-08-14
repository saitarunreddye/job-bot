# Job Bot

Automated job application system that scrapes, scores, tailors, and applies to job postings.

## Features

- **Multi-Source Ingestion**: Scrape jobs from Greenhouse, Lever, Ashby, and other platforms
- **Intelligent Scoring**: AI-powered job compatibility scoring based on skills and requirements
- **Application Tailoring**: Generate personalized resumes and cover letters per job
- **Automated Applications**: Submit applications via web forms (Greenhouse) or email
- **Email Outreach**: Send personalized outreach emails to company contacts
- **Contact Management**: Track and prioritize professional contacts
- **Pipeline Automation**: Fully automated job application workflow

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy Core
- **Database**: PostgreSQL 16
- **Queue**: Redis + RQ (Redis Queue)
- **Automation**: Playwright (browser automation)
- **Email**: Gmail API with OAuth2
- **Scraping**: httpx + regex parsing
- **File Management**: Organized artifact system

## Quickstart

### Option 1: Docker (Recommended)

1. **Prerequisites**
   - Install [Docker](https://docs.docker.com/get-docker/) and Docker Compose
   - For Windows users: Install [WSL2](https://docs.microsoft.com/en-us/windows/wsl/install) for best performance

2. **Quick Start with Make (Linux/macOS)**
   ```bash
   make quick-start
   ```

3. **Quick Start with Scripts (Windows)**
   ```powershell
   # PowerShell
   .\scripts\docker.ps1 up
   .\scripts\docker.ps1 db-init
   .\scripts\docker.ps1 seed
   
   # Command Prompt
   scripts\docker.bat up
   ```

4. **Manual Docker Setup**
   ```bash
   # Copy environment template
   cp env.example .env
   
   # Start all services
   docker compose up -d
   
   # Initialize database
   docker compose exec api python scripts/init_db.py
   
   # Seed with sample data
   docker compose exec api python scripts/seed_and_run.py
   ```

### Option 2: Local Development

1. **Start Infrastructure Only**
   ```bash
   # Start PostgreSQL and Redis only
   docker compose up -d postgres redis
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

3. **Run Services Locally**
   ```bash
   # Terminal 1: API Server
   uvicorn apps.api.main:app --reload
   
   # Terminal 2: Worker
   rq worker -u redis://localhost:6379/0 jobs
   
   # Terminal 3: Initialize and seed
   python scripts/init_db.py
   python scripts/seed_and_run.py
   ```

### 🌐 Access Services

After startup, services are available at:
- **API & Docs**: http://localhost:8000
- **Dashboard**: http://localhost:8080  
- **RQ Dashboard**: http://localhost:9181
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

### 📋 Docker Management

#### Using Make (Linux/macOS)
```bash
make up          # Start all services
make down        # Stop all services
make logs        # View logs
make status      # Check service status
make clean       # Clean up containers
```

#### Using PowerShell (Windows)
```powershell
.\scripts\docker.ps1 up        # Start all services
.\scripts\docker.ps1 down      # Stop all services
.\scripts\docker.ps1 logs      # View logs
.\scripts\docker.ps1 status    # Check service status
.\scripts\docker.ps1 clean     # Clean up containers
```

#### Using Batch Script (Windows)
```cmd
scripts\docker.bat up          # Start all services
scripts\docker.bat down        # Stop all services
scripts\docker.bat logs        # View logs
scripts\docker.bat status      # Check service status
```

### 🐛 Docker Troubleshooting

#### Common Issues

**Services won't start:**
```bash
# Check Docker status
docker version
docker compose version

# Check logs for errors
docker compose logs postgres
docker compose logs redis
docker compose logs api

# Restart specific service
docker compose restart api
```

**Database connection issues:**
```bash
# Check if PostgreSQL is running
docker compose ps postgres

# Check PostgreSQL logs
docker compose logs postgres

# Test database connection
docker compose exec postgres psql -U jobbot -d jobbot -c "\dt"
```

**Port conflicts:**
```bash
# Check what's using ports
netstat -tulpn | grep :8000
netstat -tulpn | grep :5432

# Use different ports in .env file
API_PORT=8001
POSTGRES_PORT=5433
```

**Disk space issues:**
```bash
# Clean up Docker resources
docker system prune -af
docker volume prune -f

# Check disk usage
docker system df
```

**Permission issues (Linux/macOS):**
```bash
# Fix file permissions
sudo chown -R $USER:$USER ./artifacts ./config ./logs

# Fix Docker socket permissions
sudo usermod -aG docker $USER
```

#### Health Checks

```bash
# Check service health
curl http://localhost:8000/health

# Check API status
curl http://localhost:8000/

# Check RQ Dashboard
curl http://localhost:9181/

# Database health check
docker compose exec postgres pg_isready -U jobbot -d jobbot
```

#### Logs and Debugging

```bash
# View specific service logs
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f postgres

# Follow logs with timestamps
docker compose logs -f -t

# View last 100 lines
docker compose logs --tail=100 api
```

## Automated Pipeline

For automated job application processing, use the scheduler:

### Manual Execution
```bash
# Run the complete pipeline
python scripts/schedule.py

# With custom parameters
python scripts/schedule.py --min-score 80 --max-jobs 5 --sources greenhouse lever

# Dry run (no actual actions)
python scripts/schedule.py --dry-run
```

### Automated Execution (Cron)

Add this line to your crontab to run the pipeline every 2 hours:

```bash
# Edit crontab
crontab -e

# Add this line (adjust paths as needed)
0 */2 * * * cd /path/to/job-bot && /usr/bin/python3 scripts/schedule.py --min-score 70 --max-jobs 10 >> schedule.log 2>&1
```

**Example cron schedule options:**
```bash
# Every 2 hours
0 */2 * * * cd /path/to/job-bot && python3 scripts/schedule.py

# Every 4 hours during business hours (9 AM - 5 PM)
0 9,13,17 * * 1-5 cd /path/to/job-bot && python3 scripts/schedule.py

# Daily at 9 AM on weekdays
0 9 * * 1-5 cd /path/to/job-bot && python3 scripts/schedule.py

# Twice daily (9 AM and 2 PM) on weekdays
0 9,14 * * 1-5 cd /path/to/job-bot && python3 scripts/schedule.py
```

### Pipeline Process

The automated pipeline performs the following sequence:

1. **Ingest** → Scrape new jobs from configured sources
2. **Score** → Analyze and score all unscored jobs  
3. **Filter** → Select top N jobs with score ≥ 70
4. **Tailor** → Generate personalized resumes and cover letters
5. **Apply** → Submit applications (auto for Greenhouse, manual flag for others)
6. **Email** → Send outreach emails if company contacts exist

### Pipeline Configuration

Configure the pipeline behavior:

```bash
# Environment variables
export MIN_SCORE_THRESHOLD=70
export MAX_JOBS_PER_RUN=10
export EMAIL_CONTACTS_ONLY=true

# Or use command line arguments
python scripts/schedule.py \
  --min-score 75 \
  --max-jobs 5 \
  --sources greenhouse ashby \
  --no-email-contacts-only
```

## API Endpoints

### Job Processing
- `POST /v1/ingest` - Scrape jobs from sources
- `POST /v1/score` - Score all unscored jobs
- `POST /v1/tailor/{job_id}` - Generate tailored application materials
- `POST /v1/apply/{job_id}` - Submit job application
- `POST /v1/outreach/email` - Send outreach email

### Information & Analytics
- `GET /v1/stats` - Application pipeline statistics
- `GET /v1/linkedin/draft/{job_id}` - LinkedIn message draft with contact suggestions

## API Usage Examples

After starting the API server (`uvicorn apps.api.main:app --reload`), you can test the endpoints:

### 0. Process Follow-up Emails

```bash
# Process all due follow-up emails (typically run by scheduler)
curl -X POST "http://localhost:8000/v1/followups/process" \
  -H "Content-Type: application/json"

# Response example:
# {
#   "task_id": "12345",
#   "message": "Follow-up processing queued successfully",
#   "stats": null
# }
```

### 1. Search and Filter Jobs

```bash
# Get all jobs (paginated)
curl "http://localhost:8000/v1/jobs"

# Filter by visa sponsorship (H-1B, OPT, CPT, etc.)
curl "http://localhost:8000/v1/jobs?visa_friendly=true"

# Filter by location (US-only jobs)
curl "http://localhost:8000/v1/jobs?country=US"

# Filter by state/province
curl "http://localhost:8000/v1/jobs?state_province=CA"
curl "http://localhost:8000/v1/jobs?state_province=NY"

# Filter by remote work options
curl "http://localhost:8000/v1/jobs?is_remote=true"
curl "http://localhost:8000/v1/jobs?remote_type=full"
curl "http://localhost:8000/v1/jobs?remote_type=hybrid"

# Combined filters (visa-friendly remote jobs in US)
curl "http://localhost:8000/v1/jobs?visa_friendly=true&country=US&is_remote=true"

# Filter by score and company
curl "http://localhost:8000/v1/jobs?min_score=80&company=Google"

# Search by job title
curl "http://localhost:8000/v1/jobs?title=python"

# Pagination
curl "http://localhost:8000/v1/jobs?page=2&page_size=10"

# Get specific job by ID
curl "http://localhost:8000/v1/jobs/123e4567-e89b-12d3-a456-426614174000"

# Response example:
# {
#   "jobs": [
#     {
#       "id": "123e4567-e89b-12d3-a456-426614174000",
#       "title": "Senior Software Engineer",
#       "company": "TechCorp",
#       "location": "San Francisco, CA",
#       "visa_friendly": true,
#       "visa_keywords": ["h-1b", "sponsorship available"],
#       "country": "US",
#       "state_province": "CA",
#       "city": "San Francisco",
#       "is_remote": false,
#       "score": 85,
#       "status": "active"
#     }
#   ],
#   "total_count": 1,
#   "page": 1,
#   "page_size": 20,
#   "has_next": false
# }
```

### 2. Ingest Jobs
```bash
# Ingest jobs from all sources (default max 50 jobs)
curl -X POST "http://localhost:8000/v1/ingest" \
  -H "Content-Type: application/json" \
  -d '{}'

# Ingest from specific sources with custom limits
curl -X POST "http://localhost:8000/v1/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "source": "greenhouse",
    "max_jobs": 20,
    "search_terms": ["python", "software engineer"],
    "location": "San Francisco"
  }'
```

### 3. Score Jobs
```bash
# Score all unscored jobs
curl -X POST "http://localhost:8000/v1/score" \
  -H "Content-Type: application/json"

# Response example:
# {
#   "message": "Job scoring completed",
#   "jobs_scored": 15,
#   "average_score": 73.2
# }
```

### 4. Tailor Application Materials
```bash
# Generate tailored assets for a specific job (use job ID from database/stats)
curl -X POST "http://localhost:8000/v1/tailor/123e4567-e89b-12d3-a456-426614174000" \
  -H "Content-Type: application/json"

# Response example:
# {
#   "job_id": "123e4567-e89b-12d3-a456-426614174000",
#   "artifacts": {
#     "resume_docx": "/path/to/artifacts/123e4567.../resume.docx",
#     "resume_txt": "/path/to/artifacts/123e4567.../resume.txt",
#     "cover_email": "/path/to/artifacts/123e4567.../cover_email.txt",
#     "linkedin_msg": "/path/to/artifacts/123e4567.../linkedin_msg.txt",
#     "meta_json": "/path/to/artifacts/123e4567.../meta.json"
#   },
#   "generation_time": 2.3
# }
```

### 5. Submit Application
```bash
# Submit application for a job (job must be tailored first)
curl -X POST "http://localhost:8000/v1/apply/123e4567-e89b-12d3-a456-426614174000" \
  -H "Content-Type: application/json" \
  -d '{
    "method": "email",
    "cover_letter": true
  }'

# Response example:
# {
#   "job_id": "123e4567-e89b-12d3-a456-426614174000",
#   "application_id": "app-789",
#   "status": "submitted",
#   "method": "email",
#   "confirmation": "EMAIL_SENT_2025"
# }
```

### 6. View Statistics
```bash
# Get pipeline statistics and job overview
curl -X GET "http://localhost:8000/v1/stats" \
  -H "Accept: application/json"

# Response example:
# {
#   "jobs": {
#     "total": 150,
#     "active": 120,
#     "scored": 115,
#     "high_score": 45,
#     "applications": 12
#   },
#   "scores": {
#     "average": 71.5,
#     "median": 74.0,
#     "min": 23,
#     "max": 98
#   },
#   "pipeline": {
#     "last_ingest": "2025-01-08T10:30:00Z",
#     "last_score": "2025-01-08T10:35:00Z",
#     "pending_applications": 8
#   }
# }
```

### 6. Get All Jobs (with filtering)
```bash
# Get jobs with score >= 80
curl -X GET "http://localhost:8000/v1/jobs?min_score=80&limit=10" \
  -H "Accept: application/json"

# Get jobs by status
curl -X GET "http://localhost:8000/v1/jobs?status=active&limit=20" \
  -H "Accept: application/json"
```

### 7. Get Specific Job Details
```bash
# Get detailed information about a specific job
curl -X GET "http://localhost:8000/v1/jobs/123e4567-e89b-12d3-a456-426614174000" \
  -H "Accept: application/json"
```

### Error Handling
All endpoints return consistent error responses:

```bash
# Example error response
# {
#   "detail": "Job not found",
#   "error_code": "JOB_NOT_FOUND",
#   "job_id": "123e4567-e89b-12d3-a456-426614174000"
# }
```

### Testing the Complete Pipeline

```bash
# Complete pipeline test sequence
echo "1. Ingest jobs..."
curl -X POST "http://localhost:8000/v1/ingest" -H "Content-Type: application/json" -d '{}'

echo "2. Score jobs..."
curl -X POST "http://localhost:8000/v1/score" -H "Content-Type: application/json"

echo "3. Get stats..."
curl -X GET "http://localhost:8000/v1/stats"

echo "4. Get high-scoring jobs..."
curl -X GET "http://localhost:8000/v1/jobs?min_score=80&limit=5"

# Use a job ID from the previous response for the next steps
JOB_ID="replace-with-actual-job-id"

echo "5. Tailor application..."
curl -X POST "http://localhost:8000/v1/tailor/$JOB_ID" -H "Content-Type: application/json"

echo "6. Submit application..."
curl -X POST "http://localhost:8000/v1/apply/$JOB_ID" -H "Content-Type: application/json" -d '{"method": "email"}'
```

## Setup Guides

### Gmail API Setup
```bash
python scripts/setup_gmail.py
```
Follow the detailed instructions in `config/gmail_setup_instructions.md`.

### Playwright Setup
```bash
python scripts/setup_playwright.py
```

## File Organization

```
artifacts/{job_id}/
├── resume.docx              # Tailored resume
├── resume.txt               # Plain text resume
├── cover_email.txt          # Cover email content
├── linkedin_msg.txt         # LinkedIn outreach message
├── meta.json               # Job metadata and analysis
└── apply_error.png         # Error screenshots (if any)
```

## Configuration

### Environment Variables (.env)
```bash
# Database
DATABASE_URL=postgresql://jobbot:jobbot_password@localhost:5432/jobbot

# Redis
REDIS_URL=redis://localhost:6379/0

# File Storage
ARTIFACT_DIR=./artifacts

# Gmail API
GMAIL_CREDENTIALS_FILE=./config/configgmail_credentials.json
```

### User Profile (apps/worker/user_profile.py)
Update with your personal information for automated applications:
```python
DEFAULT_USER_PROFILE = {
    'first_name': 'Your Name',
    'last_name': 'Last Name',
    'email': 'your.email@example.com',
    'phone': '+1 (555) 123-4567',
    'location': 'Your City, State'
}
```

## Development

### Project Structure
```
job-bot/
├── apps/
│   ├── api/                 # FastAPI application
│   ├── worker/              # Background workers and processing
│   └── dash/                # Dashboard (future)
├── config/                  # Configuration and settings
├── db/                      # Database schema and utilities
├── scripts/                 # Setup and utility scripts
├── artifacts/               # Generated application materials
└── docker/                  # Docker configuration
```

### Key Components
- **Scrapers**: `apps/worker/scraper_*.py` - Job board scrapers
- **Scoring**: `apps/worker/scorer.py` - Job compatibility analysis
- **File Management**: `apps/worker/file_manager.py` - Artifact organization
- **Email System**: `apps/worker/emailer.py` - Gmail API integration
- **Automation**: `apps/worker/apply_greenhouse.py` - Browser automation
- **LinkedIn**: `apps/worker/linkedin.py` - Message preparation
- **Scheduler**: `scripts/schedule.py` - Pipeline automation

## License

This project is for personal use. Please respect the terms of service of job boards and email providers when using this tool.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Responsible Usage & Safeguards

The Job Bot includes multiple safeguards to ensure responsible and compliant automation:

### ✅ Email Safeguards
- **Do-Not-Contact List**: Automatically prevents emails to blocked addresses
- **Rate Limiting**: Maximum 30 emails per day with respectful 2-minute delays
- **Bounce Handling**: Automatic addition of bounced emails to do-not-contact list
- **Unsubscribe Support**: Easy opt-out mechanism for recipients

### ✅ LinkedIn Compliance
- **Draft-Only Mode**: LinkedIn messages are generated as drafts only, never sent automatically
- **ToS Warning**: Clear dashboard banner explaining LinkedIn's Terms of Service
- **Manual Review**: All LinkedIn outreach requires human review and manual sending
- **Personalization Encouraged**: Generated messages serve as starting points for customization

### ✅ Truth Verification
- **Achievement Bank**: All resume claims verified against `config/achievement_bank.json`
- **No Fabrication**: System prevents inflated experience, skills, or accomplishments
- **Skill Verification**: Only professionally verified skills are included in applications
- **Experience Accuracy**: Years of experience claims must match actual timeline
- **Quantified Claims**: Performance improvements and achievements must be verifiable

### ✅ Content Quality
- **ATS-Safe Formats**: Generated resumes compatible with Applicant Tracking Systems
- **Professional Standards**: All content maintains professional tone and structure
- **Truthful Bullets**: Resume bullets generated only from verified achievements
- **No Exaggeration**: System prevents claims like "10+ years experience" or "expert level"

### Managing Safeguards

#### Do-Not-Contact List
```bash
# Add email to do-not-contact list
curl -X POST "http://localhost:8000/v1/do-not-contact" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "example@company.com",
    "reason": "unsubscribed",
    "notes": "User requested removal"
  }'

# Check if email is blocked
curl -X GET "http://localhost:8000/v1/do-not-contact/check?email=example@company.com"
```

#### Email Rate Limits
```bash
# Check current email quota
curl -X GET "http://localhost:8000/v1/email/quota"

# Update daily limit (admin only)
curl -X PUT "http://localhost:8000/v1/email/quota" \
  -H "Content-Type: application/json" \
  -d '{"daily_limit": 25}'
```

#### Truth Verification
- Update `config/achievement_bank.json` with your actual experience and achievements
- All generated content is automatically verified against this bank
- Prohibited claims are logged and prevented from appearing in applications
- Verification results are stored in each job's `meta.json` file

## Support

For issues and questions:
1. Check the logs in `schedule.log`
2. Review error screenshots in `artifacts/{job_id}/`
3. Verify configuration in `.env` and user profile
4. Test individual components before running the full pipeline
5. Review truth verification results in job metadata files
