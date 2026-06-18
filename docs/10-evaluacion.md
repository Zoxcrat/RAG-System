# Etapa 10 — Evaluación del retrieval (vector vs híbrido)

Hasta acá medíamos "a ojo". Esta etapa pone **números**: ¿cuánto mejoró realmente la
búsqueda híbrida ([[09-busqueda-hibrida]])? Es la pregunta que todo entrevistador hace
("¿cómo sabés que mejoró?").

## Metodología

- **Gold set** (`eval/gold_set.json`): 11 preguntas in-domain + 2 out-of-domain. El
  **ground truth es por construcción**: la(s) página(s) cuyo texto OCR contiene la
  respuesta, verificadas contra `data/cessna_172_ocr.json`. Son preguntas distribuidas
  por todo el catálogo (págs. 33, 121, 199, 201, 202, 203, 241, 360, 481, 601).
- **Métricas** (`eval/evaluate.py`, `make eval`):
  - **recall@k**: fracción de preguntas donde una página correcta aparece en el top-k.
    Mide **cobertura** (¿está el dato entre lo recuperado?).
  - **MRR@k** (Mean Reciprocal Rank): promedio de `1/(rank de la primera página correcta)`.
    Mide **orden** (¿qué tan arriba está?).
  - **Gate**: las out-of-domain deben ser **rechazadas** (sin llamar al LLM).
- Se comparan dos arms: `retrieve` (vector puro) vs `retrieve_hybrid` (vector + keyword + RRF).

## Resultados (2026-06-16)

| Métrica | Vector-only | Híbrido | Δ |
|---|---|---|---|
| **recall@5** | 0.455 | **0.727** | **+0.27** |
| **recall@10** | 0.455 | **0.818** | **+0.36** |
| MRR@5 | 0.364 | 0.382 | +0.02 |
| MRR@10 | 0.364 | 0.391 | +0.03 |

- **Out-of-domain:** 2/2 rechazadas (el gate funciona).
- **Rescates** (preguntas que el vector perdía y el híbrido recupera): headliner hanger
  (rank 10), parte 0411680 (rank 3), dorsal assembly (rank 5), overhead console support
  (rank 3).

## Interpretación (lo importante para defender)

1. **El híbrido casi duplica el recall@10** (0.45 → 0.82). El arm léxico encuentra datos
   que el embedding sepulta en chunks densos. Es la mejora central, ahora **medida**.
2. **El MRR casi no se mueve.** Es coherente, no contradictorio: los rescates entran en
   **ranks profundos** (5–10), así que suben la *cobertura* pero no el *orden*. 
3. **Esto señala el próximo paso con precisión: reranking.** Un cross-encoder re-puntúa el
   top-k fusionado y empuja el hit rescatado a rank 1–2 → ahí **el MRR debería saltar**.
   El eval ya está listo para medir esa mejora (no hay que adivinar).
4. **Limitaciones honestas:** 2 preguntas fallan en ambos arms (radio shelf p202, rear
   baggage panel p33) — probablemente desajuste de wording/OCR. Candidatas a query
   expansion o mejor chunking.

## Por qué importa medir (conceptos)
- **Sin métrica, "mejoró" es una anécdota.** Con un gold set chico (11 preguntas) ya se
  distingue una mejora real de una percibida, y se evita una **regresión** silenciosa.
- **recall vs MRR**: separan dos preguntas distintas (¿está? vs ¿está arriba?). Un sistema
  puede subir una y no la otra — justo lo que pasó acá.
- **Ground truth barato y defendible**: derivarlo del texto fuente (la página que contiene
  la respuesta) evita etiquetar a mano y es reproducible.
- **El eval es una herramienta de tuning**: con esto se pueden barrer `top_k`, `RRF_K`,
  `candidates` y quedarse con lo que sube las métricas, en vez de elegir por intuición.

## Dónde está
- `eval/gold_set.json` — preguntas + páginas correctas + tipo.
- `eval/evaluate.py` — corre ambos arms, calcula recall@k / MRR@k, chequea el gate.
- `make eval` — levanta Postgres y corre la evaluación (necesita `OPENAI_API_KEY`).

## Próximos pasos en esta línea
- **Reranking** (cross-encoder) — el eval ya mide el impacto esperado en MRR.
- **Ampliar el gold set** (20–30 preguntas, incluir multi-página y casos negativos).
- **Faithfulness** de la generación (LLM-judge: ¿la respuesta se sostiene en el contexto citado?).
