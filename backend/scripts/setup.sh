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

execute_command "sudo -u postgres psql -c \"DROP DATABASE IF EXISTS staff_control;\"" 
execute_command "sudo -u postgres psql -c \"DROP USER IF EXISTS djangoadmin;\"" 

# Change password for djangoadmin to real one from .env 
execute_command "sudo -u postgres psql -c \"CREATE USER djangoadmin WITH PASSWORD 'Very_Strong_Password_123';\""
execute_command "sudo -u postgres psql -c \"CREATE DATABASE staff_control;\""
execute_command "sudo -u postgres psql -c \"GRANT ALL PRIVILEGES ON DATABASE staff_control TO djangoadmin;\""
execute_command "sudo -u postgres psql -d staff_control -c \"GRANT ALL PRIVILEGES ON SCHEMA public TO djangoadmin;\""


echo -e "\e[92mПожалуйста, перезагрузите терминал и запустите nvm_install.sh\e[0m"
