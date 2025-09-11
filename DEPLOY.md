# Deployment Guide for Hot Stocks App with Apache2

This guide provides step-by-step instructions for deploying the Hot Stocks Flask application on a Digital Ocean server running Ubuntu. The application will be served using **Apache2** as a reverse proxy and Gunicorn as the WSGI server.

The application will be accessible at `https://zapp.sytes.net/stock/`.
The application files will be located in `/var/www/webhost/stock/`.

## Prerequisites

- A Digital Ocean Droplet with Ubuntu 20.04 or later.
- A non-root user with `sudo` privileges.
- **Apache2** installed and running.
- Python 3 and `pip` installed.

## Step 1: Clone the Repository and Set Up the Environment

1.  **SSH into your server:**
    ```bash
    ssh your_user@zapp.sytes.net
    ```

2.  **Create the directory and clone the repository:**
    ```bash
    sudo mkdir -p /var/www/webhost/stock
    git clone <your-repo-url> /var/www/webhost/stock
    ```

3.  **Set Directory Permissions:**
    This is a crucial step. The Gunicorn process runs as the `www-data` user, so this user needs to own the application files.
    ```bash
    sudo chown -R www-data:www-data /var/www/webhost/stock
    ```

4.  **Set up Python Environment:**
    Change into the project directory:
    ```bash
    cd /var/www/webhost/stock
    ```
    Create a Python virtual environment and install dependencies:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    pip install gunicorn
    ```

## Step 2: Configure Gunicorn

We will use `systemd` to manage the Gunicorn process.

1.  **Create a `systemd` service file:**
    ```bash
    sudo nano /etc/systemd/system/hotstocks.service
    ```

2.  **Add the following content to the file.**

    ```ini
    [Unit]
    Description=Gunicorn instance to serve Hot Stocks app
    After=network.target

    [Service]
    User=www-data
    Group=www-data
    WorkingDirectory=/var/www/webhost/stock
    Environment="PATH=/var/www/webhost/stock/venv/bin"
    ExecStart=/var/www/webhost/stock/venv/bin/gunicorn --workers 3 --bind unix:hotstocks.sock -m 007 wsgi:application

    [Install]
    WantedBy=multi-user.target
    ```

3.  **Create a `wsgi.py` file** for Gunicorn to use:
    ```bash
    sudo nano wsgi.py # Use sudo as the directory is now owned by www-data
    ```
    Add the following content. This imports the Flask `app` object from your `app.py` file and assigns it to a variable named `application`, which Gunicorn expects.
    ```python
    from app import app

    application = app
    ```

## Step 3: Configure Apache2

You will add a proxy configuration to your existing Apache2 site.

1.  **Enable the required Apache modules:**
    This is a critical step. The configuration requires the `proxy`, `proxy_http`, and `headers` modules.
    ```bash
    sudo a2enmod proxy proxy_http headers
    sudo systemctl restart apache2
    ```

2.  **Edit your existing Apache2 site configuration file:**
    ```bash
    sudo nano /etc/apache2/sites-enabled/webhost-le-ssl.conf
    ```

3.  **Add the proxy directives.** Inside the `<VirtualHost *:443>` block, add the following lines.

    ```apache
    # --- Configuration for Hot Stocks App ---
    ProxyPass /stock/ unix:/var/www/webhost/stock/hotstocks.sock|http://localhost/
    ProxyPassReverse /stock/ unix:/var/www/webhost/stock/hotstocks.sock|http://localhost/
    RequestHeader set X-Forwarded-Prefix /stock
    ```
    *Note: We are now using `X-Forwarded-Prefix`. This header works with the `ProxyFix` middleware in the Flask app to correctly handle the `/stock/` URL prefix.*

4.  **Test the Apache2 configuration for syntax errors:**
    ```bash
    sudo apache2ctl configtest
    ```
    If you see `Syntax OK`, you can proceed.

## Step 4: Start and Enable the Services

1.  **Start and enable the `hotstocks` service:**
    ```bash
    sudo systemctl start hotstocks
    sudo systemctl enable hotstocks
    ```

2.  **Restart Apache2 to apply the new configuration:**
    ```bash
    sudo systemctl restart apache2
    ```

## Step 5: Access Your Application

You should now be able to access your application in your web browser at:
`https://zapp.sytes.net/stock/`

If you encounter any issues, you can check the logs for Apache2 and your application:
-   **Apache2 logs:** `sudo journalctl -u apache2` or check `/var/log/apache2/error.log`
-   **Application logs:** `sudo journalctl -u hotstocks`

---

## Step 6 (Optional): Automate Data Scraping with n8n

To keep the stock lists fresh, you can automate the scraper to run daily using your `n8n` server. This is a more robust and manageable solution than a traditional cron job.

The application has a secure API endpoint specifically for this purpose. Your `n8n` workflow will send a request to this endpoint to trigger the scraping process.

### 1. The Scraper Endpoint

-   **URL:** `https://zapp.sytes.net/stock/api/run-scraper`
-   **Method:** `POST`
-   **Security:** The endpoint is protected by a secret API key. You must include this key in the request headers.

### 2. Set Your Secret API Key

The default API key is `your-super-secret-key`. For security, you should change this.

1.  **On your server**, open the `hotstocks.service` file:
    ```bash
    sudo nano /etc/systemd/system/hotstocks.service
    ```
2.  **Add an `Environment` variable** with your own secret key. Choose a long, random string.
    ```ini
    [Service]
    User=www-data
    Group=www-data
    WorkingDirectory=/var/www/webhost/stock
    Environment="PATH=/var/www/webhost/stock/venv/bin"
    Environment="SCRAPER_API_KEY=YOUR_REALLY_LONG_AND_SECRET_KEY_HERE" # Add this line
    ExecStart=/var/www/webhost/stock/venv/bin/gunicorn --workers 2 --timeout 120 --bind unix:hotstocks.sock -m 007 wsgi:application
    ```
    *Note on `--timeout 120`: This increases the worker timeout to 120 seconds to prevent the process from being killed during long-running API calls to Yahoo Finance.*
3.  **Reload the services** to apply the change:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart hotstocks
    ```

### 3. Create the n8n Workflow

On your `n8n` server, create a new workflow with two nodes:

**Node 1: Cron Trigger**
-   Add a **Cron** node.
-   Set the **Mode** to `Every Day`.
-   Set the **Hour** to `8`.
-   Set the **Minute** to `0`.
-   Set the **Timezone** to `America/New_York`.

**Node 2: HTTP Request**
-   Add an **HTTP Request** node and connect it to the Cron node.
-   Set the **Method** to `POST`.
-   Set the **URL** to: `https://zapp.sytes.net/stock/api/run-scraper`
-   Under **Authentication**, select `Header Auth`.
-   In the **Name** field, enter `X-API-Key`.
-   In the **Value** field, enter the same secret key you set in the `hotstocks.service` file.
-   Enable the **"Ignore SSL Issues"** option if your server uses a self-signed certificate and you run into SSL errors.

**Activate your workflow.** Now, every day at 8:00 AM New York time, `n8n` will automatically call your API and trigger the scraper to update the database.
