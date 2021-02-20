@Echo off
call "C:\Users\minja\anaconda3\Scripts\activate.bat" py37_64
call python "%~dp0\..\ai_filter.py" %1 %2
