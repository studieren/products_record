@echo off
setlocal

:: 获取批处理脚本所在目录作为项目目录
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"  REM 移除末尾的反斜杠

:: 检查目录是否存在
if not exist "%PROJECT_DIR%" (
    echo 错误: 项目目录 "%PROJECT_DIR%" 不存在!
    goto :END
)

:: 切换到项目目录
cd /d "%PROJECT_DIR%"

:: 检查uvicorn是否安装
where uv >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo 错误: 未找到uvicorn命令。请确保已安装uvicorn。
    goto :END
)

:: 检查app.py文件是否存在
if not exist "app.py" (
    echo 错误: 在 "%PROJECT_DIR%" 中未找到app.py文件!
    goto :END
)

:: 启动Flask应用
echo 正在启动Flask应用...
uv run app.py

:END
endlocal
    