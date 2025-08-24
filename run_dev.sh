#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Activate the virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

export FLASK_APP=app.py
export FLASK_DEBUG=1

# Upgrade the database to the latest migration
echo "Upgrading database..."
./venv/bin/python3 -m flask db upgrade

# Start the Flask development server
echo "Starting Flask development server on port 8000..."
./venv/bin/python3 -m flask run --port=8000
