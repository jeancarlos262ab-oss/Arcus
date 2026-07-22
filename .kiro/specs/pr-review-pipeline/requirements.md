# Requirements — PR Review Pipeline (feature end-to-end)

## Introducción

Primera feature end-to-end de Arcus: cuando se abre (o actualiza) un Pull Request en un
repositorio de GitHub donde está instalada la GitHub App de Arcus, el sistema recibe el
webhook, ejecuta el pipeline de agentes especializados usando el contexto persistente del
repositorio, y publica un comentario en el PR con los hallazgos (inconsistencias, bugs y
fixes sugeridos). Además registra el resultado para alimentar el dashboard de métricas.

Esta feature abarca el camino completo: webhook → orquestación → 5 agentes → comentario
en el PR + persistencia. Es el "esqueleto que camina" del hackatón; todo lo demás se
construye encima.

## Alcance (in / out)

**Dentro:** webhook de PR `opened`/`synchronize`, construcción/actualización del grafo de
contexto, los 5 agentes, comentario en el PR, persistencia de historial, degradación ante
fallo de un agente. Lenguaje de análisis inicial: **Python** (tree-sitter con parser de
Python).

**Fuera (esta feature):** UI del dashboard (solo persistimos los datos que consumirá),
multi-lenguaje más allá de Python, comentarios inline por línea (usamos un comentario
resumen), aprendizaje/feedback del usuario sobre hallazgos, soporte de repos privados a
escala. Ver `tasks.md` para qué es recortable.

## Requerimientos

### Requerimiento 1 — Recepción y validación del webhook

**Historia de usuario:** Como mantenedor de un repo, quiero que Arcus detecte
automáticamente cuando se abre o actualiza un PR, para no tener que dispararlo a mano.

#### Criterios de aceptación

1. CUANDO GitHub envía un evento `pull_request` con acción `opened` o `synchronize`,
   ENTONCES el sistema DEBERÁ responder con HTTP 202 en menos de 3 segundos y continuar
   el procesamiento de forma asíncrona.
2. CUANDO llega cualquier request al endpoint del webhook, ENTONCES el sistema DEBERÁ
   verificar la firma HMAC-SHA256 (`X-Hub-Signature-256`) contra el webhook secret ANTES
   de procesar el cuerpo.
3. SI la firma es inválida o falta, ENTONCES el sistema DEBERÁ responder HTTP 401 y no
   iniciar el pipeline.
4. CUANDO el evento es de un tipo o acción que no nos interesa (p. ej. `closed`, `labeled`),
   ENTONCES el sistema DEBERÁ responder HTTP 202 y no iniciar el pipeline.
5. CUANDO el webhook es válido y relevante, ENTONCES el sistema DEBERÁ iniciar una
   ejecución de la state machine con un `pipeline_run_id` único y un envelope inicial
   poblado con los datos del PR.
6. SI la misma combinación `repo + pr_number + commit_sha` ya tiene una ejecución en
   curso o completada, ENTONCES el sistema DEBERÁ evitar iniciar una ejecución duplicada
   (idempotencia).

### Requerimiento 2 — Contexto persistente del repositorio (grafo)

**Historia de usuario:** Como sistema de revisión, quiero mantener un mapa persistente del
repo, para analizar cada PR con contexto global sin releer todo el repo cada vez.

#### Criterios de aceptación

1. CUANDO se procesa un PR de un repo que aún no tiene grafo, ENTONCES el Context Builder
   DEBERÁ clonar/obtener el árbol del repo, parsear los archivos Python con tree-sitter y
   construir un grafo (módulos, símbolos, dependencias, convenciones detectadas).
2. CUANDO ya existe un grafo para el repo, ENTONCES el Context Builder DEBERÁ cargarlo
   desde S3 y actualizar solo lo afectado por el commit del PR, en lugar de reconstruir
   todo.
3. CUANDO el grafo se construye o actualiza, ENTONCES DEBERÁ persistirse en S3 con una
   versión asociada al `commit_sha`.
4. CUANDO se necesita analizar un PR, ENTONCES el sistema DEBERÁ extraer un subgrafo
   relevante (archivos cambiados + sus vecinos directos) para acotar el contexto que se
   envía al LLM.
5. SI el repo excede un tamaño máximo configurable, ENTONCES el Context Builder DEBERÁ
   limitar el parseo a los directorios afectados por el PR y marcarlo en el envelope.

### Requerimiento 3 — Análisis de consistencia arquitectónica

**Historia de usuario:** Como mantenedor, quiero saber si un PR rompe los patrones
establecidos del repo, para mantener la coherencia arquitectónica.

#### Criterios de aceptación

1. CUANDO el Consistency Checker recibe el envelope con contexto, ENTONCES DEBERÁ comparar
   el diff contra las convenciones y patrones detectados en el grafo.
