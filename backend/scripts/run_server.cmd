@echo off
cd ..
call venv\Scripts\Activate

python manage.py runserver 0.0.0.0:8000