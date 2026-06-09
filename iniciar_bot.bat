@echo off
title Boty viajero - LEVEL monitor
cd /d "%~dp0"
set TELEGRAM_TOKEN=8892317374:AAGLbIwq1x6S4twE_kih8Y__FsgiUH7128E
set TELEGRAM_CHAT_ID=6794945244
set CHECK_INTERVAL=180
set ALERT_THRESHOLD=300
set PYTHONIOENCODING=utf-8
echo Bot iniciado. Chequeando cada 3 min. No cierres esta ventana.
echo.
python monitor.py --loop
pause
