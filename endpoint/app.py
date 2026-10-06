"""API de inferencia del modelo de deserción universitaria (FastAPI).

Sirve el modelo `dropout-classifier` (versión en Production del Model
Registry). El modelo se descarga antes del build (ver `download_model.sh`)
a la carpeta `MODEL_PATH`, de modo que la imagen es autocontenida para ACI.
El modelo se lee directamente del formato MLflow (MLmodel + cloudpickle),
sin instalar MLflow en la imagen.

Endpoints:
- GET  /health        -> estado del servicio y del modelo (sin autenticación)
- GET  /model-info    -> versión, clases, variables y métricas del modelo
- POST /predict       -> riesgo de deserción de un estudiante
- POST /predict/batch -> riesgo de una lista de estudiantes (máx. 500)
- POST /explain       -> variables que más empujan la predicción (explicabilidad)

Seguridad (variables de entorno):
- API_KEY: si está definida, exige el header `X-API-Key` (el valor se
  guarda en Key Vault y se inyecta como variable segura en ACI).
- RATE_LIMIT_PER_MIN: solicitudes por minuto por IP (por defecto 60).
"""

import json
import logging
import math
import os
import secrets
import sys
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import cloudpickle
import numpy as np
import pandas as pd
import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from explain import explain

MODEL_PATH = os.environ.get("MODEL_PATH", "/app/model")
MODEL_NAME = "dropout-classifier"
DEFAULT_CLASSES = ["Dropout", "Enrolled", "Graduate"]

# Umbrales de P(Dropout) para el nivel de riesgo que ve Bienestar Universitario
RISK_HIGH = float(os.environ.get("RISK_HIGH", "0.5"))
RISK_MEDIUM = float(os.environ.get("RISK_MEDIUM", "0.3"))
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "60"))
LOG_FEATURES = os.environ.get("LOG_FEATURES", "true").lower() == "true"

logger = logging.getLogger("inference")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


# ---------------------------------------------------------------------------
# Carga del modelo
# ---------------------------------------------------------------------------
def find_model_dir() -> Path:
    """Localiza la carpeta MLflow del modelo (contiene MLmodel)."""
    base = Path(MODEL_PATH)
    candidates = [
        base,
        base / MODEL_NAME,
        base / MODEL_NAME / "model",
        base / "model",
    ]
    for cand in candidates:
        if (cand / "MLmodel").is_file():
            return cand
    raise FileNotFoundError(f"No se encontró un modelo MLflow en {[str(c) for c in candidates]}")


def load_model(model_dir: Path) -> tuple[object, dict]:
    """Carga el estimador sklearn y los metadatos desde la carpeta MLflow."""
    mlmodel = yaml.safe_load((model_dir / "MLmodel").read_text())
    flavor = mlmodel["flavors"]["sklearn"]
    if flavor.get("serialization_format", "cloudpickle") not in ("cloudpickle", "pickle"):
        raise ValueError(f"Formato no soportado: {flavor['serialization_format']}")
    with open(model_dir / flavor["pickled_model"], "rb") as fh:
        model = cloudpickle.load(fh)

    meta = {
        "run_id": mlmodel.get("run_id"),
        "created": mlmodel.get("utc_time_created"),
        "sklearn_version": flavor.get("sklearn_version"),
        "classes": (mlmodel.get("metadata") or {}).get("classes", DEFAULT_CLASSES),
        "version": None,
        "metrics": None,
    }
    registered = model_dir / "registered_model_meta"
    if registered.is_file():
        meta["version"] = str(yaml.safe_load(registered.read_text()).get("model_version"))
    metrics = model_dir / "metrics.json"
    if metrics.is_file():
        meta["metrics"] = json.loads(metrics.read_text())
    return model, meta


def configure_telemetry() -> None:
    """Envía los logs de inferencia a Application Insights si hay connection string."""
    if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
        return
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(logger_name="inference")
    except Exception as exc:  # noqa: BLE001
        logger.warning(json.dumps({"event": "telemetry_disabled", "error": str(exc)}))


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_telemetry()
    try:
        model, meta = load_model(find_model_dir())
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Fallo al cargar el modelo: {exc}")
    app.state.model = model
    app.state.meta = meta
    app.state.features = list(getattr(model, "feature_names_in_", []))
    yield


