# Design — PR Review Pipeline

## Decisiones fijadas (cerradas, no re-discutir en el hackatón)

Estas eran las decisiones abiertas; quedan resueltas así para no perder tiempo:

1. **Lenguaje de análisis:** solo **Python** en el MVP (tree-sitter con parser Python).
2. **Formato de reporte:** **un comentario resumen** en el PR (no inline por línea).
3. **Disparadores:** `opened` y `synchronize` (revisa al abrir y en cada push).
4. **Diff:** se descarga en el estado `FetchPR` de Step Functions, no en el webhook handler.
5. **Envelope:** viaja entero entre estados; datos pesados por referencia S3.
6. **Fallo de agente:** `Catch` salta al siguiente agente; nunca aborta el pipeline.
7. **Contexto:** subgrafo a **1 salto** de los archivos cambiados.
8. **DynamoDB:** single-table, PK `REPO#owner/repo`, SK `RUN#...` / `DEDUP#...`.
9. **Step Functions:** tipo **Standard**.
10. **Agentes:** los **5 quedan separados** (el pitch es "multiagente especializado").
    Fusionar Fix Suggester en Bug Hunter solo si el día 6 la integración va tarde.
11. **Seguridad del endpoint:** público + firma HMAC obligatoria (no IAM/VPC).
12. **Secretos:** AWS Secrets Manager.

## Visión general

El pipeline es una orquestación lineal en AWS Step Functions disparada por un webhook de
GitHub. Un envelope JSON viaja entre 5 Lambdas (una por agente), cada una enriqueciendo su
sección. El contexto del repo vive como grafo en S3; el historial de revisiones en
DynamoDB; el dashboard (React + Vite) lee ambos en modo solo lectura vía una API HTTP.

```
GitHub PR event
      │  (webhook HTTPS, firmado HMAC)
      ▼
API Gateway ──► Lambda webhook_handler
                    │ 1. verifica firma
                    │ 2. filtra acción (opened/synchronize)
                    │ 3. dedup por (repo,pr,sha)
                    │ 4. guarda diff en S3
                    │ 5. StartExecution(SFN, envelope inicial)
                    ▼
        ┌─────────────── Step Functions: arcus-{env}-pr-pipeline ───────────────┐
        │                                                                        │
        │  ContextBuilder ─► ConsistencyChecker ─► BugHunter ─► FixSuggester ─► Reporter
        │       │                                                                │
        │   (S3 grafo)                                                    (GitHub API + DynamoDB)
        └────────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
        Comentario en el PR  +  fila en DynamoDB  ──►  Dashboard (React, read-only)
```

Todas las Lambdas comparten el paquete `arcus` (código en `src/arcus/`), desplegado como
capa o incluido en el bundle. Cada Lambda tiene un handler delgado en `agents/` que llama
a la lógica testeable.

---

## Componentes

### 1. Ingreso: API Gateway + `webhook_handler` (Lambda)

- **API Gateway** (HTTP API) con una ruta `POST /webhook`. Timeout corto.
- **`webhook_handler`** hace lo mínimo para responder rápido (Req 1.1, <3s):
  1. Verifica `X-Hub-Signature-256` (HMAC-SHA256 con el webhook secret de Secrets Manager).
  2. Parsea el evento; si acción ∉ {`opened`, `synchronize`} → 202 sin más (Req 1.4).
  3. Dedup: escritura condicional en DynamoDB con clave `(repo#pr, sha)`; si ya existe,
     no arranca (Req 1.6, 7.5).
  4. Descarga el diff del PR (GitHub API) y lo guarda en S3 (`.../prs/.../diff.patch`).
     *Nota:* si el diff es grande, esto puede acercarse al presupuesto de 3s; ver
     "Decisión: dónde se obtiene el diff" abajo.
  5. Construye el `PipelineEnvelope` inicial y hace `StartExecution` en Step Functions.
  6. Responde 202.

**Decisión: dónde se obtiene el diff.** Para respetar los <3s, el handler solo guarda
punteros ligeros (repo, pr, sha) y arranca la SFN; el **primer estado de la SFN**
(un paso "Fetch PR") descarga el diff y lo sube a S3. Así el handler nunca se bloquea por
un diff grande. El envelope inicial lleva `diff_ref` que se poblará en ese primer paso.

