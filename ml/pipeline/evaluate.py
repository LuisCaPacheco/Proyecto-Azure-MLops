"""Evaluación del modelo: compara el candidato vs el modelo en producción.

Este script lee las métricas del run de entrenamiento (el JSON que genera
`train.py --metrics-output`) y las compara con el modelo actualmente en
Producción del Model Registry, decidiendo si el nuevo candidato debe
desplegarse.

Reglas (prueba de regresión del modelo):
1. **PR-AUC >= 0.35** en el candidato: con 6,5 % de positivos la accuracy es
   engañosa; PR-AUC mide directamente la calidad sobre la clase Abandona.
2. **Recall de Abandona >= 0.60** (umbral de `DEFAULT_CLASS_THRESHOLDS`):
   no se acepta un modelo que deje de detectar abandonos para verse "mejor".
3. El registro debe contener una versión en Production con PR-AUC; sin esa
   referencia no se autoriza el despliegue.
4. El PR-AUC del candidato no puede retroceder más de 0.005 respecto a Production.
5. El candidato no puede ser la misma versión que ya está en Production.

El candidato llega en Staging (`train.py` no promueve); si el gate aprueba,
el pipeline despliega y luego `promote.py` lo pasa a Production.

Salida: imprime un JSON que la etapa 'Evaluate' del pipeline CI/CD
interpreta como condición de despliegue (exit code 1 con --fail-on-reject).
"""

import argparse
import json
import os
import sys
from pathlib import Path

from mlflow.tracking import MlflowClient

from ml.pipeline.modeling import CLASSES, DEFAULT_CLASS_THRESHOLDS

MIN_PR_AUC = 0.35
MIN_RECALL_ABANDONA = 0.60
TOLERANCE = 0.005
POSITIVE_CLASS = "Abandona"


def get_production_metrics(model_name: str) -> dict | None:
    """Devuelve las métricas del run del modelo en Production, o None si no existe.

    Usa el API de stages (MLflow 2.x / Azure ML) y, si no hay resultado,
    el alias `production` (MLflow 3.x).
    """
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        raise RuntimeError(
            "MLFLOW_TRACKING_URI no está definido: no se puede comparar el candidato "
            "contra el modelo Production. No se permite desplegar sin el registry."
        )
    client = MlflowClient(tracking_uri=tracking_uri)
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

    if version is None or not getattr(version, "run_id", None):
        return None
    try:
        metrics = client.get_run(version.run_id).data.metrics
    except Exception as exc:
        raise RuntimeError(
            f"No se pudieron leer métricas de Production ({model_name} v{version.version}); "
            "no se permite desplegar sin la referencia completa."
        ) from exc
    return {"version": str(version.version), **metrics}


def _production_recall(production: dict | None) -> float | None:
    """Recall de Abandona del modelo en Production (métricas planas de MLflow)."""
    if not production:
        return None
    if f"recall_{POSITIVE_CLASS}" in production:
        return float(production[f"recall_{POSITIVE_CLASS}"])
    per_class = production.get("per_class") or {}
    value = (per_class.get(POSITIVE_CLASS) or {}).get("recall")
    return None if value is None else float(value)


def decide(
    candidate: dict,
    production: dict | None = None,
    min_pr_auc: float = MIN_PR_AUC,
    min_recall: float = MIN_RECALL_ABANDONA,
    thresholds: dict | None = None,
    tolerance: float = TOLERANCE,
) -> dict:
    """Aplica las reglas de despliegue y devuelve el detalle de la decisión."""
    thresholds = DEFAULT_CLASS_THRESHOLDS if thresholds is None else thresholds
    per_class = candidate.get("per_class") or {}

    recall_failures = []
    for name, minimum in thresholds.items():
        value = (per_class.get(name) or {}).get("recall")
        if value is None:
            recall_failures.append(f"{name}: sin recall en las métricas del candidato")
        elif value < minimum:
            recall_failures.append(f"{name}: recall {value:.3f} < {minimum:.2f}")

    new_pr_auc = candidate.get("pr_auc")
    if new_pr_auc is None:
        recall_failures.append("pr_auc: sin PR-AUC en las métricas del candidato")
    recall = (per_class.get(POSITIVE_CLASS) or {}).get("recall")

    production_pr_auc = production.get("pr_auc") if production else None
    production_recall = _production_recall(production)

    # El candidato no puede ser la misma versión que ya está en Production:
    # compararlo consigo mismo aprobaría siempre.
    candidate_version = (candidate.get("registry") or {}).get("version")
    same_version = (
        bool(production)
        and candidate_version is not None
        and str(candidate_version) == str(production.get("version"))
    )

    meets_pr_auc = new_pr_auc is not None and float(new_pr_auc) >= min_pr_auc
    meets_recall = recall is not None and float(recall) >= min_recall and not recall_failures
    beats_production = (
        production is not None
        and production_pr_auc is not None
        and new_pr_auc is not None
        and float(new_pr_auc) >= float(production_pr_auc) - tolerance
    )

    return {
        "candidate_version": candidate_version,
        "new_pr_auc": None if new_pr_auc is None else float(new_pr_auc),
        "new_recall_abandona": None if recall is None else float(recall),
        "production_version": production.get("version") if production else None,
        "production_pr_auc": None if production_pr_auc is None else float(production_pr_auc),
        "production_recall_abandona": production_recall,
        "min_pr_auc": min_pr_auc,
        "min_recall_abandona": min_recall,
        "tolerance": tolerance,
        "meets_pr_auc": meets_pr_auc,
        "meets_recall_abandona": meets_recall,
        "beats_production_pr_auc": beats_production,
        "same_version_as_production": same_version,
        "recall_failures": recall_failures,
        "deploy": meets_pr_auc and meets_recall and beats_production and not same_version,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalúa candidato vs producción")
    parser.add_argument("--model-name", default="enape-abandono")
    parser.add_argument(
        "--metrics-file",
        type=Path,
        required=True,
        help="JSON de train.py --metrics-output (pr_auc, per_class, registry)",
    )
    parser.add_argument("--min-pr-auc", type=float, default=MIN_PR_AUC)
    parser.add_argument("--min-recall", type=float, default=MIN_RECALL_ABANDONA)
    parser.add_argument(
        "--skip-registry",
        action="store_true",
        help="No consultar el Model Registry (p.ej. en CI sin workspace)",
    )
    parser.add_argument("--fail-on-reject", action="store_true")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    candidate = json.loads(args.metrics_file.read_text(encoding="utf-8"))
    production = (
        None
        if args.skip_registry
        else get_production_metrics(args.model_name)
    )
    result = decide(
        candidate,
        production,
        min_pr_auc=args.min_pr_auc,
        min_recall=args.min_recall,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        print(f"Resultado guardado en {args.output}")

    if args.fail_on_reject and not result["deploy"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
