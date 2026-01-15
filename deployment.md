# Deployment Guide

This guide describes how to deploy the Portfolio Analyzer application to your existing Linux web server (Apache2).

## Prerequisites

*   **Linux Server**: Ubuntu 20.04 LTS or later.
*   **Root/Sudo Access**: You need administrative privileges.
*   **Git**: To clone the repository.
*   **Python 3.8+**: The application requires Python 3.8 or newer.
*   **MySQL Server**: The application uses a MySQL database.
*   **Apache Modules**: Ensure `proxy`, `proxy_http`, and `headers` modules are enabled.

## Step 1: System Update & Dependencies

Update your package lists and install necessary system packages:

```bash
sudo apt update
sudo apt install -y python3-pip python3-dev python3-venv build-essential libssl-dev libffi-dev python3-setuptools mysql-server libmysqlclient-dev git apache2
```

Enable required Apache modules:
```bash
sudo a2enmod proxy proxy_http headers
sudo systemctl restart apache2
```

## Step 2: Database Setup

1.  Log in to MySQL as root:
    ```bash
    sudo mysql
    ```

2.  Create the database and user:
    ```sql
    CREATE DATABASE portfolio_db;
    CREATE USER 'portfolio_user'@'localhost' IDENTIFIED BY 'your_strong_password';
    GRANT ALL PRIVILEGES ON portfolio_db.* TO 'portfolio_user'@'localhost';
    FLUSH PRIVILEGES;
    EXIT;
    ```
    *(Replace `portfolio_db`, `portfolio_user`, and `your_strong_password` with your desired values.)*

## Step 3: Clone the Repository

Navigate to your web host directory and clone the app:

```bash
cd /var/www/webhost
sudo git clone <repository_url> portfolio
cd portfolio
sudo chown -R $USER:$USER .
```

## Step 4: Python Environment Setup

1.  Create a virtual environment:
    ```bash
    python3 -m venv venv
    ```

2.  Activate the virtual environment:
    ```bash
    source venv/bin/activate
    ```

3.  Install Python dependencies:
    ```bash
    pip install -r requirements.txt
    pip install gunicorn
    ```

## Step 5: Configuration

1.  Create a `.env` file in the project root:

    ```bash
    nano .env
    ```

    **Add the following content:**

    ```env
    # Flask Security
    SECRET_KEY=your_very_long_random_secret_string

    # Database Configuration
    DB_HOST=localhost
    DB_USER=portfolio_user
    DB_PASSWORD=your_strong_password
    DB_NAME=portfolio_db

    # API Keys
    MARKETAUX_API_KEY=your_marketaux_api_key

    # Session Configuration (Important for multi-app setups)
    SESSION_COOKIE_NAME=portfolio_session
    SESSION_COOKIE_PATH=/portfolio
    SESSION_COOKIE_SECURE=True
    ```

2.  **Initialize the Database**:
    Run the application once to initialize the database tables.
    ```bash
    python3 -c "from app import init_db, init_user_db; init_db(); init_user_db()"
    ```
    *Note: This creates the tables. You can also run `python3 data_loader.py` to populate initial stock data.*

## Step 6: Configure Gunicorn with Systemd

Create a systemd service file to keep the application running.

1.  Create the file:
    ```bash
    sudo nano /etc/systemd/system/portfolio.service
    ```

2.  Add the following content:

    ```ini
    [Unit]
    Description=Gunicorn instance to serve Portfolio Analyzer
    After=network.target

    [Service]
    User=www-data
    Group=www-data
    WorkingDirectory=/var/www/webhost/portfolio
    Environment="PATH=/var/www/webhost/portfolio/venv/bin"
    EnvironmentFile=/var/www/webhost/portfolio/.env
    ExecStart=/var/www/webhost/portfolio/venv/bin/gunicorn --workers 3 --bind unix:portfolio.sock -m 007 wsgi:application
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

3.  Set ownership and start the service:
    ```bash
    sudo chown -R www-data:www-data /var/www/webhost/portfolio
    sudo systemctl start portfolio
    sudo systemctl enable portfolio
    ```

4.  Check status:
    ```bash
    sudo systemctl status portfolio
    ```

## Step 7: Configure Apache2

Add the application to your existing VirtualHost configuration file (`/etc/apache2/sites-enabled/webhost-le-ssl.conf`).

1.  Open the configuration file:
    ```bash
    sudo nano /etc/apache2/sites-enabled/webhost-le-ssl.conf
    ```

2.  **Add to SECTION 1: STATIC FILE HANDLING**
    Add the alias for the portfolio static files:

    ```apache
    Alias /portfolio/static/ /var/www/webhost/portfolio/static/
    <Directory /var/www/webhost/portfolio/static>
        Require all granted
    </Directory>
    ```

3.  **Add to SECTION 2: APPLICATION PROXIES**
    Add the location block to proxy requests to the Gunicorn socket.
    *Note: The `X-Forwarded-Prefix` header is required for Flask to generate correct URLs when running under a sub-path.*

    ```apache
    # --- Portfolio Analyzer App ---
    <Location /portfolio/>
        RequestHeader set X-Forwarded-Prefix "/portfolio/"
        ProxyPass unix:/var/www/webhost/portfolio/portfolio.sock|http://localhost/
        ProxyPassReverse unix:/var/www/webhost/portfolio/portfolio.sock|http://localhost/
    </Location>
    ```

4.  **Save and Restart Apache**:
    ```bash
    sudo apachectl configtest
    sudo systemctl restart apache2
    ```

## Step 8: Final Verification

Visit `https://zapp.sytes.net/portfolio/` in your browser. You should see the Portfolio Analyzer login page.