### 2. Orquestación: Step Functions (Standard)

Máquina de estados `Standard` (no Express) porque las corridas pueden durar minutos por
las llamadas al LLM y queremos historial de ejecución completo para depurar.

Estados (todos tipo `Task` que invocan Lambda, más `Pass`/`Choice` de control):

1. `FetchPR` — descarga diff + lista de archivos cambiados → escribe `pr.diff_ref`,
   `pr.changed_files`.
2. `ContextBuilder`
3. `ConsistencyChecker`
4. `BugHunter`
5. `FixSuggester`
6. `Reporter` (siempre se ejecuta)
7. `Done` (Succeed)

Ver "Manejo de fallos" para los bloques `Retry`/`Catch`.

### 3. Agentes (5 Lambdas)

Cada agente sigue el patrón `BaseAgent`: `parse(event) -> Envelope`, `run(envelope) ->
Envelope`, con un `try/except` que convierte fallos en `status:"failed"` sin lanzar (salvo
errores de infra que sí deben reintentarse a nivel SFN).

- **Context Builder** (`graph/`): usa tree-sitter para parsear Python, construye/actualiza
  el grafo networkx, lo persiste en S3, extrae el subgrafo relevante y lo referencia.
- **Consistency Checker**: carga subgrafo + convenciones, arma prompt, llama Claude,
  parsea a `Finding[]`.
- **Bug Hunter**: igual, enfocado en lógica/seguridad con contexto.
- **Fix Suggester**: recorre findings existentes, llama Claude para proponer `fix`.
- **Reporter**: renderiza Markdown, publica/actualiza comentario en GitHub, escribe fila
  en DynamoDB.

### 4. Persistencia
- **S3** (`arcus-{env}-context-graphs`): grafos, subgrafos y diffs.
- **DynamoDB** (`arcus-{env}-review-history`): historial + dedup + métricas.

### 5. Dashboard (React + Vite + Tailwind + Recharts)
SPA que consume una API HTTP de solo lectura sobre DynamoDB (métricas por repo/tiempo).
Nunca escribe. Hoy corre con una capa de datos simulados (`MockDataSource`) que imita el
esquema real, así que se desarrolla completo sin el pipeline vivo; conectar la API real es
cambiar una sola implementación de `DataSource`.

---

## Esquema del grafo de contexto (S3)

### Layout de S3

```
arcus-{env}-context-graphs/
├── graphs/{owner}/{repo}/main.json          # grafo actual del branch base
├── graphs/{owner}/{repo}/history/{sha}.json # snapshots por commit (opcional)
├── prs/{owner}/{repo}/{pr}/diff.patch        # diff del PR
└── prs/{owner}/{repo}/{pr}/subgraph.json     # subgrafo relevante extraído
```

### Formato del grafo (networkx → JSON node-link)

Serializamos con `networkx.node_link_data` (JSON estándar de networkx). Estructura lógica:

```json
{
  "schema_version": "1",
  "repo": "owner/repo",
  "graph_version": "commit-def456",
  "built_at": "2026-07-21T10:00:00Z",
  "language": "python",
  "directed": true,
  "conventions": {
    "naming": "snake_case",
    "error_handling": "custom_exceptions",
    "test_framework": "pytest",
    "notes": ["DTOs con pydantic", "logging estructurado"]
  },
  "nodes": [
    {
      "id": "src/config.py::load_config",
      "kind": "function",              // module | class | function | method
      "file": "src/config.py",
      "name": "load_config",
      "line_start": 10,
      "line_end": 24,
      "signature": "def load_config(path: Path) -> Config",
      "docstring_present": true
    }
  ],
  "links": [
    {
      "source": "src/loader.py::run",
      "target": "src/config.py::load_config",
      "type": "calls"                  // calls | imports | inherits | defines
    }
  ]
}
```

**Tipos de nodo:** `module`, `class`, `function`, `method`.
**Tipos de arista:** `imports`, `calls`, `inherits`, `defines`.
**Convenciones detectadas:** heurísticas simples del Context Builder (estilo de nombres
dominante, presencia de excepciones custom, framework de test). No pretende ser perfecto;
alimenta el prompt del Consistency Checker.

### Extracción del subgrafo relevante

