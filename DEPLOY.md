# Deployment Guide for Stock App with Apache2 and MySQL

This guide provides step-by-step instructions for deploying the Stock Picker Flask application on a Digital Ocean server running Ubuntu. The application will be served using **Apache2** as a reverse proxy, Gunicorn as the WSGI server, and **MySQL** as the database.

The application will be accessible at `https://zapp.sytes.net/stock/`.
The application files will be located in `/var/www/webhost/stock/`.

## Prerequisites

- A Digital Ocean Droplet with Ubuntu 20.04 or later.
- A non-root user with `sudo` privileges.
- **Apache2** installed and running.
- **MySQL Server** installed and running.
- Python 3 and `pip` installed.

## Step 1: Install and Configure MySQL

If you don't have MySQL installed, follow these steps.

1.  **Install MySQL Server:**
    ```bash
    sudo apt update
    sudo apt install mysql-server
    ```

2.  **Secure Your MySQL Installation:**
    Run the included security script. You'll be asked to set a root password and answer several security-related questions. It's recommended to answer 'yes' to all of them.
    ```bash
    sudo mysql_secure_installation
    ```

3.  **Allow Remote Connections (CRITICAL):**
    By default, MySQL only listens for local connections. You must enable remote connections so the application can access it.
    ```bash
    sudo nano /etc/mysql/mysql.conf.d/mysqld.cnf
    ```
    Find the line `bind-address = 127.0.0.1` and change it to `bind-address = 0.0.0.0`.

4.  **Configure Firewall:**
    Allow incoming connections to the MySQL port (3306).
    ```bash
    sudo ufw allow 3306/tcp
    ```

5.  **Restart MySQL Service:**
    ```bash
    sudo systemctl restart mysql
    ```

## Step 2: Create the Database and User

1.  **Log in to MySQL as root:**
    ```bash
    sudo mysql -u root -p
    ```

2.  **Run the following SQL commands** to create the database and a dedicated user for the application. Replace `'your_strong_password'` with a secure password.

    ```sql
    -- Create the database
    CREATE DATABASE stocks_db;

    -- Create the user for remote connections
    CREATE USER 'stocks'@'%' IDENTIFIED BY 'your_strong_password';

    -- Grant privileges to the new user on the new database
    GRANT ALL PRIVILEGES ON stocks_db.* TO 'stocks'@'%';

    -- Apply the changes
    FLUSH PRIVILEGES;

    -- Exit the MySQL prompt
    EXIT;
    ```

## Step 3: Clone the Repository and Set Up the Environment

1.  **Create the directory and clone the repository:**
    ```bash
    sudo mkdir -p /var/www/webhost/stock
    git clone <your-repo-url> /var/www/webhost/stock
    ```

2.  **Set Directory Permissions:**
    The Gunicorn process runs as the `www-data` user, so this user needs to own the application files.
    ```bash
    sudo chown -R www-data:www-data /var/www/webhost/stock
    ```

3.  **Set up Python Environment:**
    ```bash
    cd /var/www/webhost/stock
    python3 -m venv venv
    source venv/bin/activate

    # Install system dependencies required for the MySQL connector
    sudo apt-get install -y default-libmysqlclient-dev build-essential

    # Install Python packages
    pip install -r requirements.txt
    pip install gunicorn
    ```

## Step 4: Set Up the Database Schema and Initial Data

Run the included setup script to create the necessary tables and populate them with starter data.
```bash
# Make sure you are in the project directory and the virtual environment is activated
cd /var/www/webhost/stock
source venv/bin/activate

python setup_database.py
```

## Step 5: Configure Gunicorn and Apache2

This part of the setup remains largely the same.

1.  **Create a `wsgi.py` file:**
    ```bash
    sudo nano wsgi.py
    ```
    Content:
    ```python
    from app import app
    application = app
    ```

2.  **Create a `systemd` service file for Gunicorn:**
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
    # --- Application Configuration ---
    # Set your secret API key for the scraper
    Environment="SCRAPER_API_KEY=YOUR_REALLY_LONG_AND_SECRET_KEY_HERE"
    # Set the database connection details
    Environment="DB_HOST=127.0.0.1" # Or your remote DB IP
    Environment="DB_USER=stocks"
    Environment="DB_PASSWORD=your_strong_password"
    Environment="DB_NAME=stocks_db"

    # With MySQL, we can safely use multiple workers
    ExecStart=/var/www/webhost/stock/venv/bin/gunicorn --workers 3 --timeout 120 --bind unix:hotstocks.sock -m 007 wsgi:application

    [Install]
    WantedBy=multi-user.target
    ```
    **Note:** We can now use `--workers 3` since MySQL handles concurrent connections gracefully, unlike SQLite.

3.  **Configure Apache2:**
    Enable the required modules:
    ```bash
    sudo a2enmod proxy proxy_http headers
    sudo systemctl restart apache2
    ```
    Edit your site configuration (`sudo nano /etc/apache2/sites-enabled/webhost-le-ssl.conf`) and add the proxy directives inside the `<VirtualHost *:443>` block:
    ```apache
    ProxyPass /stock/ unix:/var/www/webhost/stock/hotstocks.sock|http://localhost/
    ProxyPassReverse /stock/ unix:/var/www/webhost/stock/hotstocks.sock|http://localhost/
    RequestHeader set X-Forwarded-Prefix /stock
    ```

## Step 6: Start the Services

1.  **Reload `systemd`, then start and enable the `hotstocks` service:**
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl start hotstocks
    sudo systemctl enable hotstocks
    ```

2.  **Restart Apache2:**
    ```bash
    sudo systemctl restart apache2
    ```

## Step 7: Access Your Application

You should now be able to access your application at: `https://zapp.sytes.net/stock/`

The automation setup for `n8n` remains the same as before. Just make sure to use the `SCRAPER_API_KEY` you set in the `hotstocks.service` file.
