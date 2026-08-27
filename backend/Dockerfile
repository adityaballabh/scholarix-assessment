FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY backend/pyproject.toml ./backend/pyproject.toml
COPY backend/src ./backend/src
# -e keeps the package at /app/backend/src, so dataset/ and cache/ resolve to /app
RUN pip install --no-cache-dir -e ./backend

COPY dataset/authors.zip ./dataset/authors.zip

EXPOSE 8000

ENTRYPOINT ["python", "-m", "merge_review.docker_entrypoint"]
CMD ["uvicorn", "merge_review.main:app", "--host", "0.0.0.0", "--port", "8000"]
