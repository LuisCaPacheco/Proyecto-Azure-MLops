#!/usr/bin/env bash
# Crea (una sola vez) la cuenta de almacenamiento donde vive el estado remoto
# de Terraform. Va en un resource group aparte para que `terraform destroy`
# de la plataforma no borre su propio estado.
#
# Requiere: az login.
# Uso: ./bootstrap_tfstate.sh [storage_account] [resource_group] [location]
set -euo pipefail

STORAGE="${1:-sttfstatemlopslab}"
RG="${2:-rg-tfstate-mlops}"
LOCATION="${3:-centralus}"
CONTAINER="tfstate"

az group create -n "$RG" -l "$LOCATION" -o none
az storage account create -n "$STORAGE" -g "$RG" -l "$LOCATION" \
  --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 \
  --allow-blob-public-access false -o none
# Versionado de blobs: permite recuperar un estado anterior
az storage account blob-service-properties update \
  --account-name "$STORAGE" -g "$RG" --enable-versioning true -o none

# Acceso al estado con Azure AD (use_azuread_auth = true), sin claves
USER_ID=$(az ad signed-in-user show --query id -o tsv)
SCOPE=$(az storage account show -n "$STORAGE" -g "$RG" --query id -o tsv)
az role assignment create --assignee "$USER_ID" \
  --role "Storage Blob Data Contributor" --scope "$SCOPE" -o none

az storage container create -n "$CONTAINER" --account-name "$STORAGE" --auth-mode login -o none

echo "Estado remoto listo: ${STORAGE}/${CONTAINER}"
echo "Siguiente paso: cd terraform && cp backend.hcl.example backend.hcl && terraform init -backend-config=backend.hcl -migrate-state"
