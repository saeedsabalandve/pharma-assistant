#!/bin/bash
# ============================================================================
# PharmaAssist Container Entrypoint Script
# Handles:
# - Environment validation
# - Database migrations
# - AWS credential verification
# - Graceful startup
# ============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# ---------------------------------------------------------------------------
# Environment validation
# ---------------------------------------------------------------------------
validate_environment() {
    log_info "Validating environment..."
    
    # Check required environment variables
    REQUIRED_VARS=(
        "APP_ENV"
        "AWS_REGION"
        "POSTGRES_HOST"
        "POSTGRES_DB"
        "MONGODB_URI"
        "REDIS_HOST"
    )
    
    MISSING_VARS=()
    for var in "${REQUIRED_VARS[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            MISSING_VARS+=("$var")
        fi
    done
    
    if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
        log_error "Missing required environment variables: ${MISSING_VARS[*]}"
        exit 1
    fi
    
    log_info "Environment validation passed"
}

# ---------------------------------------------------------------------------
# Database migrations
# ---------------------------------------------------------------------------
run_migrations() {
    if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
        log_info "Running database migrations..."
        
        # Wait for database to be ready
        MAX_RETRIES=30
        RETRY_COUNT=0
        until pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER}" &>/dev/null; do
            RETRY_COUNT=$((RETRY_COUNT + 1))
            if [[ $RETRY_COUNT -ge $MAX_RETRIES ]]; then
                log_error "Database not ready after ${MAX_RETRIES} retries"
                exit 1
            fi
            log_warn "Waiting for database... (${RETRY_COUNT}/${MAX_RETRIES})"
            sleep 2
        done
        
        # Run Alembic migrations
        if alembic upgrade head; then
            log_info "Database migrations completed successfully"
        else
            log_error "Database migrations failed"
            exit 1
        fi
    else
        log_info "Skipping database migrations (RUN_MIGRATIONS=false)"
    fi
}

# ---------------------------------------------------------------------------
# AWS credential verification
# ---------------------------------------------------------------------------
verify_aws_credentials() {
    if [[ "${APP_ENV}" != "development" ]]; then
        log_info "Verifying AWS credentials..."
        
        if aws sts get-caller-identity --query Account --output text &>/dev/null; then
            AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
            log_info "AWS credentials valid (Account: ${AWS_ACCOUNT_ID})"
        else
            log_warn "AWS credentials verification failed - continuing anyway"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Signal handling for graceful shutdown
# ---------------------------------------------------------------------------
handle_shutdown() {
    log_info "Received shutdown signal - stopping gracefully..."
    
    # Forward signal to child process
    if [[ -n "${APP_PID:-}" ]]; then
        kill -TERM "${APP_PID}" 2>/dev/null || true
        wait "${APP_PID}" 2>/dev/null || true
    fi
    
    log_info "Shutdown complete"
    exit 0
}

trap handle_shutdown SIGTERM SIGINT SIGQUIT

# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------
main() {
    log_info "Starting PharmaAssist v${APP_VERSION:-unknown}"
    log_info "Environment: ${APP_ENV}"
    
    # Run startup checks
    validate_environment
    
    # Verify AWS credentials in non-dev environments
    if [[ "${APP_ENV}" != "development" ]]; then
        verify_aws_credentials
    fi
    
    # Run migrations (if enabled)
    run_migrations
    
    # Execute the main command
    log_info "Starting application: $*"
    exec "$@" &
    APP_PID=$!
    
    # Wait for application to finish
    wait "${APP_PID}"
}

main "$@"
