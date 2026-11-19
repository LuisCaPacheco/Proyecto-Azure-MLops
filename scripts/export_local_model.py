"""Empaqueta un modelo entrenado localmente como artefacto MLflow en endpoint/model.

Es el equivalente sin Azure de `scripts/export_production_model.py`: toma el
``model.pkl`` que deja ``ml/pipeline/train.py --output`` y escribe la carpeta
que consume el contenedor (``MLmodel``, ``model.pkl``, ``input_example.json``,
``metrics.json``). Útil para construir la imagen localmente y para los tests
del endpoint antes de tener un Model Registry.

Uso:
    python -m ml.pipeline.train --skip-register --output outputs/model \
        --metrics-output outputs/metrics_enape.json
    python scripts/export_local_model.py --model outputs/model/model.pkl \
        --metrics outputs/metrics_enape.json
"""

import argparse
import json
import shutil
from pathlib import Path

import joblib
import mlflow.sklearn
import pandas as pd
from mlflow.models import infer_signature

from ml.data.load_enape import CLASSES, FEATURES
from ml.pipeline.modeling import MODEL_FEATURES

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "endpoint" / "model" / "enape-abandono"
DEFAULT_MODEL = ROOT / "outputs" / "model" / "model.pkl"
DEFAULT_METRICS = ROOT / "outputs" / "metrics_enape.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta el modelo local a endpoint/model")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--dest", type=Path, default=DEST)
    args = parser.parse_args()

    if not args.model.is_file():
        raise SystemExit(f"No existe {args.model}. Entrena antes con ml/pipeline/train.py --output")
    model = joblib.load(args.model)

    # Ejemplo de entrada con las features que usa el modelo. El contrato
    # público completo (18 columnas) está en endpoint/examples/.
    example = pd.read_csv(ROOT / "ml" / "data" / "enape.csv")[FEATURES].head(2)
    signature = infer_signature(example[MODEL_FEATURES], model.predict(example[MODEL_FEATURES]))

    shutil.rmtree(args.dest, ignore_errors=True)
    args.dest.mkdir(parents=True, exist_ok=True)
    mlflow.sklearn.save_model(
        model,
        str(args.dest),
        signature=signature,
        input_example=example[MODEL_FEATURES],
        metadata={"classes": CLASSES},
        serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
    )

    if args.metrics.is_file():
        shutil.copy(args.metrics, args.dest / "metrics.json")
        metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
        print(
            f"ROC-AUC={metrics['roc_auc']:.4f} PR-AUC={metrics['pr_auc']:.4f} "
            f"accuracy={metrics['accuracy']:.4f}"
        )
    # El endpoint informa `model_version`; en local es siempre v1.
    (args.dest / "registered_model_meta").write_text(
        "model_name: enape-abandono\nmodel_version: 1\n", encoding="utf-8"
    )
    print(f"Modelo exportado a {args.dest}")


if __name__ == "__main__":
    main()
