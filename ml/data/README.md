# Datos

Dataset **Predict Students' Dropout and Academic Success** (UCI ML Repository, id 697):
4424 estudiantes, 36 variables académicas, demográficas y socioeconómicas, clase
objetivo `Dropout` / `Enrolled` / `Graduate`.

- `dropout.csv` → versión preparada (columnas en snake_case, `target` 0/1/2 y
  `target_label`), generada por `python -m ml.data.load_data`.
- `upload_to_blob.sh` → la sube al contenedor `raw` del Storage Account y la registra
  como Data Asset `student-dropout` en Azure ML.
- `iris.csv` → dataset de la primera iteración (histórico).

Los CSV están en `.gitignore` (ver raíz) a excepción de este README y `.gitkeep`.
