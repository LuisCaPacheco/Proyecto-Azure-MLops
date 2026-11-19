"""Monitoreo de degradación del modelo en producción (accuracy decay).

El data drift (``drift.py``) avisa cuando cambian las entradas; este módulo
mide lo que de verdad importa: si el modelo sigue acertando. Cruza, por
``prediction_id``, dos eventos de los logs JSON del endpoint:

- ``event=inference``: lo que predijo el modelo (``prediction_ids`` + ``predictions``).
- ``event=feedback``: la clase real que Bienestar Universitario reporta en
  ``POST /feedback`` al cierre del periodo.

Con los pares (predicción, real) calcula accuracy y recall por clase, y los
compara con las métricas de test del modelo en Production
(``evaluation/metrics.json`` del run). Hay degradación si la accuracy cae
más de ``--tolerance`` bajo la de referencia o si el recall de alguna clase
baja de su umbral mínimo.

Uso:
    python -m ml.monitoring.performance --logs inference.log \
        --reference outputs/evaluation/metrics.json --output decay.json --fail-on-decay
"""

import argparse
import json
import sys
from pathlib import Path

from ml.pipeline.modeling import CLASSES, DEFAULT_CLASS_THRESHOLDS

MIN_SAMPLES = 30


def load_pairs(path: Path) -> list[tuple[str, str]]:
    """Devuelve los pares (predicción, real) que tienen feedback.

    Si llegan varios feedback para la misma predicción, vale el último.
    """
    predicted: dict[str, str] = {}
    actual: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") == "inference":
            predicted.update(zip(record.get("prediction_ids", []), record.get("predictions", [])))
        elif record.get("event") == "feedback":
            actual[record["prediction_id"]] = record["actual"]
    return [(predicted[pid], real) for pid, real in actual.items() if pid in predicted]


def performance_report(
    pairs: list[tuple[str, str]],
    reference: dict,
    tolerance: float = 0.05,
    thresholds: dict | None = None,
    min_samples: int = MIN_SAMPLES,
) -> dict:
    """Compara la accuracy observada en producción con la de referencia."""
    thresholds = DEFAULT_CLASS_THRESHOLDS if thresholds is None else thresholds
    n = len(pairs)
    ref_acc = reference["accuracy"]
    report = {
        "n_labeled": n,
        "min_samples": min_samples,
        "reference_accuracy": ref_acc,
        "tolerance": tolerance,
        "accuracy": None,
        "accuracy_drop": None,
        "per_class": {},
        "reasons": [],
        "enough_data": n >= min_samples,
        "decay_detected": False,
        "retrain_recommended": False,
    }
    if n == 0:
        return report

    accuracy = sum(pred == real for pred, real in pairs) / n
    report["accuracy"] = round(accuracy, 4)
    report["accuracy_drop"] = round(ref_acc - accuracy, 4)

    for name in CLASSES:
        of_class = [pred for pred, real in pairs if real == name]
        recall = sum(pred == name for pred in of_class) / len(of_class) if of_class else None
        report["per_class"][name] = {
            "support": len(of_class),
            "recall": None if recall is None else round(recall, 4),
        }

    # Con pocas etiquetas el estimado es ruido: se reporta pero no dispara nada
    if not report["enough_data"]:
        return report

    if accuracy < ref_acc - tolerance:
        report["reasons"].append(
            f"accuracy {accuracy:.3f} < referencia {ref_acc:.3f} - tolerancia {tolerance:.2f}"
        )
    for name, minimum in thresholds.items():
        stats = report["per_class"].get(name, {})
        # mismo criterio de soporte mínimo por clase, repartido entre las clases
        if stats.get("recall") is not None and stats["support"] >= min_samples // len(CLASSES) \
                and stats["recall"] < minimum:
            report["reasons"].append(f"{name}: recall {stats['recall']:.3f} < {minimum:.2f}")

    report["decay_detected"] = bool(report["reasons"])
    report["retrain_recommended"] = report["decay_detected"]
    return report


def to_markdown(report: dict) -> str:
    lines = ["## Desempeño del modelo en producción", ""]
    if report["accuracy"] is None:
        return "\n".join(lines + ["Sin predicciones etiquetadas (no hay feedback todavía)."])
    lines += [
        f"- Predicciones con resultado real: **{report['n_labeled']}** (mínimo {report['min_samples']})",
        f"- Accuracy observada: **{report['accuracy']:.3f}** (referencia {report['reference_accuracy']:.3f}, "
        f"caída {report['accuracy_drop']:+.3f})",
        "",
        "| Clase | Casos | Recall |",
        "|---|---|---|",
    ]
    for name, stats in report["per_class"].items():
        recall = "—" if stats["recall"] is None else f"{stats['recall']:.3f}"
        lines.append(f"| {name} | {stats['support']} | {recall} |")
    lines.append("")
    if not report["enough_data"]:
        lines.append("Datos insuficientes para decidir; solo informativo.")
    elif report["decay_detected"]:
        lines.append("**Degradación detectada — se recomienda reentrenar:** " + "; ".join(report["reasons"]))
    else:
        lines.append("Sin degradación.")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Detección de accuracy decay con feedback real")
    parser.add_argument("--logs", type=Path, required=True, help="Logs JSON del endpoint (inference + feedback)")
    parser.add_argument("--reference", type=Path, required=True, help="metrics.json del modelo en Production")
    parser.add_argument("--tolerance", type=float, default=0.05)
    parser.add_argument("--min-samples", type=int, default=MIN_SAMPLES)
    parser.add_argument("--output", type=Path, default=None, help="JSON del reporte")
    parser.add_argument("--markdown", type=Path, default=None, help="Resumen en Markdown")
    parser.add_argument("--fail-on-decay", action="store_true")
    args = parser.parse_args()

    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    report = performance_report(load_pairs(args.logs), reference, args.tolerance, min_samples=args.min_samples)
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(to_markdown(report), encoding="utf-8")

    if args.fail_on_decay and report["decay_detected"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
