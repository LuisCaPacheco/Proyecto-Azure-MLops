"""Script de entrenamiento del modelo Iris con MLflow autologging.

Ejecutable como Azure ML job (entrenamiento en el compute cluster) o
localmente. Registra en el Model Registry los artefactos del modelo.

Uso local:
    python train.py --data ../data/iris.csv --model-name iris-classifier \
        --n-estimators 100 --max-depth 4

La lógica pura de entrenamiento vive en `modeling.py` para facilitar los
tests; aquí se orquesta el tracking con MLflow y el registro en el
Model Registry con política de promoción (Staging → Production).
"""

import argparse
from pathlib import Path

import mlflow
import mlflow.sklearn
from mlflow.tracking import MlflowClient

from ml.pipeline.modeling import (
    TARGET,
    evaluate_model,
    load_data,
    save_model,
    split_data,
    train_model,
)


def register_model(run_id: str, model_name: str, accuracy: float, baseline: float) -> None:
    """Registra el modelo en el Model Registry y aplica promoción (Staging/Production)."""
    client = MlflowClient()
    result = mlflow.register_model(
        model_uri=f"runs:/{run_id}/model",
        name=model_name,
    )
    version = result.version

    # Política de promoción: Staging → Production si accuracy >= baseline
    client.transition_model_version_stage(
        name=model_name, version=version, stage="Staging"
    )

    if accuracy >= baseline:
        try:
            prod_versions = client.search_model_versions(
                f"name='{model_name}' and stage='Production'"
            )
            for pv in prod_versions:
                client.transition_model_version_stage(
                    name=model_name, version=pv.version, stage="Archived"
                )
        except Exception:
            pass
        client.transition_model_version_stage(
            name=model_name, version=version, stage="Production"
        )
        print(f"Modelo {model_name} v{version} promovido a Production (acc={accuracy:.4f})")
    else:
        print(
            f"Modelo {model_name} v{version} NO promovido: "
            f"acc={accuracy:.4f} < baseline={baseline:.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrenamiento Iris con MLflow")
    parser.add_argument("--data", type=Path, default=Path(__file__).parent.parent / "data/iris.csv")
    parser.add_argument("--model-name", default="iris-classifier")
    parser.add_argument("--n-estimators", type=int, default=100)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--baseline-accuracy", type=float, default=0.75)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    data = load_data(args.data)
    X_train, X_test, y_train, y_test = split_data(data)

    mlflow.sklearn.autolog()  # params, métricas, artefactos automáticos

    with mlflow.start_run() as run:
        mlflow.log_param("n_estimators", args.n_estimators)
        mlflow.log_param("max_depth", args.max_depth)
        mlflow.log_param("dataset", "iris")

        model = train_model(X_train, y_train, args.n_estimators, args.max_depth)
        acc = evaluate_model(model, X_test, y_test)
        mlflow.log_metric("accuracy", acc)
        print(f"Accuracy test: {acc:.4f}")

        # `mlflow.sklearn.autolog()` ya guarda el modelo en
        # `runs:/<run_id>/model` tras el fit, así que NO llamamos log_model
        # de nuevo (evita conflicto de artefactos en el mismo path).

        register_model(run.info.run_id, args.model_name, acc, args.baseline_accuracy)

        if args.output:
            save_model(model, args.output)
            print(f"Modelo local guardado en {args.output / 'model.pkl'}")


if __name__ == "__main__":
    main()
