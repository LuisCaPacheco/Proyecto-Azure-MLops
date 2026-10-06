"""Entrenamiento del modelo de deserción universitaria con MLflow.

Ejecutable como Azure ML job (entrenamiento en el compute cluster) o
localmente. Registra en MLflow parámetros, métricas globales y por clase,
matriz de confusión, importancia de variables y el perfil de referencia
para data drift; luego registra el modelo en el Model Registry.

Uso local (tracking en ./mlruns.db):
    python -m ml.pipeline.train --data ml/data/dropout.csv \
        --tracking-uri sqlite:///mlruns.db

La lógica pura de entrenamiento vive en `modeling.py` para facilitar los
tests; aquí se orquesta el tracking con MLflow y el registro en el
Model Registry con política de promoción (Staging → Production).
"""

import argparse
import json
import tempfile
from pathlib import Path

import mlflow
import mlflow.sklearn
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient

from ml.pipeline.modeling import (
    CLASSES,
    DEFAULT_CLASS_THRESHOLDS,
    check_class_thresholds,
    evaluate_detailed,
    feature_importance,
    load_data,
    reference_profile,
    save_model,
    split_data,
    train_model,
)
from ml.pipeline.reporting import plot_confusion_matrix, plot_feature_importance


def register_model(
    model_uri: str,
    model_name: str,
    accuracy: float,
    baseline: float,
    class_failures: list[str],
) -> dict:
    """Registra el modelo en el Model Registry y aplica promoción (Staging/Production).

    Se promueve a Production solo si supera el baseline global Y los umbrales
    de recall por clase. La versión anterior en Production pasa a Archived.
    """
    client = MlflowClient()
    result = mlflow.register_model(model_uri=model_uri, name=model_name)
    version = result.version

    client.transition_model_version_stage(name=model_name, version=version, stage="Staging")

    promote = accuracy >= baseline and not class_failures
    if promote:
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
        client.transition_model_version_stage(name=model_name, version=version, stage="Production")
        # Alias equivalente para backends MLflow sin stages (MLflow 3.x)
        try:
            client.set_registered_model_alias(model_name, "production", version)
        except Exception:
            pass
        print(f"Modelo {model_name} v{version} promovido a Production (acc={accuracy:.4f})")
    else:
        reasons = [f"acc={accuracy:.4f} < baseline={baseline:.4f}"] if accuracy < baseline else []
        reasons += class_failures
        print(f"Modelo {model_name} v{version} NO promovido: {'; '.join(reasons)}")

    return {"model_name": model_name, "version": str(version), "promoted": promote}


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrenamiento del modelo de deserción con MLflow")
    parser.add_argument("--data", type=Path, default=Path(__file__).parent.parent / "data/dropout.csv")
    parser.add_argument("--model-name", default="dropout-classifier")
    parser.add_argument("--n-estimators", type=int, default=300)
    parser.add_argument("--max-depth", type=int, default=10, help="0 = sin límite")
    parser.add_argument("--min-samples-leaf", type=int, default=3)
    parser.add_argument("--class-weight", default="balanced_subsample", help="'none' para desactivar")
    parser.add_argument("--baseline-accuracy", type=float, default=0.70)
    parser.add_argument("--experiment", default=None, help="Nombre del experimento (solo local)")
    parser.add_argument("--tracking-uri", default=None, help="Solo local; en Azure ML se toma del job")
    parser.add_argument("--skip-register", action="store_true", help="No registrar (CI / pruebas)")
    parser.add_argument("--output", type=Path, default=None, help="Carpeta para guardar model.pkl")
    parser.add_argument("--metrics-output", type=Path, default=None, help="JSON con métricas y versión")
    args = parser.parse_args()

    if args.tracking_uri:
        mlflow.set_tracking_uri(args.tracking_uri)
    if args.experiment:
        mlflow.set_experiment(args.experiment)

    max_depth = args.max_depth or None
    class_weight = None if args.class_weight.lower() == "none" else args.class_weight

    data = load_data(args.data)
    X_train, X_test, y_train, y_test = split_data(data)

    # autolog registra params/métricas de sklearn; el modelo lo logueamos nosotros
    # (con firma y ejemplo de entrada) para evitar el conflicto de artefactos `model/`.
    mlflow.sklearn.autolog(log_models=False)

    with mlflow.start_run() as run:
        mlflow.log_params(
            {
                "dataset": "uci-student-dropout",
                "n_rows": len(data),
                "n_features": X_train.shape[1],
                "model_type": "RandomForestClassifier",
                "cfg_n_estimators": args.n_estimators,
                "cfg_max_depth": max_depth,
                "cfg_min_samples_leaf": args.min_samples_leaf,
                "cfg_class_weight": class_weight,
            }
        )

        model = train_model(
            X_train, y_train, args.n_estimators, max_depth, args.min_samples_leaf, class_weight
        )
        report = evaluate_detailed(model, X_test, y_test)
        acc = report["accuracy"]

        mlflow.log_metric("accuracy", acc)
        mlflow.log_metric("f1_macro", report["f1_macro"])
        for name, m in report["per_class"].items():
            for metric in ("precision", "recall", "f1"):
                mlflow.log_metric(f"{metric}_{name}", m[metric])

        class_failures = check_class_thresholds(report)
        mlflow.set_tag("class_thresholds_ok", str(not class_failures))

        print(f"Accuracy test: {acc:.4f} | F1 macro: {report['f1_macro']:.4f}")
        for name, m in report["per_class"].items():
            print(f"  {name:<9} precision={m['precision']:.3f} recall={m['recall']:.3f} f1={m['f1']:.3f}")

        importances = feature_importance(model)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "metrics.json").write_text(json.dumps(report, indent=2))
            (tmp / "feature_importance.json").write_text(json.dumps(importances, indent=2))
            (tmp / "reference_profile.json").write_text(json.dumps(reference_profile(X_train)))
            (tmp / "class_thresholds.json").write_text(json.dumps(DEFAULT_CLASS_THRESHOLDS, indent=2))
            plot_confusion_matrix(report["confusion_matrix"], tmp / "confusion_matrix.png")
            plot_feature_importance(importances, tmp / "feature_importance.png")
            mlflow.log_artifacts(str(tmp), artifact_path="evaluation")

        signature = infer_signature(X_test, model.predict(X_test))
        # cloudpickle: formato común a MLflow 2.x (cluster Azure ML) y 3.x (local),
        # y el que lee el endpoint sin depender de MLflow.
        model_info = mlflow.sklearn.log_model(
            model,
            artifact_path="model",
            serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
            signature=signature,
            input_example=X_test.iloc[:2],
            metadata={"classes": CLASSES},
        )

        registry = None
        if not args.skip_register:
            registry = register_model(
                model_info.model_uri, args.model_name, acc, args.baseline_accuracy, class_failures
            )

        if args.output:
            save_model(model, args.output)
            print(f"Modelo local guardado en {args.output / 'model.pkl'}")

        if args.metrics_output:
            args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
            args.metrics_output.write_text(
                json.dumps(
                    {
                        "run_id": run.info.run_id,
                        "model_uri": model_info.model_uri,
                        "accuracy": acc,
                        "f1_macro": report["f1_macro"],
                        "per_class": report["per_class"],
                        "class_failures": class_failures,
                        "registry": registry,
                    },
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()
