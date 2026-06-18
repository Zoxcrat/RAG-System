# Cada archivo en detalle (qué hace, qué tiene adentro, lo relevante)

> Para cuando te pregunten por un archivo puntual ("¿qué hace `api.py`?"). Cada uno tiene:
> **qué hace** (su trabajo), **qué tiene adentro** (sus piezas) y **lo relevante** (la
> decisión o detalle que vale la pena saber). En lenguaje claro, nombrando las piezas reales
> por si querés conectar con el código.

---

# BACKEND (Python, carpeta `src/`)

## `config.py` — la libreta de ajustes
- **Qué hace:** guarda en **un solo lugar** todos los parámetros del sistema y es el único
  que lee la configuración del entorno (claves, datos de la base).
- **Qué tiene adentro:** los valores que se pueden tocar sin meterse en la lógica: qué modelo
  de IA usar, cuántos resultados traer (`top_k`), el umbral para decidir "no sé"
  (`RELEVANCE_THRESHOLD`), tamaño de los pedacitos, etc.
- **Relevante:** centralizar la config hace que cambiar un comportamiento sea cambiar **un
  número acá**, sin tocar diez archivos. Sus valores por defecto coinciden con la base de
  datos, así arranca sin configurar nada.

## `db.py` — el encargado de la base de datos
- **Qué hace:** abre la conexión a la base (Postgres) y arma los "estantes" donde se guarda
  todo.
- **Qué tiene adentro:** `get_connection` (abre la conexión) e `init_schema` (crea la tabla
  `documents` y los **índices** que hacen la búsqueda rápida: uno para buscar por significado,
  otro para buscar por palabra, y uno que evita guardar duplicados).
- **Relevante:** todo está hecho para poder correrse **muchas veces sin romper** (crea las
  cosas "solo si no existen"). Así agregar una columna nueva no rompe lo que ya estaba.

## `pdf_loader.py` — el lector/escáner
- **Qué hace:** toma el PDF (que son **fotos** de páginas) y lo convierte en **texto**, página
  por página. (Esto es el "OCR".)
- **Qué tiene adentro:** `extract_pages_from_pdf` (recorre el PDF, convierte cada página en
  imagen y le pasa el reconocedor de texto), y `save/load_extracted_text` (guarda el resultado
  en un archivo para no tener que volver a leerlo).
- **Relevante:** si una página falla, **no se cae todo** (la saltea y sigue). Y como leer las
  670 páginas es lo lento, se hace **una sola vez** y se guarda.

## `embed.py` — el traductor a "idioma de búsqueda"
- **Qué hace:** convierte texto en una lista de números que captura su **significado** (lo que
  permite buscar por idea, no solo por palabra).
- **Qué tiene adentro:** `embed_text` (traduce un texto) y `embed_texts` (traduce muchos de
  una, en tandas).
- **Relevante:** acá vivía **uno de los bugs reales** que encontré: el servicio de IA acepta
  como máximo 2048 textos por pedido; mandaba todos juntos y fallaba. Lo arreglé partiéndolos
  en **tandas**.

## `ingest.py` — el archivista
- **Qué hace:** corta el texto **por página**, le pega a cada pedacito su número de página, y
  lo guarda en la base **sin duplicar**.
- **Qué tiene adentro:** `chunk_text` (corta el texto en pedazos), `ingest_pages` (procesa las
  páginas del PDF), `ingest_file` (procesa texto plano), y una "huella digital" por pedacito
  (`content_hash`) para no guardar lo mismo dos veces.
- **Relevante:** **un pedacito = una página**. Esa decisión es la que permite que la cita
  "[página N]" sea exacta. Y la huella incluye el número de página, así el mismo texto repetido
  en dos páginas queda como **dos registros citables** distintos.

## `retrieve.py` — el buscador
- **Qué hace:** dada una pregunta, encuentra los pedacitos relevantes en la base.
- **Qué tiene adentro:** dos formas de buscar y una de combinarlas:
  - búsqueda **por significado** (`retrieve`),
  - búsqueda **por palabra exacta** (`_keyword_search`),
  - y el **combinador** (`reciprocal_rank_fusion`) que junta las dos listas en una sola.
  Todo eso lo orquesta `retrieve_hybrid`.
- **Relevante:** es el corazón de la **búsqueda híbrida**. Cada forma falla donde la otra es
  fuerte, así que juntas encuentran mucho más.

## `rerank.py` — el experto que reordena
- **Qué hace:** de los ~20 candidatos que trajo el buscador, hace una **segunda pasada más
  cuidadosa** y deja los mejores arriba.
- **Qué tiene adentro:** `rerank` (le pide a la IA que ordene los pasajes por relevancia) y
  `_parse_ranking` (interpreta esa respuesta de forma a prueba de errores).
- **Relevante:** está hecho para **fallar de forma segura**: si la IA se cuelga o responde
  raro, se queda con el orden anterior. Nunca puede empeorar la respuesta, solo mejorarla.

## `rag.py` — el que arma la respuesta
- **Qué hace:** junta los mejores pedacitos, le pone a la IA la regla de **no inventar**, y
  pide la respuesta con la cita de la página.
- **Qué tiene adentro:** `build_prompt` (arma las instrucciones + el contexto para la IA),
  el **chequeo de honestidad** (si lo encontrado no es bastante relevante, ni le pregunta a la
  IA), `generate_answer` (llama a la IA), y `ask` (orquesta todo: buscar → reordenar →
  responder).
