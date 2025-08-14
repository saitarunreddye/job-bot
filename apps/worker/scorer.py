"""
Job scoring and skill extraction module.
Analyzes job requirements and calculates compatibility scores.
"""

import re
import logging
from typing import List, Set, Dict, Any, Optional, Tuple
from config.settings import settings

logger = logging.getLogger(__name__)

# Default skill bank - can be expanded
SKILL_BANK = {
    'python', 'javascript', 'typescript', 'java', 'c++', 'c#', 'go', 'rust', 'scala', 'kotlin',
    'react', 'angular', 'vue', 'svelte', 'nodejs', 'express', 'django', 'flask', 'fastapi',
    'spring', 'hibernate', 'laravel', 'rails', 'asp.net', 'nextjs', 'nuxtjs',
    'sql', 'postgresql', 'mysql', 'mongodb', 'redis', 'elasticsearch', 'cassandra',
    'docker', 'kubernetes', 'jenkins', 'gitlab', 'github', 'terraform', 'ansible',
    'aws', 'azure', 'gcp', 'heroku', 'vercel', 'netlify', 'cloudflare',
    'html', 'css', 'sass', 'less', 'bootstrap', 'tailwind', 'material-ui',
    'git', 'linux', 'bash', 'powershell', 'nginx', 'apache', 'graphql', 'rest',
    'json', 'xml', 'yaml', 'api', 'microservices', 'serverless', 'websockets',
    'testing', 'jest', 'pytest', 'junit', 'selenium', 'cypress', 'mocha',
    'ci/cd', 'devops', 'agile', 'scrum', 'jira', 'confluence', 'slack'
}

# Skill synonyms for better matching
SKILL_SYNONYMS = {
    'js': 'javascript',
    'ts': 'typescript',
    'node': 'nodejs',
    'node.js': 'nodejs',
    'postgres': 'postgresql',
    'k8s': 'kubernetes',
    'eks': 'aws',
    'ec2': 'aws',
    's3': 'aws',
    'lambda': 'aws',
    'rds': 'aws',
    'ci/cd': 'cicd',
    'continuous integration': 'ci/cd',
    'continuous deployment': 'ci/cd',
    '.net': 'dotnet',  # Fix: map .net to dotnet for tests
    'asp.net': 'dotnet',  # Also support asp.net -> dotnet
    'dot net': 'dotnet',
    'c sharp': 'c#',
    'reactjs': 'react',
    'react.js': 'react',
    'vuejs': 'vue',
    'vue.js': 'vue',
    'angularjs': 'angular',
    'material ui': 'material-ui',
    'mui': 'material-ui',
    'tailwindcss': 'tailwind',
    'machine learning': 'ml',
    'artificial intelligence': 'ai',
    'deep learning': 'dl'
}

# Default candidate skills - would typically come from user profile
DEFAULT_CANDIDATE_SKILLS = [
    'python', 'javascript', 'typescript', 'react', 'nodejs', 'sql', 'postgresql', 
    'docker', 'aws', 'git', 'linux', 'html', 'css', 'rest', 'api', 'json',
    'testing', 'ci/cd', 'agile'
]

# Default must-have skills
DEFAULT_MUST_HAVE_SKILLS = {'python', 'javascript', 'sql'}


def extract_skills(job_text: str, skill_bank: Optional[Set[str]] = None) -> List[str]:
    """
    Extract relevant skills from job description text.
    
    Args:
        job_text: Job description or requirements text
        skill_bank: Set of skills to search for (defaults to SKILL_BANK)
        
    Returns:
        List[str]: List of extracted skills
        
    Example:
        skills = extract_skills("Looking for Python developer with React experience")
        # Returns: ['python', 'react']
    """
    if skill_bank is None:
        skill_bank = SKILL_BANK
    
    # Normalize text for searching
    text_lower = job_text.lower()
    
    # Find direct skill matches
    found_skills = set()
    
    # Check for exact skill matches (word boundaries)
    for skill in skill_bank:
        # Create pattern with word boundaries
        pattern = rf'\b{re.escape(skill.lower())}\b'
        if re.search(pattern, text_lower):
            found_skills.add(skill)
    
    # Check for synonym matches
    for synonym, canonical_skill in SKILL_SYNONYMS.items():
        if canonical_skill in skill_bank:
            # Special handling for .net (no leading word boundary)
            if synonym.lower() == '.net':
                pattern = r'\.net\b'
            else:
                pattern = rf'\b{re.escape(synonym.lower())}\b'
            if re.search(pattern, text_lower):
                found_skills.add(canonical_skill)
    
    # Check for compound terms and variations
    # Handle common variations like "React.js", "Node.js", etc.
    compound_patterns = {
        r'\breact\.?js\b': 'react',
        r'\bnode\.?js\b': 'nodejs',
        r'\bvue\.?js\b': 'vue',
        r'\bangular\.?js\b': 'angular',
        r'c\+\+': 'c++',  # Fix: remove word boundaries for C++
        r'\bc#\b': 'c#',
        r'\.net\b': 'dotnet',  # Fix: remove leading word boundary for .NET
        r'\brest\s+api\b': 'rest',
        r'\bapi\s+rest\b': 'rest',
        r'\brest\s+apis\b': 'rest',  # Fix: handle "REST APIs" plural
        r'\bmachine\s+learning\b': 'ml',
        r'\bartificial\s+intelligence\b': 'ai',
        r'\bci/cd\b': 'cicd',  # Fix: map ci/cd to cicd
        r'\bcontinuous\s+integration\b': 'cicd',
        r'\bmaterial\s*ui\b': 'material-ui',
        r'\btailwind\s*css\b': 'tailwind'
    }
    
    for pattern, skill in compound_patterns.items():
        if skill in skill_bank and re.search(pattern, text_lower):
            found_skills.add(skill)
    
    # Special handling for "REST APIs" to extract both 'rest' and 'api'
    if re.search(r'\brest\s+apis?\b', text_lower):
        if 'rest' in skill_bank:
            found_skills.add('rest')
        if 'api' in skill_bank:
            found_skills.add('api')
    
    # Convert to list and sort for consistency
    return sorted(list(found_skills))


