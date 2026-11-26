# Taskboard

Aplicacion web en espanol para crear, consultar, avanzar y eliminar tareas. Este es el punto de partida del proyecto de CI/CD, pruebas automatizadas y observabilidad.

## Requisitos

- Python 3.10 o posterior
- Node.js 20 o posterior
- npm

## Preparar el entorno en Windows

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
npx playwright install chromium
```

## Ejecutar localmente

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Abre `http://127.0.0.1:8000`. La API interactiva esta disponible en `http://127.0.0.1:8000/docs`.

La aplicacion crea su base SQLite en `data/tasks.db`. Para usar otra ruta, configura `TASKS_DB_PATH`.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm run test:e2e
```

Playwright inicia una instancia local aislada en el puerto `8001` y usa `data/taskboard-e2e.db`, sin modificar la base normal de desarrollo.
GitHub Actions ejecuta ambas suites en cada `push` y `pull request` hacia `main`; el reporte HTML de Playwright queda disponible como artefacto de la ejecucion.

## Cuentas y sesiones

- El registro requiere un correo valido y una contrasena de al menos 12 caracteres.
- Las contrasenas se almacenan con Argon2id; nunca se guardan ni se devuelven en texto plano.
- Las sesiones duran siete dias. El token se guarda en una cookie `HttpOnly`, `SameSite=Lax`; en SQLite solo se conserva su hash.
- Para desarrollo local, `COOKIE_SECURE` usa `false`. En un despliegue HTTPS, configura `COOKIE_SECURE=true`; no lo actives si la aplicacion solo usa HTTP.
- Cada usuario solo puede consultar y modificar sus propias tareas. Tareas anteriores sin propietario se conservan en SQLite, pero no se muestran a cuentas nuevas.

La API de autenticacion ofrece `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout` y `GET /api/auth/me`. Las operaciones de tareas requieren una sesion activa.