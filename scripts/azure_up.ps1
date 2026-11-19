# Despliegue guiado de la plataforma en Azure (Windows / PowerShell).
#
# No se ejecuta solo: cada etapa se lanza explícitamente. Pensado para que el
# equipo decida cuándo crear recursos (consume crédito de Azure for Students).
#
# Uso típico:
#   .\scripts\azure_up.ps1 -Stage preflight
#   .\scripts\azure_up.ps1 -Stage state
#   .\scripts\azure_up.ps1 -Stage base
#   .\scripts\azure_up.ps1 -Stage data
#   .\scripts\azure_up.ps1 -Stage train
#   .\scripts\azure_up.ps1 -Stage image -ImageTag v3
#   .\scripts\azure_up.ps1 -Stage aci   -ImageTag v3
#   .\scripts\azure_up.ps1 -Stage verify
#   .\scripts\azure_up.ps1 -Stage stop
#   .\scripts\azure_up.ps1 -Stage destroy      # pide confirmación
#
# O todo de una vez (tarda ~30-45 min y crea recursos):
#   .\scripts\azure_up.ps1 -Stage all -ImageTag v3
#
# Requisitos: az login, terraform, Docker Desktop (para image/aci/verify/all).
# Los nombres derivan de -ProjectName/-Environment y deben coincidir con
# terraform/terraform.tfvars.example y .azure-pipelines/*.yml.

param(
    [ValidateSet("preflight", "state", "base", "data", "train", "image", "aci", "verify", "stop", "destroy", "all")]
    [string]$Stage = "preflight",

    [string]$ProjectName = "mlopslab",
    [string]$Environment = "dev",
    [string]$Location = "centralus",

    # Tag de la imagen que se construye y se pone en el ACI.
    [string]$ImageTag = "v3",

    # Versión del Model Registry a descargar. Vacío = Production o la más reciente.
    [string]$ModelVersion = "",

    # Si la imagen se construye con endpoint/model ya exportado en local.
    [switch]$UseLocalModel,

    # No pedir confirmación en destroy.
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path $PSScriptRoot -Parent
$TerraformDir = Join-Path $RepoRoot "terraform"
$BackendFile = Join-Path $TerraformDir "backend.hcl"

# Nombres derivados (deben coincidir con terraform/main.tf, training.tf,
# datafactory.tf e inference.tf).
$Prefix = "$ProjectName-$Environment"
$ResourceGroup = "rg-$Prefix"
$Workspace = "mlw-$Prefix-v2"
$Storage = "st$ProjectName$Environment" + "001"
$Acr = "acr$ProjectName$Environment"
$KeyVault = "kv-$Prefix"
$DataFactory = "adf-$Prefix"
$AciName = "aci-$Prefix-inference"
$DnsLabel = "mlops-$Prefix"
$StateResourceGroup = "rg-tfstate-mlops"
$StateStorage = "sttfstatemlopslab"
$StateContainer = "tfstate"
$StateKey = "$ProjectName-$Environment.tfstate"

function Write-Step([string]$Text) {
    Write-Host "`n=== $Text ===" -ForegroundColor Cyan
}

function Assert-Exit([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw "$Message (exit $LASTEXITCODE)" }
}

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "No se encontró '$Name' en PATH. Instálalo y vuelve a abrir la terminal."
    }
}

function Get-BashPath {
    $candidates = @(
        "C:\Program Files\Git\bin\bash.exe",
        "C:\Program Files\Git\usr\bin\bash.exe"
    )
    foreach ($c in $candidates) { if (Test-Path $c) { return $c } }
    throw "No se encontró Git Bash. Instala Git for Windows para ejecutar los scripts .sh."
}

function ConvertTo-Posix([string]$Path) {
    $p = $Path -replace '\\', '/'
    if ($p -match '^([A-Za-z]):') { $p = "/" + $Matches[1].ToLower() + $p.Substring(2) }
    return $p
}

function Invoke-Bash([string]$Command) {
    $bash = Get-BashPath
    & $bash -lc $Command
    Assert-Exit "Falló el comando bash: $Command"
}

