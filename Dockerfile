# The EEL pipeline server (pipeline/server.py) with the demo page, in one container.
# Build and start it with deploy/docker.sh.
#
# pipeline/.env (HAI_API_KEY, PIPELINE_PASSWORD) is passed at run time, never baked into the image.
# Runs, test cases and uploads live in the /data volume, so they survive a rebuild.
# AI_CONCURRENCY (default 16) and AI_PER_RUN (default 6) size the shared AI workers.
FROM python:3.12-slim

WORKDIR /app
COPY pipeline/requirements.txt pipeline/
RUN pip install --no-cache-dir -r pipeline/requirements.txt

COPY pipeline/ pipeline/
COPY demo/ demo/
COPY docs/law_file/ docs/law_file/
COPY docs/law_file.pdf docs/

ENV PIPELINE_HOST=0.0.0.0 \
    PIPELINE_PORT=8787 \
    PIPELINE_DATA=/data \
    PYTHONUNBUFFERED=1
VOLUME /data
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/', timeout=4)"
CMD ["python", "pipeline/server.py"]
