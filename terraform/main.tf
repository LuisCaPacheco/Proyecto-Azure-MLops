locals {
  # Prefijo global: ej. "mlopsproj-dev"
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
  name                       = "kv-${local.prefix}"
  resource_group_name        = azurerm_resource_group.main.name
  location                   = azurerm_resource_group.main.location
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  purge_protection_enabled   = true
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
  name                          = "mlw-${local.prefix}"
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

# ---------------------------------------------------------------------------
# Kubernetes inference deployment (AKS, no usado por defecto) - comentado
# El endpoint de inferencia se despliega como ACI (ver más abajo).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Azure Container Instances (ACI) para inferencia
# Imagen: azurerm_container_registry.main.name + endpoint:latest
# Se despliega en la fase 5-6 una vez la imagen este en ACR.
# Descomenta/ajusta cuando tengas la imagen publicada.
# ---------------------------------------------------------------------------
# resource "azurerm_container_group" "inference" {
#   name                = "aci-${local.prefix}-inference"
#   location            = azurerm_resource_group.main.location
#   resource_group_name = azurerm_resource_group.main.name
#   os_type             = "Linux"
#   ip_address_type     = "Public"
#   dns_name_label      = "mlops-${local.prefix}"
#   restart_policy      = "Always"
#   tags                = local.tags
#
#   identity {
#     type = "SystemAssigned"
#   }
#
#   container {
#     name   = "endpoint"
#     image  = "${azurerm_container_registry.main.login_server}/endpoint:latest"
#     cpu    = var.aci_cpu
#     memory = var.aci_memory
#
#     ports {
#       port     = 8000
#       protocol = "TCP"
#     }
#   }
#
#   image_registry_credential {
#     server   = azurerm_container_registry.main.login_server
#     username = azurerm_container_registry.main.admin_username
#     password = azurerm_container_registry.main.admin_password
#   }
# }

data "azurerm_client_config" "current" {}
