import os
import subprocess
from dotenv import load_dotenv
import sys

# Load the .env file from the current directory
load_dotenv()

# Check if the required environment variables are set
plaid_client_id = os.environ.get('PLAID_CLIENT_ID')
plaid_secret = os.environ.get('PLAID_SECRET')

if not plaid_client_id or not plaid_secret:
    print("Error: PLAID_CLIENT_ID and PLAID_SECRET must be set in your .env file.")
    print("Please create a .env file in the project root with the following content:")
    print("PLAID_CLIENT_ID=your_plaid_client_id")
    print("PLAID_SECRET=your_plaid_secret")
    exit(1)

# Get the command arguments from the command line
args = sys.argv[1:]

if not args:
    print("Usage: python3 run_inspector.py <command> [args...]")
    print("Example: python3 run_inspector.py accounts 1")
    print("Example: python3 run_inspector.py transactions 1 2023-01-01 2023-01-31")
    exit(1)

# Construct the command to run
# This assumes the script is run from the project root
command = [
    './venv/bin/flask',
    'inspect-plaid',
] + args

print(f"Running command: {' '.join(command)}")

# Run the command
subprocess.run(command)
