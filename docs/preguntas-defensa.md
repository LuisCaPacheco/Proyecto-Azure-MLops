# Banco de preguntas para la defensa

Anexo de sustentación del P07. No es un manual: es lo que hay que tener en la
cabeza y saber abrir en pantalla. Cada bloque tiene **respuesta corta** (20–30 s),
**evidencia** y, cuando aplica, la **concesión honesta** que conviene admitir
antes de que la saquen.

Cómo usarlo:

1. Lee §0 (resumen de 60 s) hasta que salga sin mirar.
2. Memoriza §1 (decisiones y por qué) y §10 (cifras).
3. Ensaya §8 (preguntas trampa) en voz alta.
4. Ten abiertas las pestañas de §9.

Estado del repo: 2026-11-18. El entorno de Azure se eliminó ese día; el
relanzamiento con ENAPE es el 19-11.

---

## 0. Resumen de 60 segundos (la primera pregunta casi siempre es esta)

> "Es una plataforma MLOps end-to-end en Azure para predecir abandono escolar con
> la encuesta ENAPE 2021 del INEGI. Terraform crea toda la infraestructura:
> workspace de Azure ML, clúster de cómputo, Data Factory, Storage, ACR, Key
> Vault, Log Analytics y un ACI para inferencia. Los datos se limpian con un Data
> Flow de ADF, se versionan como Data Asset y alimentan un job de Azure ML que
> entrena un RandomForest con tracking en MLflow y lo registra en Staging. Un
> gate por PR-AUC y recall decide si es desplegable; la imagen se publica en ACR
> y el ACI sirve `/predict` con API key. Todo se monitorea con alertas, workbook,
> drift y feedback. El entorno se destruye al terminar para no consumir crédito,
> y se recrea con un solo comando."

---

## 1. Decisiones tomadas y por qué

| Decisión | Alternativa descartada | Por qué | Costo / concesión |
|---|---|---|---|
| **Terraform** | Bicep, ARM, portal | Multi-proveedor, `plan` legible, estado y `destroy` reproducible; lo pide el brief | Estado remoto que administrar |
| **Estado remoto en Blob** | `local.tfstate` | Lease (bloqueo), versionado y sobrevive al `destroy` | Dependencia de `sttfstatemlopslab` |
| **Un solo entorno (`dev`)** | Workspaces de Terraform | Un equipo, una demo; menos indirección | No hay `prod` real |
| **Sin módulos** | `modules/network`, `modules/ml` | 27 recursos en un dominio; los módulos aquí sólo añaden saltos | Deuda si crece a multi-entorno |
| **`centralus`** | `eastus` | `eastus` está bloqueado en la suscripción educativa | Es la única región viable |
| **ACR Basic** | Standard / Premium | ~5 USD/mes, sin geo-replicación | Sin *retention* avanzado |
| **ACI** | AKS, managed online endpoint | Lo pide el brief; no hay clúster que pagar en reposo | Sin autoscaling ni HTTPS |
| **ADF + Data Flow** | Limpiar con pandas en el job | ETL real y auditable; deja filas rechazadas | DIU-hora y arranque Spark de 8–15 min |
| **Data Asset versionado** | Ruta directa al blob | Linaje y reproducibilidad | Un paso más en la etapa `data` |
| **Etiqueta binaria** | 3 clases (`Dropout/Enrolled/Graduate`) | La ENAPE sólo distingue si se reinscribió; `Enrolled` era ambiguo | Se pierde el matiz "sigue estudiando" |
| **18 variables / 16 al modelo** | Usar las 67 columnas | `max_nivel_esp` y `entr_diagnost` sólo se preguntan a inscritos: delatan la etiqueta | Contrato de API con 2 campos que el modelo ignora |
| **Gate por PR-AUC + recall** | `accuracy > 0.70` | Con 6,48 % de positivos, decir siempre "Continua" acierta 93,5 % | Métricas menos "bonitas" |
| **`Staging` nunca promueve solo** | Auto-promoción | Un humano aprueba tras el smoke test | Un paso manual más |
| **Modelo dentro de la imagen** | Descargarlo al arrancar | Arranque determinista, sin registry en runtime | Imagen ~0,8 GB y rebuild por versión |
| **Docker local + push** | ACR Tasks | ACR Tasks está bloqueado en la suscripción educativa | Requiere Docker Desktop |
| **Terraform dueño del ACI** | `az container create` | Un PUT de la CLI borra identidad, probe y diagnóstico | `apply -target` en la etapa `aci` |

