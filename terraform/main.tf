locals {
  # Prefijo global: ej. "mlopslab-dev"
  prefix = "${var.project_name}-${var.environment}"

  tags = {
    Project     = "P07-MLOps-Azure"
    Environment = var.environment
    Owner       = "equipo-mlops"
  }
}

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------
resource "azurerm_resource_group" "main" {
  name     = "rg-${local.prefix}"
  location = var.location
  tags     = local.tags
}

# ---------------------------------------------------------------------------
# Storage Account (datastore para datos raw / procesados)
# ---------------------------------------------------------------------------
resource "azurerm_storage_account" "main" {
  name                            = "st${var.project_name}${var.environment}001"
  resource_group_name             = azurerm_resource_group.main.name
  location                        = azurerm_resource_group.main.location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_storage_container" "raw" {
  name                  = "raw"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "processed" {
  name                  = "processed"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# ---------------------------------------------------------------------------
# Key Vault (secretos: credenciales, conexiones, modelos)
# ---------------------------------------------------------------------------
resource "azurerm_key_vault" "main" {
  name                = "kv-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"
  # En dev se deja sin purge protection para poder destruir y recrear el
  # proyecto (el nombre `kv-...` queda reservado 7 días si solo se soft-borra).
  # En producción debe ir `true`.
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  tags                       = local.tags
}

# ---------------------------------------------------------------------------
# Container Registry (ACR) para imágenes Docker del endpoint
# ---------------------------------------------------------------------------
resource "azurerm_container_registry" "main" {
  name                = "acr${var.project_name}${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Basic"
  admin_enabled       = true
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Log Analytics Workspace (centralizar logs + monitoreo)
# ---------------------------------------------------------------------------
resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Application Insights (telemetría del ML Workspace + monitoreo)
# ---------------------------------------------------------------------------
resource "azurerm_application_insights" "main" {
  name                = "appi-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# Azure Machine Learning Workspace
# ---------------------------------------------------------------------------
resource "azurerm_machine_learning_workspace" "main" {
  name                          = "mlw-${local.prefix}-v2"
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  friendly_name                 = "Plataforma MLOps P07"
  description                   = "Workspace MLOps para entrenamiento e inferencia de modelos"
  application_insights_id       = azurerm_application_insights.main.id
  key_vault_id                  = azurerm_key_vault.main.id
  storage_account_id            = azurerm_storage_account.main.id
  container_registry_id         = azurerm_container_registry.main.id
  sku_name                      = "Basic"
  high_business_impact          = false
  public_network_access_enabled = true
  identity {
    type = "SystemAssigned"
  }
  tags = local.tags
}

# Azure ML construye la imagen del environment de cada job y la publica en el
# ACR del workspace. Sin AcrPush el build nunca arranca y el job se queda en
# "Preparing" indefinidamente (no reporta error). AcrPull cubre la descarga.
resource "azurerm_role_assignment" "workspace_acr_push" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPush"
  principal_id         = azurerm_machine_learning_workspace.main.identity[0].principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "workspace_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_machine_learning_workspace.main.identity[0].principal_id
  principal_type       = "ServicePrincipal"
}

# ---------------------------------------------------------------------------
# Kubernetes inference deployment (AKS, no usado por defecto) - comentado
# El endpoint de inferencia se despliega como ACI (ver más abajo).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Azure Container Instances (ACI) para inferencia, API key en Key Vault,
# RBAC y alertas de Azure Monitor: ver inference.tf (Etapas 3 y 4).
# ---------------------------------------------------------------------------

data "azurerm_client_config" "current" {}
