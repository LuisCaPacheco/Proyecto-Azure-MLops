#!/usr/bin/env bash
# Descarga el modelo 'dropout-classifier' (versión en Production) del Model
# Registry de Azure ML a la carpeta local ./model, que luego se empaqueta en
# la imagen Docker del endpoint.
#
# Requiere: az login + extensión 'ml' instalada.
# Uso: ./download_model.sh [workspace] [resource_group] [version]
set -euo pipefail

WORKSPACE="${1:-mlw-mlopsproj-dev}"
RG="${2:-rg-mlopsproj-dev}"
VERSION="${3:-}"
MODEL_NAME="dropout-classifier"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${SCRIPT_DIR}/model"

# Sin versión explícita: la que tenga la etiqueta de stage Production
# (MLflow la guarda como tag 'mlflow.modelVersionStage' en Azure ML);
# si no hay ninguna, la más reciente.
if [[ -z "$VERSION" ]]; then
  VERSION=$(az ml model list --name "$MODEL_NAME" \
    --query "[?tags.\"mlflow.modelVersionStage\"=='Production'] | [0].version" \
    --workspace-name "$WORKSPACE" --resource-group "$RG" -o tsv)
fi
if [[ -z "$VERSION" ]]; then
  VERSION=$(az ml model list --name "$MODEL_NAME" --query "[0].version" \
    --workspace-name "$WORKSPACE" --resource-group "$RG" -o tsv)
fi

echo "Descargando modelo '${MODEL_NAME}' v${VERSION} desde ${WORKSPACE} ..."

rm -rf "${TARGET_DIR:?}/${MODEL_NAME}"
az ml model download \
  --name "$MODEL_NAME" \
  --version "$VERSION" \
  --download-path "$TARGET_DIR" \
  --workspace-name "$WORKSPACE" \
  --resource-group "$RG"

# az ml deja el modelo en model/<nombre>/model; el endpoint busca en ambas rutas
echo "Modelo descargado en ${TARGET_DIR}:"
find "${TARGET_DIR}/${MODEL_NAME}" -maxdepth 2
