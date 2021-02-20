@Echo off
@Echo trader Start
set x=0
set time_unit=1
set max=700
set target_window="trader"
set file="%~dp0\..\trader.py"
set activate_path="C:\Users\minja\anaconda3\Scripts\activate.bat"
IF EXIST %activate_path% (
    call %activate_path% py37_32
) ELSE (
    echo Cannot find %activate_path%
    pause
    exit 1
)
IF NOT EXIST %file% (
    echo Cannot find %file%
    pause
    exit 1
)
goto start_point


:kill_point
set x=0
echo Killing trader...
@taskkill /pid %process_id% /f 2> nul


:start_point
@taskkill /f /im "opstarter.exe" 2> nul
echo Starting a new session...
start "%target_window%" python %file%
for /F "tokens=2 delims=," %%A in ('tasklist /fi "imagename eq python.exe" /v /fo:csv ^| findstr /r /c:".*%target_window%[^,]*$"') do set process_id=%%A


:count_point
@timeout /t %time_unit% /nobreak > nul
echo %x%
tasklist /fi "imagename eq python.exe" /v /fo:csv | findstr /r /c:".*%target_window%[^,]*$" > nul
IF errorlevel 1 goto kill_point
IF %x% GEQ %max% (
    goto kill_point
)
set /A "x+=time_unit"
goto count_point
