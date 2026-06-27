#!/bin/bash
###############################################################################
#         LOCAL DEV SETUP (no Docker) — Linux only                          #
#
# Прод НЕ разворачивается этим скриптом — прод работает через свои собственные
# systemd-юниты (control_app.service, celery_control_app.service,
# celery_beat_control_app.service) и nginx-конфиг, настроенные вручную один раз.
#
# Рекомендуемый путь для разработки — docker-compose.yml в корне репозитория:
#   cp backend/.env.docker.example backend/.env.docker   # один раз, заполнить
#   docker compose --profile mysql up -d                 # или --profile postgres
#
# Этот скрипт — альтернатива для тех, кто хочет работать БЕЗ Docker: ставит
# Python 3.11 + venv, Node.js (через nvm_install.sh), системные библиотеки для
# сборки mysqlclient/psycopg2, и саму БД (MySQL или PostgreSQL) локально.
###############################################################################

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$BACKEND_DIR/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$ROOT_DIR/venv"

DB_TYPE="${DB_TYPE:-mysql}"
DB_NAME="${DB_NAME:-control_app}"
DB_USER="${DB_USER:-control_app}"

GREEN="\e[92m"
BLUE="\e[94m"
RED="\e[91m"
YELLOW="\e[93m"
NC="\e[0m"

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

execute_command() {
    eval "$1"
    if [ $? -eq 0 ]; then
        log_success "Команда: $1"
    else
        log_error "Ошибка при выполнении: $1"
    fi
}

#----------------------------- DB TYPE PROMPT ---------------------------------

ask_db_type() {
    echo -en "${BLUE}Database type [mysql/postgres] (default: ${DB_TYPE}): ${NC}"
    read db_type_input
    case "$db_type_input" in
        postgres|postgresql) DB_TYPE="postgres" ;;
        mysql) DB_TYPE="mysql" ;;
        "") ;;
        *) log_warn "Неизвестный тип '$db_type_input', используется $DB_TYPE" ;;
    esac
    log_info "Будет использоваться: $DB_TYPE"
}

#----------------------------- SYSTEM PACKAGES --------------------------------

install_system_packages() {
    log_info "Установка системных пакетов (apt-get)."

    local DB_DEV_PACKAGE="libmysqlclient-dev"
    local DB_SERVER_PACKAGE="mysql-server"
    if [ "$DB_TYPE" = "postgres" ]; then
        DB_DEV_PACKAGE="libpq-dev"
        DB_SERVER_PACKAGE="postgresql postgresql-contrib"
    fi

    execute_command "sudo apt-get update -y"
    execute_command "sudo apt-get install -y \
        software-properties-common build-essential pkg-config \
        ${DB_DEV_PACKAGE} ${DB_SERVER_PACKAGE} \
        libssl-dev libffi-dev zlib1g-dev \
        redis-server \
        python3.11 python3.11-venv python3.11-dev \
        ca-certificates curl git"
}

#----------------------------- PYTHON VENV ------------------------------------

setup_python_venv_and_requirements() {
    log_info "Настройка Python 3.11 venv в ${VENV_DIR}."

    if [ ! -d "$VENV_DIR" ]; then
        execute_command "python3.11 -m venv '$VENV_DIR'"
    else
        log_warn "Venv уже существует: $VENV_DIR"
    fi

    local DB_REQ_FILE="requirements/mysql.txt"
    if [ "$DB_TYPE" = "postgres" ]; then
        DB_REQ_FILE="requirements/postgres.txt"
    fi

    execute_command "cd '$BACKEND_DIR' && source '$VENV_DIR/bin/activate' && pip install --upgrade pip"
    execute_command "cd '$BACKEND_DIR' && source '$VENV_DIR/bin/activate' && pip install -r requirements/base.txt -r ${DB_REQ_FILE} --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple"
}

#----------------------------- FRONTEND ---------------------------------------

setup_frontend() {
    if [ ! -d "$FRONTEND_DIR" ]; then
        log_warn "Frontend не найден: $FRONTEND_DIR"
        return
    fi
    if ! command -v npm >/dev/null 2>&1; then
        log_warn "npm не найден. Сначала выполните: bash scripts/nvm_install.sh"
        return
    fi

    execute_command "cd '$FRONTEND_DIR' && npm install"
}

#----------------------------- DATABASE ---------------------------------------

setup_mysql_local() {
    log_info "Настройка локального MySQL (non-fatal)."
    execute_command "sudo systemctl start mysql.service"
    execute_command "sudo systemctl enable mysql.service"

    echo -en "${BLUE}Пароль для нового пользователя MySQL '$DB_USER': ${NC}"
    read -s DB_PASSWORD
    echo

    execute_command "sudo mysql -e \"CREATE DATABASE IF NOT EXISTS \\\`$DB_NAME\\\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci\""
    execute_command "sudo mysql -e \"CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD'\""
    execute_command "sudo mysql -e \"ALTER USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASSWORD'\""
    execute_command "sudo mysql -e \"GRANT ALL PRIVILEGES ON \\\`$DB_NAME\\\`.* TO '$DB_USER'@'localhost'\""
    execute_command "sudo mysql -e \"FLUSH PRIVILEGES\""
}

setup_postgresql_local() {
    log_info "Настройка локального PostgreSQL (non-fatal)."
    execute_command "sudo systemctl start postgresql.service"
    execute_command "sudo systemctl enable postgresql.service"

    echo -en "${BLUE}Пароль для нового пользователя PostgreSQL '$DB_USER': ${NC}"
    read -s DB_PASSWORD
    echo

    execute_command "sudo -u postgres psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'\" | grep -q 1 || sudo -u postgres psql -c \"CREATE USER \\\"$DB_USER\\\" WITH PASSWORD '$DB_PASSWORD'\""
    execute_command "sudo -u postgres psql -tc \"SELECT 1 FROM pg_database WHERE datname='$DB_NAME'\" | grep -q 1 || sudo -u postgres psql -c \"CREATE DATABASE \\\"$DB_NAME\\\" OWNER \\\"$DB_USER\\\"\""
    execute_command "sudo -u postgres psql -d \"$DB_NAME\" -c \"GRANT ALL PRIVILEGES ON SCHEMA public TO \\\"$DB_USER\\\"\""
}

setup_redis_local() {
    log_info "Настройка локального Redis (non-fatal)."
    execute_command "sudo systemctl start redis-server"
    execute_command "sudo systemctl enable redis-server"
}

#----------------------------- MAIN -------------------------------------------

main() {
    log_info "Local dev setup (no Docker). Для разработки рекомендуется docker-compose.yml — см. README."

    ask_db_type
    install_system_packages
    setup_python_venv_and_requirements
    setup_frontend

    if [ "$DB_TYPE" = "postgres" ]; then
        setup_postgresql_local
    else
        setup_mysql_local
    fi
    setup_redis_local

    log_info "Готово. Дальше: создайте backend/.env (см. README), затем:"
    log_info "  source venv/bin/activate && cd backend && python manage.py migrate"
    log_info "  bash scripts/run_server.sh"
}

main
