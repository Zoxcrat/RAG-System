# Demo en vivo, mejoras a futuro y el tema de los diagramas

> Tres cosas para la entrevista: **qué preguntas mostrar en vivo** (y qué demuestra cada
> una), **qué mejoraría a futuro**, y **el tema de los diagramas del PDF** (qué pasa hoy y
> qué haría después). En lenguaje claro.

---

## 1. Preguntas para la demo en vivo

Estas están **probadas** y funcionan bien. La respuesta exacta de la IA puede variar un
poquito en las palabras, pero **la cita de página es confiable** (es lo que importa mostrar).

### Guion recomendado (3 preguntas, ~2 minutos)

**1) Una pregunta normal → muestra la cita que salta a la página.**
> *"What stringer assembly is listed for the aft cabin top?"*
- Qué pasa: responde con los números de parte y cita **[página 199]**.
- Qué mostrás: hacés **click en la cita** y el visor **salta a la página 199**. Esa es la
  función estrella: respuesta + verificación visual en un click.

**2) Búsqueda por número de parte → muestra que también encuentra al revés.**
> *"What is part number 0411680?"*
- Qué pasa: responde que es el **"HANGER~HEADLINER" [página 201]**.
- Qué mostrás: que no solo busca por significado, también por **dato exacto** (le diste un
  número y te dijo qué es y dónde está). Eso es la **búsqueda híbrida** en acción.

**3) Una pregunta fuera de tema → muestra que NO inventa.**
> *"What is the capital of France?"*
- Qué pasa: responde **"no tengo información suficiente"** (no llama a la IA).
- Qué mostrás: la parte de **confianza/seguridad**: el sistema **admite cuando no sabe** en
  vez de improvisar. En aviación, esto es clave.

> **Cierre del guion:** "Respuesta verificable + búsqueda por significado y por dato exacto +
> nunca inventa." Esos son los tres pilares.

### Otras preguntas que andan bien (de reserva)
- *"What is the part number for the headliner hanger?"* → **0411680 [página 201]** (buen caso:
  el dato estaba "sepultado" y lo encuentra gracias a híbrida + reordenamiento).
- *"Where is the dorsal assembly listed?"* → **[página 203]**.
- *"What is the part number for the wing spar assembly?"* → cita su página.

### ⚠️ Para evitar en la demo en vivo
- Preguntas demasiado genéricas o con términos que aparecen en mil páginas (ej. "screws",
  "bolts") → traen ruido.
- Hay **un caso conocido que falla** ("radio shelf", página 202): el dato no entra ni en la
  lista de candidatos. **No lo uses en vivo**, pero si te preguntan por límites, es un buen
  ejemplo honesto (ver sección 2).

> **Tip clave:** **probá estas 3-4 preguntas vos mismo antes de entrar**, con el sistema
> prendido, para que no haya sorpresas en vivo.

---

## 2. Mejoras / qué propondría a futuro

Ordenadas por impacto, en lenguaje claro. La idea es mostrar que **sé qué falta y por qué**,
sin sobre-ingeniería.

### Para que encuentre todavía mejor (calidad de búsqueda)
- **"Reformular la pregunta" antes de buscar (query expansion).** Algunos datos no se
  encuentran porque la pregunta usa otras palabras que el catálogo (caso "radio shelf").
  Generar variantes/sinónimos de la pregunta y buscar con todas ampliaría el alcance.
- **Cortar el texto por filas, no por tamaño fijo (chunking estructural).** Hoy el texto se
  corta en pedazos de tamaño parejo, lo que a veces parte una fila de la tabla. Cortar
  respetando la estructura (cada fila = un pedazo) daría señales más limpias. Es el arreglo
  **más de fondo**, pero el más difícil porque la tabla escaneada es ruidosa.
- **Un reordenador dedicado.** Hoy uso la misma IA de chat para reordenar; en producción
  usaría un modelo **especializado en reordenar** (más rápido y barato por consulta).

