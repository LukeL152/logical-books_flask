#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Check if a migration message is provided
if [ -z "$1" ]; then
  echo "Error: Migration message is required."
  echo "Usage: ./create_migration.sh \"your migration message\""
  exit 1
fi

echo "--- Starting Migration Creation Process ---"

# 1. Sync with the latest main branch
echo "1. Pulling latest changes from main branch..."
git pull origin main

# 2. Apply any pending migrations locally
echo "2. Upgrading local database to the latest version..."
./venv/bin/python3 -m flask db upgrade

# 3. Create the new migration
echo "3. Creating new migration file..."
./venv/bin/python3 -m flask db migrate -m "$1"

echo "--- Migration Creation Complete ---"
echo "New migration file created. Please review and commit it."
