# Deployment Guide for Stock App with Apache2 and MySQL

This guide provides step-by-step instructions for deploying the Stock Picker Flask application on a Digital Ocean server running Ubuntu.

## Prerequisites
- A Digital Ocean Droplet with Ubuntu 20.04 or later.
- A non-root user with `sudo` privileges.
- Apache2, MySQL Server, Python 3, and `pip` installed.

## Step 1: Install and Configure MySQL
(This section remains the same - instructions for `mysql_secure_installation`, `bind-address`, firewall, etc.)

## Step 2: Create the Database and User
(This section remains the same - instructions for `CREATE DATABASE` and `CREATE USER`.)

## Step 3: Clone Repository and Set Up Environment

1.  **Clone the Repository:**
    ```bash
    sudo mkdir -p /var/www/webhost/stock
    git clone <your-repo-url> /var/www/webhost/stock
    cd /var/www/webhost/stock
    ```

2.  **Set up Python Environment:**
    ```bash
    sudo apt-get update
    sudo apt-get install -y python3-venv default-libmysqlclient-dev build-essential
    python3 -m venv venv
    ```

3.  **Install Dependencies:**
    Activate the environment and install packages.
    ```bash
    source venv/bin/activate
    pip install -r requirements.txt
    pip install gunicorn
    deactivate
    ```

## Step 4: Create Configuration File

The application loads all secrets and configuration from a `.env` file.

1.  **Create the `.env` file:**
    ```bash
    sudo nano /var/www/webhost/stock/.env
    ```

2.  **Add your configuration.** Paste the following block into the file, replacing the placeholder values with your actual database credentials and API keys.
    ```env
    # -- Database Configuration --
    DB_HOST=64.225.55.254
    DB_USER=stocks
    DB_PASSWORD=your_strong_password
    DB_NAME=stocks_db

    # -- API Keys --
    # Secret key for securing your own API endpoints
    SCRAPER_API_KEY=YOUR_SUPER_SECRET_KEY_HERE

    # API key from marketaux.com for sentiment analysis
    MARKETAUX_API_KEY=YOUR_MARKETAUX_KEY_HERE

    # API key from alphavantage.co for enriching the stock/ETF list
    ALPHAVANTAGE_API_KEY=YOUR_ALPHAVANTAGE_KEY_HERE
    ```

## Step 5: Set Ownership and Permissions
The `www-data` user needs to own the application files to run it, but it should not own the `.env` file for security.
```bash
# Set www-data as owner for most files
sudo chown -R www-data:www-data /var/www/webhost/stock
# Set your own user as owner of the .env file
sudo chown your_user:your_user /var/www/webhost/stock/.env
# Make the .env file readable by the www-data group
sudo chmod 640 /var/www/webhost/stock/.env
```

## Step 6: Set Up and Populate the Database
Run the setup script as the `www-data` user to ensure it can connect to the database using the new `.env` file.
```bash
cd /var/www/webhost/stock
sudo -u www-data /var/www/webhost/stock/venv/bin/python setup_database.py
```

## Step 7: Configure Gunicorn Service
Create the `systemd` service file. Note that we no longer need to put `Environment=` lines here.
```bash
sudo nano /etc/systemd/system/hotstocks.service
```
Content:
```ini
[Unit]
Description=Gunicorn instance to serve Stock App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/webhost/stock
Environment="PATH=/var/www/webhost/stock/venv/bin"
ExecStart=/var/www/webhost/stock/venv/bin/gunicorn --workers 3 --timeout 120 --bind unix:hotstocks.sock -m 007 wsgi:application

[Install]
WantedBy=multi-user.target
```

## Step 8: Configure Apache2 and Start Services
(This section remains the same - create `wsgi.py`, enable modules, add ProxyPass, and start/enable services).

## Step 9: Configure Automation
Set up your `n8n` or `cron` jobs as described previously. The application will now get all its API keys and credentials from the `.env` file, so you no longer need to manage them in the service file.
