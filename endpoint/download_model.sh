#!/usr/bin/env bash
# Descarga el modelo 'enape-abandono' del Model Registry de Azure ML
# (la versión indicada; sin argumento, la que está en Production) a la carpeta local ./model, que luego se empaqueta en
# la imagen Docker del endpoint.
#
# Requiere: az login + extensión 'ml' instalada.
# Uso: ./download_model.sh [workspace] [resource_group] [version]
set -euo pipefail

WORKSPACE="${1:-mlw-mlopslab-dev}"
RG="${2:-rg-mlopslab-dev}"
VERSION="${3:-}"
MODEL_NAME="enape-abandono"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${SCRIPT_DIR}/model"

# Sin versión explícita: la que tenga la etiqueta de stage Production
# (MLflow la guarda como tag 'mlflow.modelVersionStage' en Azure ML);
# si no hay ninguna, la más reciente.
if [[ -z "$VERSION" ]]; then
  VERSION=$(az ml model list --name "$MODEL_NAME" \
    --query "[?tags.\"mlflow.modelVersionStage\"=='Production' || tags.stage=='Production'] | [0].version" \
    --workspace-name "$WORKSPACE" --resource-group "$RG" -o tsv)
fi
if [[ -z "$VERSION" ]]; then
  VERSION=$(az ml model list --name "$MODEL_NAME" --query "[0].version" \
    --workspace-name "$WORKSPACE" --resource-group "$RG" -o tsv)
fi

echo "Descargando modelo '${MODEL_NAME}' v${VERSION} desde ${WORKSPACE} ..."

# Descarga limpia: evita restos de layouts anteriores (model/<nombre> vs
# model/<nombre>/model) que confundirían al endpoint.
rm -rf "${TARGET_DIR:?}"
mkdir -p "${TARGET_DIR}"
az ml model download \
  --name "$MODEL_NAME" \
  --version "$VERSION" \
  --download-path "$TARGET_DIR" \
  --workspace-name "$WORKSPACE" \
  --resource-group "$RG"

# `az ml` crea una carpeta con el nombre del modelo, pero el MLmodel puede
# quedar en la raíz o en un subdirectorio `model/`. Escribimos el metadato de
# versión junto al MLmodel, que es donde el endpoint lo busca.
MLMODEL_PATH=$(find "${TARGET_DIR}" -name MLmodel -type f | head -1)
if [[ -z "${MLMODEL_PATH}" ]]; then
  echo "No se encontró MLmodel en ${TARGET_DIR}" >&2
  exit 1
fi
MODEL_DIR=$(dirname "${MLMODEL_PATH}")

# Normaliza el layout: `az ml model download` suele crear
# model/<nombre>/model/<artefactos>. Los dejamos en model/<nombre>/ para que
# coincidan el Dockerfile, los tests y el guard de azure_up.ps1.
if [[ "$(basename "${MODEL_DIR}")" == "model" && "$(dirname "${MODEL_DIR}")" != "${TARGET_DIR}" ]]; then
  PARENT_DIR=$(dirname "${MODEL_DIR}")
  shopt -s dotglob nullglob
  mv "${MODEL_DIR}"/* "${PARENT_DIR}/"
  shopt -u dotglob nullglob
  rmdir "${MODEL_DIR}" 2>/dev/null || true
  MODEL_DIR="${PARENT_DIR}"
fi

printf 'model_name: %s\nmodel_version: %s\n' "$MODEL_NAME" "$VERSION" \
  > "${MODEL_DIR}/registered_model_meta"

echo "Modelo descargado en ${MODEL_DIR}:"
find "${MODEL_DIR}" -maxdepth 2
