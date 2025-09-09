# Control-app

## Overview

Control-app is a system designed for managing employee attendance, calculating work efficiency, and handling administrative tasks. It integrates Django Rest Framework (DRF) on the backend and React on the frontend.

## Key Features

- **Employee Attendance Management**
- **Work Efficiency Calculation**
- **API Integration**
- **JWT Authentication**
- **Password Reset Management**
- **Role-Based Access Control**
- **Responsive UI**
- **Administrative Dashboard**

## Technologies Used

**Backend:** Django, Django Rest Framework (DRF), SimpleJWT, PostgreSQL/MySQL, Gunicorn, Swagger & ReDoc  
**Frontend:** React, Tailwind CSS, Axios, React Router

## Project Structure

### Backend

- `backend/django_settings/`: Project settings and configurations
- `backend/monitoring_app/`: Core application handling logic, models, views, and middleware
- `urls.py`: Backend API routes
- `asgi.py`: Entry point for ASGI-compatible web servers

### Frontend

- `frontend/src/`: Source directory with React components, utilities, and styles
- `frontend/src/components/`: Core components like `HeaderComponent`, `LoginPage`, etc.
- `frontend/src/api.ts`: API requests and authentication logic
- `tailwind.config.js`: Tailwind CSS configuration
- `vite.config.js`: Vite build tool configuration

## Setup and Installation

### Prerequisites

- **Python 3.11**
- **Node.js & npm**
- **PostgreSQL/MySQL**
- **Cuda 12**

### Setup
You may download the setup script using the following command:
```bash
wget https://github.com/BladEvgen/Control-app/blob/main/backend/scripts/setup.sh
```

#### CUDA Installation
To install CUDA, follow the steps provided on the NVIDIA website:

Visit the CUDA Downloads Page.
```bash
https://developer.nvidia.com/cuda-downloads?target_os=Linux
```

Select your target operating system and follow the instructions to download the appropriate installer.
Additionally, you must read the detailed installation instructions provided by NVIDIA to ensure a successful installation:

CUDA Installation Guide for Linux:
```bash
https://docs.nvidia.com/cuda/cuda-installation-guide-linux/#meta-packages
```
Make sure to follow all the steps carefully to avoid any issues during the installation process. 
####
###

### Backend Setup

1. Clone the repository:

```bash
   git clone https://github.com/BladEvgen/Control-app.git
   cd Control-app/backend
```

### Linux/MacOS

```bash
python3 -m venv venv
source venv/bin/activate
```

### Windows

```shell
python -m venv venv
call venv/Scripts/Activate
```

2. Install requirements:

```bash
pip install -r requirements_lin.txt
```

or

```shell
pip install -r requirements_win.txt
```

3. Set up the environment variables:

Create a .env file in the backend/ directory with the required environment variables.

```bash
SECRET_KEY = "django-insecure-SECRET_KEY" # Generate  in django SECRET_KEY

MAIN_IP = "http://localhost:8000" # Or set full domain name

# Defaults settings for MYSQL
db_name = "staff_app"
db_user = "django-admin"
db_password = "Password"
db_host = "localhost"
db_port = 3306



EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST="smtp.yandex.ru" # Or set for google  smtp.gmail.com
EMAIL_PORT=465
EMAIL_USE_TLS = False
EMAIL_USE_SSL = True
EMAIL_HOST_USER="email"
EMAIL_HOST_PASSWORD="password"
DEFAULT_FROM_EMAIL="email-from"

REDIS_HOST="localhost"
REDIS_PORT=6379

API_URL = "https://some-api-where-take-attendance.com/"

API_KEY = ""

# Note that EXAMPLE VALUE
SECRET_API = "KQP8NTsx6zmne582bwTB0xx-5K0iK21wfQtWx7p4v8s=" # If no  SECRET_API it will be generated automaticaly
X_API_KEY = "Generate own API in current system"
```

4. Apply migrations and start the development server:

```bash
python manage.py migrate
python manage.py runserver
```

# Frontend Setup

1. Navigate to the frontend directory:

```bash
cd ../frontend
```

2. Install the required npm packages:

```bash
npm install
```

3. Start the development server:

```bash
npm run dev
```

4. Build project

