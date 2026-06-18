# Etapa 6 — Feature estrella: citas clickeables → salto de página

## Qué se construyó
El feature central: las citas `[página N]` de la respuesta son **botones**; al
hacer click, el visor **salta a esa página**. Cierra el *hilo conductor* del
`page_number`. Continúa [[05-frontend-react]].

## El hilo conductor, completo
```
OCR (E1) → chunk con page_number (E2) → retrieval lo devuelve (E3)
        → el LLM cita [página N] (E3) → la API lo entrega (E4)
        → el front lo muestra (E5) → CLICK → SALTO en el visor (E6)
```

## Cambios
- **`src/citations.ts`** — `parseAnswer` (función pura) + su test.
- **`src/components/AnswerText.tsx`** — renderiza las citas como botones.
- **`src/components/AskPanel.tsx` / `App.tsx`** — cablea `onCite → setPage` y
  auto-salta a la primera cita.

## Decisiones técnicas y por qué
- **Parser puro y testeado.** Separar el parseo (regex `[página N]`) de la UI
  permite **testearlo sin DOM** (vitest). 6 tests cubren: sin citas, cita al
  medio, cita al inicio, múltiples, espacios extra y string vacío.
- **Componente controlado + flujo unidireccional (lo clave de React).** El click
  **no manipula** el visor directamente: actualiza el estado `page` en `App`, y
  React re-renderiza el `PdfViewer`. Por eso en la E5 "levantamos" ese estado.
  Un click → un cambio de estado → un re-render. Predecible y fácil de razonar.
- **Formato exacto `[página N]`** (definido en el prompt del backend, E3) → regex
  confiable. Acá se ve **por qué** pedimos un formato parseable y no `[1]`:
  el front lo puede convertir en navegación sin ambigüedad.
- **Auto-salto a la primera página *citada*** (no a la primera *recuperada*):
  consistente con lo que el texto realmente cita, y **no salta** en un
  "no tengo información" (que no trae citas).

## Cómo verlo
`npm run dev` + backend con `OPENAI_API_KEY`. Preguntás algo → la respuesta
muestra `[página N]` en azul, clickeable → click salta el visor a esa página.

## Estado / pendiente
- ✅ `npm run build` OK + **6 tests** (vitest).
- ⏳ Render/click en vivo: browser + backend con key.
- **Próximo (Etapa 7 — pulido):** loading/empty/error states, prolijidad visual,
  **code-split** del bundle de pdfjs (>500 kB) y las **3 vulnerabilidades npm**.

## Conceptos clave (para la entrevista)
- **Flujo de datos unidireccional / componente controlado** en React.
- **Por qué un formato de cita parseable** desacopla backend (genera el texto) y
  frontend (lo vuelve interactivo).
- **Testear lógica pura** (el parser) sin montar el DOM.
