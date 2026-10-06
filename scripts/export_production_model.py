"""Exporta la versión en Production del Model Registry a endpoint/model/.

Equivalente local de `endpoint/download_model.sh` (que usa `az ml model
download` contra el workspace). Además deja en outputs/evaluation los
artefactos de evaluación del run (métricas, gráficas, perfil de drift).
"""

import json
import shutil
from pathlib import Path

import mlflow
from mlflow.tracking import MlflowClient

MODEL_NAME = "dropout-classifier"
ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "endpoint" / "model" / MODEL_NAME


def main() -> None:
    client = MlflowClient()
    prod = client.get_latest_versions(MODEL_NAME, stages=["Production"])
    if not prod:
        raise SystemExit(f"No hay versión de {MODEL_NAME} en Production")
    version = prod[0]

    shutil.rmtree(DEST, ignore_errors=True)
    mlflow.artifacts.download_artifacts(f"models:/{MODEL_NAME}/Production", dst_path=str(DEST))

    outputs = ROOT / "outputs"
    shutil.rmtree(outputs / "evaluation", ignore_errors=True)
    mlflow.artifacts.download_artifacts(run_id=version.run_id, artifact_path="evaluation", dst_path=str(outputs))
    shutil.copy(outputs / "evaluation" / "metrics.json", DEST / "metrics.json")

    metrics = json.loads((DEST / "metrics.json").read_text())
    print(f"{MODEL_NAME} v{version.version} (run {version.run_id}) -> {DEST}")
    print(f"accuracy={metrics['accuracy']:.4f} f1_macro={metrics['f1_macro']:.4f}")


if __name__ == "__main__":
    main()
