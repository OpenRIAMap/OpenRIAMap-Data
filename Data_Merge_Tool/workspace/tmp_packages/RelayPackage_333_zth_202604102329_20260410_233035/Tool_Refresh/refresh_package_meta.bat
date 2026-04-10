@echo off
setlocal
cd /d %~dp0
python refresh_package_meta.py
pause