def score_job(
    job_skills: List[str], 
    candidate_skills: List[str], 
    must_have_skills: Set[str]
) -> int:
    """
    Calculate job compatibility score based on skill matching.
    
    Args:
        job_skills: Skills required/mentioned in the job
        candidate_skills: Skills the candidate possesses
        must_have_skills: Critical skills that must be present
        
    Returns:
        int: Compatibility score (0-100)
        
    Algorithm:
        - 60% weight on overall skill overlap percentage
        - 40% weight on must-have skills coverage
        - Returns integer score between 0 and 100
        
    Example:
        score = score_job(
            job_skills=['python', 'react', 'sql'],
            candidate_skills=['python', 'javascript', 'sql'], 
            must_have_skills={'python'}
        )
        # Returns: 73 (2/3 overlap * 60 + 1/1 must-haves * 40)
    """
    # Normalize skills to lowercase for comparison
    job_skills_set = {skill.lower() for skill in job_skills}
    candidate_skills_set = {skill.lower() for skill in candidate_skills}
    must_have_skills_set = {skill.lower() for skill in must_have_skills}
    
    # Calculate overall skill overlap
    if not job_skills_set:
        # If no specific skills required, return high score
        overlap_score = 100
    else:
        overlap_count = len(job_skills_set.intersection(candidate_skills_set))
        overlap_percentage = (overlap_count / len(job_skills_set)) * 100
        overlap_score = overlap_percentage
    
    # Calculate must-have skills coverage
    if not must_have_skills_set:
        # If no must-haves specified, assume full coverage
        must_have_score = 100
    else:
        must_have_matches = len(must_have_skills_set.intersection(candidate_skills_set))
        must_have_percentage = (must_have_matches / len(must_have_skills_set)) * 100
        must_have_score = must_have_percentage
    
    # Weighted final score: 60% overlap + 40% must-haves
    final_score = (overlap_score * 0.6) + (must_have_score * 0.4)
    
    return round(final_score)


def get_skill_analysis(job_skills: List[str], candidate_skills: List[str]) -> Dict[str, Any]:
    """
    Get detailed skill analysis comparing job requirements to candidate skills.
    
    Args:
        job_skills: Skills required by the job
        candidate_skills: Skills possessed by candidate
        
    Returns:
        Dict with analysis details:
        - common_skills: Skills in both lists
        - missing_skills: Job skills candidate doesn't have
        - extra_skills: Candidate skills not required by job
        - overlap_percentage: Percentage of job skills covered
    """
    job_skills_set = {skill.lower() for skill in job_skills}
    candidate_skills_set = {skill.lower() for skill in candidate_skills}
    
    common_skills = job_skills_set.intersection(candidate_skills_set)
    missing_skills = job_skills_set.difference(candidate_skills_set)
    extra_skills = candidate_skills_set.difference(job_skills_set)
    
    overlap_percentage = 0
    if job_skills_set:
        overlap_percentage = round((len(common_skills) / len(job_skills_set)) * 100)
    
    return {
        'common_skills': sorted(list(common_skills)),
        'missing_skills': sorted(list(missing_skills)), 
        'extra_skills': sorted(list(extra_skills)),
        'overlap_percentage': overlap_percentage
    }


