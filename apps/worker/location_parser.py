"""
Location and visa detection module for job postings.
Parses job descriptions and locations to extract visa sponsorship info and location data.
"""

import re
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LocationInfo:
    """Structured location information."""
    country: Optional[str] = None
    state_province: Optional[str] = None
    city: Optional[str] = None
    is_remote: bool = False
    remote_type: Optional[str] = None  # 'full', 'hybrid', 'occasional'
    coordinates: Optional[Tuple[float, float]] = None


@dataclass
class VisaInfo:
    """Visa sponsorship information."""
    visa_friendly: bool = False
    keywords: List[str] = None
    confidence: float = 0.0
    
    def __post_init__(self):
        if self.keywords is None:
            self.keywords = []


class VisaDetector:
    """Detects visa sponsorship mentions in job descriptions."""
    
    # Visa sponsorship keywords with confidence weights
    VISA_KEYWORDS = {
        # Direct sponsorship mentions
        'h-1b': 1.0,
        'h1b': 1.0,
        'h-1b sponsorship': 1.0,
        'h1b sponsorship': 1.0,
        'visa sponsorship': 1.0,
        'sponsor visa': 1.0,
        'sponsors visas': 1.0,
        'will sponsor': 1.0,
        'can sponsor': 1.0,
        'eligible for sponsorship': 1.0,
        
        # Student visa programs
        'opt': 0.9,
        'cpt': 0.9,
        'stem opt': 1.0,
        'f-1': 0.8,
        'f1': 0.8,
        'student visa': 0.8,
        
        # Other work visas
        'tn visa': 0.9,
        'tn-1': 0.9,
        'l-1': 0.8,
        'l1': 0.8,
        'o-1': 0.8,
        'e-3': 0.8,
        
        # General sponsorship terms
        'sponsorship available': 0.9,
        'sponsorship provided': 0.9,
        'immigration sponsorship': 1.0,
        'work authorization': 0.7,
        'employment authorization': 0.7,
        'ead': 0.6,
        
        # Less direct but positive indicators
        'international candidates': 0.6,
        'global talent': 0.5,
        'worldwide remote': 0.4,
    }
    
    # Negative keywords that indicate no sponsorship
    NEGATIVE_KEYWORDS = {
        'no sponsorship': -1.0,
        'no visa sponsorship': -1.0,
        'no h-1b': -1.0,
        'no h1b': -1.0,
        'us citizens only': -1.0,
        'citizenship required': -1.0,
        'must be authorized': -0.8,
        'authorized to work': -0.8,
        'work authorization required': -0.7,
        'eligible to work in us': -0.5,
        'us work authorization': -0.5,
    }
    
    def detect_visa_sponsorship(self, text: str) -> VisaInfo:
        """
        Detect visa sponsorship mentions in job text.
        
        Args:
            text: Job description and requirements text
            
        Returns:
            VisaInfo: Detected visa information
        """
        if not text:
            return VisaInfo()
        
        text_lower = text.lower()
        found_keywords = []
        total_score = 0.0
        
        # Check positive keywords
        for keyword, score in self.VISA_KEYWORDS.items():
            if keyword in text_lower:
                found_keywords.append(keyword)
                total_score += score
                logger.debug(f"Found visa keyword: '{keyword}' (score: {score})")
        
        # Check negative keywords
        for keyword, score in self.NEGATIVE_KEYWORDS.items():
            if keyword in text_lower:
                found_keywords.append(f"NOT: {keyword}")
                total_score += score
                logger.debug(f"Found negative visa keyword: '{keyword}' (score: {score})")
        
        # Calculate confidence and determine visa friendliness
        confidence = min(abs(total_score), 1.0)
        visa_friendly = total_score > 0.3  # Threshold for visa-friendly determination
        
        if found_keywords:
            logger.info(f"Visa detection: friendly={visa_friendly}, confidence={confidence:.2f}, keywords={found_keywords}")
        
        return VisaInfo(
            visa_friendly=visa_friendly,
            keywords=found_keywords,
            confidence=confidence
        )


