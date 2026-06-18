# El proyecto explicado en cristiano (para entender todo y para contarlo)

> Este documento es el "traductor": explica **qué hace el sistema y por qué**, sin
> tecnicismos, con analogías. Pensado para que lo entiendas a fondo y para contárselo a
> alguien que no es programador. Los otros docs (00–14) son la versión técnica, para
> repreguntas más profundas.

---

## 1. El problema, en una frase

Hay un **catálogo de partes del avión Cessna 172**: un libro **viejo, escaneado, de ~670
páginas**, lleno de tablas con números de parte. Si alguien necesita un dato ("¿cuál es el
número de parte del colgador del techo interior?"), tiene que **revisar el libro a mano**.
Es lento y tedioso.

**Lo que construí:** un sistema donde **le hacés la pregunta en lenguaje normal** y te
**responde al instante, con la cita de la página exacta**, y con un click **te salta a esa
página del PDF** para que lo verifiques con tus propios ojos.

Es, básicamente, **un buscador inteligente con respuestas** sobre ese catálogo.

---

## 2. Qué hace, desde el punto de vista del usuario

1. Abrís la página web: a la izquierda el PDF del catálogo, a la derecha un cuadro para
   preguntar.
2. Escribís una pregunta normal: *"¿Cuál es el número de parte del colgador del techo?"*
3. En un segundo aparece la respuesta: *"Es el 0411680 **[página 201]**"*.
4. Esa **[página 201]** es un **botón**: lo clickeás y el visor **salta a la página 201**
   del PDF, con la tabla real a la vista.

La gracia: **no tenés que confiar a ciegas**. El sistema siempre te muestra **de dónde sacó
la respuesta**, y lo podés chequear vos mismo.

---

## 3. Por qué esto es más difícil de lo que parece

- **El libro es un escaneo viejo, no un documento de texto.** Las páginas son básicamente
  **fotos**. La computadora no "lee" una foto; primero hay que **convertir la imagen en
  texto** (como cuando tu celular reconoce un texto en una foto). Y el escaneo tiene ruido,
  manchas, columnas torcidas → cuesta.
- **Son tablas densas de números de parte**, no prosa. Encontrar el dato correcto entre
  miles de números parecidos es difícil.
- **No puede inventar.** En aviación, una respuesta inventada es peligrosa. El sistema tiene
  que **admitir cuando no sabe**, en vez de improvisar.

---

## 4. Cómo funciona, contado con analogías

Pensalo como un **asistente con una biblioteca**. Cuando le preguntás algo, hace esto:

**a) Primero "leyó" todo el libro (una sola vez).**
Convirtió las 670 páginas-foto en texto y las guardó organizadas. Es como **pasar el libro
en limpio y armar un índice gigante**. (Término técnico: *OCR* + *indexación*.)

**b) Cuando preguntás, busca los fragmentos relevantes.**
No le manda el libro entero al "cerebro" que responde: primero **selecciona los pocos
pasajes que tienen que ver con tu pregunta**. Y lo hace de **dos formas combinadas**:
   - **Por significado:** entiende *qué querés decir*, aunque uses otras palabras. (Como un
     bibliotecario que sabe que "colgador del techo" y "hanger headliner" son lo mismo.)
   - **Por palabra exacta:** a veces necesitás el término o el número literal (un número de
     parte como "0411680"). Ahí busca la coincidencia exacta, como **Ctrl+F**.
   - **Las junta:** usar las dos a la vez encuentra mucho más que cualquiera sola.
   (Término técnico: *búsqueda híbrida*.)

**c) Ordena los candidatos con una segunda mirada más experta.**
De ~20 pasajes candidatos, una segunda pasada **más cuidadosa los reordena** para poner los
mejores arriba. (Como un primer filtro rápido y después un experto que revisa el orden.)
(Término técnico: *reranking*.)

**d) Recién ahí responde, y SOLO con lo que encontró.**
Le pasa esos pocos pasajes al modelo de lenguaje (tipo ChatGPT) con una instrucción clara:
*"Respondé únicamente con esto, citá la página, y si no está, decí que no sabés."*

---

## 5. Las 3 cosas que lo hacen confiable (lo que más vale)

1. **Cita la página y te lleva ahí.** Toda respuesta dice "página N" y el click te salta al
   PDF. Podés **verificar**. Genera confianza.