function Get-TerraformVars {
    $vars = @(
        "-var=project_name=$ProjectName",
        "-var=environment=$Environment",
        "-var=location=$Location"
    )
    $tfvars = Join-Path $TerraformDir "terraform.tfvars"
    if (Test-Path $tfvars) { $vars = @("-var-file=terraform.tfvars") + $vars }
    return $vars
}

function Ensure-Login {
    az account show --query "{name:name,id:id,tenant:tenantId}" -o json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "No hay sesión de Azure. Ejecuta 'az login' y reintenta." }
    $account = az account show --query "{name:name,id:id,tenant:tenantId,user:user.name}" -o json | ConvertFrom-Json
    Write-Host "Suscripción: $($account.name) ($($account.id)) — $($account.user)" -ForegroundColor Green

    # Limpiar cualquier lockfile huérfano de MSAL en Windows
    Remove-Item "$env:USERPROFILE\.azure\*.lockfile" -Force -ErrorAction SilentlyContinue

    # Asegurar token fresco antes de que Terraform invoque az concurrently
    az account get-access-token --output none 2>$null

    # Exportar variables ARM estándar para Terraform
    $env:ARM_SUBSCRIPTION_ID = $account.id
    if ($account.tenant) { $env:ARM_TENANT_ID = $account.tenant }
}

function Ensure-BackendFile {
    if (Test-Path $BackendFile) { return }
    if (-not (Test-Path (Join-Path $TerraformDir "backend.hcl.example"))) {
        throw "Falta terraform/backend.hcl.example"
    }
    $content = @"
resource_group_name  = "$StateResourceGroup"
storage_account_name = "$StateStorage"
container_name       = "$StateContainer"
key                  = "$StateKey"
use_azuread_auth     = true
"@
    Set-Content -Path $BackendFile -Value $content -Encoding utf8
    Write-Host "Creado terraform/backend.hcl para $StateKey" -ForegroundColor Yellow
}

function Invoke-Preflight {
    Write-Step "Preflight"
    Require-Command "az"
    Require-Command "terraform"
    Ensure-Login

    if ($Stage -in @("image", "aci", "verify", "all")) {
        Require-Command "docker"
        docker info *> $null
        if ($LASTEXITCODE -ne 0) {
            throw "Docker Desktop no está corriendo. Ábrelo y espera a que diga 'Engine running'."
        }
    }

    Write-Host @"

Nombres que se usarán:
  Resource group : $ResourceGroup
  Workspace      : $Workspace
  Storage        : $Storage
  ACR            : $Acr
  Key Vault      : $KeyVault
  Data Factory   : $DataFactory
  ACI            : $AciName
  State key      : $StateKey

"@ -ForegroundColor Gray

    $rgExists = az group exists -n $ResourceGroup -o tsv
    if ($rgExists -eq "true") {
        Write-Host "El resource group $ResourceGroup ya existe. Si el state está vacío, revisa la sección de importación de terraform/README.md." -ForegroundColor Yellow
    }

    $quota = az vm list-usage -l $Location --query "[?name.value=='standardDSv3Family'].{used:currentValue,limit:limit}" -o json | ConvertFrom-Json
    if ($quota -and $quota.limit -eq 0) {
        Write-Host "Aviso: la cuota standardDSv3Family en $Location es 0. Baja compute_max_nodes a 1 o pide cuota antes del apply." -ForegroundColor Yellow
    }
}

