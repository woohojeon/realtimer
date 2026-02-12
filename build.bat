@echo off
cd /d "%~dp0"
echo Building Lecture Lens...
python -m PyInstaller --noconfirm realtimer.spec
echo.
echo Done! Check dist\LectureLens folder.
pause
