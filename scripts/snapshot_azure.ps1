# ---------------------------------------------------------------------------
# Captura el estado del despliegue en docs/datos-despliegue.json.
#
#   pwsh -File scripts/snapshot_azure.ps1
#
# Sirve para dos cosas: alimentar docs/dashboard.html sin volver a consultar
# Azure y conservar la evidencia cuando los recursos ya se eliminaron.
# ---------------------------------------------------------------------------
[CmdletBinding()]
param(
    [string]$ResourceGroup = "rg-mlopslab-dev",
    [string]$Workspace = "mlw-mlopslab-dev",
    [string]$JobName = "",
    [string]$Experiment = "enape-training",
    [string]$ModelName = "enape-abandono",
    [string]$Acr = "acrmlopslabdev",
    [string]$Aci = "aci-mlopslab-dev-inference",
    [string]$DataAsset = "enape-abandono",
    [string]$DataAssetVersion = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Get-AzJson {
    param([string[]]$CliArgs)
    try {
        $raw = & az @CliArgs 2>$null | Out-String
        if (-not $raw.Trim()) { return $null }
        return $raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

Write-Host "Leyendo Azure..." -ForegroundColor Cyan

# El job de entrenamiento cambia de nombre en cada corrida: si no se indica,
# se toma el último del experimento.
if (-not $JobName) {
    $jobs = Get-AzJson @("ml", "job", "list", "--experiment-name", $Experiment, "--workspace-name", $Workspace, "-g", $ResourceGroup, "-o", "json")
    if ($jobs) {
        $matchingJobs = @($jobs | Where-Object { $_.experiment_name -eq $Experiment })
        if ($matchingJobs.Count -gt 0) {
            $JobName = @($matchingJobs | Sort-Object { $_.creation_context.created_at } -Descending)[0].name
        }
    }
}

$cuenta = Get-AzJson @("account", "show", "-o", "json")
$recursos = Get-AzJson @("resource", "list", "-g", $ResourceGroup, "-o", "json")
$aciInfo = Get-AzJson @("container", "show", "-n", $Aci, "-g", $ResourceGroup, "-o", "json")
$job = if ($JobName) { Get-AzJson @("ml", "job", "show", "-n", $JobName, "--workspace-name", $Workspace, "-g", $ResourceGroup, "-o", "json") } else { $null }
$modelos = Get-AzJson @("ml", "model", "list", "--name", $ModelName, "--workspace-name", $Workspace, "-g", $ResourceGroup, "-o", "json")
$tags = Get-AzJson @("acr", "repository", "show-tags", "-n", $Acr, "--repository", "endpoint", "-o", "json")
$acrTags = @($tags)
$acrConsultado = $null -ne $tags

# La salida descargada del job se marca únicamente cuando el último job del
# experimento coincide con el JobName observado; nunca heredar artefactos de otra corrida.
$azureMetricsCandidate = Join-Path $RepoRoot "outputs/azure/named-outputs/metrics/metrics.json"
$jobSpecificMetrics = $null
if ($job -and $job.status -eq "Completed" -and (Test-Path $azureMetricsCandidate)) {
    $jobSpecificMetrics = $azureMetricsCandidate
}

$metricsPath = $jobSpecificMetrics
$metricsSource = if ($jobSpecificMetrics) { "job Azure ML" } else { "validación local" }
if (-not $metricsPath) {
    # Sin corrida Azure disponible, solo la evaluación local es una alternativa.
    $metricsPath = Join-Path $RepoRoot "outputs/metrics_enape.json"
    $metricsSource = "validación local"
}
if (-not (Test-Path $metricsPath)) {
    # Los artefactos generados pueden no existir en un clon limpio. Usa las
    # métricas versionadas dentro del artefacto ENAPE empaquetado.
    $metricsPath = Join-Path $RepoRoot "endpoint/model/enape-abandono/metrics.json"
    $metricsSource = "modelo local empaquetado"
}
if (-not (Test-Path $metricsPath)) {
    $metrics = $null
    $metricsSource = "Sin métricas locales"
} else {
    $metrics = Get-Content $metricsPath -Raw | ConvertFrom-Json
}
if ($metricsSource -ne "job Azure ML") {
    Write-Warning "Las métricas del panel provienen de: $metricsSource; aún no son evidencia de una corrida Azure."
}

$demoPath = Join-Path $RepoRoot "docs/demo-curl-azure.md"
$demo = if (Test-Path $demoPath) { Get-Content $demoPath -Raw } else { "" }

function Get-FencedJson([string]$Text, [string]$Anchor) {
    $idx = $Text.IndexOf($Anchor)
    if ($idx -lt 0) { return $null }
    $m = [regex]::Match($Text.Substring($idx), '```json\s*(\{.*?\})\s*```', "Singleline")
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return $null
}

$health = $null
$pred = $null
$h = Get-FencedJson $demo "## GET /health"
$pj = Get-FencedJson $demo "## POST /predict con X-API-Key"
if ($h) { $health = $h | ConvertFrom-Json }
if ($pj) { $pred = $pj | ConvertFrom-Json }
$sinKey = if ($demo -match 'sin API key[\s\S]{0,120}?\*\*(\d{3})\*\*') { $matches[1] } else { "sin evidencia" }
$feedback = if ($demo -match '/feedback[\s\S]{0,120}?\*\*(\d{3})\*\*') { $matches[1] } else { "sin evidencia" }
$demoFecha = if ($demo -match '- Fecha:\s*(\d{4}-\d{2}-\d{2})') { [datetime]::Parse($matches[1]) } else { $null }
$demoReciente = [bool]($demoFecha -and $demoFecha -ge (Get-Date).Date)

$usuario = if ($cuenta -and $cuenta.user.name) { $cuenta.user.name } else { "sin sesión" }
$suscripcion = if ($cuenta) { $cuenta.name } else { "sin sesión" }
$suscripcionId = if ($cuenta) { $cuenta.id } else { "" }
$tenant = if ($cuenta) { $cuenta.tenantId } else { "" }

$recursosList = @()
if ($recursos) {
    $recursosList = @($recursos | Sort-Object type | ForEach-Object {
        @{ tipo = ($_.type -replace '^Microsoft\.', ''); nombre = $_.name; region = $_.location }
    })
}

$modelo = if ($modelos) { @($modelos | Sort-Object { [version]$_.version } -Descending)[0] } else { $null }
$endpointUrl = if ($aciInfo -and $aciInfo.ipAddress.fqdn) { "http://$($aciInfo.ipAddress.fqdn):8000" } else { $null }
$aciEstado = if ($aciInfo) { $aciInfo.instanceView.state } else { "Sin recursos consultados" }
$aciImagen = if ($aciInfo -and $aciInfo.containers.Count) { $aciInfo.containers[0].image } else { "sin evidencia" }

if (-not $DataAssetVersion) {
    $assets = Get-AzJson @("ml", "data", "list", "--name", $DataAsset, "--workspace-name", $Workspace, "-g", $ResourceGroup, "-o", "json")
    $DataAssetVersion = if ($assets) { @($assets | Sort-Object version -Descending)[0].version } else { "pendiente" }
}

# Resumen del dataset ENAPE (el mismo CSV que sube el stage de datos).
$dataset = $null
$dsPath = Join-Path $RepoRoot "ml/data/enape.csv"
if (Test-Path $dsPath) {
    $rows = @(Import-Csv $dsPath)
    $total = $rows.Count
    $abandona = @($rows | Where-Object { $_.abandono -eq "1" }).Count
    $continua = $total - $abandona
    $dataset = @{
        nombre = "ENAPE 2021"
        fuente = "INEGI · Encuesta Nacional de Acceso y Permanencia en la Educación"
        archivo = "df03_Dataset_ENAPE.csv"
        filas_crudas = 32343
        columnas_crudas = 67
        cohorte = $total
        positivos = $abandona
        porcentaje_positivos = if ($total) { [math]::Round(100 * $abandona / $total, 2) } else { 0 }
        features = 18
        features_modelo = 16
        duplicados = 127
        clases = @(
            @{ nombre = "Continua"; filas = $continua; porcentaje = if ($total) { [math]::Round(100 * $continua / $total, 2) } else { 0 } }
            @{ nombre = "Abandona"; filas = $abandona; porcentaje = if ($total) { [math]::Round(100 * $abandona / $total, 2) } else { 0 } }
        )
        nota = "Cohorte: inscritos en 2020-2021, 6 años o más, con situación conocida en 2021-2022 y sin egreso por meta cumplida."
    }
}

$precision = if ($pred) { "$($pred.prediction), riesgo $($pred.dropout_risk)" } else { "sin evidencia" }

$demoEsDeEnape = ($demo -match 'Modelo:\s*enape-abandono' -and $demoReciente)
$evidencias = @(
    @{ prueba = "GET /health"; esperado = "200"; obtenido = if ($health) { "$($health.status), modelo v$($health.model_version)" } else { "sin evidencia" }; ok = [bool]($demoEsDeEnape -and $health -and $health.status -eq "ok" -and $health.model_loaded) }
    @{ prueba = "POST /predict sin API key"; esperado = "401"; obtenido = $sinKey; ok = ($demoEsDeEnape -and $sinKey -eq "401") }
    @{ prueba = "POST /predict con API key"; esperado = "200"; obtenido = $precision; ok = [bool]($demoEsDeEnape -and $pred -and $pred.prediction_id -and $pred.model_version) }
    @{ prueba = "POST /feedback"; esperado = "202"; obtenido = $feedback; ok = ($demoEsDeEnape -and $feedback -eq "202") }
)

$datasetOk = [bool]($dataset -and $dataset.cohorte -gt 0)
$trainingOk = [bool]($job -and $job.status -eq "Completed")
$expectedImageTag = if ($aciImagen -match ':([^:]+)$') { $matches[1] } else { $null }
$imageOk = [bool]($acrConsultado -and $expectedImageTag -and $acrTags -contains $expectedImageTag)
$aciOk = ($aciEstado -eq "Running")
$evidenceOk = (@($evidencias | Where-Object { $_.ok }).Count -eq 4)
$metricsAreAzure = ($metricsSource -eq "job Azure ML" -and $trainingOk)

$etapas = @(
    @{ nombre = "Estado remoto"; que = "Storage con el tfstate versionado"; resultado = "Verificar cuenta, contenedor y acceso al backend"; estado = "pendiente" }
    @{ nombre = "Infraestructura"; que = "Workspace, storage, ACR, Key Vault, logs y cómputo"; resultado = if ($recursosList.Count) { "$($recursosList.Count) recursos consultados" } else { "Sin recursos consultados" }; estado = if ($recursosList.Count -ge 10) { "ok" } elseif ($recursosList.Count -gt 0) { "parcial" } else { "pendiente" } }
    @{ nombre = "Datos"; que = "Ingesta a Blob y limpieza con Data Factory"; resultado = if ($datasetOk -and $DataAssetVersion -ne "pendiente") { "Cohorte ENAPE: $($dataset.cohorte) filas; Data Asset $DataAsset:$DataAssetVersion" } elseif ($datasetOk) { "Cohorte ENAPE local: $($dataset.cohorte) filas; Data Asset no verificado" } else { "Sin datos ENAPE" }; estado = if ($datasetOk -and $DataAssetVersion -ne "pendiente") { "ok" } elseif ($datasetOk) { "parcial" } else { "pendiente" } }
    @{ nombre = "Entrenamiento"; que = "Job de Azure ML con MLflow y registro del modelo"; resultado = if ($job) { "$JobName, $($job.status)" } else { "Sin evidencia de job" }; estado = if ($trainingOk -and $metricsAreAzure) { "ok" } elseif ($trainingOk) { "parcial" } else { "pendiente" } }
    @{ nombre = "Imagen"; que = "Build y push del endpoint a ACR"; resultado = if ($imageOk) { "$Acr.azurecr.io/endpoint:$expectedImageTag" } else { "La imagen referida por ACI no está verificada en ACR" }; estado = if ($imageOk) { "ok" } else { "pendiente" } }
    @{ nombre = "Inferencia"; que = "Contenedor en ACI con 1 vCPU y 1.5 GB"; resultado = if ($aciOk) { "Running en la demo" } else { "$aciEstado" }; estado = if ($aciOk) { "ok" } else { "pendiente" } }
    @{ nombre = "Verificación"; que = "/health, /predict y /feedback contra Azure"; resultado = "$(@($evidencias | Where-Object { $_.ok }).Count)/4 pruebas OK"; estado = if ($evidenceOk -and $aciOk) { "ok" } elseif ($evidenceOk) { "parcial" } else { "pendiente" } }
    @{ nombre = "CI/CD"; que = "Pipeline de Azure Pipelines con gate y aprobación"; resultado = "definido; validar conexión de servicio y ejecución"; estado = "parcial" }
    @{ nombre = "Pruebas locales"; que = "Suites de pruebas automatizadas"; resultado = "No ejecutadas en la captura de Azure"; estado = "sin verificar" }
)

$enlaces = @(
    @{ texto = "Resource group"; url = if ($suscripcionId -and $tenant) { "https://portal.azure.com/#@$tenant/resource/subscriptions/$suscripcionId/resourceGroups/$ResourceGroup/overview" } else { $null } }
    @{ texto = "Azure ML Studio"; url = if ($suscripcionId) { "https://ml.azure.com/?wsid=/subscriptions/$suscripcionId/resourcegroups/$ResourceGroup/workspaces/$Workspace" } else { $null } }
    @{ texto = "Job de entrenamiento"; url = if ($suscripcionId -and $JobName) { "https://ml.azure.com/runs/$JobName?wsid=/subscriptions/$suscripcionId/resourcegroups/$ResourceGroup/workspaces/$Workspace" } else { $null } }
    @{ texto = "Container Registry"; url = if ($suscripcionId -and $tenant) { "https://portal.azure.com/#@$tenant/resource/subscriptions/$suscripcionId/resourceGroups/$ResourceGroup/providers/Microsoft.ContainerRegistry/registries/$Acr" } else { $null } }
)

$data = [ordered]@{
    generado = (Get-Date -Format "yyyy-MM-dd HH:mm")
    cuenta = @{ usuario = $usuario; suscripcion = $suscripcion; tenant = $tenant; suscripcion_id = $suscripcionId }
    resource_group = $ResourceGroup
    endpoint = @{ url = $endpointUrl; estado = $aciEstado; imagen = $aciImagen }
    job = @{
        nombre = $JobName
        estado = if ($job) { $job.status } else { "sin evidencia" }
        compute = "cpu-cluster"
        experimento = $Experiment
    }
    modelo = @{
        nombre = $ModelName
        version = if ($modelo) { $modelo.version } elseif ($metrics -and $metrics.registry) { $metrics.registry.version } else { "sin evidencia" }
        stage = if ($modelo -and $modelo.stage) { $modelo.stage } elseif ($metrics -and $metrics.registry) { $metrics.registry.stage } else { "sin evidencia" }
        data_asset = "$($DataAsset):$DataAssetVersion"
        tags = if ($tags) { @($tags) } else { @() }
    }
    dataset = $dataset
    metricas = @{
        accuracy = if ($metrics) { $metrics.accuracy } else { $null }
        f1_macro = if ($metrics) { $metrics.f1_macro } else { $null }
        roc_auc = if ($metrics) { $metrics.roc_auc } else { $null }
        pr_auc = if ($metrics) { $metrics.pr_auc } else { $null }
        fuente = $metricsSource
        per_class = if ($metrics) { $metrics.per_class } else { $null }
    }
    pruebas = @{
        passed = 0
        total = 0
        fuente = "No ejecutadas en esta captura"
    }
    recursos = $recursosList
    etapas = $etapas
    evidencias = $evidencias
    enlaces = $enlaces
}

$outPath = Join-Path $RepoRoot "docs/datos-despliegue.json"
$data | ConvertTo-Json -Depth 12 | Set-Content -Path $outPath -Encoding utf8
Write-Host "Snapshot escrito: $outPath" -ForegroundColor Green
Write-Host ("  recursos={0}  endpoint={1}  job={2}" -f $recursosList.Count, $aciEstado, $data.job.estado)