function Invoke-State {
    Write-Step "Estado remoto de Terraform"
    Ensure-Login
    Require-Command "az"

    az group create -n $StateResourceGroup -l $Location -o none
    Assert-Exit "No se pudo crear el resource group del state"

    az storage account create -n $StateStorage -g $StateResourceGroup -l $Location `
        --sku Standard_LRS --kind StorageV2 --min-tls-version TLS1_2 `
        --allow-blob-public-access false -o none
    Assert-Exit "No se pudo crear la cuenta de state"

    az storage account blob-service-properties update --account-name $StateStorage `
        -g $StateResourceGroup --enable-versioning true -o none
    Assert-Exit "No se pudo habilitar el versionado del state"

    $userId = az ad signed-in-user show --query id -o tsv 2>$null
    if ($userId) {
        $scope = az storage account show -n $StateStorage -g $StateResourceGroup --query id -o tsv
        az role assignment create --assignee $userId --role "Storage Blob Data Contributor" --scope $scope -o none 2>$null
    } else {
        Write-Host "No se pudo obtener el object id del usuario (¿service principal?). Verifica el rol Storage Blob Data Contributor sobre el state." -ForegroundColor Yellow
    }

    az storage container create -n $StateContainer --account-name $StateStorage --auth-mode login -o none 2>$null
    if ($LASTEXITCODE -ne 0) {
        # El rol Blob Data Contributor recién asignado puede tardar unos minutos
        # en propagarse al plano de datos.
        $created = $false
        for ($i = 0; $i -lt 12; $i++) {
            Write-Host "El rol Storage Blob Data Contributor aún no propagó; reintento en 10 s..." -ForegroundColor Yellow
            Start-Sleep -Seconds 10
            az storage container create -n $StateContainer --account-name $StateStorage --auth-mode login -o none 2>$null
            if ($LASTEXITCODE -eq 0) { $created = $true; break }
        }
        if (-not $created) {
            throw "No se pudo crear el contenedor tfstate. Revisa el rol Storage Blob Data Contributor sobre $StateStorage."
        }
    }

    Ensure-BackendFile
    Write-Host "State listo: $StateStorage/$StateContainer/$StateKey" -ForegroundColor Green
}

function Invoke-Base {
    Write-Step "Terraform: infraestructura base (sin ACI)"
    Require-Command "terraform"
    Ensure-BackendFile
    Set-Location $TerraformDir

    terraform init -backend-config backend.hcl -input=false
    Assert-Exit "terraform init falló"
    terraform validate
    Assert-Exit "terraform validate falló"

    $stateList = terraform state list 2>$null
    $rgExists = az group exists -n $ResourceGroup -o tsv
    if ($rgExists -eq "true" -and -not $stateList) {
        Write-Host "El RG existe pero el state está vacío. Importa los recursos existentes o usa otro ProjectName (ver terraform/README.md)." -ForegroundColor Red
        if (-not $Force) { throw "Apply cancelado para no duplicar recursos. Usa -Force si ya importaste." }
    }

    $tfVars = Get-TerraformVars
    terraform plan @tfVars -out base.tfplan
    Assert-Exit "terraform plan falló"
    terraform apply base.tfplan
    Assert-Exit "terraform apply falló"

    terraform output
    Write-Host "Infraestructura base aplicada." -ForegroundColor Green
}

function Invoke-Data {
    Write-Step "Datos: CSV -> raw -> Data Factory -> processed + Data Asset"
    Require-Command "az"
    Require-Command "python"

    Set-Location $RepoRoot
    python -m ml.data.load_enape --output ml/data/enape.csv
    Assert-Exit "No se pudo regenerar ml/data/enape.csv desde la fuente original"
    python -m ml.data.validate --data ml/data/enape.csv --expected-rows 18207 --clean-output outputs/processed/enape.csv
    Assert-Exit "La validación del dataset falló"

    # `datafactory` y `ml` son extensiones de la CLI; sin ellas fallan
    # `az datafactory ...` y `az ml data create`.
    az extension add -n datafactory -y -o none
    Assert-Exit "No se pudo instalar la extensión datafactory"
    az extension add -n ml -y -o none
    Assert-Exit "No se pudo instalar la extensión ml"
    $version = Get-Date -Format "yyyyMMddHHmm"
    $repoPosix = ConvertTo-Posix $RepoRoot
    Invoke-Bash "cd '$repoPosix' && export DATA_VERSION='$version' && bash ml/data/upload_to_blob.sh '$Storage' && bash ml/data/run_adf_pipeline.sh '$DataFactory' '$Storage' '$Workspace' '$ResourceGroup'"
    Write-Host "Data Asset enape-abandono creado (versión $version)." -ForegroundColor Green
}

function Invoke-Train {
    Write-Step "Entrenamiento en Azure ML"
    Require-Command "az"
    az extension add -n ml -y -o none
    Set-Location $RepoRoot

    $job = az ml job create -f ml/pipeline/job.yaml `
        --set inputs.data.path=azureml:enape-abandono@latest `
        --workspace-name $Workspace -g $ResourceGroup --query name -o tsv
    Assert-Exit "No se pudo crear el job"
    Write-Host "Job: $job" -ForegroundColor Gray

    # `az ml job stream` aborta con "binascii.Error: Incorrect padding" en algunas
    # versiones de la extensión ml. Se consulta el estado del job por polling.
    $timeoutMin = 120
    $deadline = (Get-Date).AddMinutes($timeoutMin)
    $status = "Desconocido"
    $lastStatus = ""
    while ($true) {
        $current = az ml job show -n $job --workspace-name $Workspace -g $ResourceGroup --query status -o tsv 2>$null
        if ($current) { $status = "$current".Trim() }
        if ($status -ne $lastStatus) {
            Write-Host "  estado: $status"
            $lastStatus = $status
        }
        if ($status -in @("Completed", "Failed", "Canceled")) { break }
        if ((Get-Date) -gt $deadline) { throw "El job $job no terminó en $timeoutMin minutos (estado: $status)" }
        Start-Sleep -Seconds 30
    }
    if ($status -ne "Completed") { throw "El job terminó en $status" }

    $dest = Join-Path $RepoRoot "outputs/azure"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    az ml job download -n $job --output-name metrics --download-path $dest `
        --workspace-name $Workspace -g $ResourceGroup
    Assert-Exit "No se pudieron descargar las métricas"
    Write-Host "Métricas en outputs/azure. Modelo registrado en Staging (revisa el gate en Azure ML)." -ForegroundColor Green
}

