# ---------------------------------------------------------------------------
# Genera docs/dashboard.html a partir de docs/datos-despliegue.json.
#
#   pwsh -File scripts/build_dashboard.ps1              # corre pytest y refresca Azure
#   pwsh -File scripts/build_dashboard.ps1 -SkipTests   # sin correr pytest
#
# Si hay sesión de Azure, primero actualiza el snapshot con
# scripts/snapshot_azure.ps1. Si no la hay (recursos ya eliminados), reutiliza
# el último snapshot y el informe se sigue generando.
# ---------------------------------------------------------------------------
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [string]$ResourceGroup = "rg-mlopslab-dev"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# 1. Pruebas automáticas -------------------------------------------------------
$passed = 0; $total = 0
$py = Join-Path $RepoRoot ".venv/Scripts/python.exe"
if (-not $SkipTests) {
    if (Test-Path $py) {
        Write-Host "Ejecutando pytest..." -ForegroundColor Cyan
        $out = & $py -m pytest -q 2>&1 | Out-String
    } else {
        Write-Host "No hay .venv local; ejecutando pytest con el Python del PATH..." -ForegroundColor Cyan
        $out = & python -m pytest -q 2>&1 | Out-String
    }
    if ($LASTEXITCODE -ne 0) {
        throw "pytest falló o no pudo ejecutarse (exit $LASTEXITCODE).`n$out"
    }
    $m = [regex]::Match($out, "(\d+) passed")
    $f = [regex]::Match($out, "(\d+) failed")
    $e = [regex]::Match($out, "(\d+) errors?")
    $s = [regex]::Match($out, "(\d+) skipped")
    if ($m.Success) { $passed = [int]$m.Groups[1].Value }
    if ($f.Success) { $total += [int]$f.Groups[1].Value }
    if ($e.Success) { $total += [int]$e.Groups[1].Value }
    if ($s.Success) { $total += [int]$s.Groups[1].Value }
    $total += $passed
}

# 2. Snapshot de Azure ---------------------------------------------------------
$snapshot = Join-Path $RepoRoot "docs/datos-despliegue.json"
$hasSession = $false
$sinRecursos = $false
try {
    $null = & az account show -o none 2>$null
    $hasSession = ($LASTEXITCODE -eq 0)
} catch { $hasSession = $false }

if ($hasSession) {
    $rgCount = 0
    try {
        $rg = & az resource list -g $ResourceGroup -o json 2>$null | ConvertFrom-Json
        $rgCount = @($rg).Count
    } catch { $rgCount = 0 }
    if ($rgCount -gt 0) {
        Write-Host "Actualizando snapshot desde Azure..." -ForegroundColor Cyan
        & (Join-Path $PSScriptRoot "snapshot_azure.ps1") | Out-Null
        if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Falló la actualización del snapshot de Azure." }
    } else {
        $sinRecursos = $true
        Write-Host "El grupo $ResourceGroup no tiene recursos: se conserva el snapshot." -ForegroundColor Yellow
    }
} else {
    Write-Host "Sin sesión de Azure: se usa el snapshot existente." -ForegroundColor Yellow
}

if (-not (Test-Path $snapshot)) {
    throw "No existe $snapshot. Ejecuta scripts/snapshot_azure.ps1 con los recursos desplegados."
}
$data = Get-Content $snapshot -Raw | ConvertFrom-Json

# Si el entorno ya no existe, el informe lo dice en vez de mostrar un estado
# que ya es falso (ACI "Stopped" cuando en realidad se eliminó).
if ($sinRecursos -or @($data.recursos).Count -eq 0) {
    $data.endpoint.estado = "Eliminado"
    if (-not $data.PSObject.Properties["cierre"]) {
        $data | Add-Member -NotePropertyName cierre -NotePropertyValue (Get-Date -Format "yyyy-MM-dd") -Force
    }
}

# Sin entorno de pruebas o con -SkipTests, no afirmar resultados de una corrida previa.
if ($SkipTests -or -not (Test-Path $py)) {
    $passed = 0
    $total = 0
}

# 3. Render --------------------------------------------------------------------
$data.pruebas.passed = $passed
$data.pruebas.total = $total
if (-not $data.pruebas.PSObject.Properties["fuente"]) {
    $data.pruebas | Add-Member -NotePropertyName fuente -NotePropertyValue "No ejecutadas en esta captura" -Force
}
if ($total -gt 0) { $data.pruebas.fuente = "Corrida local en esta ejecución" }
else { $data.pruebas.fuente = "No ejecutadas en esta captura" }
$data.generado = (Get-Date -Format "yyyy-MM-dd HH:mm")

# La cuenta, la suscripción y los enlaces al portal no se publican en el panel.
$data.PSObject.Properties.Remove("cuenta")
$data.PSObject.Properties.Remove("enlaces")

$json = $data | ConvertTo-Json -Depth 12
$json = $json -replace "</", "<\/"

$template = Get-Content (Join-Path $RepoRoot "docs/dashboard.template.html") -Raw
$html = $template.Replace("__DATA__", $json)
$outPath = Join-Path $RepoRoot "docs/dashboard.html"
Set-Content -Path $outPath -Value $html -Encoding utf8 -NoNewline

Write-Host "Informe generado: $outPath" -ForegroundColor Green
Write-Host ("  recursos={0}  endpoint={1}  pytest={2}/{3}" -f @($data.recursos).Count, $data.endpoint.estado, $passed, $total)
