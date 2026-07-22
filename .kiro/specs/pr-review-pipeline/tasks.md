# Tasks — PR Review Pipeline

Plan para 8 días, 4 personas, trabajo paralelo desde el día 1. Cada frente lo toma una
persona. El objetivo: **MVP integrado y funcional al final del día 5-6**, días 7-8 para
pulir y ensayar la demo.

## La clave para paralelizar: contratos primero (Día 1, mañana, TODOS juntos)

Antes de dividirse, el equipo entero hace **una sola tarea conjunta** (2-3 horas). Esto
elimina el 90% de los bloqueos.

- [ ] 0. Congelar los contratos compartidos y los fixtures
  - Definir juntos `src/arcus/contracts/` (envelope.py, findings.py, graph.py) como
    modelos Pydantic, según `agent-contracts.md`. Solo firmas y esquemas, sin lógica.
  - Crear los fixtures compartidos en `tests/fixtures/`: 1 payload de webhook de ejemplo,
    1 envelope de ejemplo por etapa, 1 grafo de ejemplo, 2-3 respuestas Bedrock de ejemplo.
  - Acordar nombres de recursos AWS (ya en `structure.md`) y `config.py` (solo firmas).
  - Crear el repo, `pyproject.toml`, ruff/mypy/pytest configurados, CI mínima.
  - _Salida:_ todos pueden importar `arcus.contracts` y usar fixtures. A partir de aquí
    cada frente trabaja aislado contra fixtures.
  - _Requisitos:_ base de Req 1-7.

---

## Frente A — Infraestructura AWS + Orquestación (Persona 1)

Dueño de `infra/` y del `webhook_handler`. Desbloquea el despliegue de todos.

- [ ] A1. Scaffolding de IaC (SAM/CDK): bucket S3, tabla DynamoDB, roles IAM base, stack `dev`.
  - _Sin dependencias. Empieza día 1._ _Req: 2.3, 6.3._
- [ ] A2. Definir la state machine `pipeline.asl.json` con 5 estados + `FetchPR`, usando
  Lambdas **stub** (que devuelven el envelope de fixture sin cambios).
  - _Depende de: contrato del envelope (Tarea 0)._ _Req: 1.5._
- [ ] A3. Implementar `webhook_handler`: verificación HMAC, filtro de acción, dedup
  condicional en DynamoDB, guardado inicial, `StartExecution`.
  - _Depende de: A1 (tabla), Tarea 0 (envelope)._ _Req: 1.1-1.6, 7.5._
- [ ] A4. API Gateway HTTP API → `webhook_handler`; Secrets Manager para webhook secret.
  - _Depende de: A3._ _Req: 1.1, seguridad._
- [ ] A5. Configurar `Retry`/`Catch` en cada estado (Catch → siguiente agente) + estado
  `Pass` que marca `failed` desde `$.lastError`.
  - _Depende de: A2._ _Req: 7.1, 7.2, 7.4._
- [ ] A6. Reemplazar stubs por las Lambdas reales conforme los otros frentes entregan; IAM
  de mínimo privilegio por Lambda.
  - _Depende de: entregables de Frentes B, C._ _Integración._

**Puede avanzar solo con:** stubs que devuelven fixtures. No necesita la lógica real de
nadie para tener el pipeline "caminando" el día 2.

---

## Frente B — Agentes, prompts y grafo de contexto (Persona 2)

El corazón de Arcus. Dueño de `agents/`, `bedrock/`, `graph/`.

- [ ] B1. `bedrock/client.py`: `invoke_claude()` con retry/backoff y parseo de respuesta;
  mockeado en tests.
  - _Sin dependencias externas. Empieza día 1._ _Req: 7.2._
- [ ] B2. `graph/builder.py`: tree-sitter (Python) → networkx (nodos/aristas del esquema
  del design) + detección heurística de convenciones.
  - _Sin dependencias de otros frentes (usa un repo de fixture)._ _Req: 2.1, 2.5._
- [ ] B3. `graph/store.py` (serialización S3) + `graph/query.py` (subgrafo a 1 salto).
  - _Depende de: B2, A1 (bucket) para prueba real; unit con moto sin esperar a A1._
    _Req: 2.2, 2.3, 2.4._
- [ ] B4. Context Builder agent (handler) que usa B2/B3 y puebla `context` en el envelope.
  - _Depende de: B2, B3, Tarea 0._ _Req: 2.*, 7.3 (bandera diff-only)._
