# Etapa 11 — Reranking con LLM

Mejora del **orden** del retrieval. La evaluación ([[10-evaluacion]]) mostró que la
búsqueda híbrida sube el recall pero deja los hits en ranks profundos (el MRR casi no se
movía). El reranking ataca justo eso.

## El problema (orden, no cobertura)
Híbrido recupera el chunk correcto, pero a veces en rank 8–10. El embedding y el
`ts_rank` son **rápidos pero gruesos**: comparan pregunta y pasaje por separado. Un
**reranker** mira el par (pregunta, pasaje) **junto** y decide cuán relevante es —
mucho más preciso, pero caro, así que corre solo sobre un puñado de candidatos.

## Diseño y decisiones

### 1. LLM como reranker (no cross-encoder local)
- El reranker "de manual" es un **cross-encoder** (sentence-transformers, ms-marco). Pero
  mete **torch (~1–2 GB)** en la imagen Docker → bloat enorme para una demo.
- Reusamos `gpt-4o-mini` como reranker **listwise**: una sola llamada con los candidatos
  numerados, pidiendo el orden como array JSON. **Cero dependencia nueva**, ~$0.0002/query.
- *Trade-off honesto (entrevista):* en producción usaría un cross-encoder dedicado o
  **Cohere Rerank** (más rápido/barato por query, determinista). Acá priorizo no inflar
  la imagen y reusar el stack.

### 2. Robustez: parser puro + fail-open
- `_parse_ranking` (función **pura**, testeada) convierte la respuesta del LLM en una
  **permutación completa** de los candidatos: lee los enteros, descarta inválidos y
  duplicados, y **agrega los que el modelo omitió** en su orden original. Un ranking
  alucinado/parcial **nunca puede tirar un candidato**.
- `rerank` **falla abierto**: si la API o el parseo fallan, queda el **orden híbrido**.
  El reranking solo puede mejorar, nunca romper una respuesta.

### 3. El gate corre antes del rerank
En `ask`: se recuperan `RERANK_CANDIDATES` (20), se aplica el **gate de relevancia sobre
los candidatos**, y solo si pasa se rerankea a `top_k` (10). Así una pregunta
out-of-domain se rechaza **sin gastar** una llamada de reranking.

## Flujo
```
query → retrieve_hybrid (20 candidatos) → [gate de relevancia]
      → rerank con LLM (listwise) → top-10 → generación con [página N]
```

## Resultado medido (`make eval`, 2026-06-16)

| Métrica | vector | híbrido | **híbrido+rerank** |
|---|---|---|---|
| recall@5 | 0.455 | 0.727 | **0.909** |
| recall@10 | 0.455 | 0.818 | **0.909** |
| MRR@5 | 0.364 | 0.382 | **0.685** |
| MRR@10 | 0.364 | 0.391 | **0.685** |

- **El MRR casi se duplica** (0.39 → 0.69): el reranking arregla el **orden**, como
  predijimos. Narrativa completa: *híbrido = recall, rerank = ranking*.
- **recall@5 → 0.91**: empuja hits profundos al top-5 (headliner 10→2, dorsal 5→1).
- **Bonus**: el rerank reordena el pool **ancho de 20**, no solo el top-10 — por eso
  recupera "rear baggage panel" (p33), que el híbrido perdía en su top-10.
- **Límite honesto**: "radio shelf" (p202) sigue fallando — **no entra ni al top-20**, así
  que el rerank no puede ayudar. Es gap de *retrieval* (no de orden) → query expansion o
  mejor chunking. El reranker **solo reordena lo que el retrieval ya trajo**.

## Dónde está
- `src/rerank.py` — `rerank` (listwise, fail-open) + `_parse_ranking` (puro).
- `src/rag.py` — `ask` recupera 20 → gate → rerank → top_k.
- `src/config.py` — `RERANK_ENABLED`, `RERANK_CANDIDATES` (20), `RERANK_MODEL`.
- `tests/test_rerank.py` — parser puro + reorder/fail-open mockeado.
- `eval/evaluate.py` — tercer arm "hybrid+rerank".

## Conceptos clave (para la entrevista)
- **Bi-encoder vs cross-encoder**: el retrieval usa bi-encoders (embeddings precomputados,
  rápidos, comparables por coseno); el reranker mira el par junto (cross-encoder/LLM), más
  preciso pero sin precomputar → solo sobre top-N.
- **Recall vs ranking**: dos problemas distintos. Híbrido subió recall; rerank subió MRR.
  Medir ambos lo dejó **demostrado**, no intuido.
- **El reranker no arregla el retrieval**: si el dato no está en el pool de candidatos, no
  hay rerank que lo traiga (caso p202). Por eso recall del retrieval sigue importando.
- **Fail-open** como patrón: una mejora opcional no debe poder degradar el camino feliz.
