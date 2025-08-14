-- Job Bot Database Schema for SQLite
-- SQLite-compatible schema for job application tracking system

-- Jobs table: stores job postings and opportunities
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    location TEXT,
    job_type TEXT, -- full-time, part-time, contract, etc.
    experience_level TEXT, -- entry, mid, senior, etc.
    salary_min INTEGER,
    salary_max INTEGER,
    currency TEXT DEFAULT 'USD',
    description TEXT,
    requirements TEXT,
    benefits TEXT,
    remote_allowed BOOLEAN DEFAULT 0,
    date_posted DATETIME,
    application_deadline DATETIME,
    status TEXT DEFAULT 'active', -- active, closed, expired
    source TEXT, -- linkedin, indeed, company_site, etc.
    scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    score INTEGER CHECK (score >= 0 AND score <= 100),
    match_reasons TEXT, -- JSON string for SQLite
    -- Visa and location fields
    visa_friendly BOOLEAN DEFAULT 0,
    visa_keywords TEXT, -- JSON string for SQLite
    country TEXT, -- ISO country code (US, CA, GB, etc.)
    state_province TEXT, -- state or province
    city TEXT, -- city name
    is_remote BOOLEAN DEFAULT 0,
    remote_type TEXT, -- 'full', 'hybrid', 'occasional'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Applications table: tracks job applications
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, submitted, reviewed, interviewed, rejected, offered
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    application_method TEXT, -- web_form, email, recruiter, etc.
    resume_version TEXT, -- filename or version identifier
    cover_letter_version TEXT,
    application_url TEXT,
    confirmation_number TEXT,
    notes TEXT,
    follow_up_date DATE,
    rejection_reason TEXT,
    interview_scheduled_at DATETIME,
    offer_amount INTEGER,
    offer_currency TEXT DEFAULT 'USD',
    response_deadline DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

-- Contacts table: stores professional contacts and recruiters
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    email TEXT UNIQUE,
    phone TEXT,
    linkedin_url TEXT,
    company TEXT,
    position TEXT,
    department TEXT,
    contact_type TEXT, -- recruiter, hiring_manager, employee, referral
    source TEXT, -- linkedin, email, referral, conference, etc.
    relationship_strength INTEGER CHECK (relationship_strength >= 1 AND relationship_strength <= 5),
    notes TEXT,
    last_contact_date DATE,
    preferred_contact_method TEXT, -- email, linkedin, phone
    time_zone TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Outreach table: tracks communications with contacts
CREATE TABLE IF NOT EXISTS outreach (
    id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL,
    job_id TEXT,
    outreach_type TEXT NOT NULL, -- cold_email, follow_up, thank_you, referral_request, etc.
    method TEXT NOT NULL, -- email, linkedin, phone, in_person
    subject TEXT,
    message TEXT,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    responded_at DATETIME,
    response_text TEXT,
    sentiment TEXT, -- positive, neutral, negative
    follow_up_required BOOLEAN DEFAULT 0,
    follow_up_date DATE,
    outcome TEXT, -- positive, neutral, negative, no_response
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL
);

-- Do not contact list
CREATE TABLE IF NOT EXISTS do_not_contact (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    reason TEXT,
    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    added_by TEXT,
    notes TEXT
);

-- Email rate limiting
CREATE TABLE IF NOT EXISTS email_rate_limits (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    date DATE NOT NULL,
    emails_sent INTEGER DEFAULT 0,
    last_email_sent_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(email, date)
);

-- Enhanced outreach tracking with email threading
CREATE TABLE IF NOT EXISTS outreach_enhanced (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    contact_id TEXT,
    to_address TEXT NOT NULL,
    subject TEXT,
    message_body TEXT,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'sent', -- sent, delivered, opened, replied, bounced
    message_id TEXT, -- Email Message-ID header
    thread_id TEXT, -- Conversation thread identifier
    parent_outreach_id TEXT, -- For follow-up emails
    followup_sequence INTEGER DEFAULT 0, -- 1 for first follow-up, 2 for second, etc.
    reply_received_at DATETIME,
    reply_content TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
    FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
    FOREIGN KEY (parent_outreach_id) REFERENCES outreach_enhanced(id) ON DELETE SET NULL
);

