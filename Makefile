# ============================================
# PharmaAssist Makefile
# Common development and operations tasks
# ============================================

.PHONY: help install dev-setup test lint format clean build docker-build deploy security-scan

APP_NAME := pharma-assistant
DOCKER_IMAGE := pharma-assistant
AWS_REGION := us-east-1
ECR_REPO := $(AWS_ACCOUNT_ID).dkr.ecr.$(AWS_REGION).amazonaws.com/$(DOCKER_IMAGE)

# Default target
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Installation
install: ## Install project dependencies with Poetry
	poetry install --with dev

dev-setup: install ## Complete development environment setup
	poetry run pre-commit install
	@echo "Development environment ready!"

# Quality Checks
lint: ## Run all linters
	poetry run ruff check src/ tests/
	poetry run mypy src/ --strict
	poetry run bandit -c pyproject.toml -r src/

format: ## Format code with Black and isort
	poetry run black src/ tests/ --line-length=100
	poetry run isort src/ tests/ --profile=black

check: lint format ## Run all code quality checks
	@echo "All checks passed!"

# Testing
test-unit: ## Run unit tests
	poetry run pytest tests/unit -v --cov=src --cov-report=term-missing --cov-report=xml

test-integration: ## Run integration tests (requires Docker)
	@docker-compose up -d postgres mongodb redis opensearch
	@sleep 10
	poetry run pytest tests/integration -v
	@docker-compose down

test-e2e: ## Run end-to-end tests
	poetry run pytest tests/e2e -v

test-all: test-unit test-integration test-e2e ## Run all tests

# Coverage
coverage: test-unit ## Generate HTML coverage report
	poetry run coverage html
	@echo "Coverage report generated in htmlcov/index.html"

# Database
migrate-create: ## Create a new Alembic migration
	poetry run alembic revision --autogenerate -m "$(message)"

migrate-up: ## Run database migrations
	poetry run alembic upgrade head

migrate-down: ## Rollback last migration
	poetry run alembic downgrade -1

seed-data: ## Seed database with sample data
	poetry run python scripts/seed_data.py

# Docker
docker-build: ## Build Docker image
	docker build -t $(DOCKER_IMAGE):latest .

docker-build-prod: ## Build production Docker image
	docker build -f Dockerfile.prod -t $(DOCKER_IMAGE):$(VERSION) .

docker-run: docker-build ## Run container locally
	docker-compose up -d postgres mongodb redis opensearch
	docker run --env-file .env -p 8000:8000 $(DOCKER_IMAGE):latest

# AWS Operations
aws-ecr-login: ## Login to AWS ECR
	aws ecr get-login-password --region $(AWS_REGION) | \
	docker login --username AWS --password-stdin $(ECR_REPO)

docker-push: aws-ecr-login ## Build and push to ECR
	docker build -f Dockerfile.prod -t $(ECR_REPO):$(VERSION) .
	docker push $(ECR_REPO):$(VERSION)

deploy-staging: ## Deploy to staging environment
	cd infrastructure/terraform/environments/staging && \
	terraform init && terraform apply -auto-approve

deploy-prod: ## Deploy to production environment
	cd infrastructure/terraform/environments/prod && \
	terraform init && terraform apply -auto-approve

# Infrastructure
tf-init: ## Initialize Terraform
	cd infrastructure/terraform/environments/dev && terraform init

tf-plan: ## Plan Terraform changes
	cd infrastructure/terraform/environments/dev && terraform plan

tf-apply: ## Apply Terraform changes
	cd infrastructure/terraform/environments/dev && terraform apply

tf-destroy: ## Destroy Terraform infrastructure
	cd infrastructure/terraform/environments/dev && terraform destroy

# Security Scanning
security-scan: ## Run security vulnerability scans
	trivy image $(DOCKER_IMAGE):latest
	trivy fs --security-checks vuln,config src/
	poetry run bandit -c pyproject.toml -r src/
	checkov -d infrastructure/

# Cleanup
clean: ## Clean up build artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov/ .coverage .coverage.* coverage.xml

clean-all: clean ## Deep clean including Docker
	docker-compose down -v --remove-orphans
	docker system prune -f

# Development
run: ## Run development server
	poetry run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

shell: ## Open Python shell with context
	poetry run python -c "from src.main import app; print('FastAPI app loaded')"

logs: ## Tail application logs
	docker-compose logs -f app

# Local Infrastructure
up: ## Start local infrastructure
	docker-compose up -d

down: ## Stop local infrastructure
	docker-compose down

restart: down up ## Restart local infrastructure
