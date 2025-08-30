#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# --- Configuration ---
REPO_URL="https://github.com/LukeL152/logical-books_flask.git" # Replace with your actual GitHub repo URL
APP_DIR="/var/www/logical-books" # Directory where the app will be cloned
VENV_DIR="$APP_DIR/venv"
GUNICORN_PORT=8000 # Gunicorn will listen on this port
APP_NAME="logical-books" # Used for systemd service and nginx config

# --- 1. Install System Dependencies ---
echo "Updating apt and installing system dependencies..."
sudo apt update
sudo apt install -y python3 python3-venv git build-essential

echo "System dependencies installed."

# --- 2. Clone Repository ---
echo "Cloning repository..."
if [ -d "$APP_DIR" ]; then
    echo "Application directory already exists. Pulling latest changes."
    cd "$APP_DIR"
    git pull
else
    echo "Cloning new repository into $APP_DIR"
    sudo mkdir -p "$APP_DIR"
    sudo chown -R $USER:$USER "$APP_DIR" # Give ownership to current user for setup
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi
echo "Repository cloned."

# --- 3. Python Environment Setup ---
echo "Setting up Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt
echo "Python environment setup complete."

# --- 4. Database Setup ---
echo "Running database migrations..."
flask db upgrade



echo "Database migrations complete."

# --- 5. Generate and Set SECRET_KEY ---
echo "Generating SECRET_KEY..."
SECRET_KEY=$(python3 -c 'import os; print(os.urandom(24).hex())')
echo "SECRET_KEY generated."

# --- 6. Create Gunicorn Systemd Service ---
# Note: The service runs as Group=www-data. For the application to be able to
# write to the SQLite database, this group may need write permissions to the
# instance folder, e.g., by running:
# sudo chown -R :www-data instance && sudo chmod -R g+w instance

echo "Creating Gunicorn Systemd service file..."
sudo bash -c "cat > /etc/systemd/system/$APP_NAME.service <<EOF
[Unit]
Description=Gunicorn instance for $APP_NAME
After=network.target

[Service]
User=$USER
Group=www-data
WorkingDirectory=$APP_DIR
Environment=\"PATH=$VENV_DIR/bin\"
Environment=\"FLASK_ENV=production\"
Environment=\"SECRET_KEY=$SECRET_KEY\"
ExecStart=$VENV_DIR/bin/gunicorn --workers 3 --bind 0.0.0.0:8000 wsgi:app
ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF"
echo "Gunicorn Systemd service file created."



# --- 8. Enable and Start Services ---
echo "Enabling and starting services..."
sudo systemctl daemon-reload
sudo systemctl start $APP_NAME
sudo systemctl enable $APP_NAME
echo "Services enabled and started."

echo "Deployment complete! Your application should be accessible via your EC2 instance's public IP address."
