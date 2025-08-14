#!/usr/bin/env python3
import subprocess
import sys
import os

def run_command(command):
    """Run a command and return the result"""
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=os.getcwd())
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def push_to_git(repo_url):
    """Push code to the specified git repository"""
    print(f"Setting up remote repository: {repo_url}")
    
    # Add remote origin
    success, stdout, stderr = run_command(f'git remote add origin {repo_url}')
    if not success:
        print(f"Error adding remote: {stderr}")
        return False
    
    print("✓ Remote repository added")
    
    # Push to master branch
    print("Pushing code to master branch...")
    success, stdout, stderr = run_command('git push -u origin master')
    if not success:
        print(f"Error pushing code: {stderr}")
        return False
    
    print("✓ Code successfully pushed to git!")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python push_to_git.py <repository-url>")
        print("Example: python push_to_git.py https://github.com/username/repo-name.git")
        sys.exit(1)
    
    repo_url = sys.argv[1]
    push_to_git(repo_url)
