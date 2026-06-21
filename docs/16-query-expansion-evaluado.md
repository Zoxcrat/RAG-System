# Etapa 16 — Query expansion: implementada, medida y… apagada (a propósito)

> Caso de **decisión basada en datos**: implementé una técnica conocida (multi-query /
> RAG-Fusion), la **medí**, vi que **empeoraba**, y decidí **no shippearla por defecto**.
> Esto es, en sí, buen material de entrevista: se mide antes de shippear.

---

## Qué es (la idea)
Si el usuario pregunta con **otras palabras** que las del catálogo ("¿qué sostiene el techo
interior?" vs "HANGER-HEADLINER"), una sola búsqueda puede fallar. **Query expansion**
(multi-query / RAG-Fusion): la IA genera **2-3 reformulaciones** de la pregunta, se busca con
**todas**, y se **fusionan** los resultados con RRF. Más ángulos sobre la misma pregunta =
más recall, en teoría.

## Cómo lo implementé
- `src/expand.py` — `expand_query`: pide N reformulaciones al LLM (falla abierto → si algo
  sale mal, devuelve solo la original).
- `src/retrieve.py` — `retrieve_multi`: corre la búsqueda híbrida para cada variante y
  **fusiona todas las listas con RRF** (el mismo que ya usábamos).
- `src/rag.py` — `ask` lo usa si está activado (flag `QUERY_EXPANSION_ENABLED`).
- `eval/evaluate.py` — agregué un **arm "expand+rerank"** para medir el impacto real.

## Lo que mostró la medición (`make eval`, 11 preguntas)

| Métrica | hybrid+rerank | **expand+rerank** |
|---|---|---|
| recall@5 | **0.909** | 0.818 ⬇ |
| mrr@5 | **0.730** | 0.685 ⬇ |
| recall@10 | 0.909 | 0.909 = |
| mrr@10 | **0.730** | 0.696 ⬇ |

**Empeoró** (o, en el mejor caso, empató).

## Por qué empeoró (la teoría)
Las preguntas del gold set **ya están bien formuladas** (usan términos cercanos al catálogo).
Cuando la pregunta original ya es buena, las paráfrasis **agregan ruido**: traen chunks
parecidos-pero-irrelevantes que **compiten en la fusión** y empujan al chunk correcto hacia
abajo. Es un modo de falla **conocido** del multi-query: ayuda cuando la pregunta está **mal
formulada**, pero **perjudica cuando ya es específica**.

## La decisión
- **Apagada por defecto** (`QUERY_EXPANSION_ENABLED=false`), porque **medido, perjudica**.
- **El código queda** (toggleable) — implementarla y medirla tiene valor; shippear algo que
  no ayuda, no.
- *Cómo se arreglaría bien (futuro):* **expansión adaptativa** — expandir **solo cuando la
  búsqueda original es débil** (la mejor distancia supera cierto umbral). Así no agrega ruido
  cuando la pregunta ya es buena, y ayuda solo cuando hace falta. (No se puede medir su
  beneficio con este gold set porque todas las preguntas están bien formuladas; haría falta
  sumar preguntas "mal formuladas" al set.)

## La moraleja (para la entrevista)
> "Implementé query expansion (RAG-Fusion), la medí con el harness de evaluación, y vi que
> **bajaba el recall** porque las preguntas ya eran específicas y las paráfrasis metían ruido.
> Así que la dejé **apagada por defecto pero toggleable**, y documenté que el camino correcto
> es **expansión adaptativa**. La gracia: **mido antes de shippear** — no agrego una técnica
> de moda solo porque suena bien."

## Dónde está
- `src/expand.py`, `src/retrieve.py` (`retrieve_multi`), `src/config.py` (flag, default off).
- `eval/evaluate.py` (arm `expand+rerank`), `tests/test_expand.py`.
