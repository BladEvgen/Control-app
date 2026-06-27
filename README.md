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

### Recommended: Docker Compose (local development)

The fastest way to run the full stack (MySQL/PostgreSQL + Redis + Django/ASGI
backend + Celery worker + Celery beat + a one-shot frontend build) is via the
`docker-compose.yml` at the repo root. This works the same way on Linux, macOS,
and Windows (with Docker Desktop) — no need to install Python, Node, MySQL,
PostgreSQL, or Redis on your machine.

**Note:** production does *not* run via Docker — the deployed server uses
native systemd services (see "Linux Service creation" below). Docker here is
for local development only.

```bash
git clone https://github.com/BladEvgen/Control-app.git
cd Control-app

cp backend/.env.docker.example backend/.env.docker
# edit backend/.env.docker: set DB_TYPE (mysql or postgres) and other values

docker compose --profile mysql up -d --build      # MySQL + Redis + backend
# or
docker compose --profile postgres up -d --build   # PostgreSQL + Redis + backend

# build the frontend (writes to ./frontend/dist, then exits)
docker compose --profile frontend up --build
```

The backend (Uvicorn/ASGI) is published on `http://127.0.0.1:10808` by default
(override with `DJANGO_PUBLISH_PORT`). `app-init` runs migrations and
`collectstatic` once before `web`/`celery-worker`/`celery-beat` start.

