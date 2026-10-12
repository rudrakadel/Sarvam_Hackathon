#!/bin/bash
cd "$(dirname "$0")"
./.venv/Scripts/python.exe -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" >> .env || true
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning
