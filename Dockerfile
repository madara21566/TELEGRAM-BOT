# Dockerfile: build a single image that can run both the FastAPI web UI and the Telegram bot
FROM python:3.11-slim


ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1


WORKDIR /app


COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt


# Copy app
COPY . /app


# Create a non-root user
RUN useradd -m runner && chown -R runner:runner /app
USER runner


EXPOSE 8000


# Start both the FastAPI server and the Telegram bot via a small launcher script
CMD ["/app/entrypoint.sh"]
