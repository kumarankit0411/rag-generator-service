FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY evals ./evals
COPY scripts ./scripts
COPY ui ./ui

# no .env in the image: pass it at run time with --env-file, so keys stay out of layers
ENV CHROMA_PERSIST_DIR=/app/data/chroma

EXPOSE 8000 8501

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]