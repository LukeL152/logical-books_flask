#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Starting Update Process ---"

# 1. Pull latest changes
echo "1. Pulling latest changes from git..."
git pull

# 2. Python Environment Setup
echo "2. Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    echo "Creating new virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo "Python environment setup complete."

# 3. Database Backup
echo "3. Creating database backup..."
if [ -f "instance/bookkeeping.db" ]; then
    mkdir -p backups
    TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
    cp instance/bookkeeping.db "backups/bookkeeping.db.$TIMESTAMP"
    echo "Backup created at backups/bookkeeping.db.$TIMESTAMP"
else
    echo "Database not found, skipping backup."
fi

# 4. Database Migration
echo "4. Running database migrations..."
./venv/bin/python3 -m flask db upgrade
echo "Database migrations complete."

echo "--- Update Complete ---"
echo "You can now run the application using ./run_prod.sh to test the changes."
