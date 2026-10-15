@echo off
REM Start the Flask web interface and open it in the browser.
cd /d "%~dp0"
echo Starting the Curriculum Capacity Planning web interface...
echo Open http://127.0.0.1:5000 when the server is ready.
start "" http://127.0.0.1:5000
python flask_app.py
pause