function Invoke-Image {
    Write-Step "Imagen Docker -> ACR"
    Require-Command "docker"
    Require-Command "az"
    docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw "Docker Desktop no está corriendo." }

    if (-not $UseLocalModel) {
        $versionArg = if ($ModelVersion) { "'$ModelVersion'" } else { "" }
        $repoPosix = ConvertTo-Posix $RepoRoot
        Invoke-Bash "cd '$repoPosix/endpoint' && bash download_model.sh '$Workspace' '$ResourceGroup' $versionArg"
    } else {
        Write-Host "Usando el modelo local de endpoint/model (no se descarga del registry)." -ForegroundColor Yellow
    }

    # `az ml model download` deja el modelo en model/<nombre>/model/MLmodel,
    # aunque según la versión de la CLI puede quedar en otra profundidad.
    $modelRoot = Join-Path $RepoRoot "endpoint/model"
    $modelFile = Get-ChildItem -Path $modelRoot -Recurse -File -Filter "MLmodel" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $modelFile) { throw "No hay modelo MLflow (MLmodel) en endpoint/model" }
    Write-Host "Modelo: $($modelFile.FullName)" -ForegroundColor Gray

    az acr login -n $Acr
    Assert-Exit "az acr login falló"

    Set-Location (Join-Path $RepoRoot "endpoint")
    docker build -t "$Acr.azurecr.io/endpoint:$ImageTag" -t "$Acr.azurecr.io/endpoint:latest" .
    Assert-Exit "docker build falló"
    docker push "$Acr.azurecr.io/endpoint:$ImageTag"
    Assert-Exit "docker push falló"
    docker push "$Acr.azurecr.io/endpoint:latest"
    Assert-Exit "docker push latest falló"
    Write-Host "Imagen publicada: $Acr.azurecr.io/endpoint:$ImageTag" -ForegroundColor Green
}

