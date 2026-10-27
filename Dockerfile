# EEL pipeline as a container. The API key and password come from pipeline/.env via --env-file, never baked in.
FROM python:3.12-slim
WORKDIR /app
COPY pipeline/requirements.txt pipeline/
RUN pip install --no-cache-dir -r pipeline/requirements.txt
COPY demo/ demo/
COPY docs/ docs/
COPY pipeline/ pipeline/
ENV PYTHONUNBUFFERED=1
EXPOSE 8787
CMD ["python", "pipeline/server.py", "--host", "0.0.0.0", "--port", "8787"]
