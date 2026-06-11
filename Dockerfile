FROM python:3.12-slim

WORKDIR /app

# system deps for GitPython, cryptography wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        git build-essential libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
