@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "MONIKA_HOME=%~dp0"
set "MONIKA_PYTHON=F:\Programs\python3.10-main\python.exe"
set "WEBSERVER_PORT=3000"
set "WEBVIEWER_DIR=%MONIKA_HOME%webviewer"

title Monika Launcher

echo ============================================
echo             MONIKA LAUNCHER
echo ============================================
echo.

if not exist "%MONIKA_PYTHON%" (
  echo [ERROR] Python not found: %MONIKA_PYTHON%
  pause
  exit /b 1
)

if not exist "%MONIKA_HOME%console_chat.py" (
  echo [ERROR] console_chat.py not found
  pause
  exit /b 1
)

:: 1. LM Studio
echo [1/3] Check LM Studio
echo Make sure LM Studio is running and the model is loaded.
echo.
pause

:: 2. HTTP-сервер для webviewer
echo [2/3] Start HTTP server for Live2D viewer
start "Monika WebViewer" cmd /k "cd /d \"%WEBVIEWER_DIR%\" && http-server -p %WEBSERVER_PORT% -c-1 --cors"
timeout /t 1 /nobreak >nul

:: 3. Запуск Моники
echo [3/3] Start Monika
cd /d "%MONIKA_HOME%"
start "Monika Chat" cmd /k "chcp 65001 >nul & set PYTHONUTF8=1 & set PYTHONIOENCODING=utf-8 & \"%MONIKA_PYTHON%\" \"%MONIKA_HOME%console_chat.py\""

timeout /t 3 /nobreak >nul

:: Открываем браузер с Live2D
echo [INFO] Opening Live2D viewer in browser
start http://localhost:3000/viewer.html

echo.
echo ============================================
echo               MONIKA STARTED
echo ============================================
echo.
echo  WebViewer: http://localhost:3000/viewer.html
echo  Python WS:  ws://localhost:8080
echo.
pause