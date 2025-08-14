@echo off
REM Job Bot Docker Management Scripts for Windows
REM Alternative to Makefile for Windows users

if "%1"=="" goto help
if "%1"=="help" goto help
if "%1"=="up" goto up
if "%1"=="down" goto down
if "%1"=="logs" goto logs
if "%1"=="build" goto build
if "%1"=="status" goto status
if "%1"=="restart" goto restart
if "%1"=="clean" goto clean
goto help

:help
echo.
echo Job Bot - Docker Management
echo ==========================
echo Available commands:
echo   docker.bat up      - Start all services
echo   docker.bat down    - Stop all services
echo   docker.bat logs    - Show logs for all services
echo   docker.bat build   - Build Docker images
echo   docker.bat status  - Show service status
echo   docker.bat restart - Restart all services
echo   docker.bat clean   - Clean up containers and volumes
echo.
goto end

:up
echo 🚀 Starting Job Bot services...
if not exist .env (
    echo Creating .env file from template...
    copy env.example .env
    echo ✅ Created .env file. Please customize it for your environment.
)
docker compose up -d
echo ✅ Services started!
echo.
echo 🌐 Available services:
echo   API:          http://localhost:8000
echo   Dashboard:    http://localhost:8080
echo   RQ Dashboard: http://localhost:9181
echo   PostgreSQL:   localhost:5432
echo   Redis:        localhost:6379
echo.
goto end

:down
echo 🛑 Stopping Job Bot services...
docker compose down
echo ✅ Services stopped!
goto end

:logs
echo 📋 Showing logs for all services (Ctrl+C to exit)...
docker compose logs -f
goto end

:build
echo 🔨 Building Job Bot Docker images...
docker compose build --no-cache
echo ✅ Images built!
goto end

:status
echo 📊 Job Bot Service Status:
echo =========================
docker compose ps
goto end

:restart
echo 🔄 Restarting Job Bot services...
docker compose restart
echo ✅ Services restarted!
goto end

:clean
echo 🧹 Cleaning up Docker resources...
docker compose down -v --remove-orphans
docker system prune -f
echo ✅ Cleanup completed!
goto end

:end
