#!/usr/bin/env bash
# Crea el compute cluster de entrenamiento sobre el ML Workspace
# usando el Azure ML CLI v2. Requiere: az login + az account set
# Uso: ./create_compute_cluster.sh <workspace> <resource_group> <subscription_id> [max_nodos] [tier]
#   max_nodos: 1 por defecto (un entrenamiento a la vez; evita problemas de cuota de vCPU)
#   tier:      dedicated (USD 0.293/h) o low_priority (≈ USD 0.06/h, puede ser interrumpido)
set -euo pipefail

WORKSPACE="${1:?Falta nombre del workspace}"
RG="${2:?Falta resource group}"
SUB_ID="${3:?Falta subscription id}"
MAX_NODES="${4:-1}"
TIER="${5:-dedicated}"

az account set --subscription "$SUB_ID"
az ml compute create \
  --name cpu-cluster \
  --size Standard_DS3_v2 \
  --min-instances 0 \
  --max-instances "$MAX_NODES" \
  --tier "$TIER" \
  --idle-time-before-scale-down 120 \
  --type AmlCompute \
  --workspace-name "$WORKSPACE" \
  --resource-group "$RG"

echo "Compute cluster 'cpu-cluster' creado (0-${MAX_NODES} nodos, ${TIER})."
