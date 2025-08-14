"""
Lever job board scraper.
Scrapes job listings from Lever-powered career pages.
"""

import asyncio
import logging
import random
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
import time

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


class LeverScrapeError(Exception):
    """Exception raised during Lever scraping."""
    pass


class LeverScraper:
    """Lever job board scraper with pagination and rate limiting."""
    
    def __init__(self, delay_min: float = 1.0, delay_max: float = 3.0):
        """
        Initialize scraper with rate limiting parameters.
        
        Args:
            delay_min: Minimum delay between requests (seconds)
            delay_max: Maximum delay between requests (seconds)
        """
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.session = None
        self.scraped_urls = set()
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = httpx.AsyncClient(
            timeout=30.0,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.aclose()
    
    async def _random_delay(self):
        """Add random delay between requests to be respectful."""
        delay = random.uniform(self.delay_min, self.delay_max)
        logger.debug(f"Waiting {delay:.2f} seconds...")
        await asyncio.sleep(delay)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError))
    )
    async def _fetch_page(self, url: str) -> str:
        """
        Fetch a single page with retry logic.
        
        Args:
            url: URL to fetch
            
        Returns:
            str: HTML content of the page
            
        Raises:
            LeverScrapeError: If page fetch fails
        """
        try:
            logger.debug(f"Fetching: {url}")
            response = await self.session.get(url)
            response.raise_for_status()
            
            # Check if we got blocked or redirected
            if "blocked" in response.text.lower() or response.status_code == 429:
                raise LeverScrapeError(f"Rate limited or blocked: {url}")
            
            return response.text
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching {url}: {e}")
            raise LeverScrapeError(f"HTTP error: {e}")
        except httpx.RequestError as e:
            logger.error(f"Request error fetching {url}: {e}")
            raise LeverScrapeError(f"Request error: {e}")
    
    def _extract_job_links(self, html: str, base_url: str) -> List[str]:
        """
        Extract job listing URLs from Lever careers page HTML.
        
        Args:
            html: HTML content of careers page
            base_url: Base URL for resolving relative links
            
        Returns:
            List[str]: List of job posting URLs
        """
        job_links = []
        
        # Common Lever job link patterns
        patterns = [
            r'<a[^>]+href="([^"]*jobs/[a-f0-9\-]+[^"]*)"',  # Standard Lever UUID-based job links
            r'<a[^>]+href="([^"]*lever\.co/[^/]+/[a-f0-9\-]+[^"]*)"',  # Full lever.co URLs
            r'href="([^"]*careers/[^/]+/[a-f0-9\-]+[^"]*)"',  # Alternative careers format
            r'data-qa="posting"[^>]*><a[^>]+href="([^"]+)"',  # Data attribute based
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for match in matches:
                full_url = urljoin(base_url, match)
                if full_url not in job_links:
                    job_links.append(full_url)
        
        logger.debug(f"Found {len(job_links)} job links")
        return job_links
    
    def _extract_job_details(self, html: str, job_url: str) -> Optional[Dict[str, Any]]:
        """
        Extract job details from individual Lever job page HTML.
        
        Args:
            html: HTML content of job page
            job_url: URL of the job posting
            
        Returns:
            Optional[Dict]: Job details dictionary or None if extraction fails
        """
        try:
            # Extract title - try multiple patterns for Lever
            title_patterns = [
                r'<h2[^>]*class="[^"]*posting-headline[^"]*"[^>]*>([^<]+)</h2>',
                r'<h1[^>]*class="[^"]*posting-headline[^"]*"[^>]*>([^<]+)</h1>',
                r'<div[^>]*class="[^"]*posting-headline[^"]*"[^>]*>([^<]+)</div>',
                r'<h1[^>]*>([^<]+)</h1>',
                r'<title>([^<]+) - ',
                r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"',
            ]
            
            title = None
            for pattern in title_patterns:
                match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
                if match:
                    title = match.group(1).strip()
                    break
            
            if not title:
                logger.warning(f"Could not extract title from {job_url}")
                return None
            
            # Extract company name
            company_patterns = [
                r'<div[^>]*class="[^"]*posting-categories[^"]*"[^>]*>.*?<div[^>]*>([^<]+)</div>',
                r'<span[^>]*class="[^"]*company[^"]*"[^>]*>([^<]+)</span>',
                r'<div[^>]*class="[^"]*company[^"]*"[^>]*>([^<]+)</div>',
                r'<h2[^>]*class="[^"]*company[^"]*"[^>]*>([^<]+)</h2>',
            ]
            
            company = None
            for pattern in company_patterns:
                match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
                if match:
                    company = match.group(1).strip()
                    break
            
            # If no company in HTML, try to extract from URL
            if not company:
                url_parts = urlparse(job_url)
                if 'lever.co' in url_parts.netloc:
                    # Extract company from jobs.lever.co/company format
                    path_parts = url_parts.path.strip('/').split('/')
                    if len(path_parts) > 0:
                        company = path_parts[0].replace('-', ' ').title()
                else:
                    # Extract from custom domain
                    company = url_parts.netloc.split('.')[0].replace('-', ' ').title()
                
                if not company:
                    company = "Unknown Company"
            
            # Extract location
            location_patterns = [
                r'<div[^>]*class="[^"]*posting-categories[^"]*"[^>]*>.*?<div[^>]*>.*?</div>.*?<div[^>]*>([^<]+)</div>',
                r'<span[^>]*class="[^"]*location[^"]*"[^>]*>([^<]+)</span>',
                r'<div[^>]*class="[^"]*location[^"]*"[^>]*>([^<]+)</div>',
                r'<div[^>]*class="[^"]*sort-by-location[^"]*"[^>]*>([^<]+)</div>',
                r'Location[^>]*>([^<]+)<',
            ]
            
            location = "Not specified"
            for pattern in location_patterns:
                match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
                if match:
                    location = match.group(1).strip()
                    # Clean up common artifacts
                    location = re.sub(r'^\s*[•·]\s*', '', location)
                    break
            
            # Extract job description text
            jd_patterns = [
                r'<div[^>]*class="[^"]*posting-content[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]*class="[^"]*section-wrapper[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</div>',
                r'<section[^>]*class="[^"]*posting[^"]*"[^>]*>(.*?)</section>',
            ]
            
            jd_text = ""
            for pattern in jd_patterns:
                match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
                if match:
                    # Clean HTML tags and extract text
                    raw_text = match.group(1)
                    # Remove HTML tags
                    jd_text = re.sub(r'<[^>]+>', ' ', raw_text)
                    # Clean up whitespace
                    jd_text = re.sub(r'\s+', ' ', jd_text).strip()
                    break
            
            # If no description found, take a larger chunk of the page
            if not jd_text:
                # Remove script and style tags
                clean_html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.IGNORECASE | re.DOTALL)
                # Remove all HTML tags
                text_content = re.sub(r'<[^>]+>', ' ', clean_html)
                # Clean up whitespace
                text_content = re.sub(r'\s+', ' ', text_content).strip()
                # Take a reasonable chunk (first 2000 chars)
                jd_text = text_content[:2000] if len(text_content) > 2000 else text_content
            
            job_data = {
                'title': title,
                'company': company,
                'location': location,
                'url': job_url,
                'jd_text': jd_text,
                'source': 'Lever'
            }
            
            logger.debug(f"Extracted job: {title} at {company}")
            return job_data
            
        except Exception as e:
            logger.error(f"Failed to extract job details from {job_url}: {e}")
            return None
    
    async def _scrape_job_page(self, job_url: str) -> Optional[Dict[str, Any]]:
        """
        Scrape individual job page.
        
        Args:
            job_url: URL of job posting
            
        Returns:
            Optional[Dict]: Job details or None if scraping fails
        """
        try:
            await self._random_delay()
            html = await self._fetch_page(job_url)
            return self._extract_job_details(html, job_url)
            
        except Exception as e:
            logger.error(f"Failed to scrape job page {job_url}: {e}")
            return None
    
    async def scrape_board(self, board_url: str, max_pages: int = 5) -> List[Dict[str, Any]]:
        """
        Scrape all jobs from a Lever board with pagination.
        
        Args:
            board_url: URL of the careers/jobs page
            max_pages: Maximum number of pages to scrape
            
        Returns:
            List[Dict]: List of job dictionaries
        """
        logger.info(f"Starting scrape of Lever board: {board_url}")
        
        all_jobs = []
        page = 0  # Lever often uses 0-based pagination
        
        try:
            while page < max_pages:
                # Handle pagination - Lever often uses ?page=N or ?offset=N
                if page == 0:
                    page_url = board_url
                else:
                    separator = '&' if '?' in board_url else '?'
                    # Try both pagination formats
                    if 'offset=' in board_url or 'page=' in board_url:
                        page_url = board_url  # Already has pagination
                    else:
                        page_url = f"{board_url}{separator}page={page}"
                
                logger.debug(f"Scraping page {page}: {page_url}")
                
                await self._random_delay()
                html = await self._fetch_page(page_url)
                
                # Extract job links from this page
                job_links = self._extract_job_links(html, board_url)
                
                if not job_links:
                    logger.info(f"No job links found on page {page}, stopping pagination")
                    break
                
                # Scrape each job page
                for job_url in job_links:
                    if job_url in self.scraped_urls:
                        logger.debug(f"Skipping duplicate URL: {job_url}")
                        continue
                    
                    self.scraped_urls.add(job_url)
                    job_data = await self._scrape_job_page(job_url)
                    
                    if job_data:
                        all_jobs.append(job_data)
                
                page += 1
                
                # Check if we should continue (look for pagination indicators)
                if not re.search(r'(next|>|page\s*' + str(page) + r'|more)', html, re.IGNORECASE):
                    logger.info("No more pages detected, stopping pagination")
                    break
            
            logger.info(f"Scraping completed: {len(all_jobs)} jobs found from {board_url}")
            return all_jobs
            
        except Exception as e:
            logger.error(f"Failed to scrape board {board_url}: {e}")
            raise LeverScrapeError(f"Board scraping failed: {e}")


