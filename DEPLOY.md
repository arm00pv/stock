# Deployment Guide

This guide details the deployment of the Stock Picker application on various platforms.

## Option 1: DigitalOcean App Platform (PaaS)
This is the easiest way to deploy a test environment.

1.  **Repo Setup**: Ensure this repository is pushed to GitHub/GitLab.
2.  **App Platform**: Create a new App in DigitalOcean.
3.  **Source**: Select this repository.
4.  **Configuration**:
    *   **Environment Variables**: Add `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `SECRET_KEY`, `SCRAPER_API_KEY`.
    *   **Database**: Add a Managed MySQL database to the app and link it.
5.  **Build Command**: App Platform detects Python automatically. Ensure `requirements.txt` is present.
6.  **Run Command**: The `Procfile` included in this repo will automatically set the run command to `gunicorn wsgi:application`.
7.  **Workers**: To run background tasks (`scraper.py`, `enricher.py`), add them as "Worker" components in the App Platform settings, specifying the start command (e.g., `python scraper.py`).

---

## Option 2: Ubuntu Server (LAMP Stack)

## System Requirements
- Ubuntu 20.04 or 22.04 LTS
- Apache2 (`sudo apt install apache2 libapache2-mod-wsgi-py3`)
- MySQL Server (`sudo apt install mysql-server`)
- Python 3.8+ (`sudo apt install python3-pip python3-venv`)

## Directory Structure
Deploy the application to `/var/www/webhost/stock`:
```
/var/www/webhost/stock/
├── app.py
├── wsgi.py
├── database.py
├── ... (other python files)
├── templates/
├── static/
└── .env
```

## Step 1: Database Setup
1. Log in to MySQL: `sudo mysql`
2. Create database and user:
   ```sql
   CREATE DATABASE stock_db;
   CREATE USER 'stock_user'@'localhost' IDENTIFIED BY 'secure_password';
   GRANT ALL PRIVILEGES ON stock_db.* TO 'stock_user'@'localhost';
   FLUSH PRIVILEGES;
   ```

## Step 2: Application Environment
1. Create a virtual environment:
   ```bash
   cd /var/www/webhost/stock
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
2. Configure `.env`:
   ```bash
   cp .env.example .env
   # Edit .env with your DB credentials and API keys
   ```

## Step 3: Apache Configuration
Create or edit your site config (e.g., `/etc/apache2/sites-available/000-default.conf`):

```apache
<VirtualHost *:80>
    ServerName zapp.sytes.net

    # ... other configurations ...

    WSGIDaemonProcess stock_app threads=5 python-home=/var/www/webhost/stock/venv
    WSGIScriptAlias /stock /var/www/webhost/stock/wsgi.py

    <Directory /var/www/webhost/stock>
        WSGIProcessGroup stock_app
        WSGIApplicationGroup %{GLOBAL}
        Order deny,allow
        Allow from all
    </Directory>
</VirtualHost>
```
*Note: The `WSGIDaemonProcess` uses `threads=5` which complements the `stock_pool` size of 5 in `database.py`.*

## Step 4: Verify Permissions
Ensure `www-data` owns the directory:
```bash
sudo chown -R www-data:www-data /var/www/webhost/stock
```

## Step 5: Pre-Flight Check
Run the included check script to verify connections and dependencies before restarting Apache:
```bash
/var/www/webhost/stock/venv/bin/python /var/www/webhost/stock/deploy_check.py
```

## Step 6: Automation (Cron)
Set up cron jobs (`crontab -e`) to run background tasks. Ensure you use the virtual environment's Python:

```cron
# Daily Scraper (1 AM)
0 1 * * * /var/www/webhost/stock/venv/bin/python /var/www/webhost/stock/scraper.py >> /var/log/stock_scraper.log 2>&1

# Daily Enrichment (2 AM)
0 2 * * * /var/www/webhost/stock/venv/bin/python /var/www/webhost/stock/enricher.py >> /var/log/stock_enricher.log 2>&1

# Hourly Sentiment (Every hour)
0 * * * * /var/www/webhost/stock/venv/bin/python /var/www/webhost/stock/sentiment_analyzer.py >> /var/log/stock_sentiment.log 2>&1
```

## Troubleshooting
- **Logs**: Check `/var/log/apache2/error.log` for WSGI errors.
- **Database**: Ensure `DB_HOST` is set to `localhost` in `.env`.
- **Dependencies**: Run `pip freeze` inside the venv to ensure `mysql-connector-python` and `scikit-learn` are installed.
