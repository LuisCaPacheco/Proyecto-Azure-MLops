# ---------------------------------------------------------------------------
# Etapa 3-4: endpoint de inferencia en ACI + seguridad + monitoreo
#
# El ACI se crea solo con deploy_aci = true, una vez la imagen esté en ACR:
#   terraform apply -var="deploy_aci=true" -var="endpoint_image_tag=<tag>"
# El pipeline CI/CD también puede desplegarlo con `az container create`.
# ---------------------------------------------------------------------------

# Permisos de quien ejecuta Terraform sobre el Key Vault (para escribir el secreto)
resource "azurerm_key_vault_access_policy" "deployer" {
  key_vault_id       = azurerm_key_vault.main.id
  tenant_id          = data.azurerm_client_config.current.tenant_id
  object_id          = data.azurerm_client_config.current.object_id
  secret_permissions = ["Get", "List", "Set", "Delete", "Recover", "Purge"]
}

# Quien ejecuta Terraform puede subir datos al Storage con Azure AD
# (az storage blob upload --auth-mode login), sin usar connection strings
resource "azurerm_role_assignment" "deployer_blob" {
  scope                = azurerm_storage_account.main.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = data.azurerm_client_config.current.object_id
}

# API key del endpoint: generada aquí, guardada solo en Key Vault
resource "random_password" "endpoint_api_key" {
  length  = 40
  special = false
}

resource "azurerm_key_vault_secret" "endpoint_api_key" {
  name         = "endpoint-api-key"
  value        = random_password.endpoint_api_key.result
  key_vault_id = azurerm_key_vault.main.id
  content_type = "API key del endpoint /predict (header X-API-Key)"
  tags         = local.tags
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_container_group" "inference" {
  count               = var.deploy_aci ? 1 : 0
  name                = "aci-${local.prefix}-inference"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  ip_address_type     = "Public"
  dns_name_label      = "mlops-${local.prefix}"
  restart_policy      = "Always"
  tags                = local.tags

  identity {
    type = "SystemAssigned"
  }

  container {
    name   = "endpoint"
    image  = "${azurerm_container_registry.main.login_server}/endpoint:${var.endpoint_image_tag}"
    cpu    = var.aci_cpu
    memory = var.aci_memory

    ports {
      port     = 8000
      protocol = "TCP"
    }

    environment_variables = {
      RATE_LIMIT_PER_MIN = tostring(var.rate_limit_per_min)
      RISK_HIGH          = "0.5"
      RISK_MEDIUM        = "0.3"
    }

    # Variables seguras: no se muestran en el portal ni en `az container show`
    secure_environment_variables = {
      API_KEY                               = azurerm_key_vault_secret.endpoint_api_key.value
      APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
    }

    liveness_probe {
      http_get {
        path   = "/health"
        port   = 8000
        scheme = "Http"
      }
      initial_delay_seconds = 20
      period_seconds        = 30
    }
  }

  image_registry_credential {
    server   = azurerm_container_registry.main.login_server
    username = azurerm_container_registry.main.admin_username
    password = azurerm_container_registry.main.admin_password
  }

  # stdout del contenedor (logs JSON de inferencia) -> Log Analytics,
  # de donde los lee el pipeline de drift (tabla ContainerInstanceLog_CL)
  diagnostics {
    log_analytics {
      workspace_id  = azurerm_log_analytics_workspace.main.workspace_id
      workspace_key = azurerm_log_analytics_workspace.main.primary_shared_key
    }
  }
}

# ---------------------------------------------------------------------------
# RBAC: roles diferenciados por responsabilidad sobre el ciclo de vida
# (asignaciones opcionales, se pasan object ids de Azure AD)
# ---------------------------------------------------------------------------
resource "azurerm_role_assignment" "data_scientists" {
  for_each             = toset(var.data_scientist_object_ids)
  scope                = azurerm_machine_learning_workspace.main.id
  role_definition_name = "AzureML Data Scientist"
  principal_id         = each.value
}

resource "azurerm_role_assignment" "readers" {
  for_each             = toset(var.reader_object_ids)
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Reader"
  principal_id         = each.value
}

# ---------------------------------------------------------------------------
# Monitoreo: alertas de Azure Monitor sobre el endpoint
# ---------------------------------------------------------------------------
resource "azurerm_monitor_action_group" "mlops" {
  name                = "ag-${local.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "mlopsalert"
  tags                = local.tags

  dynamic "email_receiver" {
    for_each = var.alert_emails
    content {
      name          = "email-${email_receiver.key}"
      email_address = email_receiver.value
    }
  }
}

# CPU sostenida alta en el contenedor de inferencia
resource "azurerm_monitor_metric_alert" "aci_cpu" {
  count               = var.deploy_aci ? 1 : 0
  name                = "alert-${local.prefix}-aci-cpu"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_container_group.inference[0].id]
  description         = "CPU del endpoint de inferencia > 80 % durante 15 min"
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"
  tags                = local.tags

  criteria {
    metric_namespace = "Microsoft.ContainerInstance/containerGroups"
    metric_name      = "CpuUsage"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 800 # millicores (80 % de 1 vCPU)
  }

  action {
    action_group_id = azurerm_monitor_action_group.mlops.id
  }
}

# Errores del endpoint (4xx/5xx) registrados por Application Insights
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "endpoint_errors" {
  count                = var.deploy_aci ? 1 : 0
  name                 = "alert-${local.prefix}-endpoint-errors"
  resource_group_name  = azurerm_resource_group.main.name
  location             = azurerm_resource_group.main.location
  scopes               = [azurerm_application_insights.main.id]
  description          = "Más de 20 respuestas con error del endpoint en 15 min"
  severity             = 2
  evaluation_frequency = "PT5M"
  window_duration      = "PT15M"
  tags                 = local.tags

  criteria {
    query                   = <<-KQL
      requests
      | where success == false
    KQL
    time_aggregation_method = "Count"
    operator                = "GreaterThan"
    threshold               = 20
  }

  action {
    action_groups = [azurerm_monitor_action_group.mlops.id]
  }
}