-- Follow-up scheduling
CREATE TABLE IF NOT EXISTS followup_schedule (
    id TEXT PRIMARY KEY,
    parent_outreach_id TEXT NOT NULL,
    to_address TEXT NOT NULL,
    scheduled_for DATETIME NOT NULL,
    followup_type TEXT DEFAULT 'standard', -- standard, value_add, final
    status TEXT DEFAULT 'pending', -- pending, sent, cancelled
    sent_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_outreach_id) REFERENCES outreach_enhanced(id) ON DELETE CASCADE
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs(location);
CREATE INDEX IF NOT EXISTS idx_jobs_date_posted ON jobs(date_posted);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at);
CREATE INDEX IF NOT EXISTS idx_jobs_visa_friendly ON jobs(visa_friendly);
CREATE INDEX IF NOT EXISTS idx_jobs_country ON jobs(country);
CREATE INDEX IF NOT EXISTS idx_jobs_state_province ON jobs(state_province);
CREATE INDEX IF NOT EXISTS idx_jobs_city ON jobs(city);
CREATE INDEX IF NOT EXISTS idx_jobs_is_remote ON jobs(is_remote);
CREATE INDEX IF NOT EXISTS idx_jobs_remote_type ON jobs(remote_type);

CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_applications_applied_at ON applications(applied_at);
CREATE INDEX IF NOT EXISTS idx_applications_follow_up_date ON applications(follow_up_date);

CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company);
CREATE INDEX IF NOT EXISTS idx_contacts_contact_type ON contacts(contact_type);
CREATE INDEX IF NOT EXISTS idx_contacts_last_contact_date ON contacts(last_contact_date);

CREATE INDEX IF NOT EXISTS idx_outreach_contact_id ON outreach(contact_id);
CREATE INDEX IF NOT EXISTS idx_outreach_job_id ON outreach(job_id);
CREATE INDEX IF NOT EXISTS idx_outreach_sent_at ON outreach(sent_at);
CREATE INDEX IF NOT EXISTS idx_outreach_follow_up_date ON outreach(follow_up_date);
CREATE INDEX IF NOT EXISTS idx_outreach_outcome ON outreach(outcome);

CREATE INDEX IF NOT EXISTS idx_do_not_contact_email ON do_not_contact(email);
CREATE INDEX IF NOT EXISTS idx_do_not_contact_reason ON do_not_contact(reason);
CREATE INDEX IF NOT EXISTS idx_do_not_contact_added_at ON do_not_contact(added_at);

CREATE INDEX IF NOT EXISTS idx_email_rate_limits_date ON email_rate_limits(date);
CREATE INDEX IF NOT EXISTS idx_email_rate_limits_last_sent ON email_rate_limits(last_email_sent_at);

CREATE INDEX IF NOT EXISTS idx_outreach_enhanced_job_id ON outreach_enhanced(job_id);
CREATE INDEX IF NOT EXISTS idx_outreach_enhanced_contact_id ON outreach_enhanced(contact_id);
CREATE INDEX IF NOT EXISTS idx_outreach_enhanced_to_address ON outreach_enhanced(to_address);
CREATE INDEX IF NOT EXISTS idx_outreach_enhanced_sent_at ON outreach_enhanced(sent_at);
CREATE INDEX IF NOT EXISTS idx_outreach_enhanced_status ON outreach_enhanced(status);
CREATE INDEX IF NOT EXISTS idx_outreach_enhanced_message_id ON outreach_enhanced(message_id);
CREATE INDEX IF NOT EXISTS idx_outreach_enhanced_thread_id ON outreach_enhanced(thread_id);
CREATE INDEX IF NOT EXISTS idx_outreach_enhanced_parent_id ON outreach_enhanced(parent_outreach_id);
CREATE INDEX IF NOT EXISTS idx_outreach_enhanced_followup_seq ON outreach_enhanced(followup_sequence);

CREATE INDEX IF NOT EXISTS idx_followup_schedule_parent_id ON followup_schedule(parent_outreach_id);
CREATE INDEX IF NOT EXISTS idx_followup_schedule_scheduled_for ON followup_schedule(scheduled_for);
CREATE INDEX IF NOT EXISTS idx_followup_schedule_status ON followup_schedule(status);
CREATE INDEX IF NOT EXISTS idx_followup_schedule_to_address ON followup_schedule(to_address);
