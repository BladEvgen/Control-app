#!/bin/bash
###############################################################################
#                FULL SERVER SETUP SCRIPT (NON-FATAL ERRORS)                  #
# This script:
#   1. Creates (or uses) a system user;
#   2. Asks for a domain, deployment directory, and FULLY cleans it if exists;
#   3. Installs system packages (Python 3.11, PostgreSQL, Redis, etc.);
#   4. Installs NVM/Node.js, clones a GitHub repo;
#   5. Sets up Python venv, frontend (npm), collectstatic;
#   6. Configures PostgreSQL/Redis, firewall, Nginx + SSL (certbot);
#   7. Creates systemd services for Celery and Uvicorn;
#   8. In case of errors, it does not stop but counts them. At the end, it shows
#      how many errors there were and where to read the log.
###############################################################################

#----------------------------- GLOBAL SETTINGS --------------------------------
LOGFILE="/var/log/setup_script.log"
ERROR_COUNT=0

DEFAULT_USERNAME="admin"
DEFAULT_DOMAIN="mydomain.example.com"
DEFAULT_APP_DIR="/var/www/myapp"
GIT_REPO_URL="https://github.com/BladEvgen/Control-app.git"

DB_NAME="my_database"
DB_USER="db_admin"

#----------------------------- COLOR CONSTANTS --------------------------------
GREEN="\e[92m"
BLUE="\e[94m"
RED="\e[91m"
YELLOW="\e[93m"
NC="\e[0m" # No color

#----------------------------- LOGGING HELPERS --------------------------------

log_info() {
    local MSG="$1"
    echo -e "${BLUE}[INFO]${NC} $MSG" | tee -a "$LOGFILE"
}

log_success() {
    local MSG="$1"
    echo -e "${GREEN}[OK]${NC} $MSG" | tee -a "$LOGFILE"
}

log_warn() {
    local MSG="$1"
    echo -e "${YELLOW}[WARN]${NC} $MSG" | tee -a "$LOGFILE"
}

log_error() {
    local MSG="$1"
    echo -e "${RED}[ERROR]${NC} $MSG" | tee -a "$LOGFILE"
}

#----------------------------- EXECUTION HELPERS ------------------------------

# Execute command and log success/error (non-fatal), if error — increment ERROR_COUNT
execute_command_nonfatal() {
    local CMD="$1"
    log_info "Running command (non-fatal): $CMD"
    eval "$CMD" >>"$LOGFILE" 2>&1
    if [ $? -eq 0 ]; then
        log_success "Command succeeded: $CMD"
    else
        log_error "Command failed (non-fatal): $CMD"
        ERROR_COUNT=$((ERROR_COUNT + 1))
    fi
}

# Fatal check: run only as root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "Please run this script as root (sudo)."
        exit 1
    fi
}

#----------------------------- USER LOGIC -------------------------------------

create_system_user_nonfatal() {
    local USERNAME_TO_CREATE="$1"
    log_info "Creating system user '$USERNAME_TO_CREATE' (non-fatal)."
    execute_command_nonfatal "adduser --disabled-password --gecos '' $USERNAME_TO_CREATE"
    execute_command_nonfatal "usermod -aG sudo $USERNAME_TO_CREATE"
    log_info "Finished creating user '$USERNAME_TO_CREATE' (check log for errors)."
}

ask_for_user() {
    # Если скрипт запущен с "sudo -u <user>", будет SUDO_USER
    local suggested_user
    if [ -n "$SUDO_USER" ] && id "$SUDO_USER" &>/dev/null; then
        suggested_user="$SUDO_USER"
    else
        suggested_user="$DEFAULT_USERNAME"
    fi

    while true; do
        echo -en "${BLUE}Enter the system username [${suggested_user}]: ${NC}"
        read CHOSEN_USER
        CHOSEN_USER=${CHOSEN_USER:-$suggested_user}
        if id "$CHOSEN_USER" &>/dev/null; then
            log_info "User '$CHOSEN_USER' already exists. Will use it."
            break
        else
            log_warn "User '$CHOSEN_USER' does not exist."
            echo -en "${YELLOW}Create user '$CHOSEN_USER'? (y/n): ${NC}"
            read ans
            if [[ "$ans" =~ ^[Yy]$ ]]; then
                create_system_user_nonfatal "$CHOSEN_USER"
                break
            else
                log_warn "Please enter another user or press Ctrl+C to abort."
            fi
        fi
    done

    USERNAME="$CHOSEN_USER"
}