def dedupe_jobs_by_url(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate jobs based on URL.
    
    Args:
        jobs: List of job dictionaries
        
    Returns:
        List[Dict]: Deduplicated list of jobs
    """
    seen_urls = set()
    unique_jobs = []
    
    for job in jobs:
        url = job.get('url')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)
        else:
            logger.debug(f"Removing duplicate job URL: {url}")
    
    logger.info(f"Deduplication: {len(jobs)} -> {len(unique_jobs)} jobs")
    return unique_jobs


async def scrape_lever(board_url: str) -> List[Dict[str, Any]]:
    """
    Scrape jobs from a Lever-powered career page.
    
    Args:
        board_url: URL of the careers/jobs page
        
    Returns:
        List[Dict]: List of job dictionaries with keys:
            - title: Job title
            - company: Company name
            - location: Job location
            - url: Job posting URL
            - jd_text: Job description text
            - source: "Lever"
    
    Example:
        jobs = await scrape_lever("https://jobs.lever.co/company")
        for job in jobs:
            print(f"{job['title']} at {job['company']}")
    """
    logger.info(f"Scraping Lever board: {board_url}")
    
    try:
        async with LeverScraper(delay_min=1.0, delay_max=3.0) as scraper:
            jobs = await scraper.scrape_board(board_url, max_pages=5)
        
        # Deduplicate by URL
        unique_jobs = dedupe_jobs_by_url(jobs)
        
        logger.info(f"Lever scraping completed: {len(unique_jobs)} unique jobs")
        return unique_jobs
        
    except Exception as e:
        logger.error(f"Lever scraping failed for {board_url}: {e}")
        raise LeverScrapeError(f"Scraping failed: {e}")


# Synchronous wrapper for compatibility
def scrape_lever_sync(board_url: str) -> List[Dict[str, Any]]:
    """
    Synchronous wrapper for scrape_lever.
    
    Args:
        board_url: URL of the careers/jobs page
        
    Returns:
        List[Dict]: List of job dictionaries
    """
    try:
        # Check if we're already in an event loop
        try:
            loop = asyncio.get_running_loop()
            # If we're in a loop, we need to run in a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, scrape_lever(board_url))
                return future.result()
        except RuntimeError:
            # No event loop running, we can use asyncio.run
            return asyncio.run(scrape_lever(board_url))
            
    except Exception as e:
        logger.error(f"Synchronous lever scraping failed: {e}")
        raise LeverScrapeError(f"Sync scraping failed: {e}")
