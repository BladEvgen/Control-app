#!/bin/bash

execute_command() {
    eval "$1"
    if [ $? -eq 0 ]; then
        echo -e "\e[94mКоманда: $1 успешно выполнена\e[0m"
    else
        echo -e "\e[91mОшибка при выполнении команды: $1\e[0m"
    fi
}
cd ..
execute_command " source ../.venv/bin/activate && python manage.py runserver 0.0.0.0:8000" 