# Job Bot Docker Management PowerShell Script
# Alternative to Makefile for Windows users

param(
    [Parameter(Position = 0)]
    [string]$Command = "help",
    
    [Parameter(Position = 1)]
    [string]$Scale = "2"
)

function Show-Help {
    Write-Host ""
    Write-Host "Job Bot - Docker Management" -ForegroundColor Cyan
    Write-Host "==========================" -ForegroundColor Cyan
    Write-Host "Available commands:" -ForegroundColor Yellow
    Write-Host "  .\scripts\docker.ps1 up        - Start all services" -ForegroundColor White
    Write-Host "  .\scripts\docker.ps1 down      - Stop all services" -ForegroundColor White
    Write-Host "  .\scripts\docker.ps1 logs      - Show logs for all services" -ForegroundColor White
    Write-Host "  .\scripts\docker.ps1 build     - Build Docker images" -ForegroundColor White
    Write-Host "  .\scripts\docker.ps1 status    - Show service status" -ForegroundColor White
    Write-Host "  .\scripts\docker.ps1 restart   - Restart all services" -ForegroundColor White
    Write-Host "  .\scripts\docker.ps1 clean     - Clean up containers and volumes" -ForegroundColor White
    Write-Host "  .\scripts\docker.ps1 db-init   - Initialize database" -ForegroundColor White
    Write-Host "  .\scripts\docker.ps1 seed      - Seed database with sample data" -ForegroundColor White
    Write-Host "  .\scripts\docker.ps1 shell     - Open shell in API container" -ForegroundColor White
    Write-Host "  .\scripts\docker.ps1 test      - Run tests" -ForegroundColor White
    Write-Host ""
}

function Start-Services {
    Write-Host "🚀 Starting Job Bot services..." -ForegroundColor Green
    
    # Create .env if it doesn't exist
    if (-not (Test-Path ".env")) {
        Write-Host "Creating .env file from template..." -ForegroundColor Yellow
        Copy-Item "env.example" ".env"
        Write-Host "✅ Created .env file. Please customize it for your environment." -ForegroundColor Green
    }
    
    docker compose up -d
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Services started!" -ForegroundColor Green
        Write-Host ""
        Write-Host "🌐 Available services:" -ForegroundColor Cyan
        Write-Host "  API:          http://localhost:8000" -ForegroundColor White
        Write-Host "  Dashboard:    http://localhost:8080" -ForegroundColor White
        Write-Host "  RQ Dashboard: http://localhost:9181" -ForegroundColor White
        Write-Host "  PostgreSQL:   localhost:5432" -ForegroundColor White
        Write-Host "  Redis:        localhost:6379" -ForegroundColor White
        Write-Host ""
    } else {
        Write-Host "❌ Failed to start services" -ForegroundColor Red
    }
}

function Stop-Services {
    Write-Host "🛑 Stopping Job Bot services..." -ForegroundColor Yellow
    docker compose down
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Services stopped!" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to stop services" -ForegroundColor Red
    }
}

function Show-Logs {
    Write-Host "📋 Showing logs for all services (Ctrl+C to exit)..." -ForegroundColor Cyan
    docker compose logs -f
}

function Build-Images {
    Write-Host "🔨 Building Job Bot Docker images..." -ForegroundColor Yellow
    docker compose build --no-cache
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Images built!" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to build images" -ForegroundColor Red
    }
}

function Show-Status {
    Write-Host "📊 Job Bot Service Status:" -ForegroundColor Cyan
    Write-Host "=========================" -ForegroundColor Cyan
    docker compose ps
}

function Restart-Services {
    Write-Host "🔄 Restarting Job Bot services..." -ForegroundColor Yellow
    docker compose restart
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Services restarted!" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to restart services" -ForegroundColor Red
    }
}

function Clean-Resources {
    Write-Host "🧹 Cleaning up Docker resources..." -ForegroundColor Yellow
    docker compose down -v --remove-orphans
    docker system prune -f
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Cleanup completed!" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to clean resources" -ForegroundColor Red
    }
}

function Initialize-Database {
    Write-Host "🗄️ Initializing database..." -ForegroundColor Yellow
    docker compose exec api python scripts/init_db.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Database initialized!" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to initialize database" -ForegroundColor Red
    }
}

function Seed-Database {
    Write-Host "🌱 Seeding database with sample data..." -ForegroundColor Yellow
    docker compose exec api python scripts/seed_and_run.py
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Database seeded!" -ForegroundColor Green
    } else {
        Write-Host "❌ Failed to seed database" -ForegroundColor Red
    }
}

function Open-Shell {
    Write-Host "🐚 Opening shell in API container..." -ForegroundColor Cyan
    docker compose exec api bash
}

function Run-Tests {
    Write-Host "🧪 Running tests..." -ForegroundColor Yellow
    docker compose exec api python -m pytest tests/ -v
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Tests completed!" -ForegroundColor Green
    } else {
        Write-Host "❌ Tests failed" -ForegroundColor Red
    }
}

# Main command switch
switch ($Command.ToLower()) {
    "help" { Show-Help }
    "up" { Start-Services }
    "down" { Stop-Services }
    "logs" { Show-Logs }
    "build" { Build-Images }
    "status" { Show-Status }
    "restart" { Restart-Services }
    "clean" { Clean-Resources }
    "db-init" { Initialize-Database }
    "seed" { Seed-Database }
    "shell" { Open-Shell }
    "test" { Run-Tests }
    default {
        Write-Host "Unknown command: $Command" -ForegroundColor Red
        Show-Help
    }
}
