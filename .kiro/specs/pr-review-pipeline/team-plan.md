# Plan de equipo — 4 personas, 8 días

Reparto por habilidad del equipo. Un dueño por frente. Todos participan en la
**Tarea 0** el día 1 por la mañana; después cada quien trabaja aislado contra fixtures
hasta la integración (día 5).

## Mapeo persona → frente

| Persona | Habilidad | Frente | Carpetas que posee |
|---------|-----------|--------|--------------------|
| **P1** | Frontend | **D** — Dashboard + Demo + Fixtures/Testing | `dashboard/`, `scripts/`, `tests/fixtures/` |
| **P2** | AWS | **A** — Infraestructura + Orquestación | `infra/`, `webhook_handler` |
| **P3** | Backend | **B** — Agentes + Grafo + Bedrock (núcleo) | `agents/`, `bedrock/`, `graph/` |
| **P4** | Integración externa | **C** — GitHub + Reporter + Storage | `github/`, `storage/`, Reporter, FetchPR |

**Nota sobre P1 (frente D):** este proyecto es backend/AWS-pesado. El dashboard solo
(React) toma ~2-3 días. Por eso P1 también es el **dueño de la demo, los fixtures y la
integración** — el rol de "pegamento" que sostiene a los otros 3 y caza roturas de
contrato. Es donde más valor aporta cuando los demás están inmersos en su frente.

---

## Día 1 (mañana) — TODOS juntos: Tarea 0 (2-3 h)

No se divide el trabajo hasta terminar esto:

- Definir `src/arcus/contracts/` (envelope.py, findings.py, graph.py) — solo esquemas Pydantic.
- Crear fixtures compartidos en `tests/fixtures/` (webhook, envelopes por etapa, grafo,
  respuestas Bedrock). **P1 lidera esto** porque es dueño de fixtures.
- Repo + `pyproject.toml` + ruff/mypy/pytest + CI mínima.
- Acordar nombres de recursos AWS.

**Regla:** nadie modifica el esquema del envelope después sin avisar a los 4. Es la interfaz.

---

## P1 — Frontend: Dashboard + Demo + Fixtures/Testing (Frente D)

**Dueño de:** `dashboard/`, `scripts/`, `tests/fixtures/`, y la salud de la integración.

Qué hace:
- D1: curar el **repo de demo** — un repo Python realista con 2-3 PRs preparados que
  disparan hallazgos jugosos (un bug lógico, una inconsistencia de convención). _Día 1. Crítico._
- D2: **liderar los fixtures** de la Tarea 0 (envelopes por etapa, grafo de ejemplo,
  respuestas Bedrock realistas). Todos dependen de esto para trabajar aislados.
- D4: `scripts/seed_history.py` — sembrar DynamoDB con runs de ejemplo. Esto **desacopla
  el dashboard del pipeline**: se puede construir toda la UI sin que nada más funcione todavía.
- D3: `dashboard/` (React + Vite + Tailwind + Recharts) — métricas por repo/tiempo, conteos
  por severidad, historial de PRs, drill-down de hallazgos. Solo lectura vía API sobre DynamoDB.
- D5: `scripts/replay_webhook.py` — el driver del ensayo end-to-end contra `dev`.
- D6: guion de demo + ensayo + smoke tests. Desde el día 5, P1 actúa como **integrador**:
  corre el end-to-end y avisa qué frente rompió el contrato.

**Trabaja aislado día 1-4:** con datos sembrados (D4) no depende de los demás frentes. El
dashboard puede estar visualmente listo el día 3-4 aunque el pipeline aún no corra.
**Extra si termina antes:** apoyar a P4 con el render Markdown del comentario del PR y a
P3 (el frente más cargado) con revisión de prompts.

---

## P2 — AWS: Infraestructura + Orquestación (Frente A)

**Dueño de:** `infra/`, `webhook_handler`, la state machine.

Qué hace:
- A1: Stack `dev` (S3, DynamoDB, roles IAM). _Día 1 tarde._
- A2: State machine con 6 estados usando Lambdas **stub** que devuelven el fixture.
  → Pipeline "caminando" el **día 2**, para que todos tengan dónde integrar.