2. CUANDO detecta una desviación, ENTONCES DEBERÁ producir un `Finding` de tipo
   `inconsistency` o `convention_violation` con archivo, líneas, título y `rationale`
   que cite evidencia del repo.
3. CUANDO no hay desviaciones, ENTONCES DEBERÁ devolver `status: "ok"` con lista de
   findings vacía.

### Requerimiento 4 — Detección de bugs con contexto

**Historia de usuario:** Como desarrollador, quiero que Arcus encuentre bugs reales
usando el contexto del resto del repo, no solo el diff aislado.

#### Criterios de aceptación

1. CUANDO el Bug Hunter recibe el envelope, ENTONCES DEBERÁ analizar el diff usando el
   subgrafo de contexto para detectar problemas lógicos o de seguridad.
2. CUANDO detecta un problema, ENTONCES DEBERÁ producir un `Finding` de tipo `logic_bug`
   o `security` con severidad y `rationale` que explique por qué es un problema en el
   contexto de este repo.
3. CUANDO no encuentra problemas, ENTONCES DEBERÁ devolver `status: "ok"` con findings
   vacíos.

### Requerimiento 5 — Sugerencia de fixes concretos

**Historia de usuario:** Como desarrollador, quiero que además de señalar el problema me
propongan un fix concreto, para resolverlo rápido.

#### Criterios de aceptación

1. CUANDO el Fix Suggester recibe findings de consistencia y bugs, ENTONCES DEBERÁ, para
   cada finding, poblar el campo `fix` con una descripción y un `suggested_diff`.
2. CUANDO un finding no admite un fix automatizable con confianza, ENTONCES DEBERÁ marcar
   `fix.confidence: "low"` y dar al menos una descripción textual.
3. CUANDO no hay findings que arreglar, ENTONCES DEBERÁ devolver `status: "skipped"`.
4. El Fix Suggester NO DEBERÁ crear findings nuevos; solo enriquece los existentes.

### Requerimiento 6 — Reporte en el PR y persistencia

**Historia de usuario:** Como mantenedor, quiero ver los hallazgos como un comentario en
el PR y que queden registrados para métricas, para actuar y hacer seguimiento.

#### Criterios de aceptación

1. CUANDO el Reporter recibe el envelope final, ENTONCES DEBERÁ sintetizar los findings en
   un comentario Markdown legible (agrupado por severidad, con fixes) y publicarlo en el PR
   vía GitHub API.
2. CUANDO ya existe un comentario previo de Arcus para ese PR, ENTONCES DEBERÁ actualizar
   ese comentario en vez de crear uno nuevo (idempotencia del comentario).
3. CUANDO se publica el reporte, ENTONCES DEBERÁ escribir un registro en DynamoDB con
   `repo`, `pr_number`, `commit_sha`, conteo de findings por severidad/tipo, estado de
   cada agente y timestamp.
4. SI no hubo ningún finding, ENTONCES el comentario DEBERÁ indicar explícitamente que no
   se detectaron problemas (evitar silencio).

### Requerimiento 7 — Resiliencia del pipeline

**Historia de usuario:** Como operador de la demo, quiero que si un agente falla el
pipeline no se caiga entero, para que la demo siempre produzca algo.

#### Criterios de aceptación

1. CUANDO un agente intermedio (Consistency, Bug Hunter, Fix Suggester) lanza una excepción
   no recuperable, ENTONCES su sección del envelope DEBERÁ marcarse `status: "failed"` con
   `error`, y el pipeline DEBERÁ continuar al siguiente agente.
2. CUANDO una llamada a Bedrock/S3/DynamoDB/GitHub falla por un error transitorio,
   ENTONCES el sistema DEBERÁ reintentar con backoff exponencial antes de marcarla como
   fallida.
3. SI el Context Builder no logra producir un grafo, ENTONCES los agentes posteriores
   DEBERÁN operar en "modo diff-only" y el reporte DEBERÁ indicar que se corrió sin
   contexto global.
4. CUANDO el Reporter corre, ENTONCES DEBERÁ publicar un comentario aunque una o más
   etapas hayan fallado, indicando qué etapas no completaron.
5. CUANDO cualquier etapa se ejecuta más de una vez (reintento), ENTONCES el efecto
   observable (comentario, fila en DynamoDB) DEBERÁ ser el mismo que una sola ejecución
   (idempotencia).

### Requerimiento 8 — Observabilidad mínima

**Historia de usuario:** Como equipo, quiero poder rastrear una ejecución de punta a
punta, para depurar durante el hackatón.

#### Criterios de aceptación

1. CUANDO cualquier componente emite un log, ENTONCES DEBERÁ incluir `pipeline_run_id`,
   `agent` y `pr_id` en formato JSON estructurado.
2. CUANDO una ejecución de la state machine termina (éxito o fallo), ENTONCES su estado
   DEBERÁ ser consultable (Step Functions console / historial en DynamoDB).
