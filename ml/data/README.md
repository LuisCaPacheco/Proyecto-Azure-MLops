# Datos

Dataset **ENAPE 2021 — Encuesta Nacional de Acceso y Permanencia en la Educación**
(INEGI, México). El archivo crudo `archive (1)/df03_Dataset_ENAPE.csv` tiene
32.343 registros y 67 columnas (join de vivienda y módulo por `FOLIO`). La unidad
de análisis es la persona de 6 años o más que cursó el ciclo 2020-2021.

- `load_enape.py` → aplica la cohorte, deriva la etiqueta binaria `abandono`
  (`1` = no se reinscribió en 2021-2022), renombra al contrato snake_case y
  recodifica las binarias 1/2 → 1/0. Genera `enape.csv`: **18.207 × 21**
  (`FOLIO` + 18 variables + `abandono` + `abandono_label`), con **1.179 positivos
  (6,48 %)**.
- `load_data.py` → loader del dataset UCI 697 anterior. Queda como legado y no lo
  usa nadie del pipeline.
- `validate.py` → valida el contrato (esquema, tipos, rangos, mínimo de filas y
  representación de clases) y cuenta filas inválidas y duplicadas contra los
  umbrales de `ml/data/contract.json`. `--clean-output` aplica en local las
  mismas reglas que el Data Flow de Azure Data Factory.
- `upload_to_blob.sh` → sube el CSV a `raw/enape/<versión>/` y a
  `raw/enape/latest/` (`--auth-mode login`, sin connection strings).
- `run_adf_pipeline.sh` → ejecuta el pipeline `pl_clean_enape` de Data Factory
  (`raw` → `processed`, rechazadas a `raw/rejected/enape/`) y registra la salida
  como Data Asset `enape-abandono` en Azure ML.

**Contrato de 18 variables** (orden fijo, `FEATURES` en `load_enape.py`):
`sexo, edad, edu_inicial, nivel_edu, terminado, ent, q_personas, q_hombres,
q_mujeres, menores_30, pc, laptop, tv_plana, tablet, smartphone, internet_f,
max_nivel_esp, entr_diagnost`.

El modelo entrena con **16**: `max_nivel_esp` y `entr_diagnost` se excluyen por
fuga estructural (sólo se preguntan a quien sigue inscrito, así que el código 0
delata la etiqueta). Ver `MODEL_FEATURES` en `ml/pipeline/modeling.py`.

```powershell
$env:PYTHONPATH=(Get-Location).Path
python -m ml.data.load_enape        # 18.207 filas, 6,48 % positivos
python -m ml.data.validate --data ml/data/enape.csv --report outputs/validation.json
```

El reporte debe salir `ok: true`, con 0 filas inválidas y ~127 duplicados
(0,7 %), por debajo del 5 % permitido.

Los CSV están en `.gitignore` (ver raíz) a excepción de este README y `.gitkeep`.
