FROM python:3.14-slim

WORKDIR /app

# Runtime deps only — requirements-dev.txt (ruff, pytest) stays out of the image.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY genai ./genai

# No --reload: this image exists so the project starts with one command.
# The day-to-day dev loop stays native uvicorn on the host.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
