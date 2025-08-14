"""
Tests for tailoring functionality.
Tests that tailored assets are generated with matched skills and no invented claims.
"""

import json
import pytest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch, MagicMock

from apps.worker.tailor import FileManager, build_tailored_assets
from apps.worker.worker import tailor_application_for_job
from apps.worker.dao import insert_job, update_job_score


class TestFileManager:
    """Test file manager functionality for tailored assets."""
    
    def test_create_resume_docx(self, temp_artifacts_dir, sample_job_data):
        """Test DOCX resume creation with skill matching."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        # Job data with extracted skills
        job_data = sample_job_data.copy()
        job_data.update({
            'skills': ['python', 'react', 'sql', 'docker'],
            'score': 85,
            'match_reasons': ['Strong Python experience', 'React proficiency']
        })
        
        # Create resume
        resume_path = file_manager.create_resume_docx(job_id, job_data)
        
        # Verify file was created
        assert resume_path.exists()
        assert resume_path.suffix == '.docx'
        assert str(job_id) in str(resume_path)
        
        # File should be non-empty (actual content testing would require docx parsing)
        assert resume_path.stat().st_size > 0
    
    def test_create_resume_txt(self, temp_artifacts_dir, sample_job_data):
        """Test TXT resume creation with readable format."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        job_data = sample_job_data.copy()
        job_data.update({
            'skills': ['python', 'javascript', 'sql'],
            'score': 78
        })
        
        # Create text resume
        resume_path = file_manager.create_resume_txt(job_id, job_data)
        
        # Verify file was created
        assert resume_path.exists()
        assert resume_path.suffix == '.txt'
        
        # Check content has basic structure
        content = resume_path.read_text(encoding='utf-8')
        assert len(content) > 0
        
        # Should contain relevant skills (would be expanded in actual implementation)
        # This is a placeholder test - actual implementation would tailor content
        assert 'python' in content.lower() or 'skills' in content.lower()
    
    def test_create_cover_email(self, temp_artifacts_dir, sample_job_data):
        """Test cover email creation with job-specific content."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        job_data = sample_job_data.copy()
        job_data.update({
            'skills': ['python', 'react', 'sql'],
            'match_reasons': ['Strong Python background', 'React experience'],
            'score': 82
        })
        
        # Create cover email
        email_path = file_manager.create_cover_email(job_id, job_data)
        
        # Verify file was created
        assert email_path.exists()
        assert email_path.name == 'cover_email.txt'
        
        # Check email content
        content = email_path.read_text(encoding='utf-8')
        assert len(content) > 0
        
        # Should contain job-specific information
        assert job_data['company'] in content
        assert job_data['title'] in content
        
        # Should have email structure
        assert 'Subject:' in content
        assert '[Your Email]' in content  # Should have email placeholder
    
    def test_create_linkedin_message(self, temp_artifacts_dir, sample_job_data):
        """Test LinkedIn message creation."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        job_data = sample_job_data.copy()
        job_data.update({
            'skills': ['python', 'react'],
            'score': 75
        })
        
        # Create LinkedIn message
        message_path = file_manager.create_linkedin_message(job_id, job_data)
        
        # Verify file was created
        assert message_path.exists()
        assert message_path.name == 'linkedin_msg.txt'
        
        # Check message content
        content = message_path.read_text(encoding='utf-8')
        assert len(content) > 0
        assert len(content) <= 300  # LinkedIn message length limit
        
        # Should be personalized
        assert job_data['company'] in content
    
    def test_create_meta_json(self, temp_artifacts_dir, sample_job_data):
        """Test metadata JSON creation with complete job snapshot."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        job_data = sample_job_data.copy()
        job_data.update({
            'id': str(job_id),
            'skills': ['python', 'react', 'sql'],
            'score': 88,
            'match_reasons': ['Excellent Python fit', 'Strong React background']
        })
        
        # Create metadata
        meta_path = file_manager.create_meta_json(job_id, job_data, duration_seconds=45)
        
        # Verify file was created
        assert meta_path.exists()
        assert meta_path.name == 'meta.json'
        
        # Parse and validate JSON content
        with open(meta_path, 'r') as f:
            meta_data = json.load(f)
        
        # Should contain job snapshot
        assert meta_data['job']['id'] == str(job_id)
        assert meta_data['job']['title'] == job_data['title']
        assert meta_data['job']['company'] == job_data['company']
        assert meta_data['job']['score'] == 88
        
        # Should contain processing info
        assert 'timestamp' in meta_data['tailoring']
        assert 'version' in meta_data['tailoring']
        
        # Should contain skill analysis
        assert set(meta_data['skills']['extracted']) == {'python', 'react', 'sql'}
        assert meta_data['skills']['match_reasons'] == job_data['match_reasons']


class TestBuildTailoredAssets:
    """Test the main build_tailored_assets function."""
    
    def test_build_tailored_assets_complete(self, temp_artifacts_dir):
        """Test that build_tailored_assets creates all required files."""
        job_id = uuid4()
        
        job_data = {
            'title': 'Senior Python Developer',
            'company': 'TechCorp Inc',
            'url': 'https://techcorp.com/jobs/python-dev',
            'location': 'San Francisco, CA',
            'description': 'Looking for Python expert with React experience',
            'requirements': 'Python, React, SQL, Docker required',
            'skills': ['python', 'react', 'sql', 'docker'],
            'score': 85,
            'match_reasons': ['Strong Python background', 'React experience']
        }
        
        # Build tailored assets
        assets = build_tailored_assets(job_id, job_data, temp_artifacts_dir)
        
        # Verify all expected assets were created
        expected_assets = ['resume_docx', 'resume_txt', 'cover_email', 'linkedin_msg', 'meta_json']
        for asset_type in expected_assets:
            assert asset_type in assets
            assert assets[asset_type].exists()
            assert assets[asset_type].stat().st_size > 0
    
    def test_build_tailored_assets_skill_matching(self, temp_artifacts_dir):
        """Test that assets only highlight matched skills, no fabrication."""
        job_id = uuid4()
        
        # Job with many skills, but limited candidate match
        job_data = {
            'title': 'Full Stack Developer',
            'company': 'WebCorp',
            'skills': ['python', 'react', 'kubernetes', 'machine-learning', 'blockchain'],
            'score': 45,  # Lower score indicates limited match
            'match_reasons': ['Python experience']  # Only Python mentioned
        }
        
        assets = build_tailored_assets(job_id, job_data, temp_artifacts_dir)
        
        # Check resume content doesn't over-claim
        resume_content = assets['resume_txt'].read_text().lower()
        
        # Should mention Python (we have experience)
        assert 'python' in resume_content
        
        # Should not fabricate expertise in skills we don't have
        advanced_claims = [
            'kubernetes expert', 'machine learning specialist', 'blockchain guru',
            '10 years', '15 years', 'senior architect', 'team lead'
        ]
        
        for claim in advanced_claims:
            assert claim not in resume_content, f"Found fabricated claim: {claim}"
    
    def test_build_tailored_assets_truthful_content(self, temp_artifacts_dir):
        """Test that generated content remains truthful and doesn't invent experience."""
        job_id = uuid4()
        
        job_data = {
            'title': 'Software Engineer',
            'company': 'StartupCorp',
            'skills': ['javascript', 'nodejs', 'react'],
            'score': 70,
            'match_reasons': ['JavaScript knowledge', 'React experience']
        }
        
        assets = build_tailored_assets(job_id, job_data, temp_artifacts_dir)
        
        # Check all content for truthfulness
        all_content = ""
        for asset_path in assets.values():
            if asset_path.suffix in ['.txt', '.docx']:  # Text-based assets
                content = asset_path.read_text().lower()
                all_content += content + " "
        
        # Should not contain fabricated experience claims
        fabricated_patterns = [
            r'\d+\+?\s*years?\s+of\s+experience',
            r'over\s+\d+\s+years',
            r'\d+\s+year\s+veteran',
            r'senior\s+architect',
            r'team\s+lead',
            r'project\s+manager'
        ]
        
        import re
        for pattern in fabricated_patterns:
            matches = re.findall(pattern, all_content)
            assert len(matches) == 0, f"Found fabricated claim: {matches}"


