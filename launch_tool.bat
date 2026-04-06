@echo off
setlocal
cd /d "%~dp0"
call Data_Merge_Tool\launch_tool.bat
set "EXITCODE=%errorlevel%"
endlocal & exit /b %EXITCODE%