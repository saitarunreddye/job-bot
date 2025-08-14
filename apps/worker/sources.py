"""
Job source registry for managing different job board scrapers.
Provides a unified interface for all job scraping sources.
"""

import logging
from typing import Dict, List, Any, Callable, Tuple
from dataclasses import dataclass

from config.settings import settings
from apps.worker.scraper_greenhouse import scrape_greenhouse_sync
from apps.worker.scraper_lever import scrape_lever_sync
from apps.worker.scraper_ashby import scrape_ashby_sync

logger = logging.getLogger(__name__)


@dataclass
class JobSource:
    """
    Data class representing a job scraping source.
    """
    name: str
    scraper_func: Callable[[str], List[Dict[str, Any]]]
    boards: List[str]
    description: str
    enabled: bool = True


class JobSourceRegistry:
    """
    Registry for managing job scraping sources.
    Provides centralized access to all configured scrapers.
    """
    
    def __init__(self):
        """Initialize the source registry with all available sources."""
        self._sources: Dict[str, JobSource] = {}
        self._register_default_sources()
    
    def _register_default_sources(self):
        """Register all default job sources from settings."""
        
        # Greenhouse sources
        if settings.greenhouse_boards:
            self.register_source(JobSource(
                name="greenhouse",
                scraper_func=scrape_greenhouse_sync,
                boards=settings.greenhouse_boards,
                description="Greenhouse-powered career pages",
                enabled=True
            ))
        
        # Lever sources
        if settings.lever_boards:
            self.register_source(JobSource(
                name="lever",
                scraper_func=scrape_lever_sync,
                boards=settings.lever_boards,
                description="Lever-powered career pages",
                enabled=True
            ))
        
        # Ashby sources
        if settings.ashby_boards:
            self.register_source(JobSource(
                name="ashby",
                scraper_func=scrape_ashby_sync,
                boards=settings.ashby_boards,
                description="Ashby-powered career pages",
                enabled=True
            ))
        
        logger.info(f"Registered {len(self._sources)} job sources")
    
    def register_source(self, source: JobSource):
        """
        Register a new job source.
        
        Args:
            source: JobSource instance to register
        """
        self._sources[source.name] = source
        logger.debug(f"Registered source: {source.name} with {len(source.boards)} boards")
    
    def get_source(self, name: str) -> JobSource:
        """
        Get a specific job source by name.
        
        Args:
            name: Name of the source to retrieve
            
        Returns:
            JobSource: The requested source
            
        Raises:
            KeyError: If source is not found
        """
        if name not in self._sources:
            raise KeyError(f"Source '{name}' not found. Available sources: {list(self._sources.keys())}")
        
        return self._sources[name]
    
    def get_all_sources(self) -> Dict[str, JobSource]:
        """
        Get all registered sources.
        
        Returns:
            Dict[str, JobSource]: All registered sources
        """
        return self._sources.copy()
    
    def get_enabled_sources(self) -> Dict[str, JobSource]:
        """
        Get only enabled sources.
        
        Returns:
            Dict[str, JobSource]: Enabled sources only
        """
        return {name: source for name, source in self._sources.items() if source.enabled}
    
    def get_source_names(self) -> List[str]:
        """
        Get list of all source names.
        
        Returns:
            List[str]: List of source names
        """
        return list(self._sources.keys())
    
    def get_enabled_source_names(self) -> List[str]:
        """
        Get list of enabled source names.
        
        Returns:
            List[str]: List of enabled source names
        """
        return [name for name, source in self._sources.items() if source.enabled]
    
    def enable_source(self, name: str):
        """
        Enable a specific source.
        
        Args:
            name: Name of the source to enable
        """
        if name in self._sources:
            self._sources[name].enabled = True
            logger.info(f"Enabled source: {name}")
        else:
            logger.warning(f"Cannot enable unknown source: {name}")
    
    def disable_source(self, name: str):
        """
        Disable a specific source.
        
        Args:
            name: Name of the source to disable
        """
        if name in self._sources:
            self._sources[name].enabled = False
            logger.info(f"Disabled source: {name}")
        else:
            logger.warning(f"Cannot disable unknown source: {name}")
    
    def get_total_boards(self) -> int:
        """
        Get total number of boards across all enabled sources.
        
        Returns:
            int: Total number of boards
        """
        return sum(len(source.boards) for source in self._sources.values() if source.enabled)
    
    def get_source_stats(self) -> Dict[str, Any]:
        """
        Get statistics about registered sources.
        
        Returns:
            Dict: Statistics including source counts, board counts, etc.
        """
        enabled_sources = self.get_enabled_sources()
        
        stats = {
            "total_sources": len(self._sources),
            "enabled_sources": len(enabled_sources),
            "disabled_sources": len(self._sources) - len(enabled_sources),
            "total_boards": sum(len(source.boards) for source in self._sources.values()),
            "enabled_boards": sum(len(source.boards) for source in enabled_sources.values()),
            "sources_by_type": {
                name: {
                    "boards": len(source.boards),
                    "enabled": source.enabled,
                    "description": source.description
                }
                for name, source in self._sources.items()
            }
        }
        
        return stats
    
    def scrape_all_sources(self, max_jobs_per_source: int = 50) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Scrape jobs from all enabled sources.
        
        Args:
            max_jobs_per_source: Maximum jobs to scrape per source
            
        Returns:
            Tuple[List[Dict], Dict[str, int]]: (all_jobs, jobs_per_source_count)
        """
        all_jobs = []
        jobs_per_source = {}
        
        enabled_sources = self.get_enabled_sources()
        logger.info(f"Scraping {len(enabled_sources)} enabled sources")
        
        for source_name, source in enabled_sources.items():
            try:
                logger.info(f"Scraping source: {source_name} ({len(source.boards)} boards)")
                source_jobs = []
                
                for board_url in source.boards:
                    try:
                        logger.debug(f"Scraping board: {board_url}")
                        board_jobs = source.scraper_func(board_url)
                        source_jobs.extend(board_jobs)
                        
                        # Limit per source if specified
                        if max_jobs_per_source and len(source_jobs) >= max_jobs_per_source:
                            source_jobs = source_jobs[:max_jobs_per_source]
                            logger.info(f"Limited {source_name} to {max_jobs_per_source} jobs")
                            break
                            
                    except Exception as e:
                        logger.error(f"Failed to scrape board {board_url}: {e}")
                        continue
                
                all_jobs.extend(source_jobs)
                jobs_per_source[source_name] = len(source_jobs)
                logger.info(f"Scraped {len(source_jobs)} jobs from {source_name}")
                
            except Exception as e:
                logger.error(f"Failed to scrape source {source_name}: {e}")
                jobs_per_source[source_name] = 0
                continue
        
        logger.info(f"Total jobs scraped: {len(all_jobs)} from {len(enabled_sources)} sources")
        return all_jobs, jobs_per_source
    
    def scrape_source(self, source_name: str, max_jobs: int = 50) -> List[Dict[str, Any]]:
        """
        Scrape jobs from a specific source.
        
        Args:
            source_name: Name of the source to scrape
            max_jobs: Maximum number of jobs to scrape
            
        Returns:
            List[Dict]: List of scraped jobs
            
        Raises:
            KeyError: If source is not found
            ValueError: If source is disabled
        """
        source = self.get_source(source_name)
        
        if not source.enabled:
            raise ValueError(f"Source '{source_name}' is disabled")
        
        logger.info(f"Scraping specific source: {source_name}")
        
        all_jobs = []
        for board_url in source.boards:
            try:
                board_jobs = source.scraper_func(board_url)
                all_jobs.extend(board_jobs)
                
                # Limit total jobs if specified
                if max_jobs and len(all_jobs) >= max_jobs:
                    all_jobs = all_jobs[:max_jobs]
                    break
                    
            except Exception as e:
                logger.error(f"Failed to scrape board {board_url}: {e}")
                continue
        
        logger.info(f"Scraped {len(all_jobs)} jobs from {source_name}")
        return all_jobs


# Global registry instance
job_source_registry = JobSourceRegistry()


# Convenience functions
def get_available_sources() -> List[str]:
    """Get list of all available source names."""
    return job_source_registry.get_source_names()


def get_enabled_sources() -> List[str]:
    """Get list of enabled source names."""
    return job_source_registry.get_enabled_source_names()


def scrape_all_sources(max_jobs_per_source: int = 50) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Scrape jobs from all enabled sources."""
    return job_source_registry.scrape_all_sources(max_jobs_per_source)


def scrape_source(source_name: str, max_jobs: int = 50) -> List[Dict[str, Any]]:
    """Scrape jobs from a specific source."""
    return job_source_registry.scrape_source(source_name, max_jobs)


def get_source_stats() -> Dict[str, Any]:
    """Get statistics about all sources."""
    return job_source_registry.get_source_stats()


def is_source_available(source_name: str) -> bool:
    """Check if a source is available."""
    try:
        job_source_registry.get_source(source_name)
        return True
    except KeyError:
        return False


def is_source_enabled(source_name: str) -> bool:
    """Check if a source is enabled."""
    try:
        source = job_source_registry.get_source(source_name)
        return source.enabled
    except KeyError:
        return False