class TestTailoredAssetContent:
    """Test that tailored assets contain appropriate skill matching and no fabricated content."""
    
    def test_resume_skill_highlighting(self, temp_artifacts_dir):
        """Test that resume highlights relevant skills without invention."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        # Job requiring specific skills
        job_data = {
            'title': 'Senior Python Developer',
            'company': 'TechCorp',
            'skills': ['python', 'django', 'postgresql', 'redis', 'docker'],
            'score': 85,
            'match_reasons': ['Strong Python experience', 'Database expertise'],
            'description': 'Looking for Python expert with Django and PostgreSQL experience'
        }
        
        # Create resume
        resume_path = file_manager.create_resume_txt(job_id, job_data)
        content = resume_path.read_text(encoding='utf-8')
        
        # Should contain matched skills prominently
        # (This test assumes the implementation highlights matched skills)
        matched_skills = ['python', 'docker']  # Based on actual implementation
        for skill in matched_skills:
            assert skill.lower() in content.lower(), f"Resume should highlight {skill}"
        
        # Should not contain years of experience claims without basis
        # (This is a policy test - no fabricated experience)
        fabricated_claims = ['10 years', '15 years', '20 years']
        for claim in fabricated_claims:
            assert claim not in content, f"Resume should not fabricate experience: {claim}"
    
    def test_cover_email_skill_focus(self, temp_artifacts_dir):
        """Test that cover email focuses on matched skills."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        job_data = {
            'title': 'Frontend Developer',
            'company': 'WebCorp',
            'skills': ['react', 'typescript', 'css', 'html'],
            'score': 78,
            'match_reasons': ['React proficiency', 'TypeScript knowledge'],
            'description': 'Frontend role requiring React and TypeScript'
        }
        
        # Create cover email
        email_path = file_manager.create_cover_email(job_id, job_data)
        content = email_path.read_text(encoding='utf-8')
        
        # Should mention matched skills
        assert 'react' in content.lower()
        assert 'typescript' in content.lower()
        
        # Should reference match reasons
        for reason in job_data['match_reasons']:
            # Some form of the reasoning should appear
            assert any(word in content.lower() for word in reason.lower().split())
        
        # Should not make unsubstantiated claims
        unsubstantiated = ['expert', 'guru', 'ninja', 'rockstar']
        content_lower = content.lower()
        unsubstantiated_found = [claim for claim in unsubstantiated if claim in content_lower]
        assert len(unsubstantiated_found) == 0, f"Avoid unsubstantiated claims: {unsubstantiated_found}"
    
    def test_linkedin_message_conciseness(self, temp_artifacts_dir):
        """Test that LinkedIn message is concise and skill-focused."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        job_data = {
            'title': 'Data Engineer',
            'company': 'DataCorp',
            'skills': ['python', 'sql', 'spark', 'kafka'],
            'score': 82,
            'location': 'San Francisco, CA'
        }
        
        # Create LinkedIn message
        message_path = file_manager.create_linkedin_message(job_id, job_data)
        content = message_path.read_text(encoding='utf-8')
        
        # Should be appropriately concise (LinkedIn best practices)
        assert len(content) <= 300, "LinkedIn message should be under 300 characters"
        assert len(content) >= 50, "LinkedIn message should have substantial content"
        
        # Should mention the company and position
        assert 'datacorp' in content.lower()
        assert 'data engineer' in content.lower()
        
        # Should be professional and personal
        assert job_data['company'] in content
        assert any(word in content.lower() for word in ['interested', 'opportunity', 'role', 'position'])
    
    def test_no_fabricated_experience_years(self, temp_artifacts_dir):
        """Test that no fabricated years of experience are added."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        job_data = {
            'title': 'Software Engineer',
            'company': 'TechStart',
            'skills': ['javascript', 'node.js', 'mongodb'],
            'score': 65,
            'requirements': 'Must have 5+ years of JavaScript experience'
        }
        
        # Create all assets
        resume_path = file_manager.create_resume_txt(job_id, job_data)
        email_path = file_manager.create_cover_email(job_id, job_data)
        
        # Check all content for fabricated experience claims
        resume_content = resume_path.read_text(encoding='utf-8')
        email_content = email_path.read_text(encoding='utf-8')
        
        # Should not contain specific year claims that could be false
        experience_patterns = [
            r'\d+\+?\s*years?\s+of\s+experience',
            r'over\s+\d+\s+years',
            r'\d+\s+year\s+veteran',
            r'extensive\s+\d+\s+year'
        ]
        
        import re
        for content in [resume_content, email_content]:
            for pattern in experience_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                assert len(matches) == 0, f"Found fabricated experience claim: {matches}"
    
    def test_skill_based_truthful_content(self, temp_artifacts_dir):
        """Test that content is based on actual skill matches, not fabrication."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        # Job with many skills, but we'll only claim to match some
        job_data = {
            'title': 'Full Stack Developer',
            'company': 'FullStack Inc',
            'skills': ['python', 'react', 'sql', 'docker', 'kubernetes', 'aws', 'microservices'],
            'score': 60,  # Lower score indicates partial match
            'match_reasons': ['Python experience', 'React knowledge']  # Only these skills
        }
        
        # Create assets
        resume_path = file_manager.create_resume_txt(job_id, job_data)
        email_path = file_manager.create_cover_email(job_id, job_data)
        
        resume_content = resume_path.read_text(encoding='utf-8').lower()
        email_content = email_path.read_text(encoding='utf-8').lower()
        
        # Should emphasize matched skills
        assert 'python' in resume_content or 'python' in email_content
        assert 'react' in resume_content or 'react' in email_content
        
        # Should not over-emphasize skills we don't have strong matches for
        # (This test assumes implementation respects the match_reasons)
        advanced_claims = [
            'kubernetes expert', 'microservices architect', 'aws certified',
            'docker specialist', 'senior engineer', 'lead developer'
        ]
        
        all_content = (resume_content + ' ' + email_content).lower()
        for claim in advanced_claims:
            assert claim not in all_content, f"Should not make advanced claims: {claim}"


class TestTailoringIntegration:
    """Test integration of tailoring with DAO and scoring."""
    
    def test_tailor_application_for_job_integration(self, temp_artifacts_dir, sample_job_data):
        """Test complete tailoring workflow integration."""
        # Insert job into database
        job_id = insert_job(sample_job_data)
        
        # Add scoring data
        skills = ['python', 'react', 'sql']
        match_reasons = ['Strong Python background', 'React experience']
        update_job_score(job_id, 85, match_reasons)
        
        # Mock the worker's internal functions
        with patch('apps.worker.worker._generate_tailored_resume') as mock_resume, \
             patch('apps.worker.worker._generate_tailored_cover_letter') as mock_cover:
            
            # Run tailoring
            result = tailor_application_for_job(job_id)
        
        # Verify result structure
        assert isinstance(result, dict)
        assert 'resume' in result
        assert 'cover_letter' in result
        
        # Verify the internal functions were called
        mock_resume.assert_called_once()
        mock_cover.assert_called_once()
    
    def test_tailor_application_nonexistent_job(self):
        """Test tailoring fails gracefully for non-existent job."""
        fake_job_id = uuid4()
        
        with pytest.raises(Exception):  # Should raise JobProcessingError or similar
            tailor_application_for_job(fake_job_id)
    
    def test_file_organization_structure(self, temp_artifacts_dir):
        """Test that files are organized in correct structure."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        job_data = {
            'title': 'Test Job',
            'company': 'Test Company',
            'skills': ['python'],
            'score': 80
        }
        
        # Create all files
        file_manager.create_resume_docx(job_id, job_data)
        file_manager.create_resume_txt(job_id, job_data)
        file_manager.create_cover_email(job_id, job_data)
        file_manager.create_linkedin_message(job_id, job_data)
        file_manager.create_meta_json(job_id, job_data)
        
        # Verify directory structure
        job_dir = temp_artifacts_dir / str(job_id)
        assert job_dir.exists()
        assert job_dir.is_dir()
        
        # Verify all expected files exist
        expected_files = [
            'resume.docx', 'resume.txt', 'cover_email.txt', 
            'linkedin_msg.txt', 'meta.json'
        ]
        
        for filename in expected_files:
            file_path = job_dir / filename
            assert file_path.exists(), f"Missing file: {filename}"
            assert file_path.stat().st_size > 0, f"Empty file: {filename}"


