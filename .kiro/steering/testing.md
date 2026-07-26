# Arcus — Estrategia de testing

Contexto: hackatón de 8 días. El testing existe para **proteger la demo**, no para
alcanzar cobertura perfecta. Priorizamos las costuras que rompen la demo si fallan.

## Framework

- **pytest** + **pytest-mock**.
- **moto** para mockear AWS (S3, DynamoDB) sin tocar la nube.
- **responses** (o `respx`) para mockear la GitHub API.
- Bedrock siempre mockeado en unit/integration; las respuestas del LLM se cargan desde
  `tests/fixtures/bedrock/`. Nunca se llama a Bedrock real en CI.

## Pirámide (pragmática)

1. **Unit (la mayoría).** Lógica pura y determinista:
   - `graph/builder.py`: dado un repo pequeño de fixture, produce los nodos/aristas
     esperados.
   - `graph/query.py`: dado un grafo y archivos cambiados, devuelve el subgrafo correcto.
   - `contracts/`: validación de modelos (envelope válido/ inválido).
   - `github/webhook.py`: verificación de firma HMAC (firma buena, mala, ausente).
   - Parseo de la respuesta del LLM a `list[Finding]` (incluye respuestas malformadas).

2. **Integration (las costuras críticas).**
   - Handler de webhook end-to-end con moto + responses: recibe payload → arranca SFN
     (mock) → responde 202.
   - Cada agente Lambda: recibe un envelope de fixture → produce un envelope válido.
     Este test es el **contrato**: si un agente rompe el esquema, falla aquí.
   - `storage/history.py` contra DynamoDB de moto: escritura idempotente (dos writes
     con la misma clave no duplican).

3. **End-to-end (uno, manual/scripted para la demo).**
   - `scripts/replay_webhook.py`: reproduce un evento de PR real guardado y corre el
     pipeline completo contra un stack de `dev`. Es el ensayo de la demo.

## Reglas de oro

- **El test de contrato de cada agente es innegociable.** Como 4 personas trabajan en
  paralelo, el esquema del envelope es el punto de integración. Cada agente tiene un
  test que consume un envelope de entrada de fixture y valida el de salida contra el
  modelo Pydantic. Si esto pasa, los frentes integran sin sorpresas.

- **Fixtures compartidos en `tests/fixtures/`.** Un PR de ejemplo, un grafo de ejemplo,
  y respuestas de Bedrock de ejemplo. Todos los frentes usan los mismos, así que el
  frente de agentes puede trabajar sin el frente de GitHub y viceversa.

- **Determinismo.** Como el LLM no es determinista, los tests nunca afirman texto exacto
  del modelo; mockean la respuesta y prueban el *parsing* y el *flujo*.

## Qué NO testeamos (por tiempo)

- La calidad semántica de los hallazgos del LLM (se evalúa a mano en la demo).
- La definición de la state machine en sí (se valida ejecutándola en `dev`).
- Cobertura exhaustiva del dashboard (es solo lectura; smoke test manual).

## Comandos

```bash
uv run pytest tests/unit           # rápido, corre en cada commit
uv run pytest tests/integration    # antes de merge a main
uv run pytest -m contract          # solo los tests de contrato de agentes
```

Meta de cobertura: ~60% global, pero **100% de los tests de contrato de agentes verdes
en todo momento**. Un contrato roto bloquea el merge.
