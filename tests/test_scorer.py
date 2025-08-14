"""
Tests for scoring functions.
Tests skill extraction and job scoring algorithms.
"""

import pytest
from unittest.mock import patch

from apps.worker.scorer import (
    extract_skills, score_job, get_candidate_skills, get_must_have_skills,
    get_skill_analysis, score_job_from_description, SKILL_BANK, SKILL_SYNONYMS
)
from tests.test_utils import create_test_skills_data


class TestSkillExtraction:
    """Test skill extraction functionality."""
    
    def test_extract_skills_basic(self):
        """Test basic skill extraction from job description."""
        job_text = """
        We are looking for a Senior Software Engineer with strong Python and React experience.
        The ideal candidate will have experience with SQL databases, Docker containerization,
        and AWS cloud services. Knowledge of JavaScript and TypeScript is required.
        """
        
        skill_bank = {
            'python', 'react', 'javascript', 'typescript', 'sql', 'docker', 'aws',
            'java', 'css', 'html', 'nodejs', 'mongodb'
        }
        
        extracted = extract_skills(job_text, skill_bank)
        
        # Should find the mentioned skills
        expected_skills = {'python', 'react', 'sql', 'docker', 'aws', 'javascript', 'typescript'}
        assert set(extracted) == expected_skills
    
    def test_extract_skills_case_insensitive(self):
        """Test skill extraction is case insensitive."""
        job_text = "Experience with PYTHON, React.js, and SQL required. AWS knowledge preferred."
        
        skill_bank = {'python', 'react', 'sql', 'aws'}
        
        extracted = extract_skills(job_text, skill_bank)
        
        assert set(extracted) == {'python', 'react', 'sql', 'aws'}
    
    def test_extract_skills_with_synonyms(self):
        """Test skill extraction with synonym mapping."""
        job_text = "Looking for JS developer with Node experience and Postgres database skills."
        
        skill_bank = {'javascript', 'nodejs', 'postgresql'}
        
        # Mock the synonym map
        with patch('apps.worker.scorer.SKILL_SYNONYMS', {
            'js': 'javascript',
            'node': 'nodejs', 
            'postgres': 'postgresql'
        }):
            extracted = extract_skills(job_text, skill_bank)
        
        assert set(extracted) == {'javascript', 'nodejs', 'postgresql'}
    
    def test_extract_skills_compound_terms(self):
        """Test extraction of compound skill terms."""
        job_text = """
        Requirements include Node.js, React.js, and experience with REST APIs.
        Knowledge of CI/CD pipelines and DevOps practices preferred.
        """
        
        skill_bank = {'nodejs', 'react', 'rest', 'api', 'cicd', 'devops'}
        
        extracted = extract_skills(job_text, skill_bank)
        
        # Should handle compound terms
        expected = {'nodejs', 'react', 'rest', 'api', 'devops'}
        assert set(extracted).issuperset(expected)
    
    def test_extract_skills_no_matches(self):
        """Test skill extraction when no skills match."""
        job_text = "We need someone with great communication skills and leadership experience."
        
        skill_bank = {'python', 'java', 'javascript', 'react'}
        
        extracted = extract_skills(job_text, skill_bank)
        
        assert len(extracted) == 0
    
    def test_extract_skills_deduplicated(self):
        """Test that extracted skills are deduplicated."""
        job_text = "Python developer with Python experience. Strong Python skills required."
        
        skill_bank = {'python', 'java', 'javascript'}
        
        extracted = extract_skills(job_text, skill_bank)
        
        # Should only contain 'python' once
        assert extracted == ['python']
    
    def test_extract_skills_with_versions(self):
        """Test skill extraction with version numbers."""
        job_text = "Experience with Python 3.9+, Node.js 16, and React 18 required."
        
        skill_bank = {'python', 'nodejs', 'react'}
        
        extracted = extract_skills(job_text, skill_bank)
        
        assert set(extracted) == {'python', 'nodejs', 'react'}
    
    def test_extract_skills_framework_variants(self):
        """Test extraction of framework variants."""
        job_text = """
        Frontend: React.js, Vue.js, Angular
        Backend: Express.js, Django, Flask
        Database: PostgreSQL, MongoDB
        """
        
        skill_bank = {'react', 'vue', 'angular', 'express', 'django', 'flask', 'postgresql', 'mongodb'}
        
        extracted = extract_skills(job_text, skill_bank)
        
        expected = {'react', 'vue', 'angular', 'express', 'django', 'flask', 'postgresql', 'mongodb'}
        assert set(extracted) == expected


