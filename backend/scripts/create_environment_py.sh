#!/bin/bash

execute_command() {
    eval "$1"
    if [ $? -eq 0 ]; then
        echo -e "\e[94mКоманда: $1 успешно выполнена\e[0m"
    else
        echo -e "\e[91mОшибка при выполнении команды: $1\e[0m"
    fi
}

execute_command "cd .."
execute_command "python3.11 -m venv venv"
execute_command "source venv/bin/activate"
execute_command "pip install -r requirements.txt"
