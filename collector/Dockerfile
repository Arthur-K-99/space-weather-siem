FROM python:3.12-slim

WORKDIR /app

# Deps first for layer caching
COPY collector/requirements.txt collector/requirements.txt
RUN pip install --no-cache-dir -r collector/requirements.txt

COPY collector/ collector/

ENV PYTHONUNBUFFERED=1

# Loops forever, polling each feed on its own cadence. ES_URL + ELASTIC_PASSWORD
# come from the environment (docker-compose injects them).
CMD ["python", "-m", "collector"]
