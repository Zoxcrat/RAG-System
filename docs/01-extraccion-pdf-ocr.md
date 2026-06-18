# Paso 1 — Extracción de PDF con OCR

## Qué se construyó
Módulo `src/pdf_loader.py`: toma un PDF escaneado y devuelve el texto de cada
página usando OCR. Es la primera etapa del pipeline para indexar el catálogo de
partes del Cessna 172 (**670 páginas**). El motor de OCR (Tesseract) corre **dentro
de la imagen Docker**, así no depende de lo que tengas instalado en la máquina.

## Por qué OCR y no el texto embebido del PDF
El PDF es un escaneo con una **capa de OCR parcial e incompleta**. Si
confiáramos en el texto embebido (`page.get_text()` de PyMuPDF) tendríamos
huecos y texto basura. Por eso **ignoramos el texto embebido** y, en su lugar,
**renderizamos cada página a imagen** y le corremos un motor de OCR moderno
(Tesseract). Es más lento, pero la calidad y la cobertura del texto son mucho
mejores y predecibles.

## Cómo funciona (flujo)
1. `PyMuPDF` (`fitz`) abre el PDF.
2. Por cada página: se renderiza a imagen a una resolución `dpi` controlada.
3. `pytesseract` (binding de Tesseract) hace OCR de esa imagen → texto.
4. Se devuelve una lista de dicts `{page_number, text}` (página 1-based).
5. El resultado se cachea en JSON para no re-OCR-ear.

## Decisiones técnicas y trade-offs
- **Tesseract va en la imagen Docker, no en la Mac.** El objetivo es
  reproducibilidad: que cualquiera levante el OCR sin instalar nada a mano. El
  `Dockerfile` instala `tesseract-ocr` (incluye el idioma inglés). Esto sigue la
  misma política que ya tenía el proyecto: hornear todo en la imagen y no
  bind-montear la carpeta sincronizada por iCloud (ver [[00-sistema-rag-existente]]).
- **El PDF vive en `data/`** y se copia a la imagen (consistente con lo
  anterior). *Trade-off:* suma ~18 MB a la imagen; aceptable para una demo. Para
  OCR-ear otro PDF: ponerlo en `data/` y rebuildear, o correr local pasando la
  ruta.
- **DPI 200 por defecto, configurable.** El PDF está en unidades de 72 pt/inch,
  así que el zoom de render es `dpi / 72`. 200 DPI da detalle suficiente para
  leer números de parte chicos sin inflar el tamaño de imagen ni el tiempo de
  OCR. 300 DPI lee un poco mejor pero es más lento; por eso `dpi` es un
  parámetro y no un valor fijo.
- **Render vía buffer PNG en memoria** (`pixmap.tobytes("png")` → `PIL.Image`)
  en lugar de leer `pixmap.samples` crudo. Así la conversión es correcta sin
  importar el espacio de color o el canal alfa de la página. El costo de
  codificar/decodificar PNG es despreciable frente al OCR.
- **Cache a JSON** (`save_extracted_text` / `load_extracted_text`). El OCR de
  670 páginas tarda (segundos por página). Se corre **una sola vez** y las
  etapas siguientes (chunking, embeddings) leen el JSON. Se guarda con
  `ensure_ascii=False` para que los acentos queden legibles.
- **Aislamiento de errores por página.** Cada página va en su propio
  `try/except`: si una falla el OCR, se registra un warning en `stderr` y la
  página queda con `text=""`, pero **no se aborta** el trabajo ya hecho en las
  demás. Registrar el error ≠ silenciarlo.
- **Fail-fast si falta Tesseract.** Antes de procesar se valida que el binario
  de Tesseract exista (`_check_tesseract_available`). Si no está, se lanza un
  error claro con el comando de instalación. Sin esto, las 670 páginas fallarían
  una por una generando ruido inútil.
- **`TypedDict` `ExtractedPage`** para documentar la forma del registro
  (`page_number: int`, `text: str`). En runtime son dicts normales, así que el
  JSON y el resto del código no cambian.

## Dónde está el código
`src/pdf_loader.py`:
- `extract_pages_from_pdf(pdf_path, dpi=200, max_pages=None, lang="eng")` — núcleo.
- `save_extracted_text(pages, output_path)` / `load_extracted_text(input_path)` — cache JSON.
- `_render_page_to_image(page, dpi)` — render página → imagen (privada).
- `_check_tesseract_available()` — preflight del binario (privada).
- Bloque `__main__` — OCR de las primeras 5 páginas e imprime un preview de 300
  caracteres por página para verificar a ojo que el OCR anda.

## Dependencias
- Python (en `requirements.txt`): `PyMuPDF`, `pytesseract`, `Pillow`.
- Sistema: el motor **Tesseract OCR**.
  - **Con Docker no instalás nada**: ya viene en la imagen (`Dockerfile`).
  - Solo si corrés **local sin Docker** lo necesitás en el sistema:
    - Linux (Debian/Ubuntu): `sudo apt-get install -y tesseract-ocr`
    - macOS (Homebrew): `brew install tesseract`

## Cómo probarlo
**Recomendado (Docker, sin instalar nada):**
```bash
make docker-ocr                      # usa el Cessna por defecto, primeras 5 páginas
make docker-ocr PDF=data/otro.pdf    # otro PDF
```
Por debajo corre, dentro del contenedor:
```bash
docker compose run --rm --no-deps --entrypoint python app \
  -m src.pdf_loader "data/Cessna 172 Parts Catalog (1963-1974).pdf"
```
`--no-deps` y `--entrypoint` saltean Postgres y la inicialización del esquema:
el OCR no necesita base de datos.

**Local (si tenés tesseract + deps instalados):**
```bash
make install        # crea venv e instala requirements (o: pip install -r requirements.txt)
make ocr
```

## Conceptos clave (para la entrevista)
- **OCR (Optical Character Recognition):** convertir la imagen de una página en
  texto. Tesseract es el motor open-source estándar; `pytesseract` es solo el
  puente Python que lo invoca.
- **DPI / zoom de render:** el PDF mide en puntos (72 por pulgada). Para obtener
  N DPI hay que escalar por `N/72` al rasterizar. Más DPI = más píxeles = OCR
  más preciso pero más lento.
- **Por qué cachear:** el OCR es la parte cara del pipeline; separarlo y
  persistirlo permite iterar en chunking/embeddings sin re-pagar ese costo.

## Estado (2026-06-16)
- ✅ **OCR completo corrido y persistido:** las **670 páginas** → `data/cessna_172_ocr.json`
  (~998 KB, gitignored porque es derivado del PDF). 0 páginas vacías; mediana ~1240
  chars/página. Detalle de calidad en [[08-validacion-end-to-end]].
- ✅ **Chunking + ingesta** ya integrados (ver [[02-ingestion-con-pagina]] y
  [[03-retrieval-citas-pagina]]); 2605 chunks ingeridos con su `page_number`.

## Pendiente / próximos pasos
- Posible **preprocesado de imagen** (escala de grises, binarización, deskew) o más
  DPI para subir la precisión del OCR en tablas densas — relevante para el problema
  de **recall** detectado (ver [[08-validacion-end-to-end]]).
- Si se OCR-ea otro PDF más grande, persistir el JSON en un **named volume** en vez
  de `data/` del host.
