#!/bin/bash

execute_command() {
    eval "$1"
    if [ $? -eq 0 ]; then
        echo -e "\e[94mКоманда: $1 успешно выполнена\e[0m"
    else
        echo -e "\e[91mОшибка при выполнении команды: $1\e[0m"
    fi
}

execute_command "sudo apt-get update -y"
execute_command "sudo apt-get upgrade -y"

execute_command "sudo apt-get install -y nginx gunicorn wget gcc make curl git"
execute_command "sudo apt-get install -y build-essential libncursesw5-dev libssl-dev libsqlite3-dev tk-dev libgdbm-dev libc6-dev libbz2-dev libffi-dev zlib1g-dev"

execute_command "sudo add-apt-repository ppa:deadsnakes/ppa"
execute_command "sudo apt-get install -y python3.11 python3.11-venv python3.11-dev"

execute_command "sudo ufw enable" 
execute_command "sudo ufw allow 'Nginx Full'"

execute_command "sudo apt install postgresql postgresql-contrib"

curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash
source ~/.bashrc

read -p "Введите имя пользователя (пользователь должен иметь доступ): " username

execute_command "cd /var/www/ && sudo mkdir -p app"

execute_command "sudo chown -R $username:www-data /var/www/app"

execute_command "sudo systemctl start postgresql.service"

execute_command "sudo -u postgres psql -c \"DROP DATABASE IF EXISTS storage;\"" 
execute_command "sudo -u postgres psql -c \"DROP USER IF EXISTS django-admin;\"" 

# Change password for django-admin to real one from .env 
execute_command "sudo -u postgres psql -c \"CREATE USER django-admin WITH PASSWORD 'django-admin';\""
execute_command "sudo -u postgres psql -c \"CREATE DATABASE storage;\""
execute_command "sudo -u postgres psql -c \"GRANT ALL PRIVILEGES ON DATABASE storage TO django-admin;\""
execute_command "sudo -u postgres psql -d storage -c \"GRANT ALL PRIVILEGES ON SCHEMA public TO django-admin;\""


echo -e "\e[92mПожалуйста, перезагрузите терминал и запустите nvm_install.sh\e[0m"
