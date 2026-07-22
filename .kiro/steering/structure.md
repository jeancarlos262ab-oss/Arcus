# Arcus — Estructura del proyecto

Sistema multiagente que revisa Pull Requests de GitHub de forma autónoma usando
contexto persistente del repositorio.

## Layout de carpetas

```
arcus/
├── infra/                      # IaC: Step Functions, Lambdas, API GW, IAM, S3, DynamoDB
│   ├── template.yaml           # AWS SAM (o CDK) — recurso principal
│   ├── statemachine/
│   │   └── pipeline.asl.json   # Definición de la máquina de estados (Amazon States Language)
│   └── env/
│       ├── dev.json            # Parámetros por entorno
│       └── demo.json
│
├── src/
│   └── arcus/
│       ├── __init__.py
│       ├── config.py           # Carga de env vars, nombres de recursos, region, model id
│       ├── logging.py          # Setup de logging estructurado (JSON)
│       │
│       ├── contracts/          # Modelos Pydantic compartidos (el "lenguaje común")
│       │   ├── __init__.py
│       │   ├── envelope.py     # PipelineEnvelope: el JSON que viaja entre agentes
│       │   ├── findings.py     # Finding, Severity, Fix
│       │   └── graph.py        # RepoGraph, Node, Edge (esquema del grafo)
│       │
│       ├── agents/             # Un módulo por agente. Cada uno es un handler Lambda.
│       │   ├── __init__.py
│       │   ├── base.py         # BaseAgent: parseo de entrada, validación, manejo de error
│       │   ├── context_builder.py
│       │   ├── consistency_checker.py
│       │   ├── bug_hunter.py
│       │   ├── fix_suggester.py
│       │   └── reporter.py
│       │
│       ├── bedrock/            # Cliente Claude vía Bedrock + reintentos + parsing
│       │   ├── __init__.py
│       │   ├── client.py       # invoke_claude() con retry/backoff
│       │   └── prompts/        # Plantillas de prompt por agente (archivos .md/.txt)
│       │
│       ├── graph/              # Construcción y persistencia del grafo de contexto
│       │   ├── __init__.py
│       │   ├── builder.py      # tree-sitter -> networkx
│       │   ├── store.py        # serialización networkx <-> S3
│       │   └── query.py        # helpers para extraer sub-contexto relevante a un PR
│       │
│       ├── github/             # Cliente de GitHub App + verificación de webhook
│       │   ├── __init__.py
│       │   ├── webhook.py      # verificación de firma HMAC, parseo del evento
│       │   ├── app_auth.py     # JWT de GitHub App -> installation token
│       │   └── api.py          # get diff/files, post comment
│       │
│       ├── storage/            # Acceso a DynamoDB (historial y métricas)
│       │   ├── __init__.py
│       │   └── history.py      # put/query de resultados de revisión
│       │
│       └── entrypoints/        # Handlers Lambda "delgados" (webhook, arranque de SFN)
│           ├── __init__.py
│           └── webhook_handler.py
│
├── dashboard/                  # React + Vite + Tailwind + Recharts (SPA, solo lectura)
│   ├── src/
│   │   ├── App.tsx             # ensamblado del dashboard
│   │   ├── components/         # UI + charts (Recharts)
│   │   └── lib/                # tipos, tema, datos (DataSource: mock hoy, API real después)
│   └── package.json
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/               # PRs de ejemplo, repos pequeños, respuestas Bedrock mock
│
├── scripts/                    # utilidades locales (seed de grafo, replay de webhook)
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Principios de organización

- **`contracts/` es la fuente de verdad.** Cualquier dato que cruce el límite de un
  agente se define como modelo Pydantic ahí. Nadie inventa dicts sueltos.
- **Los handlers de `entrypoints/` y `agents/` son delgados.** Toda la lógica vive en
  módulos testeables (`graph/`, `github/`, `bedrock/`, `storage/`). Un handler solo:
  parsea entrada → llama lógica → devuelve el envelope validado.
- **`dashboard/` es solo lectura.** Nunca escribe en DynamoDB/S3; consume lo que el
  pipeline produjo. Así el frente de dashboard no bloquea a nadie.
- **`infra/` es propiedad de un solo frente** (Infra/Orquestación) para evitar conflictos
  de merge en la definición de la state machine.

## Nombres de recursos AWS (convención)

Prefijo `arcus-{env}-`:

- S3 bucket grafos: `arcus-{env}-context-graphs`
- DynamoDB historial: `arcus-{env}-review-history`
- State machine: `arcus-{env}-pr-pipeline`
- Lambdas: `arcus-{env}-agent-{nombre}` y `arcus-{env}-webhook`
