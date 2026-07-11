#!/bin/bash
# ============================================================================
# PharmaAssist Health Check Script
# Used by Kubernetes/ECS health probes
# ============================================================================

set -euo pipefail

# Configuration
HEALTH_CHECK_URL="${HEALTH_CHECK_URL:-http://localhost:8000/health}"
READINESS_URL="${READINESS_URL:-http://localhost:8000/api/v1/health/ready}"
TIMEOUT="${TIMEOUT:-5}"
MAX_RETRIES="${MAX_RETRIES:-3}"

# Function to perform HTTP health check
check_endpoint() {
    local url=$1
    local expected_status=${2:-200}
    
    for i in $(seq 1 $MAX_RETRIES); do
        response=$(curl -s -o /dev/null -w "%{http_code}" \
            --max-time "$TIMEOUT" \
            "$url" 2>/dev/null || echo "000")
        
        if [ "$response" = "$expected_status" ]; then
            return 0
        fi
        
        if [ $i -lt $MAX_RETRIES ]; then
            sleep 1
        fi
    done
    
    return 1
}

# Main health check logic
main() {
    case "${1:-liveness}" in
        liveness)
            # Simple liveness check
            if check_endpoint "$HEALTH_CHECK_URL" 200; then
                echo "Liveness check passed"
                exit 0
            else
                echo "Liveness check failed"
                exit 1
            fi
            ;;
        
        readiness)
            # Readiness check with dependencies
            if check_endpoint "$READINESS_URL" 200; then
                echo "Readiness check passed"
                exit 0
            else
                echo "Readiness check failed"
                exit 1
            fi
            ;;
        
        *)
            echo "Usage: $0 {liveness|readiness}"
            exit 1
            ;;
    esac
}

main "$@"