app = FastAPI(
    title="Dropout Risk API",
    description="Predicción temprana de deserción universitaria (P07 - The Odyssey)",
    version="2.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Seguridad: API key + rate limiting
# ---------------------------------------------------------------------------
_requests: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    """Ventana deslizante de 60 s por IP para mitigar abuso / model scraping."""
    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window = _requests[client]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="Demasiadas solicitudes, intente en un minuto")
    window.append(now)


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Exige `X-API-Key` cuando la variable API_KEY está configurada."""
    expected = os.environ.get("API_KEY")
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="API key inválida o ausente")


protected = [Depends(verify_api_key), Depends(rate_limit)]


# ---------------------------------------------------------------------------
# Esquemas
# ---------------------------------------------------------------------------
class PredictRequest(BaseModel):
    """Un estudiante: vector ordenado `features` o diccionario `student`."""

    features: list[float] | None = Field(default=None, description="36 valores en el orden de /model-info")
    student: dict[str, float] | None = Field(default=None, description="Variable -> valor")

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.features is None) == (self.student is None):
            raise ValueError("Envíe exactamente uno de 'features' o 'student'")
        return self


class BatchRequest(BaseModel):
    students: list[dict[str, float]] = Field(min_length=1, max_length=500)


class PredictResponse(BaseModel):
    prediction: str
    class_index: int
    confidence: float
    probabilities: dict[str, float]
    dropout_risk: float
    risk_level: str
    model_version: str | None


# ---------------------------------------------------------------------------
# Lógica de inferencia
# ---------------------------------------------------------------------------
def to_frame(rows: list[dict[str, float]] | None = None, vector: list[float] | None = None) -> pd.DataFrame:
    """Valida la entrada y la convierte al DataFrame que espera el modelo."""
    features = app.state.features
    if vector is not None:
        if len(vector) != len(features):
            raise HTTPException(
                status_code=400,
                detail=f"Se esperaban {len(features)} features, se recibieron {len(vector)}",
            )
        rows = [dict(zip(features, vector))]

    for i, row in enumerate(rows):
        missing = [f for f in features if f not in row]
        unknown = [k for k in row if k not in features]
        if missing or unknown:
            raise HTTPException(
                status_code=400,
                detail={"row": i, "missing": missing, "unknown": unknown},
            )
        if any(not math.isfinite(v) for v in row.values()):
            raise HTTPException(status_code=400, detail={"row": i, "error": "valores no finitos"})
    return pd.DataFrame(rows, columns=features)


def risk_level(p_dropout: float) -> str:
    if p_dropout >= RISK_HIGH:
        return "alto"
    if p_dropout >= RISK_MEDIUM:
        return "medio"
    return "bajo"


def build_response(proba: np.ndarray) -> PredictResponse:
    classes = app.state.meta["classes"]
    idx = int(np.argmax(proba))
    p_dropout = float(proba[classes.index("Dropout")])
    return PredictResponse(
        prediction=classes[idx],
        class_index=idx,
        confidence=round(float(proba[idx]), 4),
        probabilities={c: round(float(p), 4) for c, p in zip(classes, proba)},
        dropout_risk=round(p_dropout, 4),
        risk_level=risk_level(p_dropout),
        model_version=app.state.meta["version"],
    )


def log_inference(endpoint: str, X: pd.DataFrame, responses: list[PredictResponse], started: float) -> None:
    """Log estructurado (stdout → Log Analytics / App Insights) para monitoreo y drift."""
    record = {
        "event": "inference",
        "request_id": str(uuid.uuid4()),
        "endpoint": endpoint,
        "n": len(responses),
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        "model_version": app.state.meta["version"],
        "predictions": [r.prediction for r in responses],
        "risk_levels": [r.risk_level for r in responses],
    }
    if LOG_FEATURES:
        record["features"] = X.to_dict(orient="records")
    logger.info(json.dumps(record))


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    model = getattr(app.state, "model", None)
    return {"status": "ok", "model_loaded": model is not None, "model_version": app.state.meta["version"]}


@app.get("/model-info", dependencies=protected)
def model_info() -> dict:
    meta = app.state.meta
    return {
        "name": MODEL_NAME,
        "version": meta["version"],
        "run_id": meta["run_id"],
        "created": meta["created"],
        "classes": meta["classes"],
        "features": app.state.features,
        "risk_thresholds": {"alto": RISK_HIGH, "medio": RISK_MEDIUM},
        "metrics": meta["metrics"],
    }


@app.post("/predict", response_model=PredictResponse, dependencies=protected)
def predict(req: PredictRequest) -> PredictResponse:
    started = time.perf_counter()
    X = to_frame([req.student] if req.student is not None else None, req.features)
    response = build_response(app.state.model.predict_proba(X)[0])
    log_inference("predict", X, [response], started)
    return response


@app.post("/predict/batch", response_model=list[PredictResponse], dependencies=protected)
def predict_batch(req: BatchRequest) -> list[PredictResponse]:
    started = time.perf_counter()
    X = to_frame(req.students)
    responses = [build_response(p) for p in app.state.model.predict_proba(X)]
    log_inference("predict_batch", X, responses, started)
    return responses


@app.post("/explain", dependencies=protected)
def explain_prediction(req: PredictRequest, top: int = 8) -> dict:
    X = to_frame([req.student] if req.student is not None else None, req.features)
    prediction = build_response(app.state.model.predict_proba(X)[0])
    explanation = explain(
        app.state.model,
        X.to_numpy()[0],
        app.state.features,
        app.state.meta["classes"],
        target_class="Dropout",
        top=max(1, min(top, len(app.state.features))),
    )
    return {"prediction": prediction.model_dump(), "explanation": explanation}
