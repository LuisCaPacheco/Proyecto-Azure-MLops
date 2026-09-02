#!/usr/bin/env bash
# Descarga el modelo 'iris-classifier' (Producción) del Model Registry de
# Azure ML a la carpeta local ./model, que luego se empaqueta en la imagen
# Docker del endpoint.
#
# Requiere: az login + extensión 'ml' instalada.
# Uso: ./download_model.sh [workspace] [resource_group] [version]
set -euo pipefail

WORKSPACE="${1:-mlw-mlopsproj-dev}"
RG="${2:-rg-mlopsproj-dev}"
VERSION="${3:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${SCRIPT_DIR}/model"

# Si no se pasa versión, se toma la última (más reciente) del Model Registry
if [[ -z "$VERSION" ]]; then
  VERSION=$(az ml model list --name iris-classifier \
    --query "[0].version" \
    --workspace-name "$WORKSPACE" --resource-group "$RG" -o tsv)
fi

echo "Descargando modelo 'iris-classifier' v${VERSION} desde ${WORKSPACE} ..."

az ml model download \
  --name iris-classifier \
  --version "$VERSION" \
  --download-path "$TARGET_DIR" \
  --workspace-name "$WORKSPACE" \
  --resource-group "$RG"

echo "Modelo descargado en ${TARGET_DIR}:"
ls -la "${TARGET_DIR}"
