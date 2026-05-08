# Veo3-gen — Generación Automatizada de Videos con Google Flow

Aplicación web full-stack que automatiza la generación de videos usando **Google Flow (Veo 3)** mediante automatización de navegador. Subí imágenes, asignales prompts y recibí los videos generados organizados en Google Drive — todo desde una interfaz web.

---

## Arquitectura

```
┌─────────────────┐     ┌──────────────────────┐     ┌─────────────────────────┐
│  React Frontend │────▶│  Node/Express Backend │────▶│  Flask VM Worker        │
│  (Vite)         │     │  + MySQL              │     │  (Playwright + Chrome)  │
│  :5173 / dist   │     │  :3000                │     │  :8000                  │
└─────────────────┘     └──────────────────────┘     └─────────────────────────┘
                                                                │
                                                                ▼
                                                       Google Flow (Veo 3)
                                                       labs.google/fx/tools/flow
                                                                │
                                                                ▼
                                                       Google Drive (G:\)
```

**Frontend** — SPA en React + Vite, servida por el backend en producción. Maneja la carga de imágenes, asignación de prompts por imagen (vía UI o Excel/CSV), polling del estado del job y links de Drive.

**Backend** — API REST en Node.js/Express con MySQL. Gestiona usuarios, sesiones JWT y registros de jobs. Actúa como proxy entre el frontend y el VM Worker.

**VM Worker** — API Flask que corre en una máquina Windows local con Chrome y una cuenta de Google autenticada. Usa Playwright para automatizar Google Flow, generar los videos y subirlos a Google Drive vía el mount local `G:\`.

---

## Funcionalidades

- Carga de múltiples imágenes (JPG, PNG, WEBP) con prompt individual por imagen
- Carga masiva de prompts desde Excel o CSV (soporta múltiples prompts por imagen con sufijos `_p2`, `_p3`)
- 3 workers paralelos en el navegador para mayor velocidad
- Videos organizados automáticamente en Google Drive — una subcarpeta por imagen
- Link público compartible de Drive entregado al frontend al completar el job
- Limpieza automática de carpetas antiguas en Drive después de 2 horas
- Autenticación JWT con revocación de sesión
- Soporte para cancelación de jobs
- Seguimiento del progreso en tiempo real

---

## Requisitos

### Backend y Frontend
- Node.js >= 18
- MySQL 8 (o Docker)
- Docker (opcional, para despliegue en contenedor)

### VM Worker (solo Windows)
- Python 3.10+
- Google Chrome instalado
- Cuenta de Google con acceso a [Google Flow](https://labs.google/fx/tools/flow)
- Google Drive app de escritorio montada como `G:\`
- Cuenta de servicio de Google Cloud con la API de Drive habilitada (para permisos de carpeta)
- Script de automatización `google_flow_bot_paralelo.py` (no incluido — propietario)

---

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/automationventamon/Veo3-gen.git
cd Veo3-gen
```

### 2. Variables de entorno

Copiá `.env.example` a `.env` y completá los valores:

```bash
cp .env.example .env
```

```env
PORT=3000
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=flowgen
MYSQL_USER=flowgen
MYSQL_PASSWORD=tu_contraseña
JWT_SECRET=tu_secreto_jwt
JWT_EXPIRES_IN=8h
VM_WORKER_URL=http://<ip-del-worker>:8000
CLIENT_URL=*
```

### 3. Base de datos

Ejecutá el schema en tu instancia de MySQL:

```bash
mysql -u root -p < backend/docker/mysql/init/01_schema.sql
```

O usá Docker Compose (ver más abajo).

### 4. Backend

```bash
cd backend
npm install
npm start
```

### 5. Frontend (desarrollo)

```bash
cd frontend
npm install
npm run dev
```

Para producción, compilá el frontend primero — el backend sirve `frontend/dist` como archivos estáticos:

```bash
cd frontend && npm run build
cd ../backend && npm start
```

### 6. Docker (backend + MySQL)

```bash
docker build -t veo3-gen .
docker run -p 3000:3000 --env-file .env veo3-gen
```

---

## Configuración del VM Worker (Windows)

El VM Worker es una app Flask que controla Chrome vía Playwright para automatizar la generación de videos en Google Flow.

### Instalar dependencias

```bash
cd vm-worker
pip install flask playwright google-auth google-api-python-client
playwright install chrome
```

### Configurar rutas en `app.py`

