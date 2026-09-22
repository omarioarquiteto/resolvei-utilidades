@echo off
setlocal
cd /d "%~dp0"
echo.
echo ==========================================
echo        CONFIGURADOR DO RESOLVEI
 echo ==========================================
echo.
set /p OPENAI_API_KEY=Digite sua OPENAI_API_KEY (Enter para pular): 
set /p SERPAPI_KEY=Digite sua SERPAPI_KEY (Enter para pular): 
echo OPENAI_API_KEY=%OPENAI_API_KEY%> .env
echo OPENAI_MODEL=gpt-5.6-luna>> .env
echo SERPAPI_KEY=%SERPAPI_KEY%>> .env
echo.
echo Arquivo .env criado/atualizado.
echo Agora execute iniciar_resolvei.bat
pause
