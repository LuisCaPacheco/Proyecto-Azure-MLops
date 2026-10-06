#!/usr/bin/env bash
# Data-prep: sube el dataset preparado al contenedor `raw` del Storage Account
# y lo registra como Data Asset versionado en el workspace de Azure ML.
#
# Requiere: az login + extensión 'ml'. Autenticación con Azure AD (RBAC
# "Storage Blob Data Contributor"), sin connection strings en el código.
# Uso: ./upload_to_blob.sh [storage_account] [workspace] [resource_group]
set -euo pipefail

STORAGE="${1:-stmlopsprojdev001}"
WORKSPACE="${2:-mlw-mlopsproj-dev}"
RG="${3:-rg-mlopsproj-dev}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CSV="${SCRIPT_DIR}/dropout.csv"
VERSION="$(date +%Y%m%d%H%M)"

[[ -f "$CSV" ]] || python -m ml.data.load_data --output "$CSV"

echo "Subiendo ${CSV} a ${STORAGE}/raw ..."
az storage blob upload \
  --account-name "$STORAGE" \
  --container-name raw \
  --name "dropout/${VERSION}/dropout.csv" \
  --file "$CSV" \
  --auth-mode login \
  --overwrite

az storage blob upload \
  --account-name "$STORAGE" \
  --container-name raw \
  --name "dropout/latest/dropout.csv" \
  --file "$CSV" \
  --auth-mode login \
  --overwrite

echo "Registrando Data Asset 'student-dropout' v${VERSION} ..."
az ml data create \
  --name student-dropout \
  --version "$VERSION" \
  --type uri_file \
  --path "$CSV" \
  --description "UCI 697 - Predict Students' Dropout and Academic Success (preparado)" \
  --workspace-name "$WORKSPACE" \
  --resource-group "$RG"

echo "Listo: azureml:student-dropout:${VERSION}"
