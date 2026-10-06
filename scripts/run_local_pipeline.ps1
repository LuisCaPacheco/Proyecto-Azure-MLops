# Pipeline MLOps completo en local (Windows / PowerShell), equivalente a las
# etapas del pipeline de Azure: data-prep -> tests -> tuning -> train ->
# evaluate -> export del modelo -> drift. MLflow queda en ./mlruns.db
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
$env:MLFLOW_DISABLE_AGENT_HINT = "1"
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

Step "1. Data prep (UCI 697 -> ml/data/dropout.csv)" { & $py -m ml.data.load_data }
Step "2. Pruebas unitarias ml/" { & $py -m pytest ml/tests -q -p no:cacheprovider }
Step "3. Tuning (CV 5-fold, F1 macro)" {
    & $py -m ml.pipeline.tune --experiment dropout-tuning --output outputs/tuning_ranking.json | Select-String "Mejor"
}
Step "4a. Entrenamiento v1 (hiperparámetros de la propuesta, sin balanceo)" {
    & $py -m ml.pipeline.train --experiment dropout-training --n-estimators 100 --max-depth 10 `
        --min-samples-leaf 5 --class-weight none --metrics-output outputs/v1_metrics.json
}
Step "4b. Entrenamiento v2 (hiperparámetros del tuning)" {
    & $py -m ml.pipeline.train --experiment dropout-training --metrics-output outputs/v2_metrics.json
}
Step "5. Gate de evaluación (candidato v1 vs Production)" {
    & $py -m ml.pipeline.evaluate --metrics-file outputs/v1_metrics.json --output outputs/eval_v1.json
}
Step "6. Exportar modelo de Production al endpoint" {
    & $py scripts/export_production_model.py
}
Step "7. Drift: mismo perfil (esperado: sin drift)" {
    & $py -m ml.monitoring.drift --reference outputs/evaluation/reference_profile.json `
        --current ml/data/dropout.csv --output outputs/drift_baseline.json
}
Step "8. Drift: choque simulado (esperado: reentrenar)" {
    & $py -m ml.monitoring.drift --reference outputs/evaluation/reference_profile.json `
        --simulate-from ml/data/dropout.csv --output outputs/drift_shock.json --markdown outputs/drift_shock.md
}
Step "9. Pruebas del endpoint" {
    Push-Location endpoint; & "..\$py" -m pytest tests -q -p no:cacheprovider; Pop-Location
}
Write-Host "`nPipeline local completado. Resultados en outputs/ y endpoint/model/." -ForegroundColor Green
