-- Job Bot Database Schema
-- Simplified SQLite schema for job application tracking system

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

-- Jobs compatibility view (id/description/match_reasons)
DROP VIEW IF EXISTS jobs_view;
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
FROM jobs;

-- Applications compatibility view (adds missing columns as NULL defaults)
DROP VIEW IF EXISTS applications_view;
CREATE VIEW applications_view AS
SELECT
  app_id,
  job_id,
  resume_path,
  portal,
  tracking_url,
  status,
  submitted_at,
  NULL AS cover_letter_version,  -- tests may read it; we surface NULL
  NULL AS notes                  -- tests may read it; we surface NULL
FROM applications;

-- Contacts compatibility view (id alias)
DROP VIEW IF EXISTS contacts_view;
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
FROM contacts;

-- Outreach compatibility view (message_content already present)
DROP VIEW IF EXISTS outreach_view;
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
FROM outreach_enhanced;
