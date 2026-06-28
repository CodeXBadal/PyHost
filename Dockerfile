FROM python:3.12-slim

WORKDIR /app

# system deps for GitPython, cryptography wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8081/health', timeout=3).status == 200 else 1)"

CMD ["python", "main.py"]
