@echo off
setlocal enabledelayedexpansion

for /L %%i in (1,1,11) do (
    set "num=%%i"
    if %%i LSS 10 (
        set "filename=R0!num!.txt"
    ) else (
        set "filename=R!num!.txt"
    )
    echo. > "!filename!"
)

echo Files R01.txt through R11.txt have been created.
pause