class LocationParser:
    """Parses location information from job postings."""
    
    # US states mapping
    US_STATES = {
        'alabama': 'AL', 'alaska': 'AK', 'arizona': 'AZ', 'arkansas': 'AR', 'california': 'CA',
        'colorado': 'CO', 'connecticut': 'CT', 'delaware': 'DE', 'florida': 'FL', 'georgia': 'GA',
        'hawaii': 'HI', 'idaho': 'ID', 'illinois': 'IL', 'indiana': 'IN', 'iowa': 'IA',
        'kansas': 'KS', 'kentucky': 'KY', 'louisiana': 'LA', 'maine': 'ME', 'maryland': 'MD',
        'massachusetts': 'MA', 'michigan': 'MI', 'minnesota': 'MN', 'mississippi': 'MS', 'missouri': 'MO',
        'montana': 'MT', 'nebraska': 'NE', 'nevada': 'NV', 'new hampshire': 'NH', 'new jersey': 'NJ',
        'new mexico': 'NM', 'new york': 'NY', 'north carolina': 'NC', 'north dakota': 'ND', 'ohio': 'OH',
        'oklahoma': 'OK', 'oregon': 'OR', 'pennsylvania': 'PA', 'rhode island': 'RI', 'south carolina': 'SC',
        'south dakota': 'SD', 'tennessee': 'TN', 'texas': 'TX', 'utah': 'UT', 'vermont': 'VT',
        'virginia': 'VA', 'washington': 'WA', 'west virginia': 'WV', 'wisconsin': 'WI', 'wyoming': 'WY',
        'district of columbia': 'DC'
    }
    
    # Country patterns
    COUNTRY_PATTERNS = {
        'us': ['united states', 'usa', 'us', 'america'],
        'ca': ['canada', 'canadian'],
        'gb': ['united kingdom', 'uk', 'britain', 'england', 'scotland', 'wales'],
        'au': ['australia', 'australian'],
        'de': ['germany', 'german'],
        'fr': ['france', 'french'],
        'nl': ['netherlands', 'dutch'],
        'se': ['sweden', 'swedish'],
        'no': ['norway', 'norwegian'],
        'dk': ['denmark', 'danish'],
    }
    
    # Remote work patterns
    REMOTE_PATTERNS = {
        'full': [
            'fully remote', 'completely remote', '100% remote', 'remote only',
            'remote-first', 'remote work', 'work from home', 'wfh', 'distributed team',
            'anywhere in the world', 'location independent'
        ],
        'hybrid': [
            'hybrid', 'hybrid remote', 'remote hybrid', 'flexible remote',
            'part remote', 'partial remote', 'some remote', 'remote friendly',
            '2-3 days remote', 'remote 2-3 days'
        ],
        'occasional': [
            'remote optional', 'remote when needed', 'occasional remote',
            'remote as needed', 'flexible location'
        ]
    }
    
    def parse_location(self, location_text: str, description: str = "") -> LocationInfo:
        """
        Parse location information from job posting.
        
        Args:
            location_text: Primary location field
            description: Job description for additional context
            
        Returns:
            LocationInfo: Parsed location data
        """
        if not location_text and not description:
            return LocationInfo()
        
        combined_text = f"{location_text or ''} {description or ''}".lower()
        
        # Detect remote work
        remote_type = self._detect_remote_type(combined_text)
        is_remote = remote_type is not None
        
        # Parse geographic location
        country = self._detect_country(combined_text)
        state_province = None
        city = None
        
        if location_text:
            # Parse structured location (e.g., "San Francisco, CA, USA")
            location_parts = [part.strip() for part in location_text.split(',')]
            
            if len(location_parts) >= 2:
                city = location_parts[0]
                state_candidate = location_parts[1].lower()
                
                # Check if second part is a US state
                if state_candidate in self.US_STATES:
                    state_province = self.US_STATES[state_candidate]
                    country = 'US'
                elif any(state_candidate == abbr.lower() for abbr in self.US_STATES.values()):
                    state_province = state_candidate.upper()
                    country = 'US'
                else:
                    state_province = location_parts[1]
            
            elif len(location_parts) == 1:
                # Single location part - could be city, state, or country
                single_location = location_parts[0].lower()
                
                if single_location in self.US_STATES:
                    state_province = self.US_STATES[single_location]
                    country = 'US'
                elif any(single_location == abbr.lower() for abbr in self.US_STATES.values()):
                    state_province = single_location.upper()
                    country = 'US'
                else:
                    city = location_parts[0]
        
        # Override country if not detected from location parts
        if not country:
            country = self._detect_country(combined_text)
        
        logger.debug(f"Parsed location: country={country}, state={state_province}, city={city}, remote={remote_type}")
        
        return LocationInfo(
            country=country,
            state_province=state_province,
            city=city,
            is_remote=is_remote,
            remote_type=remote_type
        )
    
    def _detect_remote_type(self, text: str) -> Optional[str]:
        """Detect type of remote work from text."""
        text_lower = text.lower()
        
        for remote_type, patterns in self.REMOTE_PATTERNS.items():
            for pattern in patterns:
                if pattern in text_lower:
                    return remote_type
        
        return None
    
    def _detect_country(self, text: str) -> Optional[str]:
        """Detect country from text."""
        text_lower = text.lower()
        
        for country_code, patterns in self.COUNTRY_PATTERNS.items():
            for pattern in patterns:
                if pattern in text_lower:
                    return country_code.upper()
        
        return None


