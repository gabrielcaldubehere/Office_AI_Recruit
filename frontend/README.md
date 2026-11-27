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

- Ejecutá una vez `backend/migrations/001_outreach_log.sql` en el SQL Editor de Supabase. Hasta entonces, `/api/outreach` responde `503` y el historial queda vacío sin romper el resto de la oficina.
- Las aprobaciones crean registros en `outreach_log` con `status = 'pending_approval'`; el operador pasa a `enviado` / `espera_respuesta` / `respondido` / `cerrado` manualmente.
- Gmail queda inactivo hasta configurar `GMAIL_CREDENTIALS_PATH` y `GMAIL_TOKEN_PATH`. Sara solo lee/busca, aplica `Clientes` o `Postulaciones` y registra mensajes ya enviados; nunca borra, marca spam, cambia configuración ni responde automáticamente.

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
