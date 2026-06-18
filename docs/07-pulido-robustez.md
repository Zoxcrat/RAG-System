# Etapa 7 — Pulido y robustez

## Qué se construyó
El pulido final del frontend: estados claros, atajos, navegación y optimización
del bundle. **Cierra el roadmap (7/7).** Continúa [[06-citas-clickeables]].

## Cambios
- **Estados:** loading ("Searching the catalog…"), empty (hint inicial), error
  legible (lee el `detail` de FastAPI).
- **UX:** enviar con **⌘/Ctrl+Enter**, **input "ir a página"** en el visor, y la
  **cita de la página actual resaltada**.
- **Code-split** del visor (`lazy` + `Suspense`).

## Decisiones técnicas y por qué
- **Code-splitting (`React.lazy` + `Suspense`).** react-pdf/pdfjs es pesado.
  Cargarlo de forma diferida lo separa en su propio chunk, que se baja recién
  cuando se monta el visor. El **bundle inicial bajó de 522 kB → 148 kB**.
  *Por qué importa:* menos JS inicial = la UI aparece antes (mejor
  time-to-interactive); el panel de Q&A no espera a que cargue todo pdfjs.
- **Estados explícitos (loading/empty/error).** Una buena UI siempre comunica en
  qué estado está: *empty* guía al usuario, *loading* da feedback, *error* es
  legible. Es parte del diseño, no un extra.
- **Cita activa resaltada.** Conecta visualmente la respuesta con el visor: la
  cita de la página que estás viendo se marca. Refuerza el patrón de
  **componente controlado**: el estado `page` manda en ambos lados.
- **Vulnerabilidades npm: dev-only, no se fuerzan.** Las 6 advisories están en
  `vite`/`vitest` (toolchain de **build**), no en el código que corre el usuario.
  El `npm audit fix` safe no las resuelve; `--force` sube majors y puede romper.
  Decisión: documentarlas y **no forzar**. *(Buen punto de entrevista: distinguir
  riesgo de dev-dependencies vs runtime, y entender semver.)*

## Estado del proyecto
- ✅ **7/7 etapas completadas.** Build OK (code-split: main 148 kB + viewer 373 kB
  lazy) + 6 tests del frontend; backend con 40 tests.
- **Para la demo en vivo:** backend con `OPENAI_API_KEY` (`make up && make api`) +
  `cd frontend && npm run dev`.
- **Mejoras futuras** (roadmap del proyecto base): hybrid search, chunking
  estructural, reranking, evaluación, streaming.

## Conceptos clave (para la entrevista)
- **Code-splitting / lazy loading** y por qué reduce el time-to-interactive.
- **Estados de UI** (loading/empty/error) como parte del diseño.
- **Seguridad: dev-dependencies vs runtime** — no toda vulnerabilidad de
  `npm audit` afecta lo que se despliega.
