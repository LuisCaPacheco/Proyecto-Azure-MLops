"""Promoción Staging → Production en el Model Registry.

Es el último paso del CD: se ejecuta solo cuando el gate (`evaluate.py`)
aprobó al candidato y el despliegue pasó el smoke test, de modo que la
versión marcada como Production es siempre la que está sirviendo el endpoint.
La versión que estaba en Production pasa a Archived.

Uso:
    python -m ml.pipeline.promote --version 3
    python -m ml.pipeline.promote --evaluation outputs/eval.json   # lee la decisión del gate
"""

import argparse
import json
import sys
from pathlib import Path

from mlflow.tracking import MlflowClient


def promote(client, model_name: str, version: str) -> dict:
    """Archiva las versiones en Production y promueve `version`.

    Marca además el tag `stage` y el alias `production`: son el respaldo para
    backends del registry donde los stages de MLflow no están disponibles.
    """
    version = str(version)
    archived = []
    try:
        current = client.search_model_versions(f"name='{model_name}' and stage='Production'")
    except Exception:
        current = []
    for mv in current:
        if str(mv.version) == version:
            continue
        client.transition_model_version_stage(name=model_name, version=mv.version, stage="Archived")
        _best_effort(client.set_model_version_tag, model_name, mv.version, "stage", "Archived")
        archived.append(str(mv.version))

    client.transition_model_version_stage(name=model_name, version=version, stage="Production")
    _best_effort(client.set_model_version_tag, model_name, version, "stage", "Production")
    _best_effort(client.set_registered_model_alias, model_name, "production", version)
    return {"model_name": model_name, "promoted": version, "archived": archived}


def _best_effort(fn, *args) -> None:
    try:
        fn(*args)
    except Exception as exc:  # el stage ya quedó aplicado; esto es solo metadato extra
        print(f"Aviso: {fn.__name__} no disponible en este registry ({exc})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Promueve una versión del modelo a Production")
    parser.add_argument("--model-name", default="enape-abandono")
    parser.add_argument("--version", default=None, help="Versión del Model Registry a promover")
    parser.add_argument("--evaluation", type=Path, default=None,
                        help="JSON de evaluate.py; promueve candidate_version solo si deploy=true")
    args = parser.parse_args()

    version = args.version
    if args.evaluation:
        decision = json.loads(args.evaluation.read_text())
        if not decision.get("deploy"):
            print("El gate rechazó al candidato: no se promueve.")
            sys.exit(1)
        version = version or decision.get("candidate_version")
    if not version:
        parser.error("Se requiere --version o un --evaluation con candidate_version")

    result = promote(MlflowClient(), args.model_name, version)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
