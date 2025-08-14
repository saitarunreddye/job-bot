"""
Truth verification module for application content.
Ensures all claims in resumes and cover letters are verifiable from achievement_bank.json.
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any, Optional

from config.settings import settings

logger = logging.getLogger(__name__)


class TruthVerificationError(Exception):
    """Raised when content contains unverifiable claims."""
    pass


class TruthVerifier:
    """Verifies that application content only contains truthful, verifiable claims."""
    
    def __init__(self, achievement_bank_path: Optional[str] = None):
        """
        Initialize truth verifier.
        
        Args:
            achievement_bank_path: Path to achievement bank JSON file
        """
        self.achievement_bank_path = achievement_bank_path or "config/achievement_bank.json"
        self.achievement_bank = self._load_achievement_bank()
        
        # Compile prohibited patterns for efficient checking
        self._compile_prohibited_patterns()
        
        logger.debug(f"TruthVerifier initialized with bank: {self.achievement_bank_path}")
    
    def _load_achievement_bank(self) -> Dict[str, Any]:
        """Load and parse the achievement bank JSON file."""
        try:
            with open(self.achievement_bank_path, 'r', encoding='utf-8') as f:
                bank = json.load(f)
            
            logger.info(f"Loaded achievement bank with {len(bank.get('technical_skills', {}).get('programming_languages', []))} programming languages")
            return bank
            
        except FileNotFoundError:
            logger.error(f"Achievement bank not found: {self.achievement_bank_path}")
            raise TruthVerificationError(f"Achievement bank file not found: {self.achievement_bank_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in achievement bank: {e}")
            raise TruthVerificationError(f"Invalid achievement bank JSON: {e}")
    
    def _compile_prohibited_patterns(self) -> None:
        """Compile regex patterns for prohibited claims."""
        self.prohibited_patterns = []
        
        prohibited = self.achievement_bank.get('prohibited_claims', {})
        
        # Add all prohibited claim lists
        for category, claims in prohibited.items():
            for claim in claims:
                # Create case-insensitive regex pattern
                pattern = re.compile(re.escape(claim).replace(r'\[technology.*?\]', r'.*?'), re.IGNORECASE)
                self.prohibited_patterns.append((category, claim, pattern))
        
        # Add experience year patterns that exceed max allowed
        max_years = self.achievement_bank.get('verification_rules', {}).get('max_experience_years', 5)
        
        # Pattern for "X+ years" where X > max_years
        for years in range(max_years + 1, 20):  # Check up to 20 years
            pattern = re.compile(rf'\b{years}\+?\s*years?\b', re.IGNORECASE)
            self.prohibited_patterns.append(('experience_inflation', f'{years}+ years', pattern))
        
        # Pattern for "over X years" where X >= max_years
        for years in range(max_years, 15):
            pattern = re.compile(rf'\bover\s+{years}\s*years?\b', re.IGNORECASE)
            self.prohibited_patterns.append(('experience_inflation', f'over {years} years', pattern))
        
        logger.debug(f"Compiled {len(self.prohibited_patterns)} prohibited patterns")
    
    def verify_content(self, content: str, content_type: str = "general") -> Dict[str, Any]:
        """
        Verify that content contains only truthful, verifiable claims.
        
        Args:
            content: Text content to verify
            content_type: Type of content (resume, cover_letter, linkedin, etc.)
            
        Returns:
            Dict with verification results
            
        Raises:
            TruthVerificationError: If content contains unverifiable claims
        """
        logger.debug(f"Verifying {content_type} content ({len(content)} chars)")
        
        verification_result = {
            'content_type': content_type,
            'verified': True,
            'issues': [],
            'warnings': [],
            'technologies_mentioned': [],
            'skills_mentioned': [],
            'experience_claims': [],
            'achievement_claims': []
        }
        
        # Check for prohibited claims
        prohibited_found = self._check_prohibited_claims(content)
        if prohibited_found:
            verification_result['issues'].extend(prohibited_found)
            verification_result['verified'] = False
        
        # Verify technology claims
        tech_issues = self._verify_technology_claims(content)
        if tech_issues:
            verification_result['issues'].extend(tech_issues)
            verification_result['verified'] = False
        
        # Verify experience claims
        exp_issues = self._verify_experience_claims(content)
        if exp_issues:
            verification_result['issues'].extend(exp_issues)
            verification_result['verified'] = False
        
        # Verify quantified achievements
        achievement_issues = self._verify_achievement_claims(content)
        if achievement_issues:
            verification_result['issues'].extend(achievement_issues)
            verification_result['verified'] = False
        
        # Extract mentioned technologies and skills for reporting
        verification_result['technologies_mentioned'] = self._extract_technologies(content)
        verification_result['skills_mentioned'] = self._extract_skills(content)
        
        if not verification_result['verified']:
            issues_summary = '; '.join([issue['description'] for issue in verification_result['issues']])
            raise TruthVerificationError(
                f"Content verification failed for {content_type}. Issues: {issues_summary}"
            )
        
        logger.info(f"Content verification passed for {content_type}")
        return verification_result
    
    def _check_prohibited_claims(self, content: str) -> List[Dict[str, Any]]:
        """Check for prohibited claims using compiled patterns."""
        issues = []
        
        for category, claim, pattern in self.prohibited_patterns:
            matches = pattern.finditer(content)
            for match in matches:
                issues.append({
                    'type': 'prohibited_claim',
                    'category': category,
                    'claim': claim,
                    'found_text': match.group(0),
                    'position': match.span(),
                    'description': f"Prohibited claim found: '{match.group(0)}' (category: {category})"
                })
        
        return issues
    
    def _verify_technology_claims(self, content: str) -> List[Dict[str, Any]]:
        """Verify that technology claims are backed by achievement bank."""
        issues = []
        
        # Get allowed technologies from achievement bank
        allowed_techs = set()
        tech_skills = self.achievement_bank.get('technical_skills', {})
        
        for lang in tech_skills.get('programming_languages', []):
            if lang.get('professional_use', False):
                allowed_techs.add(lang['name'].lower())
                for framework in lang.get('frameworks', []):
                    allowed_techs.add(framework.lower())
        
        for tech in tech_skills.get('technologies', []):
            if tech.get('professional_use', False):
                allowed_techs.add(tech['name'].lower())
                for service in tech.get('services', []):
                    allowed_techs.add(service.lower())
                for tool in tech.get('tools', []):
                    allowed_techs.add(tool.lower())
        
        # Check for technology mentions in content
        # This is a simple approach - could be enhanced with NLP
        words = re.findall(r'\b\w+\b', content.lower())
        common_techs = [
            'python', 'javascript', 'react', 'django', 'fastapi', 'docker', 'kubernetes',
            'aws', 'postgres', 'mysql', 'redis', 'jenkins', 'git', 'linux', 'nodejs'
        ]
        
        for tech in common_techs:
            if tech in words and tech not in allowed_techs:
                issues.append({
                    'type': 'unverified_technology',
                    'technology': tech,
                    'description': f"Technology '{tech}' mentioned but not in achievement bank professional skills"
                })
        
        return issues
    
    def _verify_experience_claims(self, content: str) -> List[Dict[str, Any]]:
        """Verify experience year claims against achievement bank."""
        issues = []
        
        max_years = self.achievement_bank.get('verification_rules', {}).get('max_experience_years', 5)
        
        # Pattern for experience claims
        exp_patterns = [
            r'(\d+)\+?\s*years?\s+(?:of\s+)?experience',
            r'experience\s+(?:of\s+)?(\d+)\+?\s*years?',
            r'(\d+)\+?\s*years?\s+(?:in|with|using)',
        ]
        
        for pattern in exp_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                years_str = match.group(1)
                try:
                    years = int(years_str)
                    if years > max_years:
                        issues.append({
                            'type': 'inflated_experience',
                            'claimed_years': years,
                            'max_allowed': max_years,
                            'found_text': match.group(0),
                            'description': f"Experience claim of {years} years exceeds verified maximum of {max_years}"
                        })
                except ValueError:
                    continue
        
        return issues
    
    def _verify_achievement_claims(self, content: str) -> List[Dict[str, Any]]:
        """Verify quantified achievement claims against achievement bank."""
        issues = []
        
        # Get verified achievements
        verified_achievements = {
            achievement['description'].lower(): achievement
            for achievement in self.achievement_bank.get('achievements', [])
            if achievement.get('quantifiable', False)
        }
        
        # Pattern for percentage improvements
        percentage_patterns = [
            r'(?:improved|increased|reduced|decreased|optimized).*?by\s+(\d+)%',
            r'(\d+)%\s+(?:improvement|increase|reduction|decrease)',
        ]
        
        for pattern in percentage_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                percentage_str = match.group(1)
                try:
                    percentage = int(percentage_str)
                    
                    # Check if this improvement is verified
                    found_text = match.group(0).lower()
                    verified = False
                    
                    for verified_desc, achievement in verified_achievements.items():
                        if any(keyword in found_text for keyword in ['performance', 'response', 'time']):
                            if 'performance' in verified_desc and achievement.get('verification'):
                                verified = True
                                break
                    
                    if not verified and percentage > 50:  # Flag large claims
                        issues.append({
                            'type': 'unverified_achievement',
                            'claimed_improvement': f"{percentage}%",
                            'found_text': match.group(0),
                            'description': f"Large improvement claim ({percentage}%) not found in verified achievements"
                        })
                        
                except ValueError:
                    continue
        
        return issues
    
    def _extract_technologies(self, content: str) -> List[str]:
        """Extract technology mentions from content."""
        tech_skills = self.achievement_bank.get('technical_skills', {})
        mentioned_techs = []
        
        content_lower = content.lower()
        
        for lang in tech_skills.get('programming_languages', []):
            if lang['name'].lower() in content_lower:
                mentioned_techs.append(lang['name'])
            for framework in lang.get('frameworks', []):
                if framework.lower() in content_lower:
                    mentioned_techs.append(framework)
        
        for tech in tech_skills.get('technologies', []):
            if tech['name'].lower() in content_lower:
                mentioned_techs.append(tech['name'])
        
        return list(set(mentioned_techs))
    
    def _extract_skills(self, content: str) -> List[str]:
        """Extract skill mentions from content."""
        soft_skills = self.achievement_bank.get('soft_skills', [])
        mentioned_skills = []
        
        content_lower = content.lower()
        
        for skill_info in soft_skills:
            skill_name = skill_info['skill'].lower()
            if skill_name in content_lower:
                mentioned_skills.append(skill_info['skill'])
        
        return mentioned_skills
    
    def get_verified_skills_for_job(self, job_skills: List[str]) -> Dict[str, Any]:
        """
        Get verified skills that match job requirements.
        
        Args:
            job_skills: List of skills extracted from job description
            
        Returns:
            Dict with matched skills and proficiency levels
        """
        matched_skills = {}
        
        # Check programming languages
        for lang in self.achievement_bank.get('technical_skills', {}).get('programming_languages', []):
            lang_name = lang['name'].lower()
            if any(skill.lower() == lang_name for skill in job_skills):
                matched_skills[lang['name']] = {
                    'type': 'programming_language',
                    'years_experience': lang['years_experience'],
                    'proficiency': lang['proficiency'],
                    'professional_use': lang['professional_use'],
                    'frameworks': lang.get('frameworks', [])
                }
        
        # Check technologies
        for tech in self.achievement_bank.get('technical_skills', {}).get('technologies', []):
            tech_name = tech['name'].lower()
            if any(skill.lower() == tech_name for skill in job_skills):
                matched_skills[tech['name']] = {
                    'type': 'technology',
                    'years_experience': tech['years_experience'],
                    'proficiency': tech['proficiency'],
                    'professional_use': tech['professional_use']
                }
        
        return matched_skills
    
    def generate_truthful_bullets(self, job_skills: List[str], max_bullets: int = 5) -> List[str]:
        """
        Generate truthful resume bullets based on verified achievements and job skills.
        
        Args:
            job_skills: Skills required for the job
            max_bullets: Maximum number of bullets to generate
            
        Returns:
            List of truthful, verified bullet points
        """
        bullets = []
        matched_skills = self.get_verified_skills_for_job(job_skills)
        
        # Create bullets from verified achievements
        for achievement in self.achievement_bank.get('achievements', [])[:max_bullets]:
            bullet = achievement['description']
            
            # Add context if available
            if achievement.get('context'):
                bullet += f" in {achievement['context']}"
            
            bullets.append(bullet)
        
        # Add skill-based bullets for matched skills
        for skill_name, skill_info in matched_skills.items():
            if len(bullets) >= max_bullets:
                break
                
            if skill_info['professional_use']:
                years = skill_info['years_experience']
                proficiency = skill_info['proficiency']
                
                if years >= 3:
                    bullet = f"Developed applications using {skill_name} with {proficiency} proficiency"
                elif years >= 1:
                    bullet = f"Utilized {skill_name} for software development projects"
                else:
                    bullet = f"Applied {skill_name} in professional development work"
                
                bullets.append(bullet)
        
        return bullets[:max_bullets]


# Global truth verifier instance
truth_verifier = TruthVerifier()


# Convenience functions
def verify_content(content: str, content_type: str = "general") -> Dict[str, Any]:
    """Verify content for truthfulness."""
    return truth_verifier.verify_content(content, content_type)


def get_verified_skills_for_job(job_skills: List[str]) -> Dict[str, Any]:
    """Get verified skills matching job requirements."""
    return truth_verifier.get_verified_skills_for_job(job_skills)


def generate_truthful_bullets(job_skills: List[str], max_bullets: int = 5) -> List[str]:
    """Generate truthful resume bullets."""
    return truth_verifier.generate_truthful_bullets(job_skills, max_bullets)
