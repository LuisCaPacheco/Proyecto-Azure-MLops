"""Evaluación del modelo: compara nuevas métricas vs modelo en producción.

Este script lee el accuracy reportado por el run de entrenamiento y lo
compara con la métrica del modelo actualmente en Producción del Model
Registry, decidiendo si el nuevo candidato debe desplegarse.

Salida: imprime un JSON/booleano que la etapa 'evaluate' del pipeline
CI/CD interpreta como condición de despliegue.
"""

import argparse
import json

import mlflow
from mlflow.tracking import MlflowClient


def get_production_accuracy(model_name: str) -> float | None:
    """Devuelve el accuracy del modelo en Production, o None si no existe.

    Usa el API de stages (MLflow 2.x / Azure ML). Si el backend no lo
    soporta (p.ej. MLflow 3.x), se devuelve None y el candidato se
    trata sin competencia de producción.
    """
    client = MlflowClient()
    try:
        versions = client.search_model_versions(f"name='{model_name}' and stage='Production'")
    except Exception:
        return None
    if not versions:
        return None
    prod_version = versions[0]

    run = client.get_run(prod_version.run_id)
    return run.data.metrics.get("accuracy")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalúa candidato vs producción")
    parser.add_argument("--model-name", default="iris-classifier")
    parser.add_argument("--new-accuracy", type=float, required=True,
                        help="Accuracy del modelo candidato (nuevo run)")
    parser.add_argument("--baseline-accuracy", type=float, default=0.75)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    prod_acc = get_production_accuracy(args.model_name)
    new_acc = args.new_accuracy

    # Regla de despliegue: superar baseline Y superar (o igualar) producción
    beats_baseline = new_acc >= args.baseline_accuracy
    beats_prod = prod_acc is None or new_acc >= prod_acc
    deploy = beats_baseline and beats_prod

    result = {
        "new_accuracy": new_acc,
        "production_accuracy": prod_acc,
        "baseline_accuracy": args.baseline_accuracy,
        "beats_baseline": beats_baseline,
        "beats_prod": beats_prod,
        "deploy": deploy,
    }

    print(json.dumps(result, indent=2))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f)
        print(f"Resultado guardado en {args.output}")


if __name__ == "__main__":
    main()