def generate_match_reasons(job_skills: List[str], candidate_skills: List[str], score: int) -> List[str]:
    """
    Generate human-readable reasons for the job match score.
    
    Args:
        job_skills: Skills required by the job
        candidate_skills: Skills possessed by candidate
        score: Calculated compatibility score
        
    Returns:
        List[str]: List of match reasoning statements
    """
    analysis = get_skill_analysis(job_skills, candidate_skills)
    reasons = []
    
    # Score-based general assessment
    if score >= 90:
        reasons.append("Excellent skill alignment with job requirements")
    elif score >= 80:
        reasons.append("Strong technical skills match")
    elif score >= 70:
        reasons.append("Good skills overlap with growth potential")
    elif score >= 60:
        reasons.append("Moderate skills match with some gaps")
    else:
        reasons.append("Limited skills overlap - significant gaps exist")
    
    # Specific skill highlights
    common_skills = analysis['common_skills']
    if common_skills:
        if len(common_skills) >= 5:
            reasons.append(f"Strong coverage across {len(common_skills)} key technologies")
        elif len(common_skills) >= 3:
            reasons.append(f"Solid foundation in {len(common_skills)} required skills")
        else:
            top_skills = ', '.join(common_skills[:3])
            reasons.append(f"Relevant experience with {top_skills}")
    
    # Mention significant gaps if any
    missing_skills = analysis['missing_skills']
    if missing_skills and len(missing_skills) <= 3:
        missing_str = ', '.join(missing_skills[:3])
        reasons.append(f"Opportunity to develop skills in {missing_str}")
    
    # Highlight additional value
    extra_skills = analysis['extra_skills']
    if extra_skills and len(extra_skills) >= 3:
        reasons.append("Brings additional valuable technical expertise")
    
    return reasons


def score_job_from_description(
    job_description: str,
    candidate_skills: Optional[List[str]] = None,
    must_have_skills: Optional[Set[str]] = None
) -> Dict[str, Any]:
    """
    End-to-end job scoring from raw job description.
    
    Args:
        job_description: Raw job description text
        candidate_skills: Candidate's skills (defaults to DEFAULT_CANDIDATE_SKILLS)
        must_have_skills: Critical skills (defaults to DEFAULT_MUST_HAVE_SKILLS)
        
    Returns:
        Dict containing:
        - score: Compatibility score (0-100)
        - extracted_skills: Skills found in job description
        - analysis: Detailed skill analysis
        - match_reasons: Human-readable match explanations
    """
    if candidate_skills is None:
        candidate_skills = get_candidate_skills()
    
    if must_have_skills is None:
        must_have_skills = get_must_have_skills()
    
    # Extract skills from job description
    extracted_skills = extract_skills(job_description)
    
    # Calculate compatibility score
    score = score_job(extracted_skills, candidate_skills, must_have_skills)
    
    # Generate detailed analysis
    analysis = get_skill_analysis(extracted_skills, candidate_skills)
    
    # Generate match reasons
    match_reasons = generate_match_reasons(extracted_skills, candidate_skills, score)
    
    return {
        'score': score,
        'extracted_skills': extracted_skills,
        'analysis': analysis,
        'match_reasons': match_reasons
    }


def get_candidate_skills() -> List[str]:
    """
    Get candidate skills from configuration or defaults.
    
    Returns:
        List[str]: List of candidate skills
    """
    # In a real implementation, this would load from user profile/config
    # For now, return default skills
    return DEFAULT_CANDIDATE_SKILLS.copy()


def get_must_have_skills() -> Set[str]:
    """
    Get must-have skills from configuration or defaults.
    
    Returns:
        Set[str]: Set of critical skills
    """
    # In a real implementation, this would load from user preferences
    # For now, return default must-haves
    return DEFAULT_MUST_HAVE_SKILLS.copy()


# Integration with existing worker functions

def update_job_with_score(job_id: str, job_data: Dict[str, Any]) -> None:
    """
    Update job record with calculated score and skills analysis.
    
    Args:
        job_id: Job UUID
        job_data: Job data dictionary containing description/requirements
    """
    try:
        # Combine description and requirements for analysis
        job_text = ""
        if job_data.get('description'):
            job_text += job_data['description'] + " "
        if job_data.get('requirements'):
            job_text += job_data['requirements']
        
        if not job_text.strip():
            logger.warning(f"No text content found for job {job_id}")
            return
        
        # Score the job
        result = score_job_from_description(job_text)
        
        # Update job record using DAO
        from apps.worker.dao import update_job_score
        update_job_score(
            job_id=job_id,
            score=result['score'],
            match_reasons=result['match_reasons']
        )
        
        logger.info(f"Job {job_id} scored: {result['score']}/100 with {len(result['extracted_skills'])} skills")
        
    except Exception as e:
        logger.error(f"Failed to score job {job_id}: {e}")
        raise
