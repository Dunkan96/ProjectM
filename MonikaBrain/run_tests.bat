@echo off
chcp 65001 >nul
title Моника 3.0 - Тестирование

echo ============================================
echo         ТЕСТИРОВАНИЕ МОНИКИ 3.0
echo ============================================
echo.
echo Убедитесь, что запущены:
echo   [1] LM Studio с моделью mistral-small-24b (порт 1234)
echo   [2] Engram (engram start в отдельном окне)
echo.
echo Перед тестированием рекомендуется:
echo   [3] Выполнить сброс мозга: python reset_brain.py
echo.
pause

echo.
echo ============================================
echo         ЗАПУСК МОНИКИ
echo ============================================
echo.
echo Лог будет сохранён в Monika_test_%date:~-4%%date:~-7,-5%%date:~-10,-8%.txt
echo.

cd /d F:\МоnikaVtuber\MonikaBrain
python console_chat.py 2>&1 | tee Monika_test_log.txt

pause