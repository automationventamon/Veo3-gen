@echo off
cd /d %~dp0
echo [%date% %time%] === Worker reiniciado === >> worker.log
python app.py >> worker.log 2>&1
