# Arcus — Convenciones de código Python

Objetivo: código legible y consistente entre 4 personas que trabajan en paralelo, con
manejo de errores robusto en todo lo que toque AWS/Bedrock (donde fallan las cosas).

## Versión y herramientas

- Python 3.12.
- Formateo: **ruff** (formatter + linter). Nada de discusiones de estilo a mano.
- Tipado: **mypy** en modo estricto para `src/arcus/contracts/`, `graph/`, `github/`.
- Config en `pyproject.toml`. Correr `ruff check --fix` y `mypy` antes de cada commit.

## Type hints (obligatorio)

- Toda función pública lleva type hints completos en parámetros y retorno.
- Nada de `Any` salvo en el borde crudo de un parseo externo (payload de webhook,
  respuesta HTTP). En cuanto entra al sistema se convierte a un modelo Pydantic.
- Preferir tipos concretos (`list[Finding]`) sobre genéricos vagos (`list`, `dict`).

```python
def build_repo_graph(repo_path: Path, languages: list[str]) -> RepoGraph:
    ...
```

## Modelos de datos: Pydantic v2

- Todo dato que cruce un límite (Lambda↔Lambda, agente↔agente, servicio↔servicio)
  es un modelo Pydantic definido en `src/arcus/contracts/`.
- Serialización a Step Functions: `model.model_dump(mode="json")`.
- Deserialización en el handler: `Envelope.model_validate(event)`.
- Los modelos validan en el borde; el resto del código asume datos ya válidos.

## Docstrings

- Estilo **Google**. Toda función pública y clase lleva docstring.
- Debe explicar el *por qué* / contrato, no repetir la firma.

```python
def query_relevant_subgraph(graph: RepoGraph, changed_files: list[str]) -> RepoGraph:
    """Extrae el subgrafo de contexto relevante a un conjunto de archivos.

    Recorre dependientes y dependencias directas (1 salto) de los archivos
    modificados para dar al LLM contexto acotado sin mandar el repo entero.

    Args:
        graph: Grafo completo del repo cargado desde S3.
        changed_files: Rutas relativas de los archivos tocados por el PR.

    Returns:
        Un subgrafo con los nodos vecinos relevantes. Vacío si no hay match.
    """
```

## Manejo de errores

Regla base: **fallar con contexto, nunca en silencio.** Excepciones tipadas propias en
`arcus.errors`:

- `TransientError` — reintentable (throttling, timeout de red, 5xx).
- `PermanentError` — no reintentar (payload inválido, 4xx de config, auth mal).
- `AgentError` — un agente no pudo producir hallazgos pero el pipeline puede continuar.

Nunca capturar `except Exception: pass`. Si se captura, se loguea con contexto y se
re-lanza como uno de los tipos de arriba, o se convierte en un resultado degradado
explícito (`status="failed"` en el envelope, ver `agent-contracts.md`).

## Reintentos en llamadas a AWS / Bedrock

Toda llamada de red a Bedrock, S3, DynamoDB o GitHub usa retry con backoff exponencial
+ jitter. Dos capas:

1. **Nivel código** — decorador `@with_retries` sobre las funciones de I/O, para
   throttling y errores transitorios que no queremos que suban a Step Functions.
2. **Nivel Step Functions** — bloques `Retry`/`Catch` en la ASL como red de seguridad
   entre estados (ver `agent-contracts.md`).

Parámetros por defecto:

- Bedrock: 5 intentos, base 2s, máx 30s, jitter completo. Reintentar en
  `ThrottlingException`, `ModelTimeoutException`, `ServiceUnavailable`.
- DynamoDB/S3: usar retries nativos de boto3 en modo `adaptive` (config del cliente)
  + una capa fina propia para operaciones idempotentes.
- GitHub: respetar `Retry-After` en 403/429; máx 3 intentos.

```python
from arcus.retry import with_retries
from arcus.errors import TransientError

@with_retries(max_attempts=5, base_delay=2.0, max_delay=30.0)
def invoke_claude(prompt: str, *, max_tokens: int = 4096) -> str:
    try:
        resp = bedrock.invoke_model(...)
    except bedrock.exceptions.ThrottlingException as e:
        raise TransientError("Bedrock throttled") from e
    return _extract_text(resp)
```

- Toda escritura debe ser **idempotente** (usar `pr_id` + `commit_sha` como clave) para
  que un reintento no duplique comentarios ni filas.

## Logging

- Logging estructurado JSON (`arcus.logging`). Nada de `print()`.
- Cada log de agente incluye `correlation_id` (= `pipeline_run_id`), `agent`, `pr_id`.
- No loguear secretos, tokens de instalación, ni el diff completo (solo tamaños/hashes).

## Config

- Toda config vía variables de entorno leídas una vez en `config.py`. Nada de
  constantes hardcodeadas de nombres de recursos dispersas en el código.
- Secretos (GitHub App private key, webhook secret) vienen de AWS Secrets Manager,
  nunca del repo.