2. **No inventa.** Si lo que encuentra no es lo bastante parecido a tu pregunta, **no llama
   al modelo** y te dice *"no tengo información suficiente"*. Mejor admitir que no sabe a dar
   un dato falso. (Término técnico: *anti-alucinación* / *umbral de relevancia*.)
3. **Muestra las fuentes.** Además de la respuesta, lista los pasajes que usó.

---

## 6. Cómo lo fui mejorando (y cómo lo demuestro)

Lo importante para la entrevista: **no digo "quedó mejor" de palabra, lo medí.**

Armé una **prueba con 11 preguntas de las que ya sé la respuesta correcta** y medí **cuántas
veces el sistema encuentra la página correcta**. Fui mejorando por etapas:

| Versión | Encuentra la página correcta (entre las 5 primeras) |
|---|---|
| Buscador básico (solo por significado) | **45%** |
| + Búsqueda híbrida (significado + palabra exacta) | **73%** |
| + Reordenamiento experto (reranking) | **91%** |

**De 45% a 91%.** Y cada salto lo puedo explicar:
- La **híbrida** sumó los casos donde el dato era un número/palabra exacta que la búsqueda
  "por significado" se perdía.
- El **reordenamiento** subió los aciertos que estaban "ahí pero abajo en la lista".

(Honesto: queda ~1 caso que falla porque el dato ni siquiera entra en la lista de
candidatos — eso se arregla mejorando la búsqueda, no el orden. Saber dónde está el límite
también suma.)

---

## 7. Glosario: del tecnicismo al castellano

| Si te dicen / decís… | Traducción humana |
|---|---|
| **RAG** | "Busca primero, después responde": el asistente lee lo relevante y responde solo con eso. |
| **OCR** | Convertir una página escaneada (foto) en texto que la compu pueda leer. |
| **Embeddings / búsqueda por significado** | Encontrar por *idea*, no por palabra exacta. |
| **Búsqueda híbrida** | Combinar "por significado" + "por palabra exacta". |
| **Reranking** | Una segunda pasada que reordena para poner lo mejor arriba. |
| **Alucinación** | Cuando la IA inventa con seguridad algo que no es cierto. |
| **Umbral / gate de relevancia** | La regla que hace que diga "no sé" en vez de inventar. |
| **Cita [página N]** | El "según la página N", clickeable, para verificar. |
| **Evaluación (recall)** | Medir, con preguntas de respuesta conocida, cuántas emboca. |
| **Base de datos vectorial** | El "índice gigante" que permite buscar por significado. |

---

## 8. El pitch de 30 segundos (para alguien no técnico)

> "Agarré un catálogo de partes de avión de 670 páginas, escaneado y viejo, y construí una
> web donde le preguntás en lenguaje normal y te responde al toque, **citando la página
> exacta**: hacés click y te lleva ahí en el PDF. Lo importante es que **no inventa** —si no
> encuentra el dato, lo dice— y que **podés verificar todo**. Después lo fui haciendo más
> preciso: pasó de acertar la página correcta el 45% de las veces al 91%, y cada mejora la
> **medí**, no la supuse."

---

## 9. Si te piden ir un poco más profundo (pero todavía claro)

- **"¿Por qué no se equivoca/inventa?"** → Porque solo responde con los pasajes que
  encontró, le pongo una regla de "si no estás seguro, decí que no sabés", y siempre cita la
  fuente para que se pueda chequear.
- **"¿Cómo encuentra la info correcta?"** → Combinando dos búsquedas (por significado y por
  palabra exacta) y después reordenando los resultados con una segunda pasada más cuidadosa.
- **"¿Cómo sabés que funciona?"** → Lo medí con preguntas de respuesta conocida; mejoró de
  45% a 91% de aciertos.
- **"¿Esto sirve para otra cosa?"** → Sí: el mismo enfoque sirve para cualquier manual,
  contrato, normativa o base de conocimiento donde haga falta **respuestas confiables y
  verificables**, no un chatbot que improvisa.

---

> **Consejo para mañana:** arrancá siempre por el **problema** (el catálogo lento de
> consultar) y por el **valor** (respuestas al instante, verificables, sin inventar). El
> "cómo" técnico, contalo con las analogías de arriba. Si alguien quiere profundizar, ahí sí
> entrás en los términos —pero traducidos.