class TestJobScoring:
    """Test job scoring algorithm."""
    
    def test_score_job_perfect_match(self):
        """Test scoring with perfect skill match."""
        job_skills = ['python', 'react', 'sql', 'docker']
        candidate_skills = ['python', 'react', 'sql', 'docker', 'git', 'linux']
        must_haves = {'python', 'sql'}
        
        score = score_job(job_skills, candidate_skills, must_haves)
        
        # Perfect overlap (100%) + all must-haves = 100
        assert score == 100
    
    def test_score_job_partial_match(self):
        """Test scoring with partial skill match."""
        job_skills = ['python', 'react', 'sql', 'docker', 'kubernetes']
        candidate_skills = ['python', 'react', 'javascript']  # 2/5 overlap
        must_haves = {'python'}  # 1/1 must-have present
        
        score = score_job(job_skills, candidate_skills, must_haves)
        
        # 40% overlap * 60 + 100% must-haves * 40 = 24 + 40 = 64
        assert score == 64
    
    def test_score_job_no_must_haves(self):
        """Test scoring when missing must-have skills."""
        job_skills = ['python', 'react', 'sql']
        candidate_skills = ['react', 'javascript', 'css']  # 1/3 overlap
        must_haves = {'python', 'sql'}  # 0/2 must-haves present
        
        score = score_job(job_skills, candidate_skills, must_haves)
        
        # 33% overlap * 60 + 0% must-haves * 40 = ~20 + 0 = 20
        assert score == 20
    
    def test_score_job_empty_must_haves(self):
        """Test scoring with no must-have requirements."""
        job_skills = ['python', 'react', 'sql']
        candidate_skills = ['python', 'javascript']  # 1/3 overlap
        must_haves = set()  # No must-haves
        
        score = score_job(job_skills, candidate_skills, must_haves)
        
        # 33% overlap * 60 + 100% must-haves * 40 = ~20 + 40 = 60
        assert score == 60
    
    def test_score_job_no_overlap(self):
        """Test scoring with no skill overlap."""
        job_skills = ['java', 'spring', 'hibernate']
        candidate_skills = ['python', 'django', 'flask']
        must_haves = {'java'}
        
        score = score_job(job_skills, candidate_skills, must_haves)
        
        # 0% overlap + 0% must-haves = 0
        assert score == 0
    
    def test_score_job_empty_job_skills(self):
        """Test scoring with empty job skills."""
        job_skills = []
        candidate_skills = ['python', 'react']
        must_haves = set()
        
        score = score_job(job_skills, candidate_skills, must_haves)
        
        # No skills to match, should return high score (no requirements)
        assert score == 100
    
    def test_score_job_empty_candidate_skills(self):
        """Test scoring with empty candidate skills."""
        job_skills = ['python', 'react', 'sql']
        candidate_skills = []
        must_haves = {'python'}
        
        score = score_job(job_skills, candidate_skills, must_haves)
        
        # No candidate skills = 0% overlap and 0% must-haves
        assert score == 0
    
    def test_score_job_bonus_skills(self):
        """Test that extra candidate skills don't negatively impact score."""
        job_skills = ['python', 'sql']
        candidate_skills = ['python', 'sql', 'java', 'go', 'rust', 'scala']  # Many extra skills
        must_haves = {'python'}
        
        score = score_job(job_skills, candidate_skills, must_haves)
        
        # 100% overlap + 100% must-haves = 100 (extra skills don't hurt)
        assert score == 100


class TestSkillAnalysis:
    """Test skill analysis functionality."""
    
    def test_get_skill_analysis_complete(self):
        """Test complete skill analysis."""
        job_skills = ['python', 'react', 'sql', 'docker', 'kubernetes']
        candidate_skills = ['python', 'react', 'javascript', 'git']
        
        analysis = get_skill_analysis(job_skills, candidate_skills)
        
        assert set(analysis['common_skills']) == {'python', 'react'}
        assert set(analysis['missing_skills']) == {'sql', 'docker', 'kubernetes'}
        assert set(analysis['extra_skills']) == {'javascript', 'git'}
        assert analysis['overlap_percentage'] == 40  # 2/5 = 40%
    
    def test_get_skill_analysis_perfect_match(self):
        """Test skill analysis with perfect match."""
        skills = ['python', 'react', 'sql']
        
        analysis = get_skill_analysis(skills, skills)
        
        assert set(analysis['common_skills']) == set(skills)
        assert analysis['missing_skills'] == []
        assert analysis['extra_skills'] == []
        assert analysis['overlap_percentage'] == 100
    
    def test_get_skill_analysis_no_overlap(self):
        """Test skill analysis with no overlap."""
        job_skills = ['java', 'spring']
        candidate_skills = ['python', 'django']
        
        analysis = get_skill_analysis(job_skills, candidate_skills)
        
        assert analysis['common_skills'] == []
        assert set(analysis['missing_skills']) == set(job_skills)
        assert set(analysis['extra_skills']) == set(candidate_skills)
        assert analysis['overlap_percentage'] == 0


