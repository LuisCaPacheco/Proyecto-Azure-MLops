"""Pruebas del endpoint de inferencia (esquema, errores, seguridad, explicabilidad).

Ejecutar desde la raíz:  pytest endpoint/tests -v
Usan el modelo empaquetado en endpoint/model (el mismo que va en la imagen).
"""

import json
import os
import sys
from pathlib import Path

import pytest

ENDPOINT_DIR = Path(__file__).resolve().parent.parent
os.environ.setdefault("MODEL_PATH", str(ENDPOINT_DIR / "model"))
sys.path.insert(0, str(ENDPOINT_DIR))

from fastapi.testclient import TestClient  # noqa: E402

import app as app_module  # noqa: E402

EXAMPLES = ENDPOINT_DIR / "examples"
RISKY = json.loads((EXAMPLES / "estudiante_riesgo_alto.json").read_text(encoding="utf-8"))
SAFE = json.loads((EXAMPLES / "estudiante_riesgo_bajo.json").read_text(encoding="utf-8"))
STUDENT = RISKY["student"]
VECTOR = list(STUDENT.values())
CLASSES = {"Continua", "Abandona"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    app_module._requests.clear()
    with TestClient(app_module.app) as c:
        yield c


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True


def test_model_info_lists_18_features(client):
    body = client.get("/model-info").json()
    assert len(body["features"]) == 18
    assert body["classes"] == ["Continua", "Abandona"]
    assert "max_nivel_esp" in body["features"]
    assert "max_nivel_esp" not in body["model_features"]


def test_predict_student_schema(client):
    resp = client.post("/predict", json={"student": STUDENT})
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction"] in CLASSES
    assert abs(sum(body["probabilities"].values()) - 1) < 1e-3
    assert body["dropout_risk"] == body["probabilities"]["Abandona"]
    assert body["risk_level"] in {"alto", "medio", "bajo"}


def test_predict_vector_equals_dict(client):
    by_vector = client.post("/predict", json={"features": VECTOR}).json()
    by_dict = client.post("/predict", json={"student": STUDENT}).json()
    # cada predicción tiene su propio id; el resto debe coincidir
    assert by_vector.pop("prediction_id") != by_dict.pop("prediction_id")
    assert by_vector == by_dict


def test_predict_wrong_feature_count(client):
    resp = client.post("/predict", json={"features": [1.0, 2.0, 3.0]})
    assert resp.status_code == 400


def test_predict_missing_and_unknown_keys(client):
    missing = dict(STUDENT)
    missing.pop("edad")
    assert client.post("/predict", json={"student": missing}).status_code == 422
    unknown = dict(STUDENT)
    unknown["estrato"] = 3
    assert client.post("/predict", json={"student": unknown}).status_code == 422


def test_predict_requires_exactly_one_input(client):
    assert client.post("/predict", json={}).status_code == 422
    both = {"features": VECTOR, "student": STUDENT}
    assert client.post("/predict", json=both).status_code == 422


def test_predict_rejects_out_of_range(client):
    assert client.post("/predict", json={"student": dict(STUDENT, edad=2)}).status_code == 422
    assert client.post("/predict", json={"student": dict(STUDENT, laptop=7)}).status_code == 422


def test_batch(client):
    students = [RISKY["student"], SAFE["student"]]
    resp = client.post("/predict/batch", json={"students": students})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_explain_is_consistent_with_prediction(client):
    body = client.post("/explain?top=5", json={"student": STUDENT}).json()
    exp = body["explanation"]
    assert len(exp["top_factors"]) == 5
    # base + suma de contribuciones reproduce P(Abandona)
    assert abs(exp["predicted_probability"] - body["prediction"]["dropout_risk"]) < 1e-3


def test_api_key_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("API_KEY", "secreto-de-prueba")
    assert client.get("/health").status_code == 200  # health siempre abierto
    assert client.post("/predict", json={"student": STUDENT}).status_code == 401
    bad = {"X-API-Key": "otra"}
    assert client.post("/predict", json={"student": STUDENT}, headers=bad).status_code == 401
    ok = {"X-API-Key": "secreto-de-prueba"}
    assert client.post("/predict", json={"student": STUDENT}, headers=ok).status_code == 200


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(app_module, "RATE_LIMIT_PER_MIN", 3)
    codes = [client.post("/predict", json={"student": STUDENT}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_feedback_is_logged_with_prediction_id(client, monkeypatch):
    records = []
    monkeypatch.setattr(app_module.logger, "info", lambda msg: records.append(json.loads(msg)))
    pid = client.post("/predict", json={"student": STUDENT}).json()["prediction_id"]
    resp = client.post("/feedback", json={"prediction_id": pid, "actual": "Abandona"})
    assert resp.status_code == 202
    inference, fb = records
    assert inference["event"] == "inference" and inference["prediction_ids"] == [pid]
    assert fb == {"event": "feedback", "prediction_id": pid, "actual": "Abandona"}


def test_feedback_rejects_unknown_class(client):
    resp = client.post("/feedback", json={"prediction_id": "12345678", "actual": "Transferido"})
    assert resp.status_code == 422
