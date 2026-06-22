@echo off
cd /d %~dp0
echo Starting local web server...
python -m http.server 8080
pause