#----------------------------- ASK FOR APP DIR --------------------------------

ask_for_app_dir() {
    echo -en "${BLUE}Enter your app directory [${DEFAULT_APP_DIR}]: ${NC}"
    read app_dir_input
    if [ -n "$app_dir_input" ]; then
        DEFAULT_APP_DIR="$app_dir_input"
    fi
    log_info "Will use APP_DIR: $DEFAULT_APP_DIR"
}

#----------------------------- CLEANUP APP DIR --------------------------------

cleanup_app_dir() {
    # На этом этапе папка уже выбрана (ask_for_app_dir), пользователь определён
    if [ -d "$DEFAULT_APP_DIR" ]; then
        log_warn "Directory '$DEFAULT_APP_DIR' already exists. We will clear it now."
        # Удаляем вообще всё (включая .git, .env и т. п.)
        execute_command_nonfatal "rm -rf ${DEFAULT_APP_DIR:?}/* ${DEFAULT_APP_DIR:?}/.* 2>/dev/null"
    else
        # Если папки ещё нет
        execute_command_nonfatal "mkdir -p $DEFAULT_APP_DIR"
    fi

    # На всякий случай меняем права на неё, чтобы пользователь мог работать
    execute_command_nonfatal "chown -R $USERNAME:$USERNAME $DEFAULT_APP_DIR"
}

#----------------------------- INSTALL PACKAGES -------------------------------

install_packages() {
    log_info "Adding deadsnakes PPA for newer Python versions (non-fatal)."
    execute_command_nonfatal "apt-get update -y"
    execute_command_nonfatal "apt-get install -y software-properties-common"
    execute_command_nonfatal "add-apt-repository -y ppa:deadsnakes/ppa"

    log_info "Installing basic system packages (non-fatal)."
    execute_command_nonfatal "apt-get update -y"
    execute_command_nonfatal "apt-get upgrade -y"
    execute_command_nonfatal "apt-get install -y \
        nginx certbot python3-certbot-nginx \
        wget curl git build-essential \
        pkg-config libmysqlclient-dev libpq-dev \
        libssl-dev libffi-dev zlib1g-dev \
        postgresql postgresql-contrib \
        liblinbox-dev libgivaro-dev fflas-ffpack \
        redis-server ufw \
        python3.11 python3.11-venv python3.11-dev \
        htop ca-certificates"
    log_info "Packages installed (some may have errors, see log)."
}

#----------------------------- SETUP NVM & NODE -------------------------------

setup_nvm_system_wide() {
    log_info "Installing NVM (system-wide) in /usr/local/nvm (non-fatal)."

    if [ ! -d "/usr/local/nvm/.git" ]; then
        execute_command_nonfatal "git clone https://github.com/nvm-sh/nvm.git /usr/local/nvm"
        (
            cd /usr/local/nvm || exit 0
            execute_command_nonfatal "git checkout v0.39.1"
        )
    else
        log_warn "/usr/local/nvm already exists. Skipping clone."
    fi

    cat <<'EOF' >/etc/profile.d/nvm.sh
#!/bin/bash
export NVM_DIR="/usr/local/nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
EOF

    execute_command_nonfatal "chmod +x /etc/profile.d/nvm.sh"
    # shellcheck source=/dev/null
    source /etc/profile.d/nvm.sh

    log_info "Installing Node.js (v20.11.1) via NVM (non-fatal)."
    execute_command_nonfatal "nvm install v20.11.1"
    execute_command_nonfatal "nvm alias default v20.11.1"
    # На всякий случай ставим одну из стабильных версий npm
    execute_command_nonfatal "npm install -g npm@10.2.4"
}