- [ ] B5. Consistency Checker: prompt + parseo a `Finding[]` de inconsistencias.
  - _Depende de: B1, Tarea 0. Usa subgrafo de fixture._ _Req: 3.*._
- [ ] B6. Bug Hunter: prompt + parseo a `Finding[]` de bugs/seguridad.
  - _Depende de: B1, Tarea 0._ _Req: 4.*._
- [ ] B7. Fix Suggester: recorre findings y puebla `fix`; maneja `skipped`.
  - _Depende de: B1, Tarea 0._ _Req: 5.*._
- [ ] B8. Test de contrato por agente (entra fixture → sale envelope válido) + modo
  diff-only en Consistency/Bug Hunter.
  - _Depende de: B4-B7._ _Req: 7.3, testing._

**Puede avanzar solo con:** fixtures de envelope y grafo. No necesita GitHub ni AWS real
para desarrollar y testear los agentes (Bedrock mockeado, S3 con moto).

---

## Frente C — Integración GitHub + Reporter (Persona 3)

Dueño de `github/`, `storage/` y el agente `Reporter`.

- [ ] C1. GitHub App: registro, permisos (PR read, contents read, issues write), webhook
  secret. Doc de setup.
  - _Sin dependencias de código. Empieza día 1 (tarea de configuración)._ _Req: 1._
- [ ] C2. `github/app_auth.py`: JWT de App → installation token (mockeable).
  - _Depende de: C1._ _Req: seguridad._
- [ ] C3. `github/api.py`: obtener diff + archivos cambiados; publicar/actualizar comentario
  (marcador oculto `<!-- arcus-review -->`).
  - _Depende de: C2. Tests con `responses`._ _Req: 6.1, 6.2._
- [ ] C4. `github/webhook.py`: verificación HMAC + parseo del evento (lo consume A3).
  - _Depende de: Tarea 0. Coordinar interfaz con Frente A._ _Req: 1.2, 1.3._
- [ ] C5. `storage/history.py`: escritura idempotente del run + dedup + queries para
  dashboard (contra DynamoDB de moto).
  - _Depende de: Tarea 0 (esquema); A1 para real, moto para dev._ _Req: 6.3, 7.5._
- [ ] C6. Reporter agent: render Markdown (agrupado por severidad, con fixes, bloque de
  etapas fallidas, caso "sin hallazgos") + publicar + persistir.
  - _Depende de: C3, C5._ _Req: 6.1-6.4, 7.4._
- [ ] C7. `FetchPR` Lambda (primer estado SFN): usa C3 para bajar diff a S3.
  - _Depende de: C3, A1._ _Req: 1.5 (envelope inicial)._

**Puede avanzar solo con:** `responses`/moto y fixtures. El `FetchPR` y el Reporter se
prueban con un envelope de fixture sin el resto del pipeline vivo.

---

## Frente D — Dashboard + Testing/Demo + Datos de prueba (Persona 4)

Dueño de `dashboard/`, `scripts/`, fixtures y la salud de la demo. Es el pegamento.

- [ ] D1. Curar el **repo de demo**: un repo Python realista con 2-3 PRs preparados que
  disparan hallazgos jugosos (un bug lógico, una inconsistencia de convención).
  - _Sin dependencias. Empieza día 1. Crítico para la demo._
- [ ] D2. Generar los fixtures compartidos junto al equipo (co-dueño de Tarea 0):
  envelopes por etapa, grafo de ejemplo, respuestas Bedrock realistas.
  - _Depende de: Tarea 0._
- [ ] D3. `dashboard/data.py` + `app.py`: leer DynamoDB (métricas por repo/tiempo,
  conteos por severidad, historial de PRs). Solo lectura.
  - _Depende de: esquema DynamoDB (Tarea 0/C5). Trabaja con datos sembrados por D4._
    _Req: 6.3._
- [ ] D4. `scripts/seed_history.py`: sembrar DynamoDB con runs de ejemplo para que el
  dashboard tenga datos sin necesitar el pipeline vivo.
  - _Depende de: esquema DynamoDB._ Desbloquea D3 sin esperar a nadie.
- [ ] D5. `scripts/replay_webhook.py`: reproduce un evento de PR guardado contra el stack
  `dev`. Es el driver del ensayo end-to-end.
  - _Depende de: A4 (endpoint) para real; puede prepararse antes._ _Req: testing E2E._