Dado `changed_files`, el subgrafo incluye: los nodos definidos en esos archivos, sus
vecinos a 1 salto (quién los llama / a quién llaman / de quién heredan). Esto acota el
contexto que se manda al LLM (Req 2.4) y es la clave anti-alucinación: el LLM ve el
vecindario real, no el repo entero ni solo el diff.

---

## Esquema DynamoDB (historial y métricas)

Tabla única `arcus-{env}-review-history` con patrón de acceso por repo y por PR, más
dedup. On-demand billing.

### Claves

- **PK** (`pk`): `REPO#{owner}/{repo}`
- **SK** (`sk`): varía por tipo de ítem (single-table design ligero):
  - Registro de revisión: `RUN#{created_at}#{pr_number}`
  - Marca de dedup: `DEDUP#{pr_number}#{commit_sha}`

### Ítem: registro de revisión

```json
{
  "pk": "REPO#owner/repo",
  "sk": "RUN#2026-07-21T10:00:00Z#42",
  "item_type": "review_run",
  "pipeline_run_id": "uuid",
  "pr_number": 42,
  "commit_sha": "abc123",
  "created_at": "2026-07-21T10:00:00Z",
  "agent_status": {
    "context": "ok",
    "consistency": "ok",
    "bugs": "failed",
    "fixes": "ok",
    "report": "ok"
  },
  "findings_summary": {
    "total": 3,
    "by_severity": { "high": 1, "medium": 2, "low": 0 },
    "by_type": { "logic_bug": 1, "inconsistency": 2 }
  },
  "comment_url": "https://github.com/owner/repo/pull/42#issuecomment-1",
  "ran_diff_only": false
}
```

### Ítem: dedup (idempotencia, Req 1.6 / 7.5)

```json
{
  "pk": "REPO#owner/repo",
  "sk": "DEDUP#42#abc123",
  "item_type": "dedup",
  "pipeline_run_id": "uuid",
  "status": "in_progress | completed",
  "ttl": 1753128000
}
```

Se escribe con `ConditionExpression: attribute_not_exists(sk)`. Si falla la condición, ya
hay una corrida para ese `(pr, sha)` → no se arranca otra. TTL limpia marcas viejas.

### Patrones de consulta (para el dashboard)

- Métricas de un repo en el tiempo: `Query pk = REPO#... AND begins_with(sk, "RUN#")`.
  Como el SK empieza con timestamp ISO, sale ordenado cronológicamente gratis.
- Última revisión de un PR: query + filtro por `pr_number` (o GSI si hace falta; se puede
  recortar).

---

## Contrato JSON entre agentes (Step Functions)

El objeto que pasa de estado a estado es el `PipelineEnvelope` completo (definido en
`.kiro/steering/agent-contracts.md`). Puntos de diseño específicos de la orquestación:

- **Entrada de cada Task = salida del anterior.** No usamos `ResultPath` para fusionar
  parcialmente; cada Lambda recibe el envelope entero y devuelve el envelope entero. Esto
  simplifica el razonamiento (una sola forma de dato) a costa de payloads algo más grandes.
- **Límite de payload de Step Functions (256 KB).** Por eso los datos pesados (grafo,
  subgrafo, diff) NO van inline en el envelope: van por **referencia S3** (`graph_ref`,
  `relevant_subgraph_ref`, `diff_ref`). El envelope solo lleva punteros + findings. Los
  findings de un PR normal caben de sobra; si un PR gigante generara demasiados, el
  Reporter trunca al renderizar.
- **Envelope inicial** (lo crea el webhook handler):

```json
{
  "pipeline_run_id": "uuid",
  "created_at": "2026-07-21T10:00:00Z",
  "pr": {
    "repo_full_name": "owner/repo",
    "pr_number": 42,
    "commit_sha": "abc123",
    "installation_id": 123456,
    "changed_files": [],
    "diff_ref": null
  },
  "context":     { "status": "pending", "error": null },
  "consistency": { "status": "pending", "findings": [], "error": null },
  "bugs":        { "status": "pending", "findings": [], "error": null },
  "fixes":       { "status": "pending", "findings": [], "error": null },
  "report":      { "status": "pending", "error": null }
}
```

`FetchPR` puebla `pr.changed_files` y `pr.diff_ref`; cada agente cambia su `status` de
`pending` a `ok`/`failed`/`skipped`.