function Invoke-Aci {
    Write-Step "Terraform: ACI con la imagen $ImageTag"
    Require-Command "terraform"
    Ensure-BackendFile
    Set-Location $TerraformDir

    terraform init -backend-config backend.hcl -input=false
    Assert-Exit "terraform init falló"

    $tfVars = Get-TerraformVars
    terraform plan @tfVars -target azurerm_container_group.inference `
        -var="deploy_aci=true" -var="endpoint_image_tag=$ImageTag" -out aci.tfplan
    Assert-Exit "terraform plan del ACI falló"
    terraform apply aci.tfplan
    Assert-Exit "terraform apply del ACI falló"

    $url = terraform output -raw endpoint_url
    Write-Host "Endpoint: $url" -ForegroundColor Green
}

function Invoke-Verify {
    Write-Step "Verificación del endpoint"
    Require-Command "az"
    Set-Location $TerraformDir
    $url = terraform output -raw endpoint_url 2>$null
    if (-not $url) { $url = "http://$DnsLabel.$Location.azurecontainer.io:8000" }

    $healthy = $false
    for ($i = 0; $i -lt 60; $i++) {
        $code = curl.exe -s -o NUL -w "%{http_code}" "$url/health" 2>$null
        if ($code -eq "200") { $healthy = $true; break }
        Start-Sleep -Seconds 5
    }
    if (-not $healthy) { throw "El endpoint no respondió /health en 5 minutos ($url)" }

    $key = az keyvault secret show --vault-name $KeyVault -n endpoint-api-key --query value -o tsv
    Assert-Exit "No se pudo leer endpoint-api-key de Key Vault"

    $health = curl.exe -s "$url/health"
    $noKey = curl.exe -s -o NUL -w "%{http_code}" -X POST "$url/predict" `
        -H "Content-Type: application/json" `
        --data-binary "@$RepoRoot/endpoint/examples/estudiante_riesgo_alto.json"
    $prediction = curl.exe -s -X POST "$url/predict" `
        -H "Content-Type: application/json" -H "X-API-Key: $key" `
        --data-binary "@$RepoRoot/endpoint/examples/estudiante_riesgo_alto.json"

    $predObj = $prediction | ConvertFrom-Json
    if (-not $predObj.prediction_id -or -not $predObj.model_version -or -not $predObj.prediction) {
        throw "La respuesta autenticada no contiene prediction_id, model_version y prediction válidos."
    }
    $feedbackBody = @{ prediction_id = $predObj.prediction_id; actual = "Abandona" } | ConvertTo-Json -Compress
    $feedbackFile = Join-Path $env:TEMP "mlops-feedback.json"
    Set-Content -Path $feedbackFile -Value $feedbackBody -Encoding utf8
    $feedbackCode = curl.exe -s -o NUL -w "%{http_code}" -X POST "$url/feedback" `
        -H "Content-Type: application/json" -H "X-API-Key: $key" --data-binary "@$feedbackFile"

    $reportLines = @(
        "# Demostración de inferencia en Azure",
        "",
        "- Fecha: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        "- Endpoint: $url",
        "- Modelo: enape-abandono",
        "",
        "## GET /health",
        '```json',
        $health,
        '```',
        "",
        "## POST /predict sin API key (se espera 401)",
        "Código HTTP: **$noKey**",
        "",
        "## POST /predict con X-API-Key",
        '```json',
        $prediction,
        '```',
        "",
        "## POST /feedback (se espera 202)",
        "Código HTTP: **$feedbackCode**",
        "",
        "> Este archivo lo genera scripts/azure_up.ps1 -Stage verify."
    )
    $report = $reportLines -join "`n"
    $reportPath = Join-Path $RepoRoot "docs/demo-curl-azure.md"
    Set-Content -Path $reportPath -Value $report -Encoding utf8

    Write-Host "Health: $health" -ForegroundColor Green
    Write-Host "Sin API key: $noKey (esperado 401)"
    Write-Host "Predicción: $($predObj.prediction) (riesgo $($predObj.risk_level))"
    if ($noKey -ne "401") { throw "Se esperaba 401 sin API key; recibido $noKey" }
    if (-not $predObj.prediction_id -or -not $predObj.prediction) { throw "La respuesta autenticada no contiene una predicción válida." }
    if ($feedbackCode -ne "202") { throw "Se esperaba 202 en /feedback; recibido $feedbackCode" }

    Write-Host "Feedback: $feedbackCode (esperado 202)"
    Write-Host "Evidencia escrita en docs/demo-curl-azure.md" -ForegroundColor Green
}

