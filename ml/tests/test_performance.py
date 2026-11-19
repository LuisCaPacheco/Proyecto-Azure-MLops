"""Tests del monitor de accuracy decay (ml/monitoring/performance.py)."""

import json

from ml.monitoring.performance import load_pairs, performance_report, to_markdown

REFERENCE = {"accuracy": 0.80}
CLASSES = ["Continua", "Abandona"]


def _pairs(correct: int, wrong: int, missed: str = "Abandona") -> list[tuple[str, str]]:
    """`correct` aciertos repartidos entre las 2 clases y `wrong` casos de `missed` no detectados."""
    good = [(CLASSES[i % 2], CLASSES[i % 2]) for i in range(correct)]
    other = "Continua" if missed == "Abandona" else "Abandona"
    return good + [(other, missed)] * wrong


def test_load_pairs_joins_inference_and_feedback(tmp_path) -> None:
    log = tmp_path / "inference.log"
    lines = [
        "INFO: Uvicorn running",  # ruido que no es JSON
        json.dumps({"event": "inference", "prediction_ids": ["a", "b"], "predictions": ["Abandona", "Continua"]}),
        json.dumps({"event": "inference", "prediction_ids": ["c"], "predictions": ["Continua"]}),
        json.dumps({"event": "feedback", "prediction_id": "a", "actual": "Abandona"}),
        json.dumps({"event": "feedback", "prediction_id": "b", "actual": "Continua"}),
        json.dumps({"event": "feedback", "prediction_id": "b", "actual": "Abandona"}),   # corrección: vale el último
        json.dumps({"event": "feedback", "prediction_id": "zzz", "actual": "Abandona"}),  # sin predicción
    ]
    log.write_text("\n".join(lines), encoding="utf-8")
    assert sorted(load_pairs(log)) == [("Abandona", "Abandona"), ("Continua", "Abandona")]


def test_no_decay_when_accuracy_holds() -> None:
    # 20 Continua mal clasificados: recall de Continua 40/60 = 0.67, sobre su umbral (0.60)
    report = performance_report(_pairs(correct=80, wrong=20, missed="Continua"), REFERENCE)
    assert report["accuracy"] == 0.8
    assert report["decay_detected"] is False and report["retrain_recommended"] is False


def test_decay_when_accuracy_drops_beyond_tolerance() -> None:
    report = performance_report(_pairs(correct=60, wrong=40), REFERENCE)
    assert report["accuracy"] == 0.6
    assert report["decay_detected"] is True
    assert any("accuracy" in r for r in report["reasons"])
    # los abandonos no detectados también rompen el umbral de recall de Abandona
    assert any(r.startswith("Abandona") for r in report["reasons"])
    assert "reentrenar" in to_markdown(report)


def test_few_labels_never_trigger_retraining() -> None:
    report = performance_report(_pairs(correct=2, wrong=8), REFERENCE)
    assert report["accuracy"] == 0.2
    assert report["enough_data"] is False and report["decay_detected"] is False


def test_no_feedback_yet() -> None:
    report = performance_report([], REFERENCE)
    assert report["accuracy"] is None and report["decay_detected"] is False
    assert "Sin predicciones etiquetadas" in to_markdown(report)
