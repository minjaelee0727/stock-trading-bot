@echo off

@Echo python kill Start
echo %time%

@taskkill /f /im "opstarter.exe"
@taskkill /f /im "python.exe"
@taskkill /f /im "cmd.exe"

