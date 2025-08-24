#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Activate the virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

export FLASK_APP=app.py

# Upgrade the database to the latest migration
echo "Upgrading database..."
./venv/bin/python3 -m flask db upgrade

# Start the Flask application with Gunicorn
echo "Starting Flask application with Gunicorn on port 8000..."
./venv/bin/python3 -m gunicorn --bind 0.0.0.0:8000 wsgi:app
