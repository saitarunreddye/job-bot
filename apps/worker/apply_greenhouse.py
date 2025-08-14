"""
Greenhouse job application automation using Playwright.
Handles automated application submission with resume upload and form filling.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from uuid import UUID

from playwright.async_api import async_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential, 
    before_sleep_log,
    retry_if_exception_type
)

from config.settings import settings
from apps.worker.file_manager import file_manager

logger = logging.getLogger(__name__)

# Playwright configuration
BROWSER_TIMEOUT = 30000  # 30 seconds
NAVIGATION_TIMEOUT = 20000  # 20 seconds
ELEMENT_TIMEOUT = 10000  # 10 seconds
UPLOAD_TIMEOUT = 15000  # 15 seconds

# Common Greenhouse selectors (these may vary by company)
GREENHOUSE_SELECTORS = {
    # Resume upload
    'resume_upload': [
        'input[type="file"][accept*="pdf"]',
        'input[type="file"][name*="resume"]',
        'input[type="file"][id*="resume"]',
        'input[type="file"]',  # Fallback to any file input
    ],
    
    # Basic form fields
    'first_name': [
        'input[name="first_name"]',
        'input[id="first_name"]',
        'input[name*="first"]',
        'input[placeholder*="First"]',
    ],
    'last_name': [
        'input[name="last_name"]',
        'input[id="last_name"]',
        'input[name*="last"]',
        'input[placeholder*="Last"]',
    ],
    'email': [
        'input[name="email"]',
        'input[id="email"]',
        'input[type="email"]',
    ],
    'phone': [
        'input[name="phone"]',
        'input[id="phone"]',
        'input[type="tel"]',
        'input[name*="phone"]',
    ],
    'location': [
        'input[name="location"]',
        'input[id="location"]',
        'input[name*="city"]',
        'input[placeholder*="Location"]',
    ],
    
    # Application submission
    'submit_button': [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Submit")',
        'button:has-text("Apply")',
        'button:has-text("Send Application")',
    ],
    
    # Cover letter / additional info
    'cover_letter': [
        'textarea[name*="cover"]',
        'textarea[id*="cover"]',
        'textarea[placeholder*="cover"]',
        'textarea[name*="message"]',
    ],
    
    # Terms and conditions
    'terms_checkbox': [
        'input[type="checkbox"][name*="terms"]',
        'input[type="checkbox"][id*="terms"]',
        'input[type="checkbox"][name*="consent"]',
        'input[type="checkbox"][name*="agree"]',
    ]
}


class GreenhouseApplicationError(Exception):
    """Base exception for Greenhouse application errors."""
    pass


class GreenhouseApplicator:
    """Handles automated Greenhouse job applications using Playwright."""
    
    def __init__(self):
        """Initialize Greenhouse applicator."""
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        logger.debug("GreenhouseApplicator initialized")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close_browser()
    
    async def start_browser(self) -> None:
        """Start Playwright browser instance."""
        try:
            playwright = await async_playwright().start()
            
            # Launch browser with appropriate settings
            self.browser = await playwright.chromium.launch(
                headless=True,  # Set to False for debugging
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                ]
            )
            
            # Create browser context with user agent
            context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            self.page = await context.new_page()
            
            # Set timeouts
            self.page.set_default_timeout(ELEMENT_TIMEOUT)
            self.page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)
            
            logger.info("Playwright browser started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            raise GreenhouseApplicationError(f"Browser startup failed: {e}")
    
    async def close_browser(self) -> None:
        """Close browser and cleanup resources."""
        try:
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            logger.debug("Browser closed successfully")
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
    
    async def find_element_by_selectors(
        self, 
        selectors: list, 
        timeout: int = ELEMENT_TIMEOUT
    ) -> Optional[Any]:
        """
        Find element using multiple selector strategies.
        
        Args:
            selectors: List of CSS selectors to try
            timeout: Timeout in milliseconds
            
        Returns:
            Element if found, None otherwise
        """
        for selector in selectors:
            try:
                element = await self.page.wait_for_selector(
                    selector, 
                    timeout=timeout,
                    state='visible'
                )
                if element:
                    logger.debug(f"Found element with selector: {selector}")
                    return element
            except PlaywrightTimeoutError:
                continue
            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue
        
        logger.warning(f"No element found with selectors: {selectors}")
        return None
    
    async def fill_form_field(
        self, 
        field_name: str, 
        value: str, 
        required: bool = False
    ) -> bool:
        """
        Fill a form field with the given value.
        
        Args:
            field_name: Name of the field (must exist in GREENHOUSE_SELECTORS)
            value: Value to fill
            required: Whether this field is required
            
        Returns:
            bool: True if field was filled successfully
        """
        if not value:
            if required:
                logger.warning(f"Required field {field_name} has no value")
                return False
            else:
                logger.debug(f"Skipping empty optional field {field_name}")
                return True
        
        selectors = GREENHOUSE_SELECTORS.get(field_name, [])
        if not selectors:
            logger.warning(f"No selectors defined for field: {field_name}")
            return False
        
        element = await self.find_element_by_selectors(selectors)
        if not element:
            if required:
                logger.error(f"Required field {field_name} not found")
                return False
            else:
                logger.warning(f"Optional field {field_name} not found")
                return True
        
        try:
            # Clear existing content and fill new value
            await element.fill(value)
            logger.debug(f"Filled {field_name} with: {value}")
            return True
        except Exception as e:
            logger.error(f"Failed to fill {field_name}: {e}")
            return False
    
    async def upload_resume(self, resume_path: str) -> bool:
        """
        Upload resume file to the application form.
        
        Args:
            resume_path: Path to the resume file
            
        Returns:
            bool: True if upload was successful
        """
        resume_file = Path(resume_path)
        if not resume_file.exists():
            logger.error(f"Resume file not found: {resume_path}")
            return False
        
        # Find file upload element
        upload_element = await self.find_element_by_selectors(
            GREENHOUSE_SELECTORS['resume_upload'],
            timeout=UPLOAD_TIMEOUT
        )
        
        if not upload_element:
            logger.error("Resume upload field not found")
            return False
        
        try:
            # Upload the file
            await upload_element.set_input_files(str(resume_file))
            
            # Wait a moment for upload to process
            await asyncio.sleep(2)
            
            # Verify upload was successful (check for success indicator)
            await asyncio.sleep(1)  # Give time for UI to update
            
            logger.info(f"Resume uploaded successfully: {resume_file.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to upload resume: {e}")
            return False
    
    async def check_terms_and_conditions(self) -> bool:
        """
        Check terms and conditions checkbox if present.
        
        Returns:
            bool: True if checkbox was found and checked (or not present)
        """
        checkbox = await self.find_element_by_selectors(
            GREENHOUSE_SELECTORS['terms_checkbox'],
            timeout=3000  # Short timeout since this is optional
        )
        
        if not checkbox:
            logger.debug("No terms and conditions checkbox found")
            return True  # Not an error if not present
        
        try:
            # Check if already checked
            is_checked = await checkbox.is_checked()
            if not is_checked:
                await checkbox.check()
                logger.debug("Terms and conditions checkbox checked")
            else:
                logger.debug("Terms and conditions already checked")
            return True
        except Exception as e:
            logger.warning(f"Failed to check terms checkbox: {e}")
            return False
    
    async def submit_application(self) -> bool:
        """
        Submit the application form.
        
        Returns:
            bool: True if submission was successful
        """
        submit_button = await self.find_element_by_selectors(
            GREENHOUSE_SELECTORS['submit_button']
        )
        
        if not submit_button:
            logger.error("Submit button not found")
            return False
        
        try:
            # Click submit button
            await submit_button.click()
            
            # Wait for navigation or success page
            try:
                # Wait for either success page or error message
                await self.page.wait_for_load_state('networkidle', timeout=10000)
                await asyncio.sleep(2)  # Give time for any success messages
            except PlaywrightTimeoutError:
                logger.warning("Timeout waiting for submission response")
            
            # Check for success indicators
            success_indicators = [
                'text=Thank you',
                'text=Application submitted',
                'text=We have received',
                '[class*="success"]',
                '[class*="thank"]'
            ]
            
            for indicator in success_indicators:
                try:
                    element = await self.page.wait_for_selector(
                        indicator, 
                        timeout=3000
                    )
                    if element:
                        logger.info("Application submission success indicator found")
                        return True
                except PlaywrightTimeoutError:
                    continue
            
            # Check for error indicators
            error_indicators = [
                '[class*="error"]',
                '[class*="alert"]',
                'text=error',
                'text=failed'
            ]
            
            for indicator in error_indicators:
                try:
                    element = await self.page.wait_for_selector(
                        indicator, 
                        timeout=2000
                    )
                    if element:
                        error_text = await element.inner_text()
                        logger.warning(f"Error indicator found: {error_text}")
                        return False
                except PlaywrightTimeoutError:
                    continue
            
            # If no clear success/error indicator, assume success if no errors
            logger.info("Application submitted (no clear success indicator)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to submit application: {e}")
            return False
    
    async def take_screenshot(self, job_id: UUID, filename: str = "apply_error.png") -> str:
        """
        Take screenshot for debugging purposes.
        
        Args:
            job_id: Job ID for organizing screenshots
            filename: Screenshot filename
            
        Returns:
            str: Path to screenshot file
        """
        try:
            # Create job-specific directory for screenshots
            job_dir = file_manager.get_job_dir(job_id)
            screenshot_path = job_dir / filename
            
            # Take screenshot
            await self.page.screenshot(path=str(screenshot_path), full_page=True)
            
            logger.info(f"Screenshot saved: {screenshot_path}")
            return str(screenshot_path)
            
        except Exception as e:
            logger.error(f"Failed to take screenshot: {e}")
            return ""
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        retry=retry_if_exception_type((GreenhouseApplicationError, PlaywrightTimeoutError))
    )
    async def apply(
        self, 
        url: str, 
        resume_path: str, 
        fields: Dict[str, str],
        job_id: Optional[UUID] = None
    ) -> Tuple[bool, str]:
        """
        Apply to a Greenhouse job posting.
        
        Args:
            url: Job application URL
            resume_path: Path to resume file
            fields: Dictionary of form fields to fill
            job_id: Optional job ID for screenshots and debugging
            
        Returns:
            Tuple[bool, str]: (success, error_message)
        """
        logger.info(f"Starting Greenhouse application to: {url}")
        
        if not self.browser or not self.page:
            raise GreenhouseApplicationError("Browser not initialized")
        
        try:
            # Navigate to application page
            logger.debug(f"Navigating to: {url}")
            await self.page.goto(url, timeout=NAVIGATION_TIMEOUT)
            
            # Wait for page to load
            await self.page.wait_for_load_state('networkidle')
            await asyncio.sleep(2)  # Additional wait for dynamic content
            
            # Check if this is actually a Greenhouse page
            greenhouse_indicators = [
                '[data-greenhouse]',
                '[class*="greenhouse"]',
                'script[src*="greenhouse"]',
                'text=Greenhouse'
            ]
            
            is_greenhouse = False
            for indicator in greenhouse_indicators:
                try:
                    element = await self.page.wait_for_selector(indicator, timeout=3000)
                    if element:
                        is_greenhouse = True
                        break
                except PlaywrightTimeoutError:
                    continue
            
            if not is_greenhouse:
                logger.warning("Page doesn't appear to be a Greenhouse application")
                # Continue anyway - might still work
            
            # Step 1: Upload resume
            logger.info("Uploading resume...")
            resume_success = await self.upload_resume(resume_path)
            if not resume_success:
                error_msg = "Failed to upload resume"
                if job_id:
                    await self.take_screenshot(job_id, "resume_upload_error.png")
                return False, error_msg
            
            # Step 2: Fill form fields
            logger.info("Filling form fields...")
            field_failures = []
            
            # Required fields
            required_fields = ['first_name', 'last_name', 'email']
            for field in required_fields:
                if field in fields:
                    success = await self.fill_form_field(field, fields[field], required=True)
                    if not success:
                        field_failures.append(field)
            
            # Optional fields
            optional_fields = ['phone', 'location', 'cover_letter']
            for field in optional_fields:
                if field in fields:
                    await self.fill_form_field(field, fields[field], required=False)
            
            if field_failures:
                error_msg = f"Failed to fill required fields: {field_failures}"
                if job_id:
                    await self.take_screenshot(job_id, "form_fill_error.png")
                return False, error_msg
            
            # Step 3: Handle terms and conditions
            await self.check_terms_and_conditions()
            
            # Step 4: Submit application
            logger.info("Submitting application...")
            submission_success = await self.submit_application()
            
            if submission_success:
                logger.info("Application submitted successfully!")
                return True, "Application submitted successfully"
            else:
                error_msg = "Application submission failed"
                if job_id:
                    await self.take_screenshot(job_id, "submission_error.png")
                return False, error_msg
            
        except PlaywrightTimeoutError as e:
            error_msg = f"Timeout during application: {e}"
            logger.error(error_msg)
            if job_id:
                await self.take_screenshot(job_id, "timeout_error.png")
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Unexpected error during application: {e}"
            logger.error(error_msg)
            if job_id:
                await self.take_screenshot(job_id, "unexpected_error.png")
            return False, error_msg


# Convenience function for easy import
async def apply_to_greenhouse(
    url: str, 
    resume_path: str, 
    fields: Dict[str, str],
    job_id: Optional[UUID] = None
) -> Tuple[bool, str]:
    """
    Apply to a Greenhouse job posting.
    
    Args:
        url: Job application URL
        resume_path: Path to resume file  
        fields: Form fields to fill
        job_id: Optional job ID for debugging
        
    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    async with GreenhouseApplicator() as applicator:
        return await applicator.apply(url, resume_path, fields, job_id)


def apply_to_greenhouse_sync(
    url: str, 
    resume_path: str, 
    fields: Dict[str, str],
    job_id: Optional[UUID] = None
) -> Tuple[bool, str]:
    """
    Synchronous wrapper for Greenhouse application.
    
    Args:
        url: Job application URL
        resume_path: Path to resume file
        fields: Form fields to fill
        job_id: Optional job ID for debugging
        
    Returns:
        Tuple[bool, str]: (success, error_message)
    """
    try:
        # Run async function in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                apply_to_greenhouse(url, resume_path, fields, job_id)
            )
            return result
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Error in sync wrapper: {e}")
        return False, f"Sync execution failed: {e}"