---

## 2. Terraform e infraestructura como código

**1. ¿Por qué IaC y no crear todo en el portal?**
Porque el entorno se creó, se verificó, se destruyó y se vuelve a crear igual. El
portal no es reproducible ni auditable: no hay `plan`, no hay revisión y borrar a
mano deja recursos huérfanos cobrando.
*Evidencia:* `terraform/` completo y `scripts/azure_up.ps1`.

**2. ¿Dónde vive el estado y por qué?**
En `rg-tfstate-mlops` / `sttfstatemlopslab` / contenedor `tfstate` /
`mlopslab-dev.tfstate`. Fuera del RG del proyecto **a propósito**: `destroy`
borra `rg-mlopslab-dev` pero no el estado, así no hay que reimportar 27 recursos.
Blob con versionado y lease.

**3. ¿Qué pasa si dos personas hacen `apply` a la vez?**
El backend `azurerm` toma un lease sobre el blob: el segundo espera o falla, no
corrompe el estado. Además, el script pide confirmación por etapa.

**4. ¿Qué pasa si se pierde el estado?**
Se recupera una versión anterior del blob (versionado activo). En el peor caso,
`terraform import` recurso por recurso; por eso el estado no se borra en el
`destroy`.

**5. ¿Cómo garantizas que Terraform y Azure coinciden?**
`terraform plan` sin cambios, `terraform state list` con los 27 objetos y el
snapshot `docs/datos-despliegue.json`. Si el plan propone cambios, hay *drift*.

**6. ¿Por qué no usaste módulos?**
Entorno único y pequeño; un módulo aquí añade parámetros sin reutilización real.
La separación ya existe por responsabilidad: `main.tf`, `training.tf`,
`datafactory.tf`, `inference.tf`, `monitoring.tf`. Con `dev/prod` extraería
módulos y usaría `for_each` por entorno.

**7. ¿`count` o `for_each`?**
`count` en el ACI (`deploy_aci ? 1 : 0`) porque es un recurso único condicional;
`for_each` sería para conjuntos con nombre estable. Pasar de 0 a 1 recrea la
dirección, que es lo deseado.

**8. ¿Por qué `prevent_deletion_if_contains_resources = false`?**
Application Insights crea por su cuenta el action group *Application Insights
Smart Detection*, que Terraform no gestiona, y el borrado del RG abortaba con
`the Resource Group still contains Resources`. Está en `providers.tf` y el
script tiene *fallback* con `az group delete`.

**9. Si Terraform es el dueño, ¿por qué usas `az`?**
Regla: **Terraform es el único dueño de la forma del recurso**. `az` sólo hace
operaciones que no la cambian: subir un blob, lanzar un pipeline de ADF, crear un
job, leer un secreto, parar el contenedor. La única excepción es el borrado del
RG por el action group oculto.

**10. ¿Cómo se destruye sin dejar nada cobrando?**
`terraform destroy -var="deploy_aci=true"` (sin ese `-var`, `count = 0` y el ACI
queda huérfano), purga del Key Vault y `az group delete` si queda el RG.
Verificado: state vacío y sólo `rg-tfstate-mlops` sobrevive.

**11. ¿Dónde están los secretos en Terraform?**
`random_password` + `azurerm_key_vault_secret` `endpoint-api-key`; el ACI lo
recibe como `secure_environment_variables`.
*Concesión:* el valor también queda en el state (como cualquier recurso
sensible); por eso el state es privado, con AAD y versionado. Mitigación futura:
secreto generado en Key Vault o *external secret store*.

**12. ¿Cómo se rota la API key?**
Se regenera el `random_password` (`taint`), se aplica el secreto y se recrea el
ACI; los clientes actualizan su `X-API-Key`. No hay rotación sin corte: mejora
pendiente.

**13. ¿Por qué `terraform.tfvars` y `backend.hcl` no se versionan?**
Pueden contener correos, IDs y rutas del estado; el repo trae `.example`. El
script genera `backend.hcl` si falta.

