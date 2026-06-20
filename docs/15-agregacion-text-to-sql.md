# Etapa 15 — Preguntas de agregación (tabla estructurada + text-to-SQL)

> Resuelve la debilidad que mostró la entrevista: preguntas de **agregación** ("¿cuántas
> costillas?", "listá TODOS los adhesivos", "¿la fijación más común?"). El RAG por
> recuperación no puede con eso **por diseño**; acá sumamos un segundo camino.

---

## El problema (por qué el RAG clásico no puede)

El RAG semántico hace **"buscar y leer"**: recupera los ~10 fragmentos más parecidos y
responde. Perfecto para **un dato puntual**, imposible para **agregar**:
- "Listá TODOS los adhesivos" → necesita ver **todo** el catálogo, no 10 fragmentos.
- "¿Cuántas costillas?" / "¿la fijación más común?" → necesita **contar/agrupar** sobre todo.

El top-k **nunca ve el corpus completo**. Es un límite estructural, no un bug.

## La idea: el catálogo es una base de datos

Un catálogo de partes es **datos estructurados** (una gran tabla: nº de parte, descripción,
página). Las preguntas de agregación son, en el fondo, **consultas SQL**. Entonces:

1. **Extraemos la estructura** → tabla `parts(part_number, description, page_number, figure)`.
2. **Clasificamos la intención** → ¿es agregación o búsqueda puntual? (router)
3. **Text-to-SQL** → la IA escribe **una** consulta `SELECT` sobre `parts`.
4. **Candados** → se ejecuta solo si es segura.
5. **La IA redacta** la respuesta desde las filas, citando `[página N]`.
6. **Fallback** → si la SQL no encuentra filas, **volvemos al camino semántico**.

## Las piezas y su teoría

### 1. Extracción estructurada (`src/parts.py`)
Un parser por **línea** detecta `nº-parte  DESCRIPCIÓN` y le asocia la **figura/sección**
(de los títulos "Figure N. ...") para poder **scopear** (ej. costillas *del ala*). Resultado:
**7225 partes**, 7033 con figura.
- *Límite honesto:* la sección de **materiales/consumibles** (adhesivos, selladores) está en
  un layout de **columnas separadas** que el OCR parte en líneas distintas → el parser por
  línea no la captura. Por eso el **fallback** (abajo) es clave.

### 2. Router de intención (`is_aggregation_query`)
Una llamada barata al LLM clasifica: **AGGREGATE** (contar/listar todo/más común/total) vs
**LOOKUP** (un dato puntual). Es el patrón de **enrutamiento por intención**: distintos tipos
de pregunta van a distintos motores.

### 3. Text-to-SQL (`generate_sql`)
La IA traduce la pregunta a **una** consulta PostgreSQL sobre `parts` (le damos el esquema y
pistas: usar `ILIKE`, scopear por `figure`, incluir `page_number` para citar).

### 4. Candados de seguridad (`is_safe_select`) — **nunca confiar en la SQL generada**
La consulta solo corre si: empieza con `SELECT/WITH`, es **una sola** sentencia (sin `;`), no
contiene palabras de escritura (`INSERT/UPDATE/DELETE/DROP/...`), y va **contra `parts`**.
Además se ejecuta en una **transacción read-only** y con `LIMIT`. Defensa en profundidad
contra inyección SQL.

### 5. Redacción + 6. Fallback
La IA arma la respuesta desde las filas, citando páginas. Y si la SQL **no devuelve filas**
(`ok=False`), el sistema **cae al camino semántico** — así "listá adhesivos" termina
encontrándolos en las págs. 72-73 igual.

## Flujo
```
pregunta → ¿agregación? ─sí→ text-to-SQL sobre parts → ¿filas? ─sí→ respuesta + [página N]
                │                                          └─no→ ↓
                └─no──────────────────────────────────────────→ RAG semántico (híbrida+rerank+gate)
```

## Resultados (las preguntas de la entrevista, por HTTP)
- **"¿La fijación más común? ¿Phillips vs hex vs torx?"** → "el screw es la más común" + **honesto:
  el catálogo no especifica el tipo de cabeza** (Phillips/hex/torx = 0 en las descripciones).
- **"¿Cuántas costillas por ala?"** → conteo por página con citas `[página N]`.
- **"Listá todos los adhesivos"** → (SQL vacío → fallback) lista LOCTITE 5381, EPOXY BASE,
  EC2216B/A... citando **[página 72, 73]**.
- **"¿Qué es la parte 0411680?"** (puntual) → ruteada a búsqueda → "HANGER~HEADLINER [página 201]".

## Límites honestos (buen material de entrevista)
- La **calidad de la SQL varía** (la IA a veces agrupa de más/de menos). Mejorable con
  ejemplos en el prompt o validación de resultados.
- "Costillas **por lado**" es difícil de dar como **un número exacto** (hay variantes LH/RH y
  estaciones; el OCR de las cantidades es ruidoso). Se listan con su página.
- La **sección de materiales** (columnas) no entra a `parts`; la cubre el fallback semántico.
  Lo ideal a futuro: OCR con **layout** (que entienda columnas) o parseo de tablas.

## Dónde está
- `src/parts.py` — extracción + tabla `parts` (`ingest_parts`).
- `src/aggregate.py` — router, text-to-SQL, candados, ejecución read-only, redacción, fallback.
- `src/rag.py` — `ask` rutea: agregación (con filas) vs semántico.
- `src/db.py` — tabla `parts`. `src/ingest.py` — la reconstruye al ingerir el catálogo.
- `tests/test_parts.py`, `tests/test_aggregate.py` — extracción + candados (pura, sin DB/API).

## Conceptos clave (para la entrevista)
- **Agregación vs recuperación:** dos problemas distintos; el RAG por top-k solo sirve al segundo.
- **Structured RAG / text-to-SQL:** convertir texto en datos consultables para responder
  "cuánto/cuántos/todos/el más común".
- **Nunca ejecutar SQL generada sin candados** (solo lectura, una sentencia, tabla fija, LIMIT).
- **Enrutar por intención + fallback:** usar el motor correcto según la pregunta, y degradar
  con elegancia cuando uno no aplica.
