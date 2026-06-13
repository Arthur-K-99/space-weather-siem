FROM python:3.12-slim

WORKDIR /app

# Deps first for layer caching
COPY detector/requirements.txt detector/requirements.txt
RUN pip install --no-cache-dir -r detector/requirements.txt

COPY detector/ detector/
COPY rules/ rules/

ENV PYTHONUNBUFFERED=1 \
    RULES_DIR=/app/rules

# Loops, evaluating every rule each DETECTOR_INTERVAL. ES_URL + ELASTIC_PASSWORD
# come from the environment (docker-compose injects them).
CMD ["python", "-m", "detector"]
