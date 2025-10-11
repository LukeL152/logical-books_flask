#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

export FLASK_APP=app.py
export FLASK_DEBUG=1

# Upgrade the database to the latest migration
echo "Upgrading database..."
./venv/bin/python3 -m flask db upgrade

# Start the Flask development server
echo "Starting Flask development server on port 8001..."
./venv/bin/python3 -m flask run --host=0.0.0.0 --port=8000
