"""Evaluación del modelo: compara el candidato vs el modelo en producción.

Este script lee las métricas del run de entrenamiento (el JSON que genera
`train.py --metrics-output`, o argumentos sueltos) y las compara con el
modelo actualmente en Producción del Model Registry, decidiendo si el nuevo
candidato debe desplegarse.

Reglas (prueba de regresión del modelo):
1. accuracy >= baseline global (0.70).
2. recall por clase >= umbral (Dropout, Enrolled, Graduate): evita que un
   reentrenamiento mejore la accuracy a costa de dejar de detectar desertores.
3. F1 macro >= F1 macro del modelo en Production - tolerancia (si existe).
   Se compara F1 macro y no accuracy: es la métrica con la que se selecciona
   el modelo en `tune.py` y no premia ignorar la clase minoritaria.

Salida: imprime un JSON que la etapa 'Evaluate' del pipeline CI/CD
interpreta como condición de despliegue (exit code 1 con --fail-on-reject).
"""

import argparse
import json
import sys
from pathlib import Path

from mlflow.tracking import MlflowClient

from ml.pipeline.modeling import DEFAULT_CLASS_THRESHOLDS


def get_production_metrics(model_name: str) -> dict | None:
    """Devuelve las métricas del run del modelo en Production, o None si no existe.

    Usa el API de stages (MLflow 2.x / Azure ML) y, si no hay resultado,
    el alias `production` (MLflow 3.x).
    """
    client = MlflowClient()
    version = None
    try:
        versions = client.search_model_versions(f"name='{model_name}' and stage='Production'")
        version = versions[0] if versions else None
    except Exception:
        pass
    if version is None:
        try:
            version = client.get_model_version_by_alias(model_name, "production")
        except Exception:
            return None

    metrics = client.get_run(version.run_id).data.metrics
    return {"version": str(version.version), **metrics}


def decide(
    candidate: dict,
    production: dict | None,
    baseline: float,
    thresholds: dict,
    tolerance: float = 0.005,
) -> dict:
    """Aplica las reglas de despliegue y devuelve el detalle de la decisión."""
    class_failures = []
    per_class = candidate.get("per_class")
    if per_class:
        for name, minimum in thresholds.items():
            recall = per_class[name]["recall"]
            if recall < minimum:
                class_failures.append(f"{name}: recall {recall:.3f} < {minimum:.2f}")

    new_acc = candidate["accuracy"]
    new_f1 = candidate.get("f1_macro")
    prod_f1 = production.get("f1_macro") if production else None

    beats_baseline = new_acc >= baseline
    beats_prod = prod_f1 is None or new_f1 is None or new_f1 >= prod_f1 - tolerance
    return {
        "new_accuracy": new_acc,
        "new_f1_macro": new_f1,
        "production_version": production.get("version") if production else None,
        "production_accuracy": production.get("accuracy") if production else None,
        "production_f1_macro": prod_f1,
        "baseline_accuracy": baseline,
        "beats_baseline": beats_baseline,
        "beats_prod": beats_prod,
        "class_failures": class_failures,
        "deploy": beats_baseline and beats_prod and not class_failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalúa candidato vs producción")
    parser.add_argument("--model-name", default="dropout-classifier")
    parser.add_argument("--metrics-file", type=Path, default=None,
                        help="JSON de train.py --metrics-output (accuracy, f1_macro, per_class)")
    parser.add_argument("--new-accuracy", type=float, default=None,
                        help="Accuracy del candidato (si no se pasa --metrics-file)")
    parser.add_argument("--baseline-accuracy", type=float, default=0.70)
    parser.add_argument("--skip-registry", action="store_true",
                        help="No consultar el Model Registry (p.ej. en CI sin workspace)")
    parser.add_argument("--fail-on-reject", action="store_true")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    if args.metrics_file:
        candidate = json.loads(args.metrics_file.read_text())
    elif args.new_accuracy is not None:
        candidate = {"accuracy": args.new_accuracy}
    else:
        parser.error("Se requiere --metrics-file o --new-accuracy")

    production = None if args.skip_registry else get_production_metrics(args.model_name)
    result = decide(candidate, production, args.baseline_accuracy, DEFAULT_CLASS_THRESHOLDS)

    print(json.dumps(result, indent=2))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f)
        print(f"Resultado guardado en {args.output}")

    if args.fail_on_reject and not result["deploy"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