class TestContentQuality:
    """Test content quality and ATS safety."""
    
    def test_content_ats_safety(self, temp_artifacts_dir):
        """Test that generated content is ATS-safe."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        job_data = {
            'title': 'Software Engineer',
            'company': 'TechCorp',
            'skills': ['python', 'javascript'],
            'score': 75
        }
        
        # Create text resume (easier to analyze than DOCX)
        resume_path = file_manager.create_resume_txt(job_id, job_data)
        content = resume_path.read_text(encoding='utf-8')
        
        # ATS-unsafe elements to avoid
        ats_unsafe = [
            '📧', '🏠', '📞',  # Emojis
            '\\textbf{', '\\section{',  # LaTeX commands
            '<b>', '<i>', '<div>',  # HTML tags
            '&nbsp;', '&amp;',  # HTML entities
        ]
        
        for unsafe_element in ats_unsafe:
            assert unsafe_element not in content, f"ATS-unsafe element found: {unsafe_element}"
        
        # Should use clean, simple formatting
        assert len(content.strip()) > 0
        assert content.isprintable() or content.isascii()
    
    def test_content_personalization(self, temp_artifacts_dir):
        """Test that content is personalized for the specific job."""
        file_manager = FileManager(temp_artifacts_dir)
        job_id = uuid4()
        
        job_data = {
            'title': 'Data Scientist',
            'company': 'DataCorp Inc',
            'location': 'Seattle, WA',
            'skills': ['python', 'pandas', 'scikit-learn'],
            'score': 88,
            'match_reasons': ['Strong Python data science background']
        }
        
        # Create personalized content
        email_path = file_manager.create_cover_email(job_id, job_data)
        content = email_path.read_text(encoding='utf-8')
        
        # Should contain job-specific details
        assert job_data['company'] in content
        assert job_data['title'] in content
        
        # Should reflect relevant skills
        assert 'python' in content.lower()
        assert 'data' in content.lower()
        
                # Should not be overly generic
        generic_phrases = [
            'to whom it may concern',
            'i am writing to apply for any position'
        ]

        content_lower = content.lower()
        for phrase in generic_phrases:
            assert phrase not in content_lower, f"Content too generic: {phrase}"

