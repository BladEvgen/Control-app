@echo off
cd ..
call venv\Scripts\Activate

python manage.py makemigrations
python manage.py migrate