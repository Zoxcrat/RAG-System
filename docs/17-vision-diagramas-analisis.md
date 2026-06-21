# Etapa 17 — Visión para diagramas: análisis, diseño y PoC

> Análisis detallado de cómo extender el sistema para **entender los diagramas** del catálogo
> (no solo el texto). Incluye un **proof-of-concept real** sobre dos figuras del Cessna.
> Decisión: **diseñado y probado**, listo para implementar si se quiere el cierre "wow".

---

## 1. El problema (qué falta hoy)

El catálogo tiene, por cada figura, **dos páginas**: el **dibujo** (vista explotada, con
numeritos 1, 2, 3… señalando cada parte) y la **tabla** enfrentada que dice qué es cada
numerito. Hoy:
- La **tabla** se lee bien (texto) → de ahí sale casi todo.
- El **dibujo** es una **imagen**: el OCR solo rescata el título; **los numeritos del plano se
  pierden**. Por eso el sistema no puede responder *"¿qué es el ítem 5 de la figura 49?"* ni
  ubicar visualmente una pieza.

## 2. La idea

Para preguntas sobre una figura, **mandar la imagen de esa página a un modelo multimodal**
(que "ve" imágenes, como GPT-4o). El modelo lee el dibujo, identifica el ensamblaje y los
numeritos de callout, y eso se **combina con la tabla** (que ya tenemos estructurada) para dar
una respuesta completa con cita de página.

## 3. PoC real (lo probé sobre el catálogo)

Rendericé dos páginas de diagrama a imagen (300 DPI) y se las pasé a `gpt-4o-mini` (que tiene
visión) pidiéndole describir el ensamblaje y leer los numeritos. Resultado **real**:

**Figura 49 — "Fuselage Aft Section Assembly" (pág. 200):**
> "The assembly shown is the **Fuselage Aft Section Assembly** for the Cessna Model 172…
> The callout item numbers visible are: 1, 1A, 1B, 1C, 2, 3, 5, 5A, 7, 9, 10, 11, … 99A, 99B,
> 99C, 99D." *(leyó ~90 numeritos de callout)*

**Figura 102 — "Instrument Panel Equipment Installation" (pág. 350):**
> "The assembly shown is the **instrument panel equipment installation**… Callout item
> numbers: 1, 2, 3, … 62A, 63, 64, 65, 66, 66A, 67, 68, 69, 70."

**Conclusión del PoC:** el modelo **sí recupera los numeritos del plano** — exactamente lo que
el OCR pierde. La capacidad es viable.

## 4. Cómo lo implementaría (diseño)

```
pregunta sobre una figura
  → (router) detectar intención "diagrama/figura"
  → ubicar la página: del número de figura en la pregunta, o vía retrieval del caption
  → renderizar esa página a imagen (alta resolución, on-demand)
  → modelo de visión (imagen + pregunta)  ┐
  → tabla `parts` de esa figura (callout → parte)  ┘ → combinar
  → respuesta + cita [página N]
```

**Piezas (nuevas/reusadas):**
- `src/vision.py` (nuevo): `render_page_image(page)` + `ask_vision(image, question)` (llama al
  modelo multimodal con la imagen en base64).
- **Router**: extender el clasificador de intención (ya existe para agregación) para detectar
  preguntas de figura/diagrama ("figura", "diagram", "item N", "dónde está… en el dibujo").
- **Ubicar la página**: si la pregunta dice "figura 49", mapear figura→página (lo tenemos en la
  columna `figure` de `parts`); si no, recuperar por el caption.
- **Combinar con la tabla**: la tabla ya mapea **figura+índice → parte**; el modelo de visión
  aporta **dónde está** en el dibujo. Juntos: "el ítem 5 de la figura 49 es la parte X
  [página N], ubicada en la zona superior del conjunto".
- **On-demand**: la visión se llama **solo** en preguntas de figura (por costo).

## 5. Costos y riesgos (honesto)
- **Costo:** una llamada de visión sobre una imagen cuesta más que texto (orden de **1-2
  centavos** con `gpt-4o-mini`; más con `gpt-4o`). Como es **bajo demanda**, es manejable.
- **Resolución vs costo:** más DPI = lee mejor los numeritos chiquitos, pero la imagen pesa
  más (más tokens). 300 DPI fue un buen punto en el PoC.
- **Precisión:** el modelo puede saltarse o confundir un numerito; conviene **cruzar con la
  tabla** (si el callout no existe en la tabla de esa figura, descartarlo).
- **Latencia:** una llamada extra; aceptable para preguntas de figura.

## 6. Mejoras futuras de esta línea
- **Caché** de la descripción de cada figura (se procesa una vez, no en cada pregunta).
- **Bounding boxes**: pedir al modelo las coordenadas de cada callout para **resaltar la pieza
  en el visor** del PDF (conectar respuesta ↔ dibujo, como hoy con las citas de página).
- **Modelo de detección de layout** dedicado para diagramas técnicos, si se quiere más precisión.

## 7. Por qué es un buen cierre (para la entrevista)
- Agrega una **capacidad nueva** (entender imágenes), no solo pule lo existente.
- Es **multimodal** — muestra que no te quedás solo en texto.
- Reusa la arquitectura: **mismo patrón de ruteo por intención** que la agregación, y se
  **combina con la tabla estructurada** que ya construimos.
- **Honesto y medido:** el PoC demuestra que funciona antes de comprometerse a construirlo.

## 8. Sketch de código (la semilla del PoC, ya probada)
```python
import io, base64, fitz
from openai import OpenAI

def page_image_b64(doc, page_index, dpi=300):
    pm = doc[page_index].get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
    return base64.b64encode(pm.tobytes("png")).decode()

def ask_vision(b64, question, model="gpt-4o-mini"):
    resp = OpenAI().chat.completions.create(model=model, messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }])
    return resp.choices[0].message.content.strip()
```

> **Estado:** diseño + PoC **listos y probados**. Implementarlo end-to-end (router + ubicar
> página + combinar con la tabla + integrar en `ask`/API/frontend) es el siguiente paso si se
> decide sumar el "wow" multimodal.
