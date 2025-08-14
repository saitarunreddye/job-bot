"""
Application settings using Pydantic Settings.
Supports environment variables and .env files.
"""

from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Database Configuration
    database_url: str = Field(
        default="sqlite:///./jobbot.db",
        description="Database connection URL (SQLite for local dev, PostgreSQL for production)"
    )
    
    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for caching and queues"
    )
    
    # File Storage
    artifact_dir: str = Field(
        default="artifacts",
        description="Directory for storing generated files and artifacts"
    )
    
    # Gmail API Configuration
    gmail_credentials_file: str = Field(
        default="config/configgmail_credentials.json",
        description="Path to Gmail API credentials JSON file"
    )
    gmail_token_file: str = Field(
        default="config/gmail_token.json",
        description="Path to Gmail API token file"
    )
    
    # API Configuration
    api_host: str = Field(default="0.0.0.0", description="API server host")
    api_port: int = Field(default=8000, description="API server port")
    api_debug: bool = Field(default=False, description="Enable debug mode")
    
    # Worker Configuration
    worker_concurrency: int = Field(
        default=4, 
        description="Number of concurrent worker processes"
    )
    worker_queue_name: str = Field(
        default="default", 
        description="RQ queue name for background jobs"
    )
    
    # Job Scraping Configuration
    scraping_delay_min: int = Field(
        default=1, 
        description="Minimum delay between scraping requests (seconds)"
    )
    scraping_delay_max: int = Field(
        default=3, 
        description="Maximum delay between scraping requests (seconds)"
    )
    max_retries: int = Field(
        default=3, 
        description="Maximum number of retry attempts"
    )
    
    # Greenhouse Job Boards
    greenhouse_boards: List[str] = Field(
        default=[
            "https://boards.greenhouse.io/stripe",
            "https://boards.greenhouse.io/airbnb", 
            "https://boards.greenhouse.io/shopify",
            "https://grnh.se/gitlab",
            "https://boards.greenhouse.io/discord"
        ],
        description="List of Greenhouse career board URLs to scrape"
    )
    
    # Lever Job Boards
    lever_boards: List[str] = Field(
        default=[
            "https://jobs.lever.co/netflix",
            "https://jobs.lever.co/uber",
            "https://jobs.lever.co/square",
            "https://jobs.lever.co/postmates",
            "https://jobs.lever.co/canva"
        ],
        description="List of Lever career board URLs to scrape"
    )
    
    # Ashby Job Boards
    ashby_boards: List[str] = Field(
        default=[
            "https://jobs.ashbyhq.com/notion",
            "https://jobs.ashbyhq.com/vercel",
            "https://jobs.ashbyhq.com/linear",
            "https://jobs.ashbyhq.com/anthropic",
            "https://jobs.ashbyhq.com/figma"
        ],
        description="List of Ashby career board URLs to scrape"
    )
    
    # LLM Configuration
    openai_api_key: Optional[str] = Field(
        default=None, 
        description="OpenAI API key for content generation"
    )
    anthropic_api_key: Optional[str] = Field(
        default=None, 
        description="Anthropic API key for content generation"
    )
    
    # Email Configuration
    smtp_server: str = Field(
        default="smtp.gmail.com", 
        description="SMTP server for sending emails"
    )
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_username: Optional[str] = Field(
        default=None, 
        description="SMTP username"
    )
    smtp_password: Optional[str] = Field(
        default=None, 
        description="SMTP password or app password"
    )
    
    # Security
    secret_key: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for JWT tokens and encryption"
    )
    access_token_expire_minutes: int = Field(
        default=30,
        description="JWT token expiration time in minutes"
    )
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format (json/text)")
    
    # Application Settings
    app_name: str = Field(default="JobBot", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    environment: str = Field(
        default="development", 
        description="Environment (development/staging/production)"
    )


# Global settings instance
settings = Settings()
