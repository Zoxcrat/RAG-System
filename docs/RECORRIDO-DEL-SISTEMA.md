# Recorrido del sistema (todo junto, en lenguaje claro)

> El "tour guiado" del proyecto: la **arquitectura**, **qué hace cada archivo** (en
> castellano, no en tecnicismos), **cómo se leyó el PDF y cómo se guardó**, y **cómo se
> arma una respuesta** de punta a punta. Si querés la versión con analogías puras, mirá
> `EXPLICACION-SIMPLE.md`; si querés el detalle técnico fino, los docs 00–14.

---

## 1. La arquitectura de un vistazo

El sistema tiene **dos momentos** muy distintos:

**Momento A — Preparar el catálogo (una sola vez).**
Agarramos el PDF escaneado, lo "leemos", lo cortamos en pedacitos y lo guardamos ordenado
en una base de datos. Esto es lento y se hace **una vez**.

**Momento B — Responder preguntas (cada vez que alguien pregunta).**
Llega una pregunta, buscamos los pedacitos relevantes, los ordenamos, y le pedimos a una IA
que responda **solo con eso**, citando la página. Esto es rápido y pasa **en cada pregunta**.

```
MOMENTO A (preparar):   PDF escaneado → leer (OCR) → cortar por página → guardar en la base
MOMENTO B (responder):  pregunta → buscar → ordenar → responder con cita → mostrar en la web
```

Y hay **dos grandes partes** de software:
- **El backend** (en Python): el "cerebro". Hace toda la lógica: leer el PDF, buscar, responder.
- **El frontend** (la web, en React): la "cara". El visor de PDF y el cuadro de preguntas.

---

## 2. Qué hace cada archivo (en castellano)

Pensá cada archivo como un **empleado con un solo trabajo**. Esa es, justamente, una decisión
de diseño: cada uno hace **una cosa**, así es fácil de entender y de cambiar.

### Los cimientos
- **`config.py`** — *la libreta de ajustes.* Todos los parámetros (qué modelo de IA usar,
  cuántos resultados traer, etc.) viven acá, en un solo lugar. Si hay que cambiar algo, se
  cambia acá y nada más.
- **`db.py`** — *el encargado de la base de datos.* Abre la conexión y arma los "estantes"
  (la tabla donde se guardan los pedacitos y sus índices para buscar rápido).

### Momento A — meter el PDF (la "ingesta")
- **`pdf_loader.py`** — *el lector/escáner.* Toma el PDF (que son **fotos** de páginas) y lo
  convierte en **texto**, página por página. (Esto es el "OCR".)
- **`embed.py`** — *el traductor a "idioma de búsqueda".* Convierte cada pedazo de texto en
  una lista de números que captura su **significado**. Eso es lo que después permite buscar
  por significado y no solo por palabra exacta.
- **`ingest.py`** — *el archivista.* Corta el texto **por página**, le pega a cada pedacito
  su número de página, y lo guarda en la base **sin duplicar**.

### Momento B — responder preguntas (la "consulta")
- **`retrieve.py`** — *el buscador.* Dada una pregunta, encuentra los pedacitos relevantes.
  Busca de **dos formas a la vez**: por significado y por palabra exacta, y combina ambas.
- **`rerank.py`** — *el experto que reordena.* De los ~20 candidatos que trajo el buscador,
  hace una segunda pasada más cuidadosa y pone los mejores arriba.
- **`rag.py`** — *el que arma la respuesta.* Junta los mejores pedacitos, le pone a la IA la
  regla "respondé solo con esto y si no está, decí que no sabés", y pide la respuesta con la
  cita de la página.
- **`api.py`** — *el mostrador de atención.* Es la puerta por la que la web le habla al
  cerebro: recibe la pregunta por internet y devuelve la respuesta. También entrega el PDF
  para el visor.
- **`main.py`** — *la versión por terminal.* Lo mismo pero sin web, para probar rápido.

### La web (frontend, carpeta `frontend/`)
- **`App.tsx`** — *el plano de la pantalla.* Arma el layout (visor a la izquierda, preguntas
  a la derecha) y recuerda **qué página se está mirando**.
