#!/bin/bash
# ============================================================================
# PharmaAssist Database Migration Script
# Runs Alembic migrations with proper error handling
# ============================================================================

set -euo pipefail

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Configuration
MIGRATION_DIR="${MIGRATION_DIR:-alembic}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
RETRY_COUNT=0
MAX_RETRIES=30

# Wait for database
wait_for_db() {
    log_info "Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
    
    until pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "${POSTGRES_USER}" &>/dev/null; do
        RETRY_COUNT=$((RETRY_COUNT + 1))
        
        if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
            log_error "Database not available after ${MAX_RETRIES} retries"
            exit 1
        fi
        
        log_warn "Waiting... (${RETRY_COUNT}/${MAX_RETRIES})"
        sleep 2
    done
    
    log_info "Database is ready"
}

# Run migrations
run_migrations() {
    local action="${1:-upgrade}"
    
    case "$action" in
        upgrade)
            log_info "Running database migrations (upgrade)..."
            if alembic upgrade head; then
                log_info "Migrations completed successfully"
            else
                log_error "Migration upgrade failed"
                exit 1
            fi
            ;;
        
        downgrade)
            log_info "Rolling back last migration..."
            if alembic downgrade -1; then
                log_info "Rollback completed successfully"
            else
                log_error "Migration rollback failed"
                exit 1
            fi
            ;;
        
        history)
            log_info "Migration history:"
            alembic history
            ;;
        
        current)
            log_info "Current migration:"
            alembic current
            ;;
        
        *)
            log_error "Unknown action: $action"
            echo "Usage: $0 {upgrade|downgrade|history|current}"
            exit 1
            ;;
    esac
}

# Main
main() {
    wait_for_db
    run_migrations "${1:-upgrade}"
}

main "$@"
