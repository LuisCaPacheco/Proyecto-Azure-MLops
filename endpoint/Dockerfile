# Etapa 1: descargar el modelo desde el Model Registry de Azure ML
# y preparar el runtime de Python
FROM mcr.microsoft.com/azureml/openmpi4.1.0-ubuntu20.04:latest AS runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    MODEL_PATH=/app/model

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencias de Python de la API
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la API
COPY app.py .

# Copiar el modelo ya descargado desde el Model Registry de Azure ML.
# Ejecuta primero en el host: ./download_model.sh  (baja el modelo a ./model)
COPY model/ ./model/

# Usuario no-root para la API
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fs http://localhost:8000/health || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