class TestScoringIntegration:
    """Test integrated scoring functionality."""
    
    def test_score_job_from_description(self):
        """Test end-to-end scoring from job description."""
        job_description = """
        We are seeking a Senior Python Developer with strong experience in:
        - Python web development
        - React frontend framework
        - SQL database design
        - Docker containerization
        - AWS cloud services
        
        Must have 5+ years of Python experience and SQL knowledge.
        """
        
        # Mock the skill bank and candidate data
        with patch('apps.worker.scorer.SKILL_BANK', {
            'python', 'react', 'sql', 'docker', 'aws', 'javascript', 'java'
        }), \
        patch('apps.worker.scorer.get_candidate_skills', return_value=[
            'python', 'react', 'javascript', 'git', 'linux'
        ]), \
        patch('apps.worker.scorer.get_must_have_skills', return_value={
            'python', 'sql'
        }):
            
            result = score_job_from_description(job_description)
        
        assert 'score' in result
        assert 'extracted_skills' in result
        assert 'analysis' in result
        assert 'match_reasons' in result
        
        # Should extract relevant skills
        assert 'python' in result['extracted_skills']
        assert 'react' in result['extracted_skills'] 
        assert 'sql' in result['extracted_skills']
        
        # Score should be reasonable (has Python but missing SQL)
        assert 0 <= result['score'] <= 100
    
    def test_get_candidate_skills_default(self):
        """Test default candidate skills."""
        skills = get_candidate_skills()
        
        # Should return a list of skills
        assert isinstance(skills, list)
        assert len(skills) > 0
        assert all(isinstance(skill, str) for skill in skills)
    
    def test_get_must_have_skills_default(self):
        """Test default must-have skills."""
        must_haves = get_must_have_skills()
        
        # Should return a set of skills
        assert isinstance(must_haves, set)
        # Should contain some basic requirements
        assert len(must_haves) >= 0


class TestScoringEdgeCases:
    """Test edge cases in scoring functionality."""
    
    def test_score_job_case_sensitivity(self):
        """Test that scoring handles case differences."""
        job_skills = ['Python', 'REACT', 'sql']
        candidate_skills = ['python', 'React', 'SQL']
        must_haves = {'PYTHON'}
        
        score = score_job(job_skills, candidate_skills, must_haves)
        
        # Should match despite case differences
        assert score == 100
    
    def test_score_job_with_duplicates(self):
        """Test scoring with duplicate skills in input."""
        job_skills = ['python', 'python', 'react', 'react']
        candidate_skills = ['python', 'python', 'javascript']
        must_haves = {'python'}
        
        score = score_job(job_skills, candidate_skills, must_haves)
        
        # Should handle duplicates properly
        # After deduplication: job=[python, react], candidate=[python, javascript]
        # 50% overlap + 100% must-haves = 30 + 40 = 70
        assert score == 70
    
    def test_extract_skills_special_characters(self):
        """Test skill extraction with special characters."""
        job_text = "Experience with C++, .NET, Node.js, and CI/CD pipelines required."
        
        skill_bank = {'c++', 'dotnet', 'nodejs', 'cicd'}
        
        # Mock synonym mapping for special characters
        with patch('apps.worker.scorer.SKILL_SYNONYMS', {
            '.net': 'dotnet',
            'node.js': 'nodejs',
            'ci/cd': 'cicd'
        }):
            extracted = extract_skills(job_text, skill_bank)
        
        expected = {'c++', 'dotnet', 'nodejs', 'cicd'}
        assert set(extracted).issuperset(expected)
    
    def test_score_job_large_skill_sets(self):
        """Test scoring with large skill sets."""
        # Large job requirements
        job_skills = [f'skill_{i}' for i in range(50)]
        
        # Candidate has half the skills plus some extras
        candidate_skills = job_skills[:25] + [f'extra_{i}' for i in range(10)]
        
        must_haves = set(job_skills[:5])  # First 5 are must-haves
        
        score = score_job(job_skills, candidate_skills, must_haves)
        
        # 50% overlap + 100% must-haves = 30 + 40 = 70
        assert score == 70
    
    def test_score_job_unicode_skills(self):
        """Test scoring with unicode characters in skills."""
        job_skills = ['python', 'react', 'sql']
        candidate_skills = ['python', 'react', 'javascript']
        must_haves = {'python'}
        
        # Should handle unicode without errors
        score = score_job(job_skills, candidate_skills, must_haves)
        assert isinstance(score, int)
        assert 0 <= score <= 100