**14. ¿Qué verificas antes de un `apply`?**
`terraform fmt -check`, `terraform validate`, `plan` revisado, state vacío si el
RG existe (el script aborta para no duplicar) y cuota `standardDSv3Family`.

---

## 3. Azure: identidad, red, storage y secretos

**15. ¿Qué servicios usas y para qué?**
Azure ML (workspace, clúster, jobs, environments, registry, data assets), Data
Factory (ETL), Storage (raw/processed/state), ACR (imágenes), ACI (inferencia),
Key Vault (API key), Log Analytics + App Insights (logs/telemetría), Azure
Monitor (alertas y workbook), Managed Identity + RBAC, Azure DevOps (CI/CD
definido).

**16. ¿Cómo se autentican los servicios entre sí?**
Identidades administradas + RBAC. El workspace necesita `AcrPush`/`AcrPull`
sobre el ACR (sin `AcrPush`, el job se queda en `Preparing` para siempre sin
error); ADF necesita `Storage Blob Data Contributor` (sin él, el Data Flow da
`403`). La subida de blobs usa `--auth-mode login`, nunca connection strings.

**17. ¿Por qué Key Vault con access policy y no RBAC?**
Es lo que Terraform modela en `inference.tf` para dev; RBAC sería más granular y
es la recomendación para producción. El vault no tiene *purge protection* en dev
para poder reutilizar el nombre; en prod sí la activaría.

**18. ¿Por qué el endpoint es público y sin HTTPS?**
El brief pide ACI y la demo es académica; HTTPS exige Application Gateway/Front
Door o dominio, con costo fijo. Está documentado como brecha: `VNet + private
endpoint + HTTPS` es la evolución.

**19. ¿Cómo se protege la API?**
`X-API-Key` (desde Key Vault), *rate limiting* por IP (60/min), validación
Pydantic con `extra="forbid"`, límites de rango, contenedor no-root y
*liveness probe*.

**20. ¿Por qué el ACI tiene identidad administrada si la key va por variable?**
Para dejar el RBAC listo (lectura de Key Vault y otros recursos) y no rehacer el
recurso cuando se añada. Hoy el valor se inyecta como variable segura.

**21. ¿Qué pasa si el ACI se cae?**
El `liveness_probe` llama `GET /health` cada 30 s; ACI reinicia el contenedor.
Los logs van a Log Analytics y hay alertas de CPU, errores y latencia P99.

**22. ¿Por qué contenedores `raw` y `processed` separados?**
Separación de zonas: `raw` es inmutable/auditable (incluye `rejected/`),
`processed` es la salida del ETL que consume el entrenamiento. Los datastores de
Azure ML apuntan a cada uno.

**23. ¿Dónde ves los logs del contenedor?**
`app.py` escribe una línea JSON por inferencia a stdout → diagnóstico del ACI →
`ContainerInstanceLog_CL` en Log Analytics. De ahí leen las alertas, el workbook
y el job de drift.

**24. ¿Por qué `centralus`?**
`eastus` está bloqueado en esta suscripción; `centralus` es la única región
permitida con cuota DSv3 disponible.

**25. ¿Por qué 27 recursos en Terraform y sólo 13 en `az resource list`?**
Porque `az resource list` no lista los hijos de ADF (datasets, data flow) ni
algunos objetos anidados; el state sí tiene las 27 direcciones. Es una diferencia
de inventario, no de propiedad.

---

## 4. Datos y ETL

**26. ¿Por qué ENAPE 2021 y no el UCI 697?**
UCI son 4.424 estudiantes de Portugal con 3 clases y ya estaba usado; ENAPE es la
encuesta mexicana de acceso y permanencia (32.343 × 67), con desenlace real de
reinscripción y relevancia regional. Además `archive/dataset.csv` era el mismo
UCI duplicado.

**27. ¿Cómo defines la cohorte y por qué?**
`inscrito == 1`, `EDAD >= 6`, `inscrito_actual ∈ {1,2}`, `nins_causa != 4`. Quita
a quien nunca estuvo inscrito, a menores de 6, a quien no tiene situación
conocida y a quien egresó por meta cumplida (no es abandono). Resultado: 18.207
filas.

