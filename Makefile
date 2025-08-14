# Job Bot Makefile
# Provides convenient targets for Docker Compose management

.PHONY: help up down restart logs build clean status shell test

# Default target
help: ## Show this help message
	@echo "Job Bot - Docker Management"
	@echo "=========================="
	@echo "Available targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Environment setup
setup: ## Set up environment file
	@if [ ! -f .env ]; then \
		echo "Creating .env file from template..."; \
		cp env.example .env; \
		echo "✅ Created .env file. Please customize it for your environment."; \
	else \
		echo "⚠️  .env file already exists. Skipping creation."; \
	fi

# Primary targets
up: setup ## Start all services
	@echo "🚀 Starting Job Bot services..."
	docker-compose up -d
	@echo "✅ Services started!"
	@echo ""
	@echo "🌐 Available services:"
	@echo "  API:          http://localhost:8000"
	@echo "  Dashboard:    http://localhost:8080"
	@echo "  RQ Dashboard: http://localhost:9181"
	@echo "  PostgreSQL:   localhost:5432"
	@echo "  Redis:        localhost:6379"
	@echo ""
	@echo "📊 Check status: make status"
	@echo "📋 View logs:    make logs"

down: ## Stop all services
	@echo "🛑 Stopping Job Bot services..."
	docker-compose down
	@echo "✅ Services stopped!"

restart: ## Restart all services
	@echo "🔄 Restarting Job Bot services..."
	docker-compose restart
	@echo "✅ Services restarted!"

logs: ## Show logs for all services
	@echo "📋 Showing logs for all services (Ctrl+C to exit)..."
	docker-compose logs -f

# Service-specific logs
logs-api: ## Show API service logs
	docker-compose logs -f api

logs-worker: ## Show worker service logs
	docker-compose logs -f worker

logs-postgres: ## Show PostgreSQL logs
	docker-compose logs -f postgres

logs-redis: ## Show Redis logs
	docker-compose logs -f redis

# Build and maintenance
build: ## Build all Docker images
	@echo "🔨 Building Job Bot Docker images..."
	docker-compose build --no-cache
	@echo "✅ Images built!"

rebuild: ## Rebuild and restart services
	@echo "🔨 Rebuilding and restarting services..."
	docker-compose down
	docker-compose build --no-cache
	docker-compose up -d
	@echo "✅ Services rebuilt and restarted!"

# Status and monitoring
status: ## Show status of all services
	@echo "📊 Job Bot Service Status:"
	@echo "========================="
	docker-compose ps

health: ## Check health of all services
	@echo "🏥 Health Check:"
	@echo "==============="
	@docker-compose exec -T postgres pg_isready -U jobbot -d jobbot || echo "❌ PostgreSQL unhealthy"
	@docker-compose exec -T redis redis-cli ping || echo "❌ Redis unhealthy"
	@curl -s http://localhost:8000/health > /dev/null && echo "✅ API healthy" || echo "❌ API unhealthy"

# Database management
db-init: ## Initialize database with schema
	@echo "🗄️  Initializing database..."
	docker-compose exec api python scripts/init_db.py
	@echo "✅ Database initialized!"

db-shell: ## Open PostgreSQL shell
	@echo "🐘 Opening PostgreSQL shell..."
	docker-compose exec postgres psql -U jobbot -d jobbot

db-backup: ## Backup database
	@echo "💾 Creating database backup..."
	mkdir -p backups
	docker-compose exec postgres pg_dump -U jobbot jobbot > backups/jobbot_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "✅ Database backup created in backups/ directory"

# Application management
shell: ## Open shell in API container
	@echo "🐚 Opening shell in API container..."
	docker-compose exec api bash

worker-shell: ## Open shell in worker container
	@echo "🐚 Opening shell in worker container..."
	docker-compose exec worker bash

seed: ## Seed database with sample data
	@echo "🌱 Seeding database with sample data..."
	docker-compose exec api python scripts/seed_and_run.py
	@echo "✅ Database seeded!"

# Testing
test: ## Run tests in container
	@echo "🧪 Running tests..."
	docker-compose exec api python -m pytest tests/ -v
	@echo "✅ Tests completed!"

test-scorer: ## Run scorer tests specifically
	@echo "🧪 Running scorer tests..."
	docker-compose exec api python -m pytest tests/test_scorer.py -v

# Cleanup
clean: ## Clean up containers, networks, and volumes
	@echo "🧹 Cleaning up Docker resources..."
	docker-compose down -v --remove-orphans
	docker system prune -f
	@echo "✅ Cleanup completed!"

clean-all: ## Clean up everything including images
	@echo "🧹 Cleaning up all Docker resources..."
	docker-compose down -v --remove-orphans --rmi all
	docker system prune -af
	@echo "✅ Complete cleanup finished!"

# Development
dev: ## Start in development mode with live reload
	@echo "🔧 Starting in development mode..."
	docker-compose -f docker-compose.yml up -d postgres redis
	@echo "Database and Redis started. Run API and worker locally:"
	@echo "  API:    uvicorn apps.api.main:app --reload"
	@echo "  Worker: rq worker -u redis://localhost:6379/0 jobs"

# Production
prod: ## Start in production mode
	@echo "🚀 Starting in production mode..."
	ENVIRONMENT=production docker-compose up -d
	@echo "✅ Production services started!"

# Monitoring
monitor: ## Show real-time resource usage
	@echo "📊 Real-time resource monitoring (Ctrl+C to exit)..."
	docker stats $(shell docker-compose ps -q)

# Quick actions
quick-start: up db-init seed ## Quick start with database initialization and sample data
	@echo "🎯 Quick start completed!"
	@echo "🌐 Job Bot is ready at http://localhost:8000"

# Backup and restore
backup: db-backup ## Create full backup
	@echo "💾 Creating full backup..."
	tar -czf backups/jobbot_full_$(shell date +%Y%m%d_%H%M%S).tar.gz \
		config/ artifacts/ backups/*.sql 2>/dev/null || true
	@echo "✅ Full backup created!"

# Update
update: ## Pull latest changes and rebuild
	@echo "🔄 Updating Job Bot..."
	git pull
	docker-compose down
	docker-compose build --no-cache
	docker-compose up -d
	@echo "✅ Update completed!"

# Service management
scale-workers: ## Scale worker instances (make scale-workers N=3)
	@echo "📈 Scaling workers to $(N) instances..."
	docker-compose up -d --scale worker=$(N)
	@echo "✅ Workers scaled to $(N) instances!"
