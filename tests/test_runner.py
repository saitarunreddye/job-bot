"""
Test runner for Job Bot tests.
Provides utilities for running tests with proper setup and reporting.
"""

import sys
import pytest
import argparse
from pathlib import Path


def run_tests(
    test_path: str = "tests/",
    verbose: bool = True,
    coverage: bool = True,
    pattern: str = "test_*.py"
) -> int:
    """
    Run tests with appropriate configuration.
    
    Args:
        test_path: Path to test directory or specific test file
        verbose: Enable verbose output
        coverage: Enable coverage reporting
        pattern: Test file pattern
        
    Returns:
        int: Exit code (0 for success)
    """
    args = []
    
    # Test path
    args.append(test_path)
    
    # Verbose output
    if verbose:
        args.extend(["-v", "-s"])
    
    # Coverage
    if coverage:
        args.extend([
            "--cov=apps",
            "--cov=db", 
            "--cov=config",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov"
        ])
    
    # Additional pytest args
    args.extend([
        "--tb=short",  # Short traceback format
        "-x",  # Stop on first failure
        f"--pattern={pattern}"
    ])
    
    return pytest.main(args)


def run_specific_tests():
    """Run specific test categories."""
    categories = {
        'dao': 'tests/test_dao.py',
        'scorer': 'tests/test_scorer.py', 
        'tailor': 'tests/test_tailor.py',
        'all': 'tests/'
    }
    
    parser = argparse.ArgumentParser(description='Run Job Bot tests')
    parser.add_argument(
        'category',
        choices=list(categories.keys()),
        help='Test category to run'
    )
    parser.add_argument(
        '--no-coverage',
        action='store_true',
        help='Disable coverage reporting'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Reduce output verbosity'
    )
    
    args = parser.parse_args()
    
    test_path = categories[args.category]
    verbose = not args.quiet
    coverage = not args.no_coverage
    
    print(f"🧪 Running {args.category} tests from {test_path}")
    print("=" * 50)
    
    exit_code = run_tests(
        test_path=test_path,
        verbose=verbose,
        coverage=coverage
    )
    
    if exit_code == 0:
        print("\n✅ All tests passed!")
    else:
        print(f"\n❌ Tests failed with exit code {exit_code}")
    
    return exit_code


def check_test_environment():
    """Check that test environment is properly set up."""
    issues = []
    
    # Check required packages
    try:
        import pytest
        import sqlalchemy
    except ImportError as e:
        issues.append(f"Missing required package: {e}")
    
    # Check test database can be created
    try:
        from tests.test_utils import create_test_database
        import tempfile
        import os
        
        fd, temp_db = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        
        try:
            create_test_database(f"sqlite:///{temp_db}")
        finally:
            os.unlink(temp_db)
            
    except Exception as e:
        issues.append(f"Test database setup failed: {e}")
    
    # Check project structure
    required_dirs = ['apps/worker', 'db', 'config', 'tests']
    project_root = Path(__file__).parent.parent
    
    for dir_path in required_dirs:
        if not (project_root / dir_path).exists():
            issues.append(f"Missing directory: {dir_path}")
    
    if issues:
        print("❌ Test environment issues found:")
        for issue in issues:
            print(f"  • {issue}")
        return False
    else:
        print("✅ Test environment looks good!")
        return True


if __name__ == "__main__":
    # Check environment first
    if not check_test_environment():
        sys.exit(1)
    
    # Run tests
    exit_code = run_specific_tests()
    sys.exit(exit_code)
