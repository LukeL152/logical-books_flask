
#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

# Function to print a message to the console
function log() {
    echo "--------------------------------------------------"
    echo "$1"
    echo "--------------------------------------------------"
}

# Check if the user is running the script as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 
   exit 1
fi

# Get the absolute path of the script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the script's directory
cd $DIR

# Pull the latest changes from the git repository
log "Pulling latest changes from git..."
git pull

# Install/update dependencies
log "Installing/updating dependencies..."
pip3 install -r requirements.txt

# Run database migrations
log "Running database migrations..."
export FLASK_APP=app.py
flask db upgrade

# Collect static files
log "Collecting static files..."
flask collect

# Create a systemd service file for the application
log "Creating systemd service file..."
cat > /etc/systemd/system/logical-books.service << EOL
[Unit]
Description=Gunicorn instance to serve Logical Books
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=$DIR
Environment="PATH=$DIR/venv/bin"
ExecStart=$DIR/venv/bin/gunicorn --workers 3 --bind unix:logical-books.sock -m 007 wsgi:app

[Install]
WantedBy=multi-user.target
EOL

# Reload the systemd daemon and restart the application
log "Reloading systemd and restarting the application..."
systemctl daemon-reload
systemctl restart logical-books

# Configure Nginx to proxy requests to the application
log "Configuring Nginx..."
cat > /etc/nginx/sites-available/logical-books << EOL
server {
    listen 80;
    server_name your_domain.com; # Replace with your domain name

    location / {
        include proxy_params;
        proxy_pass http://unix:$DIR/logical-books.sock;
    }
}
EOL

# Create a symbolic link to the sites-enabled directory
ln -s /etc/nginx/sites-available/logical-books /etc/nginx/sites-enabled

# Test the Nginx configuration and restart the service
nginx -t
/etc/init.d/nginx restart

log "Deployment complete!"
