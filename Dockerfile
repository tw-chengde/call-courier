# 官方映像（Ubuntu 26.04 / Python 3.14）已內建 Chromium 與系統套件，
# 但不含 playwright Python 套件，要自己安裝；版本需與映像標籤、pyproject.toml 一致
FROM mcr.microsoft.com/playwright/python:v1.64.0-resolute

WORKDIR /app
RUN pip install --no-cache-dir playwright==1.64.0
COPY main.py .

CMD ["python", "main.py"]
