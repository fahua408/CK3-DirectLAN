@echo off
chcp 65001 >nul
title CK3-DirectLAN · 一键上传至 GitHub 开源仓库并发布 Release

cd /d "%~dp0"
python "%~dp0upload_to_github.py"
pause
