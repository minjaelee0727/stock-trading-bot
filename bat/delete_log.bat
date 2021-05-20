forfiles /P "%~dp0..\log" /S /M *.log* /D -3 /C "cmd /c del @file"
timeout 5

:: %~dp0 : Current dic
:: https://docs.microsoft.com/ko-kr/windows-server/administration/windows-commands/forfiles