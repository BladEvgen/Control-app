@echo off
cd ..
call venv\Scripts\activate
flake8 --config=config_flake.flake8 .
