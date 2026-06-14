@echo off
chcp 65001 > nul
"D:\program Files\python 3.10.11\python.exe" "%~dp0daily_news_collector.py" --no-shutdown