GPU (optional): if your machine has an NVIDIA GPU and
[nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
installed, merge the `x-gpu-reservation` anchor defined in `docker-compose.yml`
into the `web`/`celery-worker` services to enable CUDA inside the containers.
Without it, everything runs on CPU (same as the current production server).

### Alternative: local setup without Docker (Linux)

If you prefer not to use Docker, `backend/scripts/setup.sh` bootstraps Python
3.11 + venv, system packages, and a local MySQL/PostgreSQL + Redis on a Debian/
Ubuntu machine:

```bash
git clone https://github.com/BladEvgen/Control-app.git
cd Control-app
bash backend/scripts/setup.sh
```

For Node.js, run `bash backend/scripts/nvm_install.sh` first if you don't
already have Node 20+. To update dependencies later, use
`bash backend/scripts/install_dependencies.sh` (set `DB_TYPE=postgres` env var
if not using MySQL).

On macOS/Windows without Docker, install Python 3.11, Node.js, and your
chosen database manually, then follow the manual steps below.

### Manual backend setup (any OS)

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

2. Install requirements (CPU-only by default; choose your DB driver):

```bash
# Linux/macOS, MySQL
pip install -r requirements/base.txt -r requirements/mysql.txt --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple

# Linux/macOS, PostgreSQL
pip install -r requirements/base.txt -r requirements/postgres.txt --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple
```

```shell
:: Windows, PostgreSQL
pip install -r requirements/base-win.txt -r requirements/postgres.txt
```

If you have an NVIDIA GPU and want CUDA acceleration, see `requirements/cuda.txt` (Linux/macOS) or `requirements/cuda-win.txt` (Windows) for the extra install step — CUDA is optional and not required to run the project.

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

### Face recognition models (ArcFace + optional face parsing)

Everything runs on **ordinary RGB photos**; no depth/IR sensors are required.

| Component | Role | Install |
|-----------|------|---------|
| **InsightFace `buffalo_l`** | Face detection, 5-point landmarks, ArcFace embeddings | Pulled automatically on first use into `~/.insightface/models/buffalo_l/` (via `pip install insightface`). |
| **BiSeNet face parsing (ONNX)** | Segments facial parts including **eyeglasses** (`eye_g`) — better gallery aug (add/remove glasses) and extra fields on `verify_face` | Place **`face_parsing_resnet18.onnx`** (~53 MB) under `GENERAL_MODELS_ROOT` (default: `backend/models/`). |

**Download parsing ONNX manually:**

```bash
cd backend
bash scripts/download_face_parsing_onnx.sh
```

Or:

```bash
mkdir -p backend/models
curl -fL -o backend/models/face_parsing_resnet18.onnx \
  https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.onnx
```

**Auto-download on first use:** set `FACE_PARSING_AUTO_DOWNLOAD=1` in `backend/.env` (writes the same path as above).

**Useful `.env` flags:**

- `FACE_PARSING_ENABLE` — `1`/`0` (default `1`; if the ONNX file is missing, parsing is skipped and ArcFace still works).
- `FACE_PARSING_MODEL_PATH` — absolute path to the `.onnx` if not using `GENERAL_MODELS_ROOT/face_parsing_resnet18.onnx`.
- `FACE_PARSING_GLASSES_FRAC_MIN` — minimum fraction of “glasses” class pixels to treat as wearing glasses (default `0.00035`).
- `FACE_PARSING_USE_FOR_AUGMENT` / `FACE_PARSING_USE_FOR_API` — turn parsing off for augmentation only or for the verify API only.
- `FACE_ENCODING_TTA_ENABLE` — `1`/`0` (default `1`): average ArcFace embeddings over mild camera-condition variants (gamma/CLAHE/sharpen/JPEG) when extracting one probe/avatar embedding.
- `FACE_RUNTIME_INCLUDE_AUGMENTED_GALLERY` — `1`/`0` (default `1`): let runtime verify/recognize use capped validated face-ID augment crops in addition to mask/avatar/`gallery_real.npy`; `FACE_RUNTIME_AUGMENTED_GALLERY_MAX` caps the count (default `24`).
- `FACE_RUNTIME_ADD_CENTROID_PROTOTYPES` — `1`/`0` (default `1`): add robust centroid templates over available face samples, improving matching when each person has several real/augmented frames.
- `FACE_VERIFY_PROBE_BLUR_MIN`, `FACE_VERIFY_PROBE_BRIGHTNESS_MIN/MAX`, `FACE_VERIFY_PROBE_MAX_ABS_YAW/PITCH` — conservative quality gates for ordinary phone/laptop camera frames.
- `FACE_VERIFY_IMPOSTOR_GAP_ENABLE` — `1`/`0` (default `1`): during 1:1 verify, also compare the probe with the nearest other staff member and reject when the gap is too small (`FACE_VERIFY_IMPOSTOR_GAP_MIN`, default `0.035`).

`verify_face` is intentionally binary: uncertain liveness/PAD, weak probe quality, or a nearest-other-staff gap that is too small returns `final_decision: "NO"`, not a manual-review state.

After changing augmentation, rebuild staff gallery embeddings as you usually do in this project.

Parsing weights: [yakhyo/face-parsing](https://github.com/yakhyo/face-parsing) (MIT), ResNet18 ONNX.

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

The project runs ASGI (Django Channels) via **Uvicorn**, not Gunicorn/WSGI — needed for the websocket endpoints (`/ws/`).

```bash
# vim or nano /etc/systemd/system/control_app.service

[Unit]
Description=Uvicorn instance to serve ControlApp (ASGI)
After=network.target

[Service]
User=youruser
Group=yourgroup
WorkingDirectory=/path/to/project/dir/backend
ExecStart=/path/to/project/dir/venv/bin/uvicorn \
    django_settings.asgi:application \
    --uds /path/to/project/dir/backend/socket/control_app.sock \
    --workers 10 \
    --timeout-keep-alive 120 \
    --proxy-headers

Restart=always
RestartSec=3
UMask=0002

[Install]
WantedBy=multi-user.target
```

Adjust `--workers` based on CPU cores available (a common starting point is `2 * CPU cores`, lower if the box is also running Celery/ML inference).

The unix socket directory's group must include both the app user and `nginx` (`usermod -aG yourgroup nginx`) so nginx can read/write the socket — `UMask=0002` keeps it group-writable. `setup.sh` does this automatically.

# Celery service creation

```bash
# vim or nano /etc/systemd/system/celery_appName.service

[Unit]
Description=Celery Service for control_app
After=network.target

[Service]
User=youruser
Group=yourgroup
WorkingDirectory=/path/to/project/dir/backend/
Environment="DJANGO_SETTINGS_MODULE=django_settings.settings"

ExecStart=/path/to/project/dir/venv/bin/celery -A django_settings worker \
    --loglevel=info \
    --logfile=/path/to/project/dir/backend/logs/celery_worker.log \
    --concurrency=2 \
    --prefetch-multiplier=4 \
    --max-tasks-per-child=1000 \
    --queues=control_app_queue

Restart=always
RestartSec=10
TimeoutSec=300

LimitNOFILE=4096
UMask=0002

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
User=youruser
Group=yourgroup
WorkingDirectory=/path/to/project/dir/backend/
Environment="DJANGO_SETTINGS_MODULE=django_settings.settings"

ExecStart=/path/to/project/dir/venv/bin/celery -A django_settings beat \
    --loglevel=info \
    --logfile=/path/to/project/dir/backend/logs/celery_beat.log \
    --max-interval=10

Restart=always
RestartSec=5
TimeoutSec=700
UMask=0002

[Install]
WantedBy=multi-user.target
```
