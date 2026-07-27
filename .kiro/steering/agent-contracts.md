# Arcus — Contratos de comunicación entre agentes

Este es el documento más importante para trabajar en paralelo. Define **el único JSON
que viaja entre agentes** dentro de Step Functions. Si se respeta este contrato, cada frente
integra con los demás sin coordinación adicional.

## Principio: un solo envelope que crece

En vez de que cada agente tenga un formato distinto, todos leen y escriben el mismo
objeto: el `PipelineEnvelope`. Cada agente **lee** las secciones que necesita y **anexa**
su resultado en su propia sección. Nadie sobreescribe el trabajo de otro.

El flujo es lineal:

```
Context Builder → Consistency Checker → Bug Hunter → Fix Suggester → Reporter
```

Step Functions pasa el envelope de un estado al siguiente. Cada agente recibe el
envelope completo y devuelve el envelope completo + su contribución.

## PipelineEnvelope (esquema)

```json
{
  "pipeline_run_id": "uuid",
  "created_at": "2026-07-21T10:00:00Z",
  "pr": {
    "repo_full_name": "owner/repo",
    "pr_number": 42,
    "commit_sha": "abc123",
    "base_commit_sha": "def456",
    "installation_id": 123456,
    "changed_files": ["src/a.py", "src/b.py"],
    "diff_ref": "s3://arcus-dev-context-artifacts/prs/owner/repo/42/diff.patch"
  },
  "context": {
    "status": "ok",
    "graph_ref": "s3://arcus-dev-context-artifacts/graphs/owner/repo/commits/def456.json",
    "graph_version": "commit-def456",
    "relevant_subgraph_ref": "s3://.../prs/owner/repo/42/subgraph.json",
    "conventions": {
      "naming": "snake_case",
      "error_handling": "custom exceptions",
      "notes": ["usa pydantic para DTOs", "logging estructurado"]
    },
    "error": null
  },
  "consistency": {
    "status": "ok",
    "findings": [ /* Finding[] */ ],
    "error": null
  },
  "bugs": {
    "status": "ok",
    "findings": [ /* Finding[] */ ],
    "error": null
  },
  "fixes": {
    "status": "ok",
    "findings": [ /* Finding[] con campo fix poblado */ ],
    "error": null
  },
  "report": {
    "status": "ok",
    "comment_url": "https://github.com/owner/repo/pull/42#issuecomment-1",
    "summary": "3 hallazgos: 1 alto, 2 medios",
    "error": null
  }
}
```

## Finding (esquema)

Es la unidad de hallazgo que producen Consistency Checker y Bug Hunter, y que enriquece
Fix Suggester.

```json
{
  "id": "uuid",
  "agent": "bug_hunter",
  "type": "logic_bug | security | inconsistency | convention_violation",
  "severity": "high | medium | low",
  "file": "src/a.py",
  "line_start": 40,
  "line_end": 52,
  "title": "Posible None dereference en parse_config",
  "rationale": "El repo siempre valida config con validate_config() antes de usarla; aquí se omite.",
  "evidence_refs": ["src/config.py:12", "src/loader.py:88"],
  "fix": {
    "description": "Llamar validate_config(cfg) antes de acceder a cfg.timeout",
    "suggested_diff": "@@ ... @@\n- return cfg.timeout\n+ validate_config(cfg)\n+ return cfg.timeout",
    "confidence": "high | medium | low"
  }
}
```

- Consistency Checker y Bug Hunter producen `Finding` **sin** `fix` (o con `fix: null`).
- Fix Suggester recorre los findings existentes y **puebla el campo `fix`**. No crea
  findings nuevos.
- Reporter solo **lee** todos los findings; no los modifica.

## Campo `status` y manejo de fallos (clave)

Cada sección de agente tiene `status`, que es uno de:

- `"ok"` — el agente corrió y produjo resultado.
- `"failed"` — el agente falló pero el pipeline **debe continuar** (degradación
  elegante). El campo `error` lleva `{code, message}`.
- `"skipped"` — no aplicaba (p. ej. no había findings que arreglar).

Regla: **el fallo de un agente intermedio no tumba el pipeline.** El agente atrapa su
propia excepción, escribe `status: "failed"` + `error`, y devuelve el envelope para que
el siguiente agente siga. El Reporter siempre corre y reporta lo que haya, indicando qué
etapas fallaron.

La única excepción: si **Context Builder** falla en producir un grafo mínimo, los agentes
posteriores no tienen contexto útil. En ese caso operan en "modo diff-only" (analizan
solo el diff sin contexto global) y lo marcan en el reporte.

Ver `design.md` del spec para el mapeo exacto a `Retry`/`Catch` de Step Functions.

## Reglas para trabajar en paralelo

1. **Nunca cambies el esquema del envelope sin avisar.** Es la interfaz compartida. Si
   necesitas un campo nuevo, es un cambio en `contracts/envelope.py` que todos revisan.
2. **Programa contra el modelo Pydantic, no contra el JSON crudo.** Importa desde
   `arcus.contracts`.
3. **Usa los fixtures compartidos.** Hay un envelope de ejemplo en cada etapa en
   `tests/fixtures/envelopes/`. Cada agente se puede desarrollar con la entrada de fixture
   sin esperar a que el agente anterior esté listo.
4. **Cada agente debe ser idempotente y puro respecto al envelope:** lee lo que necesita,
   anexa su sección, devuelve. No depender de estado externo mutable.
