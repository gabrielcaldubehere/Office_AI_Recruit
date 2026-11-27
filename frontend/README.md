# AI Office · Frontend (Oficina 1)

React 19 + Vite 8 + TypeScript + Tailwind CSS 4. Cliente de la API FastAPI local.

## Arranque en local

```bash
# 1) Backend (desde la raíz del repo)
backend/.venv/bin/python -m uvicorn main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

# 2) Frontend
cd frontend
npm install
npm run dev
```

Vite sirve en `http://localhost:5173` (o `http://127.0.0.1:5173`). La URL del API se resuelve desde `VITE_API_BASE_URL` (buscada en `frontend/.env` y en el `.env` de la raíz por `envDir: ".."`); si no está definida, usa `http://127.0.0.1:8000`.

## Login de operador

- Usuario: `Caldegrey`
- Contraseña local: `oficina2026`

El hash PBKDF2 se guarda en `OFFICE_ADMIN_PASSWORD_HASH` en `.env`. Sin sesión, la oficina queda en modo exhibición: se ven estados, reportes, contadores de seguimiento y bandeja en solo lectura, sin botones de aprobar, rechazar, correr lotes ni usar el escritorio de Luciano.

## Migración y Gmail

- Ejecutá una vez `backend/migrations/001_outreach_log.sql` y `backend/migrations/002_outreach_log_columns.sql` en el SQL Editor de Supabase. Después aplicá `backend/migrations/003_gmail_control_status.sql` para habilitar `novedad_detectada` y reiniciá el backend (el esquema se cachea al arrancar).
- Las aprobaciones crean registros en `outreach_log` con `status = 'pending_approval'`; el operador pasa a `enviado` / `espera_respuesta` / `respondido` / `novedad_detectada` / `cerrado` manualmente.
- Gmail queda inactivo hasta configurar `GMAIL_CREDENTIALS_PATH` y `GMAIL_TOKEN_PATH` con `credentials.json` y `gmail_token.json` locales (nunca versionados). Para autorizar una vez, usá `GMAIL_ALLOW_INTERACTIVE_AUTH=true`, iniciá el backend, completá el flujo local y volvé a `false`.
- scopes permitidos: lectura, etiquetas, modificación y creación de borradores. No hay scope `gmail.send`: Sara no envía correos. No borra, no marca spam, no cambia configuración y no responde automáticamente.
- Los correos de control y los avisos de respuesta se preparan como borradores `pending_approval` dirigidos a `caldubeheregabriel@gmail.com` y etiquetados `Clientes` o `Postulaciones`. El botón "Crear borrador en Gmail" exige confirmación humana, crea un draft (nunca lo envía) y adjunta únicamente PDFs existentes y verificados.
- Para PDFs, poné los archivos en rutas relativas al repo o configurá `GMAIL_PDF_DIR`. Referencias como `cv_reference` o `attachment_reference` solo se adjuntan si el PDF existe, es legible y pesa hasta 10 MB; si no existe, el correo lo indica expresamente.
- `POST /api/gmail/sync` revisa mensajes entrantes de remitentes externos en `Clientes`/`Postulaciones`, vincula por `threadId`, marca `respondido` o `novedad_detectada`, y prepara el aviso de control.

## Scripts

- `npm run dev` — servidor de desarrollo.
- `npm run build` — typecheck (`tsc -b`) + build de producción.
- `npm run lint` — ESLint.
- `npm run preview` — vista previa del build.

## Estructura

- `src/App.tsx` — orquestación de estado, gating por login y notificaciones de reportes listos.
- `src/components/` — cubículos/avatares, panel lateral del agente, bandeja de aprobación, login, escritorio de Luciano, fuentes Upwork/Freelancer y **Enviados y Seguimiento**.
- `src/services/api.ts` — único punto de acceso HTTP; lanza `UnauthorizedError` en 401.
- `src/types/office.ts` — tipos alineados con los `response_model` del backend, incluida trazabilidad y `outreach_log`.

Toda aprobación registra la acción y prepara el paso final con datos verificados: ningún correo, postulación o mensaje se envía automáticamente.