#----------------------------- GIT CLONE PROJECT ------------------------------

clone_project_repo() {
    log_info "Cloning project repo into '$DEFAULT_APP_DIR' (non-fatal)."
    # Просто клонируем в пустую папку (которая уже очищена cleanup_app_dir)
    execute_command_nonfatal "git clone $GIT_REPO_URL $DEFAULT_APP_DIR"
    execute_command_nonfatal "chown -R $USERNAME:$USERNAME $DEFAULT_APP_DIR"
}

#----------------------------- SETUP PYTHON & BACKEND -------------------------

setup_python_venv_and_requirements() {
    log_info "Setting up Python 3.11 environment (non-fatal)."

    local VENV_DIR="${DEFAULT_APP_DIR}/backend/venv"
    if [ ! -d "$VENV_DIR" ]; then
        execute_command_nonfatal "python3.11 -m venv $VENV_DIR"
        execute_command_nonfatal "chown -R $USERNAME:$USERNAME $VENV_DIR"
    else
        log_warn "Venv already exists at $VENV_DIR (unexpected, but continuing)."
    fi

    # Если есть requirements_lin.txt — устанавливаем
    if [ -f "${DEFAULT_APP_DIR}/backend/requirements_lin.txt" ]; then
        log_info "Installing Python dependencies from requirements_lin.txt (non-fatal)."
        log_info "Proccess may take a while, please be patient."
        log_info "If any errors occur, check the log file for details, after full setup you may try to install manually, from requirements"
        execute_command_nonfatal "source $VENV_DIR/bin/activate && pip install pip install tensorflow==2.17.1"
        execute_command_nonfatal "source $VENV_DIR/bin/activate && pip install -r ${DEFAULT_APP_DIR}/backend/requirements_lin.txt"
    else
        log_warn "No requirements_lin.txt found in backend/. Skipping pip install."
    fi
}

#----------------------------- SETUP FRONTEND ---------------------------------

setup_frontend_build() {
    log_info "Installing and building frontend (npm) (non-fatal)."
    local FRONTEND_DIR="${DEFAULT_APP_DIR}/frontend"

    if [ ! -d "$FRONTEND_DIR" ]; then
        log_warn "No frontend directory found at $FRONTEND_DIR. Skipping..."
        return
    fi

    log_info "Running npm install in $FRONTEND_DIR"
    execute_command_nonfatal "cd $FRONTEND_DIR && npm install"

    log_info "Running npm run build in $FRONTEND_DIR"
    execute_command_nonfatal "cd $FRONTEND_DIR && npm run build"
}

#----------------------------- COLLECT STATIC ---------------------------------

collect_static() {
    log_info "Running Django collectstatic (non-fatal)."
    local VENV_DIR="${DEFAULT_APP_DIR}/backend/venv"
    local BACKEND_DIR="${DEFAULT_APP_DIR}/backend"

    if [ ! -f "${BACKEND_DIR}/manage.py" ]; then
        log_warn "No manage.py found in $BACKEND_DIR. Skipping collectstatic."
        return
    fi

    execute_command_nonfatal "cd $BACKEND_DIR && source $VENV_DIR/bin/activate && python manage.py collectstatic --noinput"
}

#----------------------------- POSTGRES SETUP ---------------------------------

