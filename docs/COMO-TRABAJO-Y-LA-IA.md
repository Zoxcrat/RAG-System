# Cómo mostrar tu forma de trabajo (y el uso de IA)

> Para cuando te pregunten "¿cómo trabajás?", "¿usaste IA?", o te pidan **hacer un cambio en
> vivo**. La idea: mostrar que tenés un **método** y que **manejás vos**, la IA es una
> herramienta.

---

## 1. Tu mejor evidencia ya existe: el historial de git

No hace falta que digas "trabajo ordenado": **mostralo**. Abrí `git log --oneline` y contá la
historia. El historial de este proyecto **prueba** cómo trabajás:

```
feat(retrieve): hybrid search (vector + full-text) fused with RRF
fix(embed): batch embeddings under OpenAI's 2048-input limit
feat(eval): retrieval evaluation harness (recall@k, MRR)
feat(rerank): LLM reranker over hybrid candidates
docs: record reranking (recall@5 0.73->0.91, MRR@10 0.39->0.69)
```

Qué muestra eso, sin que lo digas:
- **Pasos chicos y claros**, no "subí todo de una". Cada commit hace **una cosa**.
- **Mensajes con convención** (`feat`, `fix`, `docs`) y con el **porqué**.
- **Una historia real de ingeniería:** encontré un bug en la primera corrida real → lo arreglé
  **con un test** → medí las mejoras **con números** → lo documenté.

> **Frase:** "Mirá el historial: cada cambio es chico, tiene su test y su razón. Así trabajo —
> incremental y verificable, no un gran salto que después no se entiende."

---

## 2. Si te piden un cambio EN VIVO: tu proceso (decilo en voz alta)

Lo importante no es teclear rápido, es mostrar que tenés un **método**. Pasos:

1. **Entender / aclarar.** "¿Querés que el filtro sea por sección o por documento?" Preguntar
   bien es parte del trabajo.
2. **Ubicar dónde va.** Acá brilla que conocés la arquitectura: "esto toca el buscador
   (`retrieve.py`) y la puerta web (`api.py`)". (Tenés el mapa en `docs/14` y `ARCHIVOS-EN-DETALLE`.)
3. **Hacer el cambio**, respetando los patrones del proyecto (config centralizada, lógica
   separada de la entrada/salida).
4. **Escribir/correr un test.** El repo ya tiene el patrón: pruebas "mockeadas" (sin base ni
   internet). "Agrego un test que verifica que el filtro se aplica."
5. **Verificar.** `make test` (rápido) y, si tocaste la búsqueda, `make eval` (los números).
6. **Explicar la decisión y el trade-off.** "Lo hago así por simplicidad; si creciera, haría X."
7. **Commit con mensaje claro.**

> **Frase:** "Mi forma de trabajar un cambio es siempre la misma: entiendo, ubico dónde va, lo
> hago, lo testeo, lo mido y explico por qué. No improviso sobre el código."

---

## 3. Cómo hablar del uso de IA (postura madura, no a la defensiva)

La clave: **no lo escondas y no te disculpes.** La postura ganadora es **"la IA me acelera,
pero yo manejo"**.

**Lo que decís que hacés VOS (lo no negociable):**
- Decido la **arquitectura** y las decisiones técnicas.
- **Reviso cada cambio** antes de aceptarlo.
- **Escribo y corro los tests**, y **mido** los resultados.
- Puedo **explicar y defender cada parte** (esta entrevista es la prueba).

**Lo que la IA hace por mí:** ir más rápido en lo mecánico (borradores, código repetitivo,
explorar opciones), buscar en la documentación, no quedarme trabado en lo trivial.

> **Frase (la más importante):** "Uso IA como un copiloto para ir más rápido, pero las
> decisiones, la revisión y la verificación las hago yo. La prueba es que **puedo explicarte
> cualquier línea y por qué está**. La IA escribe más rápido; entender y responder por el
> sistema sigue siendo mío."

**La mejor defensa contra "¿lo hiciste vos o la IA?":** que podés **explicar cada decisión,
cada trade-off y cada bug** (justo lo que practicaste). Eso no se puede fingir copiando y
pegando.

### Si te piden usar IA en vivo
Es una oportunidad, no una trampa. Mostrá que **vos la dirigís**:
1. Le das una instrucción **precisa** ("escribime la función X que hace Y, con type hints").
2. **Leés y entendés** lo que devuelve (no lo aceptás a ciegas).
3. Lo **ajustás** a los patrones del proyecto.
4. Lo **testeás** y verificás.

> **Frase:** "La IA es buena si le pedís bien y revisás lo que devuelve. Si no entendés lo que
> te dio, es un problema. Por eso siempre leo, ajusto y testeo antes de aceptar nada."

---

## 4. Qué tener listo para mostrar (tu "kit de demo de proceso")

- **`git log --oneline`** → la historia de cómo trabajaste.
- **`make test`** → 57 pruebas en verde (sin internet, rápidas).
- **`make eval`** → los números reales (45% → 91%).
- **La demo** (las 3 preguntas de `DEMO-MEJORAS-Y-DIAGRAMAS.md`).
- **Los docs** → que vos documentás y entendés lo que hacés.

---

## 5. El mensaje de fondo (lo que querés que les quede)

> "Trabajo de forma **ordenada y verificable**: cambios chicos, con su test y su medición, y
> puedo explicar cada decisión. Uso herramientas modernas —incluida la IA— para ir más rápido,
> pero **el criterio, la revisión y la responsabilidad por el resultado son míos**."

Eso es exactamente lo que un equipo quiere: alguien que **usa la IA para producir más, sin
perder el control ni el entendimiento**.
