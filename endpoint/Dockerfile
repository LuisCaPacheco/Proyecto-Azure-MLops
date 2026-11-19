# Imagen del endpoint de inferencia (FastAPI) para Azure Container Instances.
# Base slim en lugar de la imagen openmpi de Azure ML: la API no necesita
# MLflow ni MPI, solo scikit-learn para leer el modelo (≈ 5x más liviana).
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MODEL_PATH=/app/model

# Dependencias de Python de la API
COPY requirements.txt .
RUN pip install -r requirements.txt

# Código de la API
COPY app.py explain.py ./

# Modelo ya descargado desde el Model Registry de Azure ML.
# Ejecuta primero en el host: ./download_model.sh  (baja el modelo a ./model)
COPY model/ ./model/

# Usuario no-root para la API
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status == 200 else 1)"

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
