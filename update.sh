#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Starting Update Process ---"

# 1. Database Backup
echo "1. Creating database backup..."
if [ -f "bookkeeping.db" ]; then
    mkdir -p backups
    TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
    cp bookkeeping.db "backups/bookkeeping.db.$TIMESTAMP"
    echo "Backup created at backups/bookkeeping.db.$TIMESTAMP"
else
    echo "Database not found, skipping backup."
fi

# 2. Pull latest changes
echo "2. Pulling latest changes from git..."
git pull

# 3. Python Environment Setup
echo "3. Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    echo "Creating new virtual environment..."
    python3 -m venv venv
fi
./venv/bin/python3 -m pip install --upgrade pip
./venv/bin/python3 -m pip install -r requirements.txt
echo "Python environment setup complete."

# 4. Database Migration
echo "4. Running database migrations..."
./venv/bin/python3 -m flask db upgrade
echo "Database migrations complete."

echo "--- Update Complete ---"

systemctl restart logical-books
