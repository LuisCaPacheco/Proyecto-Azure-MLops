"""API de inferencia del modelo Iris (FastAPI).

Carga el modelo `iris-classifier` desde el Model Registry de Azure ML.
El modelo se descarga en tiempo de build (ver `download_model.sh`) a la
carpeta `MODEL_PATH`, de modo que la imagen es autocontenida para ACI.

Endpoints:
- GET  /health  -> estado del servicio y del modelo
- POST /predict -> clasificación de flores de iris (JSON)
"""

import os
from typing import List

import mlflow.sklearn
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Orden de las features, coincide con FEATURES del entrenamiento
FEATURE_NAMES = [
    "sepal length (cm)",
    "sepal width (cm)",
    "petal length (cm)",
    "petal width (cm)",
]

SPECIES = ["setosa", "versicolor", "virginica"]

MODEL_PATH = os.environ.get("MODEL_PATH", "/app/model")

app = FastAPI(title="Iris Classifier API", version="1.0.0")
model = None


class PredictRequest(BaseModel):
    features: List[float]


class PredictResponse(BaseModel):
    prediction: str
    confidence: float
    class_index: int


def find_model_dir() -> str:
    """Localiza la carpeta MLflow del modelo (contiene MLmodel)."""
    candidates = [MODEL_PATH] if MODEL_PATH else []
    candidates += [
        os.path.join(MODEL_PATH, "model"),
        os.path.join(MODEL_PATH, "iris-classifier", "model"),
        os.path.join(MODEL_PATH, "iris-classifier"),
    ]
    for cand in candidates:
        if os.path.isfile(os.path.join(cand, "MLmodel")):
            return cand
    raise FileNotFoundError(f"No se encontró un modelo MLflow en {candidates}")


def load_model():
    """Carga el modelo sklearn desde la carpeta MLflow."""
    model_dir = find_model_dir()
    # mlflow.sklearn.load_model devuelve el objeto sklearn directamente,
    # con .predict() y .predict_proba() sobre arrays numpy.
    return mlflow.sklearn.load_model(model_dir)


@app.on_event("startup")
def startup() -> None:
    global model
    try:
        model = load_model()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Fallo al cargar el modelo: {exc}")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_loaded": model is not None}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    if model is None:
        raise HTTPException(status_code=503, detail="Modelo no cargado")

    if len(req.features) != len(FEATURE_NAMES):
        raise HTTPException(
            status_code=400,
            detail=f"Se esperaban {len(FEATURE_NAMES)} features, se recibieron {len(req.features)}",
        )

    X = np.array([req.features]).reshape(1, -1)

    # Predicción usando las clases del propio modelo
    pred = model.predict(X)
    classes = getattr(model, "classes_", np.array([0, 1, 2]))
    pred_class = int(classes[pred[0]]) if classes is not None else int(pred[0])

    # Probabilidades cuando el modelo las soporta
    confidence = 0.0
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)
        confidence = float(np.max(proba[0]))

    species = SPECIES[pred_class] if 0 <= pred_class < len(SPECIES) else str(pred_class)

    return PredictResponse(prediction=species, confidence=confidence, class_index=pred_class)
