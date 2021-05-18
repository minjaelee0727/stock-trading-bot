forfiles /P "%~dp0..\log" /S /M *.log* /D -3 /C "cmd /c del @file"
timeout 5