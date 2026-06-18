# Etapa 9 — Búsqueda híbrida (vector + keyword) con RRF

Mejora de **recall** sobre el baseline. Resuelve el caso que falló en la validación
end-to-end ([[08-validacion-end-to-end]]): "headliner hanger" → ahora responde
`0411680 [página 201]`.

## El problema (recall del vector puro)
El dato `0411680 HANGER~HEADLINER` está en la pág. 201, pero **sepultado** en un chunk
de 500 chars lleno de números de parte: su embedding queda "diluido" y el coseno no lo
prioriza → no entraba al top-k. Pero `HEADLINER`/`HANGER` son **tokens literales**, justo
lo que una búsqueda **léxica** agarra bien. La idea de la búsqueda híbrida: combinar el
arm **semántico** (vector) y el **léxico** (keyword), que fallan en lugares distintos.

## Decisiones técnicas y teoría

### 1. Keyword con full-text nativo de Postgres
Columna `tsvector` **generada y STORED** + índice **GIN** (en `db.py`). Cero infra nueva
(coherente con "un solo sistema"). `GENERATED ALWAYS AS ... STORED` se mantiene sola y se
computa para las filas existentes → **no hubo que re-ingestar**.
- **`tsvector`/`to_tsvector`**: parsea el texto a *lexemas* (tokens stemmeados: "headliner"
  → `headlin`). **`@@`** matchea contra una `tsquery`. **`ts_rank`** puntúa la relevancia.

### 2. Fusión con Reciprocal Rank Fusion (RRF)
`score(doc) = Σ_arm 1 / (k + rank_arm)` (k=60, del paper original). 
- **Por qué RRF y no sumar scores:** la distancia coseno (0–2, menor=mejor) y `ts_rank`
  (0–1, mayor=mejor) **no son comparables**. RRF usa solo el **rank**, no el score, así
  que combina ambos sin normalizar. Es el método estándar (Elastic, etc.).
- Implementado como **función pura** (`reciprocal_rank_fusion`) → testeable sin DB.

### 3. El gate anti-alucinación sigue siendo vectorial
Un hit solo-keyword no tiene distancia coseno (`distance=None`); el gate usa la **mínima
distancia entre los que sí la tienen**. Así el keyword **amplía recall** pero no puede
saltear el gate fuera de dominio (la pregunta de Francia sigue bloqueada).

## Dos bugs/sutilezas que aparecieron al implementarlo

### A. El ruido de OCR rompe la tokenización
`HANGER~HEADLINER` tokeniza como `hanger` + **`~headliner`** (¡la tilde pegada al lexema!),
que nunca matchea `headlin`. **Fix:** la columna generada hace
`regexp_replace(content, '[~=|]+', ' ', 'g')` **antes** de `to_tsvector` — normaliza el
ruido OCR sin tocar el `content` que se muestra/cita. (Los `-` se dejan: el parser ya
indexa `0512029-8` entero **y** partido.)

### B. AND vs OR: el chunking parte los términos
`websearch_to_tsquery` usa **AND** por defecto (`part & number & headlin & hanger`). Pero
el header "PART NUMBER" y la fila "HANGER HEADLINER" caen en **chunks distintos** (ventana
de 500), así que ningún chunk tiene los 4 términos → 0 matches. **Fix:** reescribir a **OR**
(`replace(...::text,'&','|')::tsquery`). `ts_rank` igual premia a los que matchean más
términos; el arm vectorial + el gate sostienen la precisión.

## La tensión recall/precisión (top_k 5 → 10)
Con OR, "hanger"/"part"/"number" son comunes → la pág. 201 quedaba en **rank 4 del keyword**
pero afuera del top-5 fusionado. Observación clave: a **top_k=8** el LLM contestaba un
*hanger equivocado* de otra página (respuesta **confiada pero incorrecta**, peor que "no
info"); a **top_k=10** entra la 201 y el LLM **desambigua bien** (el chunk dice literal
"HANGER~HEADLINER"). Por eso `DEFAULT_TOP_K = 10`: más contexto para que el rescate del
keyword llegue. Costo: sigue siendo fracciones de centavo con `gpt-4o-mini`.

## Resultado (validado por HTTP)
- "What is the part number for the headliner hanger?" → **0411680 [página 201]** (antes: "no info").
- **Búsqueda por número de parte** `0411680` → "HANGER~HEADLINER [página 201]" (capacidad nueva, ideal para un catálogo).
- Regresión OK (stringer → pág. 199); gate OK (Francia → bloqueado). **49 tests passing.**

## Dónde está el código
- `src/db.py` — columna `tsv` generada (con `regexp_replace`) + índice GIN.
- `src/retrieve.py` — `_keyword_search` (OR), `reciprocal_rank_fusion` (pura), `retrieve_hybrid`.
- `src/rag.py` — `ask` usa `retrieve_hybrid`; `_min_distance` ignora `None`.
- `src/config.py` — `RETRIEVAL_CANDIDATES` (20/arm), `RRF_K` (60), `DEFAULT_TOP_K` (10).
- `tests/test_hybrid_retrieve.py` — RRF puro + shape del SQL keyword.

## Conceptos clave (para la entrevista)
- **Híbrida = semántica + léxica**: el vector entiende *significado*; el keyword agarra
  *tokens exactos* (números de parte, siglas). Se cubren las fallas mutuas.
- **RRF** combina rankings de scores incomparables sin normalizar.
- **El recall depende de la calidad del texto**: el ruido de OCR y el chunking por ventana
  son las verdaderas causas raíz; el fix ataca ambas (normalización + OR + top_k).
- **Próximo paso natural:** **reranking** con cross-encoder sobre el top-k fusionado, y
  **chunking estructural** (por fila) para no partir header/fila.