---

## Manejo de fallos (sin tumbar el pipeline)

Dos capas, alineadas con `python-conventions.md`.

### Capa 1 — dentro del agente (degradación elegante)

Cada agente distingue:
- **Error de negocio/LLM** (no pudo producir hallazgos, respuesta malformada tras
  reintentos): atrapa, escribe `status:"failed"` + `error:{code,message}` en su sección,
  y **devuelve normalmente** (la SFN lo ve como éxito y avanza). Esto cubre Req 7.1.
- **Error de infra transitorio** (throttling Bedrock, 5xx S3): el decorador `@with_retries`
  reintenta internamente. Si se agota, puede propagarse a la Capa 2.

### Capa 2 — Step Functions `Retry` / `Catch`

Cada estado `Task` de agente lleva:

```json
{
  "Retry": [
    {
      "ErrorEquals": ["TransientError", "Lambda.ServiceException", "Lambda.TooManyRequestsException"],
      "IntervalSeconds": 2,
      "BackoffRate": 2.0,
      "MaxAttempts": 3
    }
  ],
  "Catch": [
    {
      "ErrorEquals": ["States.ALL"],
      "ResultPath": "$.lastError",
      "Next": "<siguiente_agente>"
    }
  ]
}
```

Clave: el `Catch` de un agente intermedio apunta al **siguiente agente**, no a un estado
de fallo. Así, aun si una Lambda revienta por completo (p. ej. OOM), el pipeline salta al
siguiente y termina en el Reporter. Antes de saltar, un pequeño estado `Pass`/función
marca la sección correspondiente como `failed` usando `$.lastError` (Req 7.1, 7.4).

### Reporter siempre corre

`Reporter` no tiene `Catch` hacia adelante (es el último). Tiene `Retry` propio para la
publicación en GitHub. Renderiza lo que haya en el envelope, incluyendo un bloque
"Etapas con problemas" cuando alguna sección está `failed` (Req 7.4). Si Reporter mismo
falla del todo tras reintentos, la SFN termina en `Fail` y queda registrado en el historial
de ejecución (Req 8.2).

### Modo diff-only (Req 7.3)

Si `ContextBuilder` no logra un grafo, escribe `context.status:"failed"` y setea una
bandera `context.ran_diff_only = true`. Consistency/Bug Hunter detectan la ausencia de
subgrafo y arman el prompt solo con el diff, marcando en sus findings que se corrió sin
contexto global. El Reporter lo señala en el comentario.

### Idempotencia (Req 7.5)

- **Comentario:** Reporter busca un comentario previo de Arcus (marcador oculto
  `<!-- arcus-review -->`) y hace update en vez de create.
- **DynamoDB:** el registro de run usa `pipeline_run_id`; el dedup usa
  `(pr, sha)` con escritura condicional. Un reintento no duplica.

---

## Seguridad

- Webhook secret y GitHub App private key en **Secrets Manager**, nunca en el repo.
- Verificación HMAC obligatoria antes de procesar (Req 1.2/1.3).
- El endpoint de API Gateway es público por naturaleza (GitHub debe alcanzarlo); la
  autenticación real es la **firma HMAC**, no IAM. Esto es intencional y debe quedar claro:
  sin firma válida → 401.
- IAM de mínimo privilegio por Lambda: cada agente solo con permisos a los recursos que
  toca (Reporter escribe DynamoDB y llama GitHub; Context Builder lee/escribe S3; etc.).
- Tokens de instalación de GitHub App son de vida corta; se generan por corrida, no se
  persisten.

---

## Decisiones técnicas y trade-offs

- **Standard vs Express Workflows:** Standard, por duración (minutos) y trazabilidad.
- **Envelope entero entre estados:** más simple de razonar y testear; el costo (payload)
  se mitiga con referencias S3.
- **Single-table DynamoDB:** un solo recurso que crear/permisos que dar; suficiente para
  los patrones de acceso de la demo.
- **Subgrafo a 1 salto:** balance entre contexto útil y tamaño de prompt/costo de tokens.
  Ampliable a 2 saltos si sobra tiempo.
- **Un comentario resumen** en vez de comentarios inline: más rápido de implementar y más
  robusto para la demo. Inline queda como mejora post-MVP.
