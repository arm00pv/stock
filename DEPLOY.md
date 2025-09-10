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
    sudo chown -R $USER:$USER /var/www/webhost/stock
    git clone <your-repo-url> /var/www/webhost/stock
    cd /var/www/webhost/stock
    ```

3.  **Create a Python virtual environment and install dependencies:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    pip install gunicorn
    ```
    *Note: Remember to activate the virtual environment (`source venv/bin/activate`) whenever you work in the project directory.*

## Step 2: Configure Gunicorn

We will use `systemd` to manage the Gunicorn process.

1.  **Create a `systemd` service file:**
    ```bash
    sudo nano /etc/systemd/system/hotstocks.service
    ```

2.  **Add the following content to the file.** This configuration tells `systemd` how to run our application. It will be run by the `www-data` user and group, which is the same user Apache runs as.

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

3.  **Create a `wsgi.py` file** in the root of your project directory (`/var/www/webhost/stock/`):
    ```bash
    nano wsgi.py
    ```
    Add the following content:
    ```python
    from app import application

    if __name__ == "__main__":
        application.run()
    ```

## Step 3: Configure Apache2

You will add a proxy configuration to your existing Apache2 site to avoid disrupting your other running applications.

1.  **Enable the required Apache modules:**
    This is a critical step. The configuration requires the `proxy`, `proxy_http`, and `headers` modules.
    ```bash
    sudo a2enmod proxy proxy_http headers
    sudo systemctl restart apache2
    ```
    *Note: If you receive an error about `Invalid command 'RequestHeader'`, it means the `headers` module was not enabled. Running the command above will fix this.*

2.  **Edit your existing Apache2 site configuration file:**
    Based on the information you provided, you should edit the following file:
    ```bash
    sudo nano /etc/apache2/sites-enabled/webhost-le-ssl.conf
    ```

3.  **Add the proxy directives.** Inside the `<VirtualHost *:443>` block, add the following lines. A good place is near your other `ProxyPass` directives to keep things organized.

    ```apache
    # --- Configuration for Hot Stocks App ---
    ProxyPass /stock/ unix:/var/www/webhost/stock/hotstocks.sock|http://localhost/
    ProxyPassReverse /stock/ unix:/var/www/webhost/stock/hotstocks.sock|http://localhost/
    RequestHeader set SCRIPT_NAME /stock
    ```

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

3.  **Check the status of the `hotstocks` service:**
    ```bash
    sudo systemctl status hotstocks
    ```
    You should see that it is `active (running)`.

## Step 5: Access Your Application

You should now be able to access your application in your web browser at:
`https://zapp.sytes.net/stock/`

If you encounter any issues, you can check the logs for Apache2 and your application:
-   **Apache2 logs:** `sudo journalctl -u apache2` or check `/var/log/apache2/error.log`
-   **Application logs:** `sudo journalctl -u hotstocks`