setup_postgresql() {
    log_info "Configuring PostgreSQL (non-fatal)."
    execute_command_nonfatal "systemctl start postgresql.service"
    execute_command_nonfatal "systemctl enable postgresql.service"

    echo -en "${BLUE}Enter PostgreSQL database name [${DB_NAME}]: ${NC}"
    read entered_db_name
    [ -n "$entered_db_name" ] && DB_NAME="$entered_db_name"

    echo -en "${BLUE}Enter PostgreSQL user name [${DB_USER}]: ${NC}"
    read entered_db_user
    [ -n "$entered_db_user" ] && DB_USER="$entered_db_user"

    # Проверяем существование БД
    local db_exists
    db_exists=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null)
    if [ "$db_exists" = "1" ]; then
        log_warn "Database '$DB_NAME' already exists."
        echo -en "${YELLOW}Do you want to DROP it? (y/n): ${NC}"
        read dropdb_ans
        if [[ "$dropdb_ans" =~ ^[Yy]$ ]]; then
            execute_command_nonfatal "sudo -u postgres psql -c \"DROP DATABASE \\\"$DB_NAME\\\"\""
        else
            log_warn "Skipping DROP DATABASE."
        fi
    fi

    # Проверяем существование пользователя
    local user_exists
    user_exists=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null)
    if [ "$user_exists" = "1" ]; then
        log_warn "PostgreSQL user '$DB_USER' already exists."
        echo -en "${YELLOW}Change this user's password? (y/n): ${NC}"
        read change_pw_ans
        if [[ "$change_pw_ans" =~ ^[Yy]$ ]]; then
            echo -en "${BLUE}Enter new password for user '$DB_USER': ${NC}"
            read -s DB_PASSWORD
            echo
            execute_command_nonfatal "sudo -u postgres psql -c \"ALTER USER \\\"$DB_USER\\\" WITH PASSWORD '$DB_PASSWORD'\""
        fi
    else
        # Создаём пользователя
        echo -en "${BLUE}Enter password for new user '$DB_USER': ${NC}"
        read -s DB_PASSWORD
        echo
        execute_command_nonfatal "sudo -u postgres psql -c \"CREATE USER \\\"$DB_USER\\\" WITH PASSWORD '$DB_PASSWORD'\""
    fi

    # Если БД ещё есть, проверим, возможно, её не дропнули
    db_exists=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null)
    if [ "$db_exists" = "1" ]; then
        log_info "Database '$DB_NAME' is present (or was not dropped)."
    else
        echo -en "${BLUE}Create DB '$DB_NAME'? (y/n): ${NC}"
        read create_db_ans
        if [[ "$create_db_ans" =~ ^[Yy]$ ]]; then
            execute_command_nonfatal "sudo -u postgres psql -c \"CREATE DATABASE \\\"$DB_NAME\\\"\""
        else
            log_warn "Skipping CREATE DATABASE."
        fi
    fi

    # Дадим привилегии
    db_exists=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null)
    if [ "$db_exists" = "1" ]; then
        execute_command_nonfatal "sudo -u postgres psql -c \"GRANT ALL PRIVILEGES ON DATABASE \\\"$DB_NAME\\\" TO \\\"$DB_USER\\\"\""
        execute_command_nonfatal "sudo -u postgres psql -d \"$DB_NAME\" -c \"GRANT ALL PRIVILEGES ON SCHEMA public TO \\\"$DB_USER\\\"\""
    fi
}

#----------------------------- REDIS SETUP ------------------------------------

setup_redis() {
    log_info "Configuring Redis (non-fatal)."
    execute_command_nonfatal "systemctl start redis-server"
    execute_command_nonfatal "systemctl enable redis-server"
}

#----------------------------- FIREWALL ---------------------------------------

setup_firewall() {
    log_info "Configuring UFW (non-fatal)."
    execute_command_nonfatal "ufw allow ssh"
    execute_command_nonfatal "ufw allow 'Nginx Full'"
    execute_command_nonfatal "ufw allow 6379"
    execute_command_nonfatal "ufw enable"
}

#----------------------------- NGINX SETUP ------------------------------------

