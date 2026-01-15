# Deployment Guide

This guide describes how to deploy the Portfolio Analyzer application to a Linux web server (e.g., Ubuntu).

## Prerequisites

*   **Linux Server**: Ubuntu 20.04 LTS or later is recommended.
*   **Root/Sudo Access**: You need administrative privileges on the server.
*   **Git**: To clone the repository.
*   **Python 3.8+**: The application requires Python 3.8 or newer.
*   **MySQL Server**: The application uses a MySQL database.

## Step 1: System Update & Dependencies

Update your package lists and install necessary system packages:

```bash
sudo apt update
sudo apt install -y python3-pip python3-dev python3-venv build-essential libssl-dev libffi-dev python3-setuptools mysql-server libmysqlclient-dev git nginx
```

## Step 2: Database Setup

1.  Secure your MySQL installation (optional but recommended):
    ```bash
    sudo mysql_secure_installation
    ```

2.  Log in to MySQL as root:
    ```bash
    sudo mysql
    ```

3.  Create the database and user:
    ```sql
    CREATE DATABASE portfolio_db;
    CREATE USER 'portfolio_user'@'localhost' IDENTIFIED BY 'your_strong_password';
    GRANT ALL PRIVILEGES ON portfolio_db.* TO 'portfolio_user'@'localhost';
    FLUSH PRIVILEGES;
    EXIT;
    ```
    *(Replace `portfolio_db`, `portfolio_user`, and `your_strong_password` with your desired values.)*

## Step 3: Clone the Repository

Navigate to your web directory (e.g., `/var/www/`) and clone the app:

```bash
cd /var/www
sudo git clone <repository_url> portfolio_app
cd portfolio_app
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

1.  Create a `.env` file in the project root based on the following template:

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
    # Get a free key from https://www.marketaux.com/
    MARKETAUX_API_KEY=your_marketaux_api_key

    # Optional: If you changed the data loader to use an env var
    # ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key
    ```

2.  **Initialize the Database**:
    Run the application once to initialize the database tables.
    ```bash
    python3 -c "from app import init_db, init_user_db; init_db(); init_user_db()"
    ```
    *Note: If the above command fails due to import context, you can simply run `python3 app.py` for a moment and then kill it with Ctrl+C, as the `init_db` calls are at the module level or top of script.*

    Better yet, populate the stock universe:
    ```bash
    python3 data_loader.py
    ```

## Step 6: Configure Gunicorn with Systemd

Create a systemd service file to keep the application running.

1.  Create the file:
    ```bash
    sudo nano /etc/systemd/system/portfolio.service
    ```

2.  Add the following content (adjust paths/users as needed):

    ```ini
    [Unit]
    Description=Gunicorn instance to serve Portfolio Analyzer
    After=network.target

    [Service]
    User=www-data
    Group=www-data
    WorkingDirectory=/var/www/portfolio_app
    Environment="PATH=/var/www/portfolio_app/venv/bin"
    ExecStart=/var/www/portfolio_app/venv/bin/gunicorn --workers 3 --bind unix:portfolio.sock -m 007 wsgi:application

    [Install]
    WantedBy=multi-user.target
    ```

    *Note: We assume you want to run as `www-data`. You may need to change ownership of the folder:*
    ```bash
    sudo chown -R www-data:www-data /var/www/portfolio_app
    ```

3.  Start and enable the service:
    ```bash
    sudo systemctl start portfolio
    sudo systemctl enable portfolio
    ```

4.  Check status:
    ```bash
    sudo systemctl status portfolio
    ```

## Step 7: Configure Nginx

Configure Nginx to proxy requests to Gunicorn.

1.  Create a new server block config:
    ```bash
    sudo nano /etc/nginx/sites-available/portfolio
    ```

2.  Add the following:

    ```nginx
    server {
        listen 80;
        server_name your_domain_or_IP;

        location / {
            include proxy_params;
            proxy_pass http://unix:/var/www/portfolio_app/portfolio.sock;
        }

        location /static {
            alias /var/www/portfolio_app/static;
        }
    }
    ```

3.  Enable the site:
    ```bash
    sudo ln -s /etc/nginx/sites-available/portfolio /etc/nginx/sites-enabled
    ```

4.  Test Nginx config:
    ```bash
    sudo nginx -t
    ```

5.  Restart Nginx:
    ```bash
    sudo systemctl restart nginx
    ```

## Step 8: Final Verification

Visit `http://your_domain_or_IP` in your browser. You should see the login/dashboard page.

## Maintenance

*   **View Logs**:
    ```bash
    sudo journalctl -u portfolio
    ```
*   **Restart App**:
    ```bash
    sudo systemctl restart portfolio
    ```
