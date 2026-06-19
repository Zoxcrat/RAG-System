# Cómo levantar todo para la demo en vivo (run-book)

> Pasos para seguir **bajo presión**. Necesitás: Docker instalado, la `OPENAI_API_KEY` en el
> archivo `.env`, y demostrar **desde esta misma máquina** (los datos ya están cargados acá).

---

## ⏰ Antes (en casa, con tiempo) — hacelo UNA VEZ y dejalo probado

1. **Prendé Docker** (la app Docker Desktop). Esperá a que el ícono esté **estable** (no
   girando). Puede tardar 1-2 minutos.
2. Confirmá que el `.env` tiene tu clave: que exista la línea `OPENAI_API_KEY=sk-...`.
3. **Hacé el ensayo completo** (los pasos de "En la demo" de abajo) y **probá las 3 preguntas**
   de `DEMO-MEJORAS-Y-DIAGRAMAS.md`. Si andan, estás listo. Después bajalo.

> La idea: que el día de la entrevista **ya lo hayas levantado una vez** y sepas que funciona.

---

## ▶️ En la demo — la secuencia (necesitás 2 terminales)

### Terminal 1 — el backend (cerebro + base de datos)
```bash
cd /Users/francozanier/dev/RAG
make docker-api
```
- Esto arma todo y arranca la API. **Dejá esta terminal abierta** (muestra los logs).
- Esperá ~15-30 segundos, hasta ver un mensaje tipo `Application startup complete`.

**Verificá que está vivo** (en otra terminal, o en el navegador):
```bash
curl http://localhost:8000/health      # tiene que responder: {"status":"ok"}
```

### Terminal 2 — el frontend (la web)
```bash
cd /Users/francozanier/dev/RAG/frontend
npm run dev
```
- Te va a dar una dirección: **http://localhost:5173** → abrila en el navegador.
- (Solo la **primera vez** en una máquina nueva: corré `npm install` antes.)

### ✅ Listo
Abrí **http://localhost:5173**, escribí una pregunta y mostrá la cita que salta.

---

## 🔎 Chequeo de datos (hacelo apenas levantás)

Antes de la demo, **probá una pregunta** (ej. *"What is part number 0411680?"*).
- Si responde con una **cita de página** → todo perfecto. ✅
- Si responde *"no tengo información"* a **TODO** → la base quedó vacía. Re-cargá el catálogo:
```bash
cd /Users/francozanier/dev/RAG
docker compose run --rm app python -m src.ingest "data/cessna_172_ocr.json"
```
(Tarda ~1 minuto y cuesta centavos. Después volvé a probar.)

---

## ⏹️ Bajar todo (cuando terminás)
```bash
cd /Users/francozanier/dev/RAG
make docker-down        # apaga, PERO conserva los datos
```
En la otra terminal, cortá el frontend con **Ctrl+C**. Después podés cerrar Docker.

> ⚠️ **NUNCA uses `make clean` antes de la demo:** ese borra la base de datos y tendrías que
> recargar el catálogo de cero. `make docker-down` es el seguro.

---

## 🛠️ Si algo falla (plan B rápido)

| Síntoma | Qué hacer |
|---|---|
| `curl /health` no responde / "connection refused" | Docker todavía está arrancando, o la API no terminó de levantar. Esperá 20s más y reintentá. |
| Error raro de "container ... no such container" al levantar | Estado colgado de Docker. Probá: `docker compose up -d --force-recreate api`. Si **insiste** (contenedores "fantasma" que ni se borran), ver la nota de abajo 👇 |
| "port is already allocated" / 8000 o 5173 ocupado | Liberá el puerto: `lsof -ti:8000 \| xargs kill` (y `:5173` para el front). |
| Todas las respuestas dicen "no tengo información" | Base vacía → re-ingestá el catálogo (ver "Chequeo de datos"). |
| El visor del PDF no carga | Asegurate de que el backend esté arriba (`/health` ok); el visor pide el PDF a la API. |
| `npm run dev` falla | Corré `npm install` en `frontend/` y reintentá. |

---

## 👻 Nota: contenedores "fantasma" de Docker (ya resuelto)

En esta máquina, el proyecto Docker original (`rag`) quedó con **contenedores corruptos**
que Docker lista pero no puede borrar (ni reiniciando), y trababan el arranque. **Solución
aplicada:** se cambió el nombre del proyecto Docker a `ragdemo` (con la línea
`COMPOSE_PROJECT_NAME=ragdemo` dentro del archivo `.env`), que hace que compose **ignore**
los fantasmas. Los datos quedaron recargados en el volumen nuevo `ragdemo_pgdata`.

- **Para vos esto es transparente:** los comandos `make ...` y `docker compose ...` siguen
  igual (leen el nombre del proyecto desde `.env`).
- ⚠️ **No borres la línea `COMPOSE_PROJECT_NAME=ragdemo` del `.env`** ni uses `make clean`
  (perderías la base y habría que re-ingestar con `docker compose run --rm app python -m
  src.ingest "data/cessna_172_ocr.json"`).
- Limpiar los fantasmas "de verdad" requeriría un *factory reset* de Docker Desktop (borra
  TODOS los volúmenes) — no hace falta; con el nombre nuevo está resuelto.

## 🧰 Comandos útiles (para mostrar tu proceso, ver `COMO-TRABAJO-Y-LA-IA.md`)
```bash
git log --oneline        # la historia de cómo lo construiste
make test                # 57 pruebas en verde (rápido, sin internet)
make eval                # los números: recall 45% -> 91%  (necesita backend arriba)
```

---

## 📋 Checklist de 1 minuto antes de entrar
- [ ] Docker prendido y estable.
- [ ] `make docker-api` corriendo (terminal 1) y `/health` responde ok.
- [ ] `npm run dev` corriendo (terminal 2) y http://localhost:5173 abre.
- [ ] Probaste **1 pregunta** y la cita salta bien.
- [ ] Tenés a mano las 3 preguntas de la demo.

> Si los 5 ✅ están, entrás tranquilo.
