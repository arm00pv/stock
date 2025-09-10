# Deployment Guide for Hot Stocks App

This guide provides step-by-step instructions for deploying the Hot Stocks Flask application on a Digital Ocean server running Ubuntu. The application will be served using Nginx as a reverse proxy and Gunicorn as the WSGI server.

The application will be accessible at `http://zapp.sytes.net/stock/`.
The application files will be located in `/var/www/webhost/stock/`.

## Prerequisites

- A Digital Ocean Droplet with Ubuntu 20.04 or later.
- A non-root user with `sudo` privileges.
- Nginx installed (`sudo apt update && sudo apt install nginx`).
- Python 3 and `pip` installed.

## Step 1: Clone the Repository and Set Up the Environment

1.  **SSH into your server:**
    ```bash
    ssh your_user@zapp.sytes.net
    ```

2.  **Create the directory and clone the repository:**
    ```bash
    sudo mkdir -p /var/www/webhost
    sudo chown -R $USER:$USER /var/www/webhost
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

2.  **Add the following content to the file.** This configuration tells `systemd` how to run our application. It will be run by the `www-data` user and group.

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
    *Note: We are using a Unix socket (`hotstocks.sock`) for communication between Nginx and Gunicorn. This is generally more secure and slightly faster than a TCP socket.*

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
    This file provides the `application` object that Gunicorn will use.

## Step 3: Configure Nginx

Nginx will act as a reverse proxy, forwarding requests to Gunicorn.

1.  **Create an Nginx server block configuration file:**
    ```bash
    sudo nano /etc/nginx/sites-available/hotstocks
    ```

2.  **Add the following server block.** This configures Nginx to listen on port 80 and handle requests for `zapp.sytes.net`.

    ```nginx
    server {
        listen 80;
        server_name zapp.sytes.net;

        location /stock {
            include proxy_params;
            proxy_pass http://unix:/var/www/webhost/stock/hotstocks.sock;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_set_header Host $host;
            proxy_redirect off;
            proxy_set_header SCRIPT_NAME /stock;
        }

        location / {
            # Optional: You can serve a static page or return a 404 for the root.
            return 404;
        }
    }
    ```
    *The `proxy_set_header SCRIPT_NAME /stock;` is crucial for telling Flask that it's running under a subdirectory.*

3.  **Enable the server block by creating a symbolic link:**
    ```bash
    sudo ln -s /etc/nginx/sites-available/hotstocks /etc/nginx/sites-enabled
    ```

4.  **Test the Nginx configuration for syntax errors:**
    ```bash
    sudo nginx -t
    ```
    If the test is successful, you can proceed.

## Step 4: Start and Enable the Services

1.  **Start and enable the `hotstocks` service:**
    ```bash
    sudo systemctl start hotstocks
    sudo systemctl enable hotstocks
    ```

2.  **Restart Nginx to apply the new configuration:**
    ```bash
    sudo systemctl restart nginx
    ```

3.  **Check the status of the `hotstocks` service:**
    ```bash
    sudo systemctl status hotstocks
    ```
    You should see that it is `active (running)`.

## Step 5: Access Your Application

You should now be able to access your application in your web browser at:
`http://zapp.sytes.net/stock/`

If you encounter any issues, you can check the logs for Nginx and your application:
-   **Nginx logs:** `sudo journalctl -u nginx`
-   **Application logs:** `sudo journalctl -u hotstocks`