- **Relevante:** acá vive la **regla anti-invención** y el formato exacto de la cita
  "[página N]" que después la web convierte en botón.

## `api.py` — el mostrador de atención (la puerta web)
- **Qué hace:** convierte el cerebro Python en un **servicio** al que la web le puede hablar
  por internet.
- **Qué tiene adentro:** **tres puertas (endpoints)**:
  - `/health` → "¿estás vivo?" (responde "ok"),
  - `/ask` → recibe la pregunta y devuelve la respuesta + las páginas + las fuentes,
  - `/pdf` → entrega el archivo PDF para que el visor lo muestre.
  Además: los **"moldes"** (`AskRequest`, `AskResponse`) que definen y **validan solos** lo que
  entra y sale (si mandás una pregunta vacía, la rechaza con un error claro); el permiso
  **CORS** (para que la web, que corre en otra dirección, pueda llamarlo); y el manejo de
  errores (devuelve un error prolijo en vez de explotar).
- **Relevante:** el "molde" de la respuesta (que cada fuente traiga su **número de página**)
  es justamente el **contrato** que hace que las citas salten a la página correcta. Abre una
  conexión a la base **por cada pregunta**; para mucha gente a la vez, el próximo paso sería
  un "pool" de conexiones.

## `main.py` — la versión por terminal
- **Qué hace:** lo mismo que la web pero **sin la web**: preguntás y respondés desde la
  consola. Sirve para probar rápido.
- **Qué tiene adentro:** `run_demo` (inicia la base, ofrece recargar datos, y entra en un bucle
  de pregunta/respuesta) y `_print_result` (muestra la respuesta con sus fuentes).
- **Relevante:** maneja bien las salidas (Ctrl+C, "exit") y no se cae si una pregunta falla.

---

# FRONTEND (la web, carpeta `frontend/src/`)

## `App.tsx` — el plano de la pantalla
- **Qué hace:** arma el layout (visor de PDF a la izquierda, cuadro de preguntas a la derecha)
  y **recuerda qué página se está mirando**.
- **Qué tiene adentro:** el estado `page` (la página actual, compartida entre el visor y el
  panel) y el armado de las dos secciones.
- **Relevante:** que la "página actual" viva **acá arriba** es lo que permite que, al clickear
  una cita en el panel, **el visor** (que está al lado) salte. Es la pieza que conecta ambos lados.

## `PdfViewer.tsx` — el visor del PDF
- **Qué hace:** muestra la página del PDF y deja navegar (anterior / siguiente / "ir a página").
- **Qué tiene adentro:** el componente que renderiza la página actual y los botones de
  navegación.
- **Relevante:** es un componente **"controlado"**: no decide solo qué página mostrar, muestra
  la que le dicen desde `App`. Por eso un click en una cita lo hace saltar sin esfuerzo.

## `AskPanel.tsx` — el cuadro de preguntas y respuestas
- **Qué hace:** el cuadro donde escribís, manda la pregunta al backend, y muestra la respuesta
  (con sus estados: cargando, error, vacío).
- **Qué tiene adentro:** el formulario, la lógica de enviar (`submitQuery`), los **ejemplos de
  preguntas** clickeables, y el armado de la respuesta con sus **páginas** y **fuentes**.
- **Relevante:** maneja los tres estados de una buena interfaz (cargando / error / respuesta) y
  al recibir la respuesta **salta automáticamente** a la primera página citada.

## `citations.ts` + `AnswerText.tsx` — la magia de las citas
- **Qué hacen:** detectan los "[página N]" dentro de la respuesta y los convierten en
  **botones** que saltan el visor.
- **Qué tienen adentro:** `parseAnswer` (parte el texto en "texto normal" y "citas") en
  `citations.ts`, y `AnswerText` (dibuja cada cita como un botón) en `AnswerText.tsx`.
- **Relevante:** `parseAnswer` es **lógica pura** y por eso está **testeada** (6 pruebas). El
  formato exacto "[página N]" que pide el backend es lo que hace que esto sea confiable.

## `api.ts` y `types.ts` — el cable con el backend
- **Qué hacen:** `api.ts` es el que **llama** al backend (la función `ask` y la URL del PDF);
  `types.ts` describe **la forma** de la respuesta que llega.
- **Relevante:** `types.ts` es un **espejo** del contrato de `api.py`: si el backend cambia la
  respuesta, acá se nota. Y `api.ts` muestra un **error legible** si el backend falla.

---

# MEDICIÓN (carpeta `eval/`)

## `eval/gold_set.json` y `eval/evaluate.py` — el examen
- **Qué hacen:** `gold_set.json` es la **lista de preguntas con su respuesta conocida**
  (la página correcta); `evaluate.py` corre el sistema sobre esas preguntas y **mide** cuántas
  emboca.
- **Qué tiene adentro:** el cálculo de "¿está la página correcta entre las primeras?" (recall)
  y "¿qué tan arriba está?" (MRR), comparando las tres versiones (básico / híbrido / con
  reordenamiento).
- **Relevante:** es lo que me deja decir **"mejoró de 45% a 91%"** con números, en vez de "a
  ojo". Se corre con `make eval`.

---

> **Cómo usarlo en la entrevista:** si te preguntan por un archivo, respondé con las **tres
> capas**: qué hace (una frase) → qué tiene adentro (las piezas) → lo relevante (la decisión).
> No hace falta el detalle del código; con esto mostrás que entendés **el rol de cada parte**.