setup_nginx() {
    log_info "Configuring Nginx with custom upstream (non-fatal)."

    local SITE_AVAILABLE="/etc/nginx/sites-available/${DEFAULT_DOMAIN}"
    local SITE_ENABLED="/etc/nginx/sites-enabled/${DEFAULT_DOMAIN}"

    execute_command_nonfatal "mkdir -p ${DEFAULT_APP_DIR}/backend/socket"
    execute_command_nonfatal "mkdir -p ${DEFAULT_APP_DIR}/backend/logs"

    cat <<EOF >"$SITE_AVAILABLE"
upstream control_application {
    server unix:${DEFAULT_APP_DIR}/backend/socket/control_app.sock;
}

server {
    if (\$host = ${DEFAULT_DOMAIN}) {
        return 301 https://\$host\$request_uri;
    }

    listen 80;
    server_name ${DEFAULT_DOMAIN};

    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    server_name ${DEFAULT_DOMAIN};
    client_max_body_size 15G;

    ssl_certificate /etc/letsencrypt/live/${DEFAULT_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${DEFAULT_DOMAIN}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location /ws/photos/ {
        proxy_pass http://control_application;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;

        proxy_set_header Proxy-Connection "keep-alive";
        proxy_set_header X-Ping \$time_iso8601;
        add_header Ping "pong";
    }

    location /static/ {
        alias ${DEFAULT_APP_DIR}/backend/staticroot/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }

    location /assets/ {
        alias ${DEFAULT_APP_DIR}/frontend/dist/assets/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }

    location /media/ {
        alias ${DEFAULT_APP_DIR}/backend/static/media/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }

    location /attendance_media/ {
        alias /mnt/disk/control_image/;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }

    location ~ ^/augment_media/([^/]+)/(.+)\$ {
        alias /mnt/disk/augment_images/augmented_images/\$1/\$2;
        expires 30d;
        add_header Cache-Control "public";
        access_log off;
    }

    location / {
        proxy_pass http://control_application;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_method \$request_method;
        proxy_redirect off;
        proxy_buffering off;
        proxy_http_version 1.1;
        proxy_set_header Connection keep-alive;

        proxy_read_timeout 3600s;
        proxy_connect_timeout 3600s;
        proxy_send_timeout 3600s;
        send_timeout 3600s;
        proxy_buffers 16 128k;
        proxy_buffer_size 256k;
        proxy_request_buffering off;
    }

    location = /favicon.ico {
        alias ${DEFAULT_APP_DIR}/backend/staticroot/favicon.ico;
        access_log off;
        log_not_found off;
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

    error_log ${DEFAULT_APP_DIR}/backend/logs/nginx_error.log;
    access_log ${DEFAULT_APP_DIR}/backend/logs/nginx_access.log;
}
EOF

    execute_command_nonfatal "rm -f /etc/nginx/sites-enabled/default"
    execute_command_nonfatal "ln -sfn ${SITE_AVAILABLE} ${SITE_ENABLED}"

    execute_command_nonfatal "nginx -t"
    execute_command_nonfatal "systemctl restart nginx"
}

#----------------------------- SSL (CERTBOT) ----------------------------------

setup_ssl() {
    log_info "Obtaining SSL cert from Let's Encrypt (non-fatal)."
    echo -en "${BLUE}Enter your email for Let's Encrypt [admin@example.com]: ${NC}"
    read EMAIL
    EMAIL=${EMAIL:-"admin@example.com"}

    execute_command_nonfatal "certbot --nginx -d ${DEFAULT_DOMAIN} --non-interactive --agree-tos -m ${EMAIL} --redirect"
}

#----------------------------- SYSTEMD SERVICES -------------------------------

setup_systemd_services() {
    log_info "Creating systemd services for Celery, Celery Beat, and Uvicorn (non-fatal)."

    execute_command_nonfatal "mkdir -p ${DEFAULT_APP_DIR}/backend/logs"

    # Celery worker
    cat <<EOF >/etc/systemd/system/celery_control_app.service
[Unit]
Description=Celery Service for control_app
After=network.target

[Service]
User=${USERNAME}
Group=www-data
WorkingDirectory=${DEFAULT_APP_DIR}/backend/

ExecStart=${DEFAULT_APP_DIR}/backend/venv/bin/celery -A django_settings worker \\
    --loglevel=debug \\
    --logfile=${DEFAULT_APP_DIR}/backend/logs/celery_worker.log \\
    --concurrency=2 \\
    --prefetch-multiplier=4 \\
    --max-tasks-per-child=1000

Restart=always
RestartSec=10
TimeoutSec=300

LimitNOFILE=4096

[Install]
WantedBy=multi-user.target
EOF

    # Celery beat
    cat <<EOF >/etc/systemd/system/celery_beat_control_app.service
[Unit]
Description=Celery Beat Service for control_app
After=network.target

[Service]
User=${USERNAME}
Group=www-data
WorkingDirectory=${DEFAULT_APP_DIR}/backend/

ExecStart=${DEFAULT_APP_DIR}/backend/venv/bin/celery -A django_settings beat \\
    --loglevel=debug \\
    --logfile=${DEFAULT_APP_DIR}/backend/logs/celery_beat.log \\
    --max-interval=10

Restart=always
RestartSec=5
TimeoutSec=900

[Install]
WantedBy=multi-user.target
EOF

    # Uvicorn (ASGI)
    cat <<EOF >/etc/systemd/system/control_app.service
[Unit]
Description=Uvicorn ASGI server for Django project with Channels
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=${DEFAULT_APP_DIR}/backend/
Environment="DJANGO_SETTINGS_MODULE=django_settings.settings"
Environment="PYTHONPATH=${DEFAULT_APP_DIR}/backend/"
Environment="PATH=${DEFAULT_APP_DIR}/backend/venv/bin"
Environment="MPLCONFIGDIR=${DEFAULT_APP_DIR}/backend/matplotlib_config"
UMask=0000

ExecStart=${DEFAULT_APP_DIR}/backend/venv/bin/uvicorn \\
    --uds ${DEFAULT_APP_DIR}/backend/socket/control_app.sock \\
    --workers 20 \\
    --timeout-keep-alive 600 \\
    --access-log \\
    --log-level info \\
    django_settings.asgi:application

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    # Reload, enable, start
    execute_command_nonfatal "systemctl daemon-reload"
    execute_command_nonfatal "systemctl enable celery_control_app"
    execute_command_nonfatal "systemctl enable celery_beat_control_app"
    execute_command_nonfatal "systemctl enable control_app"

    execute_command_nonfatal "systemctl start celery_control_app"
    execute_command_nonfatal "systemctl start celery_beat_control_app"
    execute_command_nonfatal "systemctl start control_app"
}

#----------------------------- MAIN -------------------------------------------

main() {
    mkdir -p "$(dirname "$LOGFILE")"
    echo "===== Setup started: $(date) =====" >"$LOGFILE"

    check_root
    log_info "Welcome to the FULL SERVER SETUP script (non-fatal)."

    # 1) Ask/create system user for deployment
    ask_for_user

    # 2) Ask for domain
    echo -en "${BLUE}Enter your domain name [${DEFAULT_DOMAIN}]: ${NC}"
    read domain_input
    [ -n "$domain_input" ] && DEFAULT_DOMAIN="$domain_input"
    log_info "Will use domain: $DEFAULT_DOMAIN"

    # 3) Ask for app directory
    ask_for_app_dir

    # 4) Fully clean up (or create) the app directory (IMPORTANT to start from scratch)
    cleanup_app_dir

    # 5) install packages
    install_packages

    # 6) install NVM/Node.js
    setup_nvm_system_wide

    # 7) clone GitHub repo
    clone_project_repo

    # 8) Setup Python + install requirements
    setup_python_venv_and_requirements

    # 9) Собрать frontend
    setup_frontend_build

    # 10) collectstatic в Django
    collect_static

    # 11) PostgreSQL
    setup_postgresql

    # 12) Redis
    setup_redis

    # 13) Firewall (UFW)
    setup_firewall

    # 14) setup Nginx
    setup_nginx

    # 15) SSL (Certbot)
    setup_ssl

    # 16) services setup Celery / Uvicorn
    setup_systemd_services

    # Итог
    if [ $ERROR_COUNT -eq 0 ]; then
        log_success "All steps completed with NO errors."
    else
        log_warn "Script completed with $ERROR_COUNT error(s)."
    fi

    log_info "You can review the log file at: $LOGFILE"
    echo -e "${GREEN}SETUP FINISHED. See log: $LOGFILE${NC}"
}

main
