output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "ml_workspace_name" {
  value = azurerm_machine_learning_workspace.main.name
}

output "ml_workspace_id" {
  value = azurerm_machine_learning_workspace.main.id
}

output "storage_account_name" {
  value = azurerm_storage_account.main.name
}

output "storage_account_id" {
  value = azurerm_storage_account.main.id
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "key_vault_id" {
  value = azurerm_key_vault.main.id
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.id
}

output "application_insights_instrumentation_key" {
  value     = azurerm_application_insights.main.instrumentation_key
  sensitive = true
}

output "endpoint_api_key_secret_name" {
  description = "Nombre del secreto en Key Vault con la API key del endpoint"
  value       = azurerm_key_vault_secret.endpoint_api_key.name
}

output "endpoint_url" {
  description = "URL pública del endpoint de inferencia (si deploy_aci = true)"
  value       = var.deploy_aci ? "http://${azurerm_container_group.inference[0].fqdn}:8000" : null
}

output "compute_cluster_name" {
  description = "Compute cluster de entrenamiento (referenciado en ml/pipeline/job.yaml)"
  value       = azurerm_machine_learning_compute_cluster.cpu.name
}

output "data_factory_name" {
  value = azurerm_data_factory.main.name
}

output "adf_pipeline_name" {
  description = "Pipeline de ADF que depura raw -> processed"
  value       = azurerm_data_factory_pipeline.clean_enape.name
}

output "processed_datastore_name" {
  description = "Datastore de Azure ML sobre el contenedor processed"
  value       = azurerm_machine_learning_datastore_blobstorage.processed.name
}
