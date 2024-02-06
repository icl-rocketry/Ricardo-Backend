@echo off

start py -3.8 .\main.py -d COM7
start py -3.8 ..\Ricardo-CommandServer\main.py
timeout /t 5
start "" http://localhost:1337/taskhandler_ui
start "" http://localhost:3000/d/OnXlzaJVk/command?orgId=1