```bash
npm run build
```

# Nginx Conf Example

```bash
upstream control_application {
    server unix:/var/run/control_app.sock;
}

server {
    listen 80;
    server_name your_domain.com;

    # Redirect all HTTP requests to HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your_domain.com;
    client_max_body_size 2G;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/your_domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your_domain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Serve static files
    location /static/ {
        alias /var/www/control_app/static/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }

    # Serve frontend assets
    location /assets/ {
        alias /var/www/control_app/frontend/assets/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }

    # Serve media files
    location /media/ {
        alias /var/www/control_app/media/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }

    location /media/ {
        alias /var/www/control_app/static/media;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }

    location = /favicon.ico {
        alias /var/www/control_app/static/favicon.ico;
        access_log off;
        log_not_found off;
    }

    location / {
        proxy_pass http://control_application;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_method $request_method;

        proxy_redirect off;
        proxy_buffering off;
        proxy_http_version 1.1;
        proxy_set_header Connection keep-alive;

        proxy_read_timeout 600s;
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        send_timeout 600s;
        proxy_buffers 8 16k;
        proxy_buffer_size 32k;
    }

    gzip on;
    gzip_comp_level 6;
    gzip_min_length 256;
    gzip_buffers 16 8k;
    gzip_proxied any;
    gzip_vary on;
    gzip_types
        application/javascript
        application/json
        application/xml
        application/xml+rss
        application/x-font-ttf
        application/x-web-app-manifest+json
        application/vnd.ms-fontobject
        font/eot
        font/opentype
        image/svg+xml
        image/x-icon
        text/css
        text/plain
        text/javascript
        text/xml;
    gzip_disable "msie6";

    error_log /var/log/nginx/control_app_error.log;
    access_log /var/log/nginx/control_app_access.log;
}


```

### Create SSL for current domain

```bash
sudo certbot certonly --nginx -d example.com
```

```bash
# Add SSL recreation in crontab
sudo certbot renew --dry-run
```

# Linux Service creation

```bash
# vim or nano /etc/systemd/system/control_app.service

[Unit]
Description=Gunicorn instance to serve control_django
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/control_app/backend/
ExecStart=/var/www/control_app/venv/bin/gunicorn \
    --access-logfile - \
    --workers 9 \  # Adjust this based on your CPU cores
    --threads 2 \  # Adjust this based on the nature of your app
    --timeout 120 \
    --bind unix:/var/run/control_app.sock \
    django_settings.wsgi:application

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## Configuring Gunicorn Workers and Threads

To ensure optimal performance, it's important to correctly configure the number of workers and threads for Gunicorn:

1. **Workers**: The recommended formula is `workers = 2 * CPU cores + 1`. This formula helps ensure that Gunicorn can handle the maximum number of requests while efficiently utilizing the CPU.

2. **Threads**: The number of threads should generally start at `2`. Threads allow each worker to handle multiple requests concurrently, which is particularly useful for I/O-bound tasks.

For example, on a server with 4 CPU cores:

- **Workers**: `2 * 4 + 1 = 9`
- **Threads**: Start with `2`, and adjust based on the application's performance.

These values can be adjusted based on the specific needs of your application and server.



# Celery service creation

```bash
# vim or nano /etc/systemd/system/celery_appName.service

[Unit]
Description=Celery Service for control_app
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/path/to/project/dir/backend/

ExecStart=/path/to/project/dir/venv/bin/celery -A django_settings worker \
    --loglevel=warning \
    --logfile=/path/to/project/dir/backend/logs/celery_worker.log \
    --concurrency=2 \
    --prefetch-multiplier=4 \
    --max-tasks-per-child=1000

Restart=on-failure
RestartSec=10
TimeoutSec=300

LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
```



# Celery Beat service creation

```bash
# vim or nano /etc/systemd/system/celery_beat_appName.service

[Unit]
Description=Celery Beat Service for control_app
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/path/to/project/dir/backend/

ExecStart=/path/to/project/dir/venv/bin/celery -A django_settings beat \
    --loglevel=warning \
    --logfile=/path/to/project/dir/backend/logs/celery_beat.log \
    --max-interval=10


Restart=on-failure
RestartSec=5
TimeoutSec=700

LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
```