function Invoke-Stop {
    Write-Step "Deteniendo el ACI (ahorra crédito)"
    az container stop -n $AciName -g $ResourceGroup -o none 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "ACI detenido." -ForegroundColor Green }
    else { Write-Host "El ACI no existe o ya estaba detenido." -ForegroundColor Yellow }
}

function Invoke-Destroy {
    Write-Step "Terraform destroy"
    if (-not $Force) {
        $answer = Read-Host "Esto elimina todos los recursos del proyecto en Azure. Escribe 'destroy' para continuar"
        if ($answer -ne "destroy") { Write-Host "Cancelado." -ForegroundColor Yellow; return }
    }
    Require-Command "terraform"
    Ensure-BackendFile
    Set-Location $TerraformDir
    terraform init -backend-config backend.hcl -input=false
    Assert-Exit "terraform init falló"
    $tfVars = Get-TerraformVars

    # Azure crea por su cuenta el action group "Application Insights Smart
    # Detection" dentro del resource group y Terraform no lo gestiona. Con
    # providers.tf >= este cambio (prevent_deletion_if_contains_resources =
    # false) el destroy ya no falla por eso; si el state es viejo y falla, se
    # borra el resource group con az y se repite el destroy para limpiar el state.
    terraform destroy @tfVars -var="deploy_aci=true" -auto-approve
    if ($LASTEXITCODE -ne 0) {
        Write-Host "terraform destroy falló: se elimina el resource group con az y se reintenta." -ForegroundColor Yellow
        az group delete -n $ResourceGroup --yes -o none
        terraform destroy @tfVars -var="deploy_aci=true" -auto-approve
    }
    Assert-Exit "terraform destroy falló"

    # El Key Vault puede quedar soft-deleted y reservar el nombre. En dev no hay
    # purge protection; se ofrece purgar y se pide confirmación explícita incluso
    # cuando -Force habilita el destroy del grupo de recursos.
    $deleted = az keyvault list-deleted --query "[?name=='$KeyVault'].name" -o tsv 2>$null
    if ($deleted) {
        $purge = $false
        $answer = Read-Host "El Key Vault $KeyVault está soft-deleted y reserva su nombre. ¿Purgarlo permanentemente? Escribe 'purge' para continuar"
        $purge = ($answer -eq "purge")
        if ($purge) {
            az keyvault purge -n $KeyVault -l $Location -o none 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Key Vault purgado: $KeyVault" -ForegroundColor Green
            } else {
                Write-Host "No se pudo purgar Key Vault; quizá no se tienen permisos." -ForegroundColor Yellow
            }
        } else {
            Write-Host "Se conserva el Key Vault soft-deleted. El nombre no podrá reutilizarse hasta expirar." -ForegroundColor Yellow
        }
    }

    Write-Host "Recursos del proyecto eliminados. El state ($StateStorage) se conserva." -ForegroundColor Green
}

try {
    switch ($Stage) {
        "preflight" { Invoke-Preflight }
        "state"     { Invoke-State }
        "base"      { Invoke-Base }
        "data"      { Invoke-Data }
        "train"     { Invoke-Train }
        "image"     { Invoke-Image }
        "aci"       { Invoke-Aci }
        "verify"    { Invoke-Verify }
        "stop"      { Invoke-Stop }
        "destroy"   { Invoke-Destroy }
        "all" {
            Invoke-Preflight
            Invoke-State
            Invoke-Base
            Invoke-Data
            Invoke-Train
            Invoke-Image
            Invoke-Aci
            Invoke-Verify
        }
    }
} finally {
    Set-Location $RepoRoot
}
