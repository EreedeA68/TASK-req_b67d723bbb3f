FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Seed default users then start the server.
# SECRET_KEY must be supplied at runtime (see README).
CMD ["sh", "-c", "python seed.py && python wsgi.py"]
