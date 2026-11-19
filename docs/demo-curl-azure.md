# Demostración de inferencia en Azure

> **Nota (2026-11-18).** Esta evidencia es de la corrida del 17-11 con el modelo
> UCI 697 (`dropout-classifier`), cuyo entorno se eliminó el 18-11. La etapa
> `verify` del relanzamiento con **ENAPE 2021** (`enape-abandono`, imagen `v3`)
> reescribe este archivo automáticamente.

- Fecha: 2026-11-17 20:33:16
- Endpoint: http://mlops-mlopslab-dev.centralus.azurecontainer.io:8000
- Modelo: dropout-classifier

## GET /health
```json
{"status":"ok","model_loaded":true,"model_version":"1"}
```

## POST /predict sin API key (se espera 401)
Código HTTP: **401**

## POST /predict con X-API-Key
```json
{"prediction_id":"1ad8fcd6-381b-4dff-9f7f-490a996db570","prediction":"Dropout","class_index":0,"confidence":0.8775,"probabilities":{"Dropout":0.8775,"Enrolled":0.0986,"Graduate":0.0239},"dropout_risk":0.8775,"risk_level":"alto","model_version":"1"}
```

## POST /feedback (se espera 202)
Código HTTP: **202**

> Este archivo lo genera scripts/azure_up.ps1 -Stage verify.