**28. ¿Cómo se define "abandono"?**
`abandono = 1` si `inscrito_actual == 2` (no se reinscribió en 2021-2022). Es un
desenlace observable y binario, no una proxy.

**29. ¿Por qué el ETL en ADF y no en el job?**
El brief pide un servicio de ingesta y separa responsabilidades: ADF limpia y
deja evidencia (filas rechazadas), el job entrena. Además el Data Flow es
reproducible y se ve en el portal.

**30. ¿Qué hace exactamente el Data Flow?**
`SplitRows` (nulos, cohorte, rangos, dominio de binarias) → `DeriveFeatures`
(renombres, 1/2→1/0, etiqueta) → `SelectFeatures` (FOLIO + 18 + etiqueta) →
`DistinctRows` por hash SHA-256 de todas las columnas → `DropHash` → sinks
`processed` y `rejected`.

**31. ¿Por qué deduplicar por hash y no por columnas clave?**
Porque el CSV no trae un ID de persona fiable más allá de `FOLIO`; el hash de
todas las columnas elimina duplicados exactos sin asumir una clave. 127
duplicados (0,7 %), por debajo del 5 % permitido.

**32. ¿Por qué versionar el Data Asset?**
Para linaje: el job referencia `azureml:enape-abandono@latest`, pero cada versión
es inmutable y permite reproducir una corrida concreta.

**33. ¿Qué pasa con las filas rechazadas?**
Van a `raw/rejected/enape/rejected.csv` con `truncate: true`; se pueden auditar,
pero no se usan para entrenar.

---

## 5. Modelo y MLOps

**34. ¿Por qué RandomForest y no una red neuronal o boosting?**
Tabla de 18k × 16, desbalance moderado, necesidad de importancia de variables y
de entrenar en CPU en 10–15 min. RF con `class_weight="balanced_subsample"` es
robusto, interpretable y barato; XGBoost sería el siguiente candidato, no una NN.

**35. ¿Por qué 16 features y no 18?**
`max_nivel_esp` y `entr_diagnost` sólo se preguntan a quien sigue inscrito: su
código 0 delata la etiqueta y daban ROC-AUC ≈ 1,0 (fuga estructural). Se quedan
en el contrato de la API por compatibilidad, pero el modelo no los usa.

**36. ¿Por qué el gate no usa accuracy?**
Con 6,48 % de positivos, un modelo trivial que diga siempre "Continua" acierta
93,5 %. El gate usa **PR-AUC ≥ 0,35**, **recall de `Abandona` ≥ 0,60**, sin
retroceso de PR-AUC frente a Production (≤ 0,005) y prohíbe compararse con la
misma versión.

**37. ¿Por qué priorizas recall sobre precisión?**
Porque el costo de no detectar a un estudiante que abandona es mayor que el de
una falsa alarma: la intervención es barata (tutoría, beca, contacto). De ahí
P 0,272 / R 0,712 en `Abandona`.

**38. ¿Por qué Staging y no Production automático?**
El registro no debe desplegar solo: train → Staging → gate → build → smoke test →
`promote.py` → Production. El entrenamiento nunca promueve.

**39. ¿Cómo se reproduce un entrenamiento?**
Semilla fija, split estratificado 80/20, `requirements.txt` con versiones,
environment versionado en Azure ML, Data Asset inmutable y parámetros + métricas
+ artefactos en MLflow.

**40. ¿Cómo detectas drift?**
`ml/monitoring/drift.py` compara el perfil de referencia con las inferencias:
PSI por variable y KS. Si supera umbral, recomienda reentrenar;
`drift-monitoring.yml` lo automatiza a diario (pendiente de service connection).

**41. ¿Cómo mides el desempeño real en producción?**
Cada predicción devuelve `prediction_id`; `POST /feedback` registra la clase real.
`performance.py` cruza ambos por ID y compara accuracy/recall observados contra
la referencia; si cae más de 5 puntos o el recall de una clase baja del umbral,
recomienda reentrenar.

**42. ¿Qué pasa si cambia el dataset mañana?**
Se sustituye el CSV, se ajusta `load_enape.py` y el contrato de `validate.py`; el
resto del pipeline es agnóstico. Fue exactamente lo que pasó al migrar de UCI a
ENAPE.

