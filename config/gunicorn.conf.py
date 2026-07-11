"""Gunicorn configuration for production deployment.

Optimized for AWS ECS Fargate with:
- Async workers for FastAPI
- Resource-based worker scaling
- Graceful timeout handling
- Access and error logging
"""

import multiprocessing
import os

# ---------------------------------------------------------------------------
# Server Socket
# ---------------------------------------------------------------------------

# Bind to all interfaces
bind = "0.0.0.0:8000"

# Backlog size for pending connections
backlog = 2048

# ---------------------------------------------------------------------------
# Worker Processes
# ---------------------------------------------------------------------------

# Worker class - use uvicorn workers for async FastAPI
worker_class = "uvicorn.workers.UvicornWorker"

# Number of workers (2-4 x CPU cores for I/O bound apps)
workers = int(os.getenv("API_WORKERS", "4"))

# Number of threads per worker
threads = int(os.getenv("API_THREADS", "2"))

# Maximum requests per worker before restart (prevents memory leaks)
max_requests = 10000
max_requests_jitter = 1000

# ---------------------------------------------------------------------------
# Process Naming
# ---------------------------------------------------------------------------

proc_name = "pharma-assistant"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

# Access log
accesslog = "-"  # stdout
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    '"%(f)s" "%(a)s" %(D)s'
)

# Error log
errorlog = "-"  # stderr

# Log level
loglevel = os.getenv("LOG_LEVEL", "info")

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------

# Worker timeout (seconds)
timeout = 30

# Graceful worker timeout
graceful_timeout = 30

# Keep-alive timeout
keepalive = 5

# ---------------------------------------------------------------------------
# Process Management
# ---------------------------------------------------------------------------

# Daemonize (False for container deployment)
daemon = False

# PID file location
pidfile = "/var/run/pharma/gunicorn.pid"

# User and group (set to non-root in Docker)
user = "pharma"
group = "pharma"

# Temporary directory
worker_tmp_dir = "/dev/shm"

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

# Limit request line size (prevent buffer overflow attacks)
limit_request_line = 4096

# Limit request field size
limit_request_fields = 100

# Limit request field size
limit_request_field_size = 8190

# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting PharmaAssist Gunicorn server")


def on_reload(server):
    """Called before SIGHUP reload."""
    server.log.info("Reloading PharmaAssist Gunicorn server")


def when_ready(server):
    """Called just after the server is started."""
    server.log.info("PharmaAssist server is ready")


def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info(f"Worker {worker.pid} received interrupt signal")


def pre_request(worker, req):
    """Called just before a worker processes the request."""
    worker.log.debug(f"Processing request: {req.method} {req.path}")


def post_request(worker, req, environ, resp):
    """Called after a worker processes the request."""
    worker.log.debug(f"Completed: {req.method} {req.path} - {resp.status}")


def worker_exit(server, worker):
    """Called just after a worker has been exited."""
    server.log.info(f"Worker {worker.pid} exited")
