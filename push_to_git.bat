@echo off
echo Job Bot - Git Push Script
echo ========================

if "%~1"=="" (
    echo Usage: push_to_git.bat ^<repository-url^>
    echo Example: push_to_git.bat https://github.com/username/repo-name.git
    pause
    exit /b 1
)

set REPO_URL=%~1
echo Setting up remote repository: %REPO_URL%

git remote add origin %REPO_URL%
if errorlevel 1 (
    echo Error: Failed to add remote repository
    pause
    exit /b 1
)

echo ✓ Remote repository added successfully

echo Pushing code to master branch...
git push -u origin master
if errorlevel 1 (
    echo Error: Failed to push code
    pause
    exit /b 1
)

echo ✓ Code successfully pushed to git!
echo Your repository is now available at: %REPO_URL%
pause