**43. ¿Cómo se eligen los hiperparámetros?**
`ml/pipeline/tune.py` con grid de 36 combinaciones y CV 5-fold, eligiendo el
mejor F1 macro que cumpla recalls mínimos; los runs quedan en MLflow (`mlruns/`).

---

## 6. Servicio de inferencia

**44. ¿Por qué FastAPI y no Flask?**
Tipado con Pydantic, validación automática, OpenAPI/Swagger gratis, `async` y
menos código para el mismo contrato.

**45. ¿Por qué el modelo va dentro de la imagen?**
Arranque determinista y sin dependencia del Model Registry en runtime; el precio
es reconstruir la imagen al cambiar de versión. Descargarlo al arrancar acopla el
contenedor a Azure ML.

**46. ¿Por qué la imagen no lleva MLflow?**
Sólo necesita leer `MLmodel` + `model.pkl` con `cloudpickle`; quitar MLflow baja
la imagen a ~0,8 GB y el arranque a segundos.

**47. ¿Qué devuelve `/predict`?**
`prediction` (`Continua`/`Abandona`), `class_index`, `confidence`,
`probabilities`, `dropout_risk` (P(Abandona)), `risk_level` (alto ≥ 0,5,
medio ≥ 0,3), `prediction_id` y `model_version`. Se conservaron los nombres
anteriores para no romper el workbook KQL ni la evidencia.

**48. ¿Qué valida la API antes de predecir?**
Esquema exacto de 18 campos, rangos (`sexo` 0/1, `edad` 6–100…), rechazo de
claves faltantes o desconocidas (`422`), vector de longitud exacta (`400`) y un
solo formato de entrada (`student` o `features`).

**49. ¿Cómo escala?**
No escala solo: ACI es un contenedor fijo de 1 vCPU/1,5 GB. Para producción real:
managed online endpoint o AKS con autoscaling. Se dice abiertamente como brecha.

---

## 7. Operación, costos y CI/CD

**50. ¿Cuánto cuesta y cómo lo controlas?**
En reposo ~9–10 USD/mes, casi todo ACR Basic (~5). Clúster a 0 nodos, ACI con
`stop` (~0,04 USD/h encendido), job de 12 min ~0,15 USD. Tras la entrega,
`destroy` completo: 0 de cómputo y 0 de ACR. Presupuesto del relanzamiento:
0,2–0,35 USD.

**51. ¿Qué alertas tienes?**
CPU del ACI (`> 0,8` núcleos), errores del endpoint (KQL sobre
`ContainerInstanceLog_CL`), latencia P99 (`> 500 ms`), más action group con
correo y workbook con volumen, riesgo, latencia y accuracy observada.

**52. ¿Qué falta en CI/CD?**
El YAML está completo (CI → DataPrep → Train → Evaluate → Build → Deploy con
aprobación → smoke test → Promote) y `drift-monitoring.yml` programado. Falta la
*service connection* ARM con Workload Identity Federation y el *variable group*
vinculado a Key Vault: objetos que sólo puede crear un administrador del tenant.
No se simula ni se dice que está verde.

**53. ¿Por qué no hay `prod` separado?**
Alcance académico con un entorno; separar `dev/prod` exige otro state, otros
nombres y otro presupuesto. Siguiente paso: módulos + workspaces + *approvals*.

**54. ¿Qué harías distinto con más tiempo?**
HTTPS + VNet/private endpoint, managed online endpoint con autoscaling, canary
release, reentrenamiento automático disparado por drift, feature store y módulos
de Terraform por entorno.

**55. ¿Qué es lo más frágil de todo esto?**
Tres cosas, y las digo antes de que las pregunten: el estado (si se pierde, toca
importar), el secreto en el state de Terraform y el CI/CD sin service connection.
Las tres tienen mitigación documentada.

---

## 8. Preguntas trampa (y cómo salir)