class JobLocationProcessor:
    """Main processor for job location and visa information."""
    
    def __init__(self):
        self.visa_detector = VisaDetector()
        self.location_parser = LocationParser()
    
    def process_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process job data to extract visa and location information.
        
        Args:
            job_data: Job data dictionary
            
        Returns:
            Dict with additional visa and location fields
        """
        # Extract text for analysis
        description = job_data.get('description', '') or ''
        requirements = job_data.get('requirements', '') or ''
        benefits = job_data.get('benefits', '') or ''
        location_text = job_data.get('location', '') or ''
        
        # Combine all text for visa detection
        full_text = f"{description} {requirements} {benefits}"
        
        # Detect visa sponsorship
        visa_info = self.visa_detector.detect_visa_sponsorship(full_text)
        
        # Parse location
        location_info = self.location_parser.parse_location(location_text, description)
        
        # Add new fields to job data
        enhanced_job = job_data.copy()
        enhanced_job.update({
            'visa_friendly': visa_info.visa_friendly,
            'visa_keywords': visa_info.keywords,
            'country': location_info.country,
            'state_province': location_info.state_province,
            'city': location_info.city,
            'is_remote': location_info.is_remote,
            'remote_type': location_info.remote_type,
            'coordinates': location_info.coordinates  # TODO: Add geocoding
        })
        
        logger.info(f"Job processed: visa_friendly={visa_info.visa_friendly}, "
                   f"location={location_info.country}/{location_info.state_province}/{location_info.city}, "
                   f"remote={location_info.remote_type}")
        
        return enhanced_job


# Global processor instance
job_location_processor = JobLocationProcessor()


# Convenience functions
def detect_visa_sponsorship(text: str) -> VisaInfo:
    """Detect visa sponsorship in text."""
    detector = VisaDetector()
    return detector.detect_visa_sponsorship(text)


def parse_job_location(location: str, description: str = "") -> LocationInfo:
    """Parse job location information."""
    parser = LocationParser()
    return parser.parse_location(location, description)


def process_job_location_data(job_data: Dict[str, Any]) -> Dict[str, Any]:
    """Process complete job for location and visa data."""
    return job_location_processor.process_job(job_data)