Editá estas constantes al inicio de `app.py` según tu máquina:

| Constante | Descripción |
|-----------|-------------|
| `_DRIVE_CREDS_FILE` | Ruta al JSON de la cuenta de servicio de Google |
| `_DRIVE_PARENT_ID` | ID de la carpeta de Google Drive donde se guardan los videos |
| `_DRIVE_LOCAL_ROOT` | Ruta local al mount de Google Drive (ej. `G:\My Drive\Flow\Videos`) |
| `gbot.SESSION_DIR` | Directorio del perfil de Chrome para Playwright |

### Configurar Google Drive

1. Habilitá la **API de Google Drive** en la [Google Cloud Console](https://console.cloud.google.com/)
2. Creá una **Cuenta de Servicio** y descargá el JSON con las credenciales
3. Compartí tu carpeta de Drive con el email de la cuenta de servicio (acceso de Editor)
4. Montá la app de escritorio de Google Drive para que los archivos se sincronicen vía sistema de archivos local (`G:\`)

> El worker copia los videos directamente a `G:\` (evitando los límites de cuota de la cuenta de servicio) y solo usa la API para hacer la carpeta pública y obtener su ID.

### Iniciar el worker

```bash
cd vm-worker
python app.py
# o hacé doble clic en start_worker.bat (guarda logs en modo append)
```

En el primer arranque, Chrome se abre y puede pedir que inicies sesión con tu cuenta de Google. Una vez logueado, la sesión queda guardada en `flow_session_chrome/`.

---

## Referencia de API

| Método | Endpoint | Auth | Descripción |
|--------|----------|------|-------------|
| `POST` | `/api/login` | — | Login, devuelve token JWT |
| `POST` | `/api/logout` | ✓ | Revocar sesión |
| `POST` | `/api/jobs` | ✓ | Crear job (multipart: `images[]`, `prompts` JSON) |
| `GET` | `/api/jobs` | ✓ | Listar todos los jobs del usuario |
| `GET` | `/api/jobs/:id` | ✓ | Estado del job + link de Drive |
| `POST` | `/api/jobs/:id/cancel` | ✓ | Cancelar un job activo |
| `GET` | `/api/health` | — | Health check |

### Endpoints del VM Worker (internos)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `POST` | `/api/job` | Enviar job al worker |
| `GET` | `/api/job/:id` | Consultar estado del job |
| `POST` | `/api/job/:id/cancel` | Cancelar job |
| `GET` | `/api/health` | Estado del worker + tamaño de la cola |

---

## Multi-prompt via Excel/CSV

Podés asignar múltiples prompts a la misma imagen usando una planilla:

| filename | prompt |
|----------|--------|
| foto.jpg | Una transición cinematográfica al atardecer |
| foto.jpg | Un zoom lento hacia el horizonte |
| otra.jpg | Una escena de acción dinámica |

El frontend renombra las imágenes duplicadas como `foto_p2.jpg`, `foto_p3.jpg`, etc. antes de enviarlas. En Drive, cada una obtiene su propia subcarpeta.

---

## Estructura del Proyecto

```
Veo3-gen/
├── frontend/               # SPA React + Vite
│   └── src/
│       ├── components/
│       │   ├── ImageUploader.jsx   # Carga de imágenes + lector de Excel
│       │   └── JobStatus.jsx       # Progreso + link de Drive
│       └── pages/
│           └── VideoGeneratorPage.jsx
├── backend/                # API Node.js / Express
│   ├── server.js
│   ├── docker/
│   │   ├── seed-users.js
│   │   └── mysql/init/01_schema.sql
│   └── package.json
├── vm-worker/              # Flask worker (Windows)
│   ├── app.py              # App Flask principal + adaptador Playwright
│   └── start_worker.bat    # Script de arranque (logs en modo append)
├── Dockerfile              # Build multi-stage (frontend + backend)
├── .env.example
└── .gitignore
```

---

## Notas

- El VM Worker debe correr en una máquina Windows con una cuenta de Google real — Google Flow requiere sesión autenticada en el navegador.
- Google Flow (Veo 3) genera hasta 4 variantes de video por prompt. Algunas pueden fallar según las políticas de contenido o los límites de uso.
- Las carpetas de Drive se eliminan automáticamente después de 2 horas mediante el thread de limpieza.
- Los logs del worker se escriben en `vm-worker/worker.log` (modo append al usar `start_worker.bat`).
