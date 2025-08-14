# Job Bot - Automated Job Application System

## Repository Description

🤖 **Automated job application system** that intelligently scrapes, scores, tailors, and applies to job postings across multiple platforms.

## Key Features

- **Multi-Source Job Ingestion**: Scrapes jobs from Greenhouse, Lever, Ashby, and other platforms
- **AI-Powered Scoring**: Intelligent job compatibility analysis based on skills and requirements
- **Personalized Applications**: Generates tailored resumes and cover letters for each position
- **Automated Submissions**: Handles application forms and email submissions
- **Smart Outreach**: Sends personalized emails to company contacts
- **Pipeline Automation**: Complete end-to-end job application workflow

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy
- **Database**: PostgreSQL 16
- **Queue System**: Redis + RQ
- **Browser Automation**: Playwright
- **Email Integration**: Gmail API with OAuth2
- **Containerization**: Docker & Docker Compose

## Quick Start

```bash
# Docker setup (recommended)
make quick-start

# Or manual setup
docker compose up -d
python scripts/init_db.py
python scripts/seed_and_run.py
```

## Services

- **API & Docs**: http://localhost:8000
- **Dashboard**: http://localhost:8080
- **RQ Dashboard**: http://localhost:9181

## Responsible Automation

Built with safeguards for ethical usage:
- Email rate limiting and bounce handling
- LinkedIn draft-only mode (manual sending required)
- Truth verification system for all claims
- Do-not-contact list management

Perfect for job seekers looking to streamline their application process while maintaining professional standards and compliance.

## License

Personal use only. Please respect job board and email provider terms of service.
