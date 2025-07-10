@echo off
setlocal

:: ��ȡ������ű�����Ŀ¼��Ϊ��ĿĿ¼
set "PROJECT_DIR=%~dp0"
set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"  REM �Ƴ�ĩβ�ķ�б��

:: ���Ŀ¼�Ƿ����
if not exist "%PROJECT_DIR%" (
    echo ����: ��ĿĿ¼ "%PROJECT_DIR%" ������!
    goto :END
)

:: �л�����ĿĿ¼
cd /d "%PROJECT_DIR%"

:: ���uvicorn�Ƿ�װ
where uv >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo ����: δ�ҵ�uvicorn�����ȷ���Ѱ�װuvicorn��
    goto :END
)

:: ���app.py�ļ��Ƿ����
if not exist "app.py" (
    echo ����: �� "%PROJECT_DIR%" ��δ�ҵ�app.py�ļ�!
    goto :END
)

:: ����FlaskӦ��
echo ��������FlaskӦ��...
uv run app.py

:END
endlocal
    