### Para confiar más en las respuestas (calidad/medición)
- **Ampliar el examen (evaluación).** Hoy mido con 11 preguntas; lo llevaría a 20-30, con
  casos de varias páginas y preguntas "trampa".
- **Medir si la respuesta se sostiene en la fuente (faithfulness).** Un segundo chequeo
  automático que verifique que lo que dice la respuesta realmente está en los pasajes citados.

### Para llevarlo a producción (lo industrial)
- **Aguantar muchos usuarios a la vez:** reutilizar conexiones a la base (hoy abre una por
  consulta), varios "trabajadores" del servidor, y **caché** de preguntas repetidas.
- **Confianza operativa:** login/permisos, registro de métricas y **del costo por consulta**,
  límites de uso, y **el examen corriendo automáticamente** para no empeorar sin darnos cuenta.
- **Respuesta más fluida:** mostrar la respuesta **mientras se va generando** (streaming),
  para que se sienta más rápida.
- **Seguridad propia de estos sistemas:** el documento es contenido "no confiable" → cuidar que
  no se "cuele" una instrucción escondida en el texto (inyección de prompt).

> Detalle técnico de todo esto: `docs/13-escalabilidad-y-produccion.md`.

---

## 3. Los diagramas del PDF (un tema honesto y con buena respuesta)

Esta es una de las preguntas más finas que te pueden hacer. La respuesta corta:
**hoy los diagramas se contemplan a medias, a propósito, y sé exactamente qué haría para
resolverlo del todo.**

### Cómo es el catálogo
Cada figura es un **par de páginas**: una con el **dibujo** (la vista "explotada" de la pieza,
con numeritos 1, 2, 3… señalando cada parte) y la de al lado con la **tabla** que dice qué es
cada numerito y su número de parte.

### Qué pasa HOY
- Las páginas de **tabla** se leen perfecto (es texto) → de ahí salen casi todas las respuestas.
- Las páginas de **dibujo** son **imágenes**: el lector de texto (OCR) solo rescata el
  **título** de la figura (ej. "Figure 49. Fuselage Aft Section Assembly") y algo de ruido.
  **El dibujo en sí no se "entiende".**
- **Lo bueno (y es una decisión, no un descuido):** esa página de dibujo **igual queda
  indexada por su título y es citable**. Así que si preguntás algo que matchea el título o la
  tabla de al lado, la cita te **salta a la página del dibujo** y **vos ves el plano** en el
  visor. O sea: **el sistema no "lee" el dibujo, pero te lleva a él para que lo veas.**

### Qué NO se resuelve hoy
- El sistema **no puede mapear el numerito del dibujo con el número de parte**. No podría
  responder *"¿qué es el ítem 7 del diagrama?"*, porque esos numeritos del plano se pierden o
  salen mal en el OCR.

### Qué haría a futuro
- Usar un **modelo que "ve" imágenes** (un modelo de visión / multimodal, tipo los que
  describen fotos) para **leer el diagrama**: detectar los numeritos y su posición, y
  **vincularlos con la tabla** de al lado. Así se podría responder preguntas sobre el dibujo
  mismo y resaltar la pieza señalada.
- Como es caro, lo haría **bajo demanda**: solo cuando la pregunta es sobre una figura, mando
  esa imagen al modelo de visión, en vez de procesar los 670 dibujos por las dudas.

> **Frase para la entrevista:** "Hoy el sistema no entiende el dibujo, pero **te lleva a él**
> para que lo verifiques con tus ojos —que para este caso ya es muy útil. Para entenderlo de
> verdad (mapear cada numerito del plano con su pieza), sumaría un **modelo de visión**, y lo
> usaría solo cuando la pregunta es sobre una figura, por costo."

---

> **Resumen para vos:** la demo la cerrás con 3 preguntas (cita que salta / búsqueda por dato
> exacto / no inventa). Para "qué mejorarías" tenés una lista priorizada y en cristiano. Y lo
> de los diagramas es de las cosas que más suma: mostrás que **conocés el límite y tenés el
> plan** para superarlo.