| Pregunta | Respuesta recomendada |
|---|---|
| "Si Terraform es el dueño, ¿por qué usas `az`?" | Sólo para operaciones que no cambian la forma del recurso; la excepción del RG está documentada. |
| "El ACI es un contenedor único, ¿eso es producción?" | No: es la inferencia que pide el brief. Producción sería managed endpoint/AKS con HTTPS y autoscaling. |
| "La precisión de `Abandona` es 0,27, ¿el modelo es malo?" | Es una decisión: con 6,5 % de positivos priorizamos recall 0,71 para no perder casos; el costo son falsas alarmas. |
| "Aceptas 2 variables que el modelo ignora, ¿no es un error de diseño?" | Es deuda consciente por compatibilidad del contrato; lo limpio es quitarlas de la API y versionar el contrato. |
| "¿Por qué no hay tests de Terraform?" | Hay `fmt`, `validate` y `plan`; falta `terraform test`/`tflint` y *policy as code*. Brecha reconocida. |
| "¿Y si Azure cambia el precio o la cuota?" | `min_nodes = 0`, `stop`, `destroy` y presupuesto medido; la cuota DSv3 ya obligó a bajar `max_nodes` a 2. |
| "¿Por qué no Databricks/Synapse?" | ADF cubre el ETL del brief con menos costo fijo; Spark gestionado no aporta a 18k filas. |
| "¿Cómo sé que no hay fuga de datos?" | Cohorte y etiqueta se definen antes del split; las 2 variables condicionadas se excluyen; el split es estratificado y el test no se toca en tuning. |
| "¿Por qué el job se quedaba en `Preparing`?" | Faltaba `AcrPush` para el MSI del workspace; sin ese rol Azure ML no publica la imagen del environment y no reporta error. |
| "¿Por qué falló el `destroy` la primera vez?" | Application Insights crea el action group Smart Detection fuera de Terraform; se resolvió con `prevent_deletion_if_contains_resources = false` y `az group delete`. |

---

## 9. "Muéstrame en pantalla" (tenlo abierto)

1. `terraform/` → `main.tf`, `datafactory.tf`, `inference.tf`, `providers.tf`
   (backend y `prevent_deletion`).
2. `terraform output` y `terraform state list` (hoy vacío: explica el `destroy`).
3. `ml/data/load_enape.py` (cohorte y etiqueta) y `ml/pipeline/modeling.py`
   (`MODEL_FEATURES`).
4. `ml/pipeline/evaluate.py` (gate) y `outputs/metrics_enape.json`.
5. `endpoint/app.py` (contrato y `/predict`) + `docs/demo-curl-azure.md`.
6. `docs/dashboard.html` → "El conjunto de datos" y "Resultados del modelo".
7. `docs/guia-tecnica.md` §3 (etapas) y `docs/despliegue-azure.md` §5 (problemas
   frecuentes).

---

## 10. Cifras que no puedes dudar

| Dato | Valor |
|---|---|
| Crudo / cohorte | 32.343 × 67 → 18.207 × 21 |
| Positivos | 1.179 (6,48 %) · 127 duplicados (0,7 %) |
| Features | 18 en el contrato · 16 en el modelo |
| ROC-AUC / PR-AUC | 0,8617 / 0,4040 |
| Exactitud / F1 macro | 0,8578 / 0,6564 |
| `Continua` | P 0,978 · R 0,868 · F1 0,919 · 3.406 casos |
| `Abandona` | P 0,272 · R 0,712 · F1 0,393 · 236 casos |
| Gate | PR-AUC ≥ 0,35 · recall ≥ 0,60 · regresión ≤ 0,005 |
| Pruebas | 52/52 |
| Recursos | 27 en Terraform · 13 visibles en `az resource list` |
| Costo | ~9–10 USD/mes en reposo · 0,2–0,35 USD el relanzamiento |
| Corrida histórica (UCI) | job `mighty_nut_8jvyq81p06` · accuracy 0,7571 · F1 0,7022 |

---

## 11. Guion de cierre (30 s)

> "La plataforma está probada en local con ENAPE —18.207 estudiantes, PR-AUC
> 0,404, recall de abandono 0,712— y el entorno de Azure se validó el 17-11 con
> 27 recursos, job en `Completed` y endpoint respondiendo las cuatro pruebas.
> Hoy está destruido para no consumir crédito y se recrea con un comando. Lo que
> queda abierto lo digo sin adornos: CI/CD espera la service connection del
> tenant y el endpoint necesita HTTPS y red privada para producción."
