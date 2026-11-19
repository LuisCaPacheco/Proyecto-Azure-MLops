# ---------------------------------------------------------------------------
# Etapa 4: monitoreo del modelo en Azure Monitor
#
# Fuente: los logs JSON que el endpoint escribe en stdout y que ACI envía a
# Log Analytics (tabla ContainerInstanceLog_CL, columna Message):
#   {"event": "inference", "latency_ms": ..., "prediction_ids": [...], "predictions": [...], ...}
#   {"event": "feedback",  "prediction_id": ..., "actual": ...}
#
# - Alerta de latencia P99 (este archivo).
# - Workbook con volumen, niveles de riesgo, latencia y accuracy observada.
# - Data drift y accuracy decay: pipeline programado drift-monitoring.yml.
# - CPU del ACI y errores del endpoint: alertas en inference.tf.
# ---------------------------------------------------------------------------

locals {
  # Prefijo común de las consultas: eventos de inferencia ya parseados
  # (trimspace: una línea en blanco partiría la consulta KQL en dos)
  kql_inference = trimspace(<<-KQL
    ContainerInstanceLog_CL
    | where Message startswith '{"event": "inference"'
    | extend d = parse_json(Message)
  KQL
  )
}

# Latencia P99 de inferencia por encima del umbral
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "latency_p99" {
  count                = var.deploy_aci ? 1 : 0
  name                 = "alert-${local.prefix}-latency-p99"
  resource_group_name  = azurerm_resource_group.main.name
  location             = azurerm_resource_group.main.location
  scopes               = [azurerm_log_analytics_workspace.main.id]
  description          = "Latencia P99 de inferencia > ${var.latency_p99_threshold_ms} ms en 15 min"
  severity             = 3
  evaluation_frequency = "PT15M"
  window_duration      = "PT15M"
  # La tabla solo existe después de la primera inferencia del contenedor
  skip_query_validation   = true
  auto_mitigation_enabled = true
  tags                    = local.tags

  criteria {
    query                   = <<-KQL
      ${local.kql_inference}
      | summarize p99_ms = percentile(todouble(d.latency_ms), 99)
    KQL
    time_aggregation_method = "Maximum"
    metric_measure_column   = "p99_ms"
    operator                = "GreaterThan"
    threshold               = var.latency_p99_threshold_ms

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.mlops.id]
  }
}

# Workbook de Azure Monitor (Portal > Monitor > Workbooks)
resource "random_uuid" "workbook" {}

resource "azurerm_application_insights_workbook" "mlops" {
  name                = random_uuid.workbook.result
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  display_name        = "MLOps - Endpoint de deserción (${var.environment})"
  source_id           = lower(azurerm_log_analytics_workspace.main.id)
  tags                = local.tags

  data_json = jsonencode({
    version = "Notebook/1.0"
    items = [
      {
        type    = 1
        name    = "titulo"
        content = { json = "## Endpoint de inferencia `enape-abandono`\nVolumen, niveles de riesgo, latencia y accuracy observada (feedback real)." }
      },
      {
        type = 3
        name = "volumen"
        content = {
          version       = "KqlItem/1.0"
          title         = "Inferencias por hora"
          query         = "${local.kql_inference}\n| summarize inferencias = sum(toint(d.n)) by bin(TimeGenerated, 1h)"
          size          = 0
          timeContext   = { durationMs = 604800000 }
          queryType     = 0
          resourceType  = "microsoft.operationalinsights/workspaces"
          visualization = "timechart"
        }
      },
      {
        type = 3
        name = "riesgo"
        content = {
          version       = "KqlItem/1.0"
          title         = "Estudiantes por nivel de riesgo"
          query         = "${local.kql_inference}\n| mv-expand nivel = d.risk_levels to typeof(string)\n| summarize estudiantes = count() by nivel"
          size          = 0
          timeContext   = { durationMs = 604800000 }
          queryType     = 0
          resourceType  = "microsoft.operationalinsights/workspaces"
          visualization = "piechart"
        }
      },
      {
        type = 3
        name = "latencia"
        content = {
          version       = "KqlItem/1.0"
          title         = "Latencia de inferencia (ms): P50 / P95 / P99"
          query         = "${local.kql_inference}\n| summarize p50 = percentile(todouble(d.latency_ms), 50), p95 = percentile(todouble(d.latency_ms), 95), p99 = percentile(todouble(d.latency_ms), 99) by bin(TimeGenerated, 1h)"
          size          = 0
          timeContext   = { durationMs = 604800000 }
          queryType     = 0
          resourceType  = "microsoft.operationalinsights/workspaces"
          visualization = "timechart"
        }
      },
      {
        type = 3
        name = "accuracy"
        content = {
          version       = "KqlItem/1.0"
          title         = "Accuracy observada por semana (predicciones con resultado real en /feedback)"
          query         = <<-KQL
            let feedback = ContainerInstanceLog_CL
              | where Message startswith '{"event": "feedback"'
              | extend f = parse_json(Message)
              | summarize arg_max(TimeGenerated, actual = tostring(f.actual)) by pid = tostring(f.prediction_id);
            ${local.kql_inference}
            | mv-expand pid = d.prediction_ids to typeof(string), pred = d.predictions to typeof(string)
            | join kind=inner feedback on pid
            | summarize etiquetadas = count(), accuracy = round(countif(pred == actual) * 1.0 / count(), 3) by semana = bin(TimeGenerated, 7d)
            | order by semana desc
          KQL
          size          = 0
          timeContext   = { durationMs = 2592000000 }
          queryType     = 0
          resourceType  = "microsoft.operationalinsights/workspaces"
          visualization = "table"
        }
      },
    ]
    fallbackResourceIds = [lower(azurerm_log_analytics_workspace.main.id)]
  })
}
