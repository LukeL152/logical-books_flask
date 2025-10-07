#!/bin/bash

echo "--- Starting Migration Creation Process ---"

# 1. Pulling latest changes from main branch...
echo "1. Pulling latest changes from main branch..."
git pull origin main --rebase
if [ $? -ne 0 ]; then
    echo "Error: Could not pull from main. Please resolve conflicts and try again."
    exit 1
fi

# 2. Running the migration command...
echo "2. Running the migration command..."
flask db migrate -m "$1"
if [ $? -ne 0 ]; then
    echo "Error: flask db migrate command failed."
    exit 1
fi

# 3. Stamping the database head...
echo "3. Stamping the database head..."
flask db stamp head
if [ $? -ne 0 ]; then
    echo "Error: flask db stamp head command failed."
    exit 1
fi

echo "--- Migration Created Successfully ---"
