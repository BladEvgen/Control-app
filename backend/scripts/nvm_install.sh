#!/bin/bash
# Локальная разработка без Docker: установка Node.js через nvm.
# Если вы используете docker-compose.yml (рекомендуемый путь), этот скрипт не нужен —
# Node.js ставится внутри docker/frontend/Dockerfile.

set -euo pipefail

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

if ! command -v nvm >/dev/null 2>&1; then
    echo -e "\e[93mnvm не найден. Установите его: https://github.com/nvm-sh/nvm#installing-and-updating\e[0m"
    exit 1
fi

NODE_VERSION="20.11.1"

execute_command() {
    eval "$1"
    if [ $? -eq 0 ]; then
        echo -e "\e[94mКоманда: $1 успешно выполнена\e[0m"
    else
        echo -e "\e[91mОшибка при выполнении команды: $1\e[0m"
    fi
}

execute_command "nvm install ${NODE_VERSION}"
execute_command "nvm alias default ${NODE_VERSION}"

echo -e "\e[92mГотово. Далее: backend/scripts/install_dependencies.sh\e[0m"