- A3: `webhook_handler` (HMAC, filtro de acción, dedup condicional, StartExecution).
- A4: API Gateway + Secrets Manager.
- A5: `Retry`/`Catch` en cada estado (Catch → siguiente agente) + estado que marca `failed`.
- A6: reemplazar stubs por Lambdas reales según entregan P3 y P4; IAM mínimo por Lambda.

**Entrega crítica:** pipeline desplegable con stubs el día 2. No depende de la lógica de
nadie al principio. Es quien despliega, así que coordina los nombres de recursos con todos.

---

## P3 — Backend: Agentes + Grafo + Bedrock (Frente B, el núcleo)

**Dueño de:** `agents/`, `bedrock/`, `graph/`. Es el corazón técnico y el frente más pesado.

Qué hace:
- B1: `bedrock/client.py` — `invoke_model()` mediante Bedrock Converse con retry + parseo. _Día 1._
- B2: `graph/builder.py` — tree-sitter (Python) → networkx + detección de convenciones.
- B3: `graph/store.py` (S3) + `graph/query.py` (subgrafo 1 salto).
- B4: agente **Context Builder**.
- B5: agente **Consistency Checker**.
- B6: agente **Bug Hunter**.
- B7: agente **Fix Suggester**.
- B8: test de contrato por agente + modo diff-only.

**Trabaja aislado:** Bedrock mockeado + S3 con moto + fixtures (de P1). No necesita AWS ni
GitHub reales hasta integrar. **Es el frente más cargado**: si va tarde, P1 le apoya con
prompts y el primer recorte es fusionar Fix Suggester (B7) dentro de Bug Hunter.

---

## P4 — Integración externa: GitHub + Reporter + Storage (Frente C)

**Dueño de:** `github/`, `storage/`, agente `Reporter`, `FetchPR`.

Qué hace:
- C1: registrar la **GitHub App** (permisos, webhook secret) + doc de setup. _Día 1._
- C2: `github/app_auth.py` — JWT App → installation token.
- C3: `github/api.py` — bajar diff/archivos, publicar/actualizar comentario (marcador oculto).
- C4: `github/webhook.py` — verificación HMAC + parseo (lo consume P2 en A3; coordinar interfaz).
- C5: `storage/history.py` — escritura idempotente + dedup + queries del dashboard (que usa P1).
- C6: agente **Reporter** (render Markdown + publicar + persistir).
- C7: Lambda **FetchPR** (baja el diff a S3, primer estado de la SFN).

**Trabaja aislado:** `responses` + moto + fixtures. Reporter y FetchPR se prueban con un
envelope de fixture sin el pipeline vivo. **Está en el camino crítico de la demo** (el
comentario en el PR), así que P1 lo respalda con el render Markdown si hace falta.

---

## Cómo encajan (línea de tiempo)

| Día | P1 (Frontend/Demo) | P2 (AWS) | P3 (Backend/Agentes) | P4 (GitHub/Reporter) |
|-----|--------------------|----------|----------------------|----------------------|
| 1   | Tarea 0 (lidera fixtures) → D1/D4 | Tarea 0 → A1 | Tarea 0 → B1/B2 | Tarea 0 → C1 |
| 2   | D3 (sobre seed) | A2-A5 (stubs) | B2/B3 | C2/C3 |
| 3   | D3 | A5 | B4/B5 | C4/C5 |
| 4   | D5 (prep) | apoyo integración | B6/B7 | C6/C7 |
| 5   | D5 (E2E real, integrador) | A6 (Lambdas reales) | B8 | integración |
| 6   | MVP end-to-end funcional — cerrar bugs de integración (todos) |
| 7   | pulir: reporte, dashboard, resiliencia (todos) |
| 8   | ensayo de demo + colchón (todos) |

**Meta:** MVP funcional el día 6, no el 8. Días 7-8 para pulir y ensayar.

## Reglas de convivencia para no bloquearse

- Cada persona es dueña de sus carpetas (ver `structure.md`). `infra/` solo lo toca P2.
- El envelope y los `contracts/` son de todos: cualquier cambio se avisa a los 4.
- P1 mantiene los fixtures verdes; si un frente rompe el contrato, se detecta ahí.
- Si un frente termina antes, apoya a P3 (el más cargado) o a P1 con la demo.
- Ver `tasks.md` → "Qué recortar" para el orden de recortes si el día 6 se va tarde.