- [ ] D6. Guion de demo + ensayo end-to-end + smoke tests. Detectar y reportar roturas de
  integración temprano.
  - _Depende de: integración (día 5+)._

**Puede avanzar solo con:** nada. D1, D2, D4 arrancan el día 1 sin depender de código de
nadie, y sostienen a todos los demás frentes (fixtures y datos sembrados).

---

## Mapa de dependencias (resumen)

```
Tarea 0 (todos, día 1 AM)
   ├─► Frente A (infra + orquestación)  ──┐
   ├─► Frente B (agentes + grafo)         ├─► Integración (día 5-6): A6, C6, C7
   ├─► Frente C (github + reporter)      ─┘        │
   └─► Frente D (dashboard + demo)  ◄──── datos sembrados (D4) desacopla D del resto
                                              │
                                              ▼
                                    Ensayo demo (D5, D6) día 7-8
```

Dependencias reales (no artificiales):
- Todo depende de **Tarea 0** (contratos + fixtures). Por eso se hace primero y juntos.
- **A6** (Lambdas reales en la SFN) depende de que B y C entreguen sus handlers. Hasta
  entonces, stubs.
- **C6/C7** (Reporter, FetchPR) dependen de `github/api.py` (C3) y storage (C5).
- **D3** (dashboard) depende solo del **esquema** de DynamoDB, no del pipeline: se
  desacopla con **D4** (seed). Por eso D nunca se bloquea.

Lo que **NO** se bloquea entre sí (trabajo verdaderamente paralelo día 1-4):
- B desarrolla agentes con Bedrock mockeado + fixtures, sin AWS ni GitHub reales.
- C desarrolla GitHub/Reporter con `responses`/moto + fixtures, sin el pipeline vivo.
- A tiene el pipeline "caminando" con stubs el día 2, sin lógica de nadie.
- D construye dashboard sobre datos sembrados y cura el repo de demo, sin nada del resto.

---

## Cronograma sugerido

- **Día 1:** Tarea 0 (mañana, todos). Tarde: A1, B1/B2, C1, D1/D4 arrancan.
- **Día 2:** Pipeline caminando con stubs (A2-A5). B sigue con grafo/agentes. C con auth/api. D dashboard sobre seed.
- **Día 3-4:** Agentes reales (B4-B7), Reporter (C6), FetchPR (C7), dashboard (D3).
- **Día 5:** Integración: reemplazar stubs (A6), primer end-to-end real (D5).
- **Día 6:** MVP funcional end-to-end. Cerrar bugs de integración.
- **Día 7:** Pulir salida del reporte, dashboard, resiliencia (fallos de agente).
- **Día 8:** Ensayo de demo, colchón. **La demo debe estar lista, no construyéndose.**

---

## Qué recortar si el tiempo aprieta (sin romper la demo central)

La demo central e innegociable es: **PR abierto → comentario con hallazgos + fix →
dashboard muestra la métrica.** Todo lo siguiente es recortable en orden de prioridad:

1. **Actualización incremental del grafo (B3).** Recorte: reconstruir el grafo entero cada
   vez. Más lento pero más simple. La demo no lo nota.
2. **Fix Suggester (B7) como agente separado.** Recorte: fusionar el fix dentro del prompt
   del Bug Hunter (un solo LLM call que ya devuelve el fix). Menos agentes que orquestar.
3. **Dashboard rico (D3).** Recorte: una sola vista con conteo de findings por PR en el
   tiempo. Nada de filtros ni drill-down.
4. **Modo diff-only elaborado (7.3).** Recorte: si no hay grafo, simplemente reportar el
   fallo del Context Builder; no hace falta un modo degradado sofisticado para la demo.
5. **Snapshots históricos del grafo en S3.** Recorte: guardar solo `main.json`, sin
   `history/{sha}.json`.
6. **Actualizar comentario existente (6.2).** Recorte: siempre crear comentario nuevo. En
   la demo se abre un PR fresco, así que no se nota.
7. **Consistency Checker (Req 3) como agente separado.** Último recurso: si hay que elegir
   un solo agente de análisis para la demo, quedarse con **Bug Hunter + Fix** (el "wow" es
   encontrar un bug real y proponer el arreglo). Consistency es secundario.

Lo que **NO** se recorta porque es el núcleo de la demo: webhook → SFN → Context Builder
(aunque sea reconstrucción completa) → Bug Hunter → Reporter comenta el PR → una fila en
DynamoDB que el dashboard muestra.
