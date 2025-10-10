#!/bin/bash
set -e

# Activate virtual environment
source venv/bin/activate

# Run Gunicorn with live logging
# This is intended for live debugging and will stop when you close the terminal.
# For persistent background service, use the systemd service.
echo "Starting Gunicorn on 0.0.0.0:8000 with INFO log level..."
gunicorn --workers 3 --bind 0.0.0.0:8000 --log-level info wsgi:app