- **`PdfViewer.tsx`** — *el visor de PDF* (con los botones de avanzar/retroceder e "ir a
  página").
- **`AskPanel.tsx`** — *el cuadro de preguntas y respuestas* (con sus estados: cargando,
  error, respuesta).
- **`citations.ts`** + **`AnswerText.tsx`** — *los que hacen la magia de las citas:* detectan
  el "[página N]" en la respuesta y lo convierten en un **botón** que salta el visor.
- **`api.ts`** / **`types.ts`** — *el cable* que conecta la web con el backend.

### La medición
- **carpeta `eval/`** — *el examen.* Un set de preguntas con respuesta conocida para **medir**
  qué tan bien busca el sistema (y demostrar que las mejoras sirvieron).

---

## 3. El viaje del PDF: de la foto escaneada a la base de datos

Esto es lo que pasa **una sola vez**, al preparar el catálogo:

1. **Tenemos un PDF que son fotos.** Es un escaneo viejo. Aunque parezca texto, para la
   computadora es una **imagen**. (El texto que el PDF trae "pegado" es basura, lo ignoramos.)
2. **Lo "leemos" página por página (OCR).** `pdf_loader.py` toma cada página como imagen y la
   pasa por un motor que reconoce el texto (Tesseract). Sale el texto de cada página.
   *(Como cuando tu celular reconoce el texto de una foto.)*
3. **Lo guardamos en un archivo de texto** (un JSON) para no tener que volver a leerlo: es el
   paso lento, se hace una vez.
4. **Lo cortamos en pedacitos, una página = un pedacito.** `ingest.py` corta el texto **por
   página**. ¿Por qué por página? Porque así **cada pedacito sabe de qué página salió** — y
   eso es lo que después permite la cita "[página N]" exacta.
5. **Lo traducimos a "idioma de búsqueda".** `embed.py` convierte cada pedacito en números
   que capturan su significado.
6. **Lo guardamos en la base de datos** (Postgres). Cada fila tiene: el texto, **el número de
   página**, y su "huella digital" (para no guardar dos veces lo mismo).

Resultado: el catálogo entero quedó convertido en una base **buscable**, donde cada pedacito
recuerda su página.

> **El hilo conductor (lo más importante del proyecto):** el **número de página** viaja con
> el pedacito desde que se lee el PDF, pasa a la base, después a la respuesta, y termina en el
> botón que te lleva a esa página. Si ese hilo se cortara en cualquier eslabón, se caería la
> función estrella (la cita que salta a la página exacta).

---

## 4. El viaje de una pregunta: del cuadro de texto a la respuesta con cita

Esto pasa **cada vez** que alguien pregunta:

1. **Escribís la pregunta** en la web y apretás "Ask". La web se la manda al backend (al
   "mostrador", `api.py`).
2. **Se buscan los pedacitos relevantes** (`retrieve.py`), de dos formas combinadas:
   - *por significado* (encuentra aunque uses otras palabras),
   - *por palabra exacta* (encuentra un número de parte o término literal).
3. **Se reordenan** (`rerank.py`): de ~20 candidatos, los mejores quedan arriba.
4. **Chequeo de honestidad:** si lo que se encontró no es lo bastante parecido a la pregunta,
   el sistema **no le pregunta a la IA** y responde "no tengo información suficiente". *(Así
   no inventa.)*
5. **Se arma la respuesta** (`rag.py`): se le pasan a la IA los mejores pedacitos con la
   instrucción de responder **solo con eso** y citar la página → la IA devuelve algo como
   *"Es el 0411680 [página 201]"*.
6. **La web la muestra y la vuelve interactiva:** detecta el "[página 201]", lo convierte en
   un **botón**, y al clickearlo **el visor salta a la página 201** del PDF.

Todo esto, en alrededor de un segundo.

---

## 5. Cómo se conecta todo (resumen de una frase)

> Leímos un catálogo escaneado y lo convertimos en una base **buscable que recuerda la página
> de cada dato**; cuando preguntás, **buscamos** (de dos formas), **reordenamos**,
> **respondemos solo con lo encontrado citando la página**, y la web vuelve esa cita un
> **botón que te lleva a verla**. El número de página es el hilo que une todo de punta a punta.

---

## 6. Chuleta: "¿qué hace el archivo X?" (para responder al toque)

| Archivo | En una línea |
|---|---|
| `config.py` | La libreta de ajustes (todos los parámetros juntos). |
| `db.py` | Conexión y "estantes" de la base de datos. |
| `pdf_loader.py` | Convierte el PDF-foto en texto (OCR). |
| `embed.py` | Traduce texto a números de significado (para buscar). |
| `ingest.py` | Corta por página y guarda sin duplicar. |
| `retrieve.py` | Busca los pedacitos relevantes (significado + palabra exacta). |
| `rerank.py` | Reordena para dejar los mejores arriba. |
| `rag.py` | Arma la respuesta con la regla de no inventar y la cita. |
| `api.py` | El mostrador: conecta la web con el cerebro. |
| `App.tsx` | El plano de la pantalla web. |
| `PdfViewer.tsx` | El visor del PDF. |
| `AskPanel.tsx` | El cuadro de preguntas/respuestas. |
| `citations.ts` + `AnswerText.tsx` | Convierten "[página N]" en un botón que salta. |
| `eval/` | El examen: mide qué tan bien busca. |

---

> **Cómo usar este doc para la entrevista:** si te preguntan "¿cómo está hecho?", contá los
> **dos momentos** (preparar el catálogo / responder preguntas) y el **hilo del número de
> página**. Si te preguntan por una parte puntual, tenés la chuleta de la sección 6. Y si
> quieren más profundidad, ahí bajás al doc técnico correspondiente.
