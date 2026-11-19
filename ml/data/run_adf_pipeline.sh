#!/usr/bin/env bash
# Data-prep (2/2): ejecuta el pipeline de Azure Data Factory que depura
# raw -> processed, espera el resultado y registra la salida como Data Asset
# versionado `enape-abandono` en Azure ML (lo que consume el entrenamiento).
#
#   raw/enape/latest/enape.csv ──ADF pl_clean_enape──► processed/enape/latest/enape.csv
#                                                  └─► raw/rejected/enape/rejected.csv
#
# Requiere: az login + extensiones `datafactory` y `ml`.
# Uso: ./run_adf_pipeline.sh [data_factory] [storage_account] [workspace] [resource_group]
set -euo pipefail

FACTORY="${1:-adf-mlopslab-dev}"
STORAGE="${2:-stmlopslabdev001}"
WORKSPACE="${3:-mlw-mlopslab-dev}"
RG="${4:-rg-mlopslab-dev}"
PIPELINE="pl_clean_enape"
DATASTORE="processed_data"
VERSION="${DATA_VERSION:-$(date +%Y%m%d%H%M)}"
TIMEOUT_MIN="${ADF_TIMEOUT_MIN:-30}"

RUN_ID=$(az datafactory pipeline create-run --factory-name "$FACTORY" -g "$RG" \
  --name "$PIPELINE" --query runId -o tsv)
echo "ADF ${PIPELINE}: run ${RUN_ID}"

# El cluster Spark del Data Flow tarda unos minutos en arrancar
STATUS="Queued"
for _ in $(seq 1 $((TIMEOUT_MIN * 4))); do
  STATUS=$(az datafactory pipeline-run show --factory-name "$FACTORY" -g "$RG" \
    --run-id "$RUN_ID" --query status -o tsv)
  echo "  estado: ${STATUS}"
  case "$STATUS" in
    Succeeded|Failed|Cancelled) break ;;
  esac
  sleep 15
done
if [[ "$STATUS" != "Succeeded" ]]; then
  az datafactory pipeline-run show --factory-name "$FACTORY" -g "$RG" \
    --run-id "$RUN_ID" --query message -o tsv || true
  echo "El pipeline de ADF terminó en ${STATUS}" >&2
  exit 1
fi

# Filas descartadas por el Data Flow (informativo)
REJECTED=$(az storage blob show --account-name "$STORAGE" --container-name raw \
  --name rejected/enape/rejected.csv --auth-mode login \
  --query properties.contentLength -o tsv 2>/dev/null || echo 0)
echo "Archivo de filas rechazadas: ${REJECTED} bytes (raw/rejected/enape/rejected.csv)"

# Copia inmutable de la salida: el Data Asset no debe apuntar a `latest`.
# La copia de blobs es asíncrona: hay que esperar a que termine antes de
# registrar el Data Asset o Azure ML apuntaría a un blob que aún no existe.
az storage blob copy start --account-name "$STORAGE" --auth-mode login \
  --source-container processed --source-blob enape/latest/enape.csv \
  --destination-container processed --destination-blob "enape/${VERSION}/enape.csv" \
  --output none

echo "Esperando a que termine la copia del blob versionado..."
COPY_STATUS="pending"
for _ in $(seq 1 60); do
  COPY_STATUS=$(az storage blob show --account-name "$STORAGE" --auth-mode login \
    --container-name processed --name "enape/${VERSION}/enape.csv" \
    --query "properties.copy.status" -o tsv 2>/dev/null || echo "pending")
  case "$COPY_STATUS" in
    success) break ;;
    failed|aborted) break ;;
  esac
  sleep 5
done
if [[ "$COPY_STATUS" != "success" ]]; then
  echo "La copia del blob terminó en '${COPY_STATUS}' (se esperaba 'success')" >&2
  exit 1
fi

echo "Registrando Data Asset 'enape-abandono' v${VERSION} ..."
az ml data create \
  --name enape-abandono \
  --version "$VERSION" \
  --type uri_file \
  --path "azureml://datastores/${DATASTORE}/paths/enape/${VERSION}/enape.csv" \
  --description "ENAPE 2021 (INEGI) depurado por Azure Data Factory (${PIPELINE}, run ${RUN_ID})" \
  --workspace-name "$WORKSPACE" \
  --resource-group "$RG"

echo "Listo: azureml:enape-abandono:${VERSION}"
