#!/bin/bash
# Локальная разработка БЕЗ Docker: обновляет Python/npm зависимости и
# пересобирает фронтенд в уже существующем venv (для первого раза — setup.sh).
#
# Если вы используете docker-compose.yml (рекомендуемый путь для разработки),
# этот скрипт не нужен — образ собирается через `docker compose build`.
#
# Пути определяются относительно расположения самого скрипта, поэтому
# работает на любой машине, куда склонирован репозиторий.
#
# Выбор БД-драйвера: DB_TYPE=mysql (по умолчанию) или DB_TYPE=postgres
#   DB_TYPE=postgres ./install_dependencies.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$BACKEND_DIR/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_DIR="$ROOT_DIR/venv"

DB_TYPE="${DB_TYPE:-mysql}"

execute_command() {
    eval "$1"
    if [ $? -eq 0 ]; then
        echo -e "\e[94mКоманда: $1 успешно выполнена\e[0m"
    else
        echo -e "\e[91mОшибка при выполнении команды: $1\e[0m"
    fi
}

if [ -d "$FRONTEND_DIR" ]; then
    execute_command "cd '$FRONTEND_DIR' && npm i"
    execute_command "cd '$FRONTEND_DIR' && npm run build"
else
    echo -e "\e[93mПропуск фронтенда: $FRONTEND_DIR не найден\e[0m"
fi

if [ ! -d "$VENV_DIR" ]; then
    execute_command "python3.11 -m venv '$VENV_DIR'"
fi

DB_REQ_FILE="requirements/mysql.txt"
if [ "$DB_TYPE" = "postgres" ] || [ "$DB_TYPE" = "postgresql" ]; then
    DB_REQ_FILE="requirements/postgres.txt"
fi

execute_command "cd '$BACKEND_DIR' && source '$VENV_DIR/bin/activate' && pip install -r requirements/base.txt -r $DB_REQ_FILE --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple"
execute_command "cd '$BACKEND_DIR' && source '$VENV_DIR/bin/activate' && python manage.py makemigrations && python manage.py migrate"
