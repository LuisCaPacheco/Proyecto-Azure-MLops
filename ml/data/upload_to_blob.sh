#!/usr/bin/env bash
# Data-prep (1/2): sube el dataset al contenedor `raw` del Storage Account.
# La depuración y el registro del Data Asset los hace run_adf_pipeline.sh.
#
# Requiere: az login. Autenticación con Azure AD (RBAC "Storage Blob Data
# Contributor"), sin connection strings en el código.
# Uso: ./upload_to_blob.sh [storage_account]
set -euo pipefail

STORAGE="${1:-stmlopslabdev001}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CSV="${SCRIPT_DIR}/enape.csv"
VERSION="${DATA_VERSION:-$(date +%Y%m%d%H%M)}"

[[ -f "$CSV" ]] || python -m ml.data.load_enape --output "$CSV"

# Copia versionada (auditoría) + `latest`, que es la que lee Data Factory
for BLOB in "enape/${VERSION}/enape.csv" "enape/latest/enape.csv"; do
  echo "Subiendo ${CSV} a ${STORAGE}/raw/${BLOB} ..."
  az storage blob upload \
    --account-name "$STORAGE" \
    --container-name raw \
    --name "$BLOB" \
    --file "$CSV" \
    --auth-mode login \
    --overwrite \
    --output none
done

echo "Listo: raw/enape/${VERSION}/enape.csv"
