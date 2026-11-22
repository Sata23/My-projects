FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TELECOM_DEMO=false TELECOM_DATA_DIR=/app/runtime
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 telecom
COPY telecomiq ./telecomiq
RUN mkdir /app/runtime && chown -R telecom:telecom /app
USER telecom
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=4)"
CMD ["uvicorn","telecomiq.api:create_app","--factory","--host","0.0.0.0","--port","8000","--workers","1"]
