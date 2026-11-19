# Pipeline MLOps completo en local (Windows / PowerShell), equivalente a las
# etapas del pipeline de Azure: data-prep (validar + depurar) -> tests -> tuning ->
# train (Staging) -> gate vs Production -> promote -> export del modelo -> drift. MLflow queda en ./mlruns.db
# (ver la UI con: .venv\Scripts\mlflow ui --backend-store-uri sqlite:///mlruns.db).
#
# Uso (desde la raíz del repo):
#   python -m venv .venv
#   .venv\Scripts\pip install -r ml\requirements-local.txt
#   powershell -ExecutionPolicy Bypass -File scripts\run_local_pipeline.ps1 [-Clean]
param([switch]$Clean)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$py = ".\.venv\Scripts\python.exe"
$env:MLFLOW_TRACKING_URI = "sqlite:///mlruns.db"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONWARNINGS = "ignore"

function Step($name, [scriptblock]$block) {
    Write-Host "`n=== $name ===" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) { throw "Falló la etapa: $name" }
}

if ($Clean) {
    Remove-Item mlruns.db, mlruns, outputs -Recurse -Force -ErrorAction SilentlyContinue
}

Step "1a. Data prep (ENAPE 2021 -> ml/data/enape.csv)" {
    & $py -m ml.data.load_enape
    if ($LASTEXITCODE -ne 0) { throw "No se pudo generar ml/data/enape.csv" }
}
Step "1b. Validar y depurar (equivalente local del Data Flow de ADF)" {
    & $py -m ml.data.validate --data ml/data/enape.csv --expected-rows 18207 --report outputs/validation.json `
        --clean-output outputs/processed/enape.csv
}
Step "2. Pruebas unitarias ml/" { & $py -m pytest ml/tests -q -p no:cacheprovider }
Step "3. Tuning (CV 5-fold, F1 macro)" {
    & $py -m ml.pipeline.tune --experiment enape-tuning --data outputs/processed/enape.csv `
        --output outputs/tuning_ranking.json | Select-String "Mejor"
}
Step "4a. Candidato v1 (hiperparámetros de la propuesta, sin balanceo) -> Staging" {
    & $py -m ml.pipeline.train --experiment enape-training --data outputs/processed/enape.csv `
        --n-estimators 100 --max-depth 10 --min-samples-leaf 5 --class-weight none `
        --metrics-output outputs/v1_metrics.json
}
Step "4b. Gate v1 (esperado: rechazado por recall de Abandona; no se promueve)" {
    & $py -m ml.pipeline.evaluate --metrics-file outputs/v1_metrics.json --output outputs/eval_v1.json
}
Step "5a. Candidato v2 (hiperparámetros del tuning) -> Staging" {
    & $py -m ml.pipeline.train --experiment enape-training --data outputs/processed/enape.csv `
        --metrics-output outputs/v2_metrics.json
}
Step "5b. Gate v2 vs Production (esperado: aprobado) y promoción a Production" {
    & $py -m ml.pipeline.evaluate --metrics-file outputs/v2_metrics.json --output outputs/eval_v2.json `
        --fail-on-reject
    if ($LASTEXITCODE -eq 0) { & $py -m ml.pipeline.promote --evaluation outputs/eval_v2.json }
}
Step "6. Exportar modelo de Production al endpoint" {
    & $py scripts/export_production_model.py
}
Step "7. Drift: mismo perfil (esperado: sin drift)" {
    & $py -m ml.monitoring.drift --reference outputs/evaluation/reference_profile.json `
        --current outputs/processed/enape.csv --output outputs/drift_baseline.json
}
Step "8. Drift: choque simulado (esperado: reentrenar)" {
    & $py -m ml.monitoring.drift --reference outputs/evaluation/reference_profile.json `
        --simulate-from outputs/processed/enape.csv --output outputs/drift_shock.json --markdown outputs/drift_shock.md
}
Step "9. Pruebas del endpoint" {
    Push-Location endpoint; & "..\$py" -m pytest tests -q -p no:cacheprovider; Pop-Location
}
Write-Host "`nPipeline local completado. Resultados en outputs/ y endpoint/model/." -ForegroundColor Green
