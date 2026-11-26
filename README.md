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

## Observabilidad con OpenTelemetry

La aplicacion puede exportar trazas, metricas HTTP y logs mediante OTLP/HTTP. La instrumentacion se activa solo cuando `OTEL_EXPORTER_OTLP_ENDPOINT` tiene un valor; sin ese valor la aplicacion sigue funcionando localmente sin intentar conectarse a un colector.

Configura estas variables en el entorno del proceso, nunca en el repositorio:

- `OTEL_SERVICE_NAME=taskboard`
- `OTEL_EXPORTER_OTLP_ENDPOINT`: endpoint base OTLP/HTTP proporcionado por OpenObserve.
- `OTEL_EXPORTER_OTLP_HEADERS`: encabezados de autenticacion requeridos por el servicio.

No agregues tokens, claves ni encabezados reales a `.env.example`, archivos versionados, capturas publicas ni logs. El formato exacto del endpoint y la autenticacion se completa al crear el espacio de OpenObserve.

### Metricas del host EC2

Las metricas HTTP de Taskboard las envia la aplicacion; para CPU, memoria, disco, filesystem, carga, red y paging se usa OpenTelemetry Collector Contrib. El collector consulta el host cada 60 segundos y exporta por HTTPS al mismo endpoint OTLP y al stream `default`. No abre puertos de entrada.

En `/etc/taskboard/taskboard.env`, agrega el valor de autorizacion de OpenObserve como variable separada para que el collector lo use. El valor debe incluir el esquema `Basic`, pero no el nombre del encabezado:

```text
OPENOBSERVE_AUTHORIZATION="Basic <valor-de-autorizacion>"
```

No compartas ese valor ni lo guardes en el repositorio. Protege el archivo y despliega el collector:

```bash
sudo chmod 600 /etc/taskboard/taskboard.env
sudo bash /opt/taskboard/scripts/install-hostmetrics-collector.sh
sudo systemctl is-active taskboard-hostmetrics
```

El instalador descarga una version fijada de OpenTelemetry Collector Contrib, verifica su SHA-256, valida la configuracion y crea un servicio `systemd` dedicado. En OpenObserve, busca las metricas del recurso `service_name=taskboard-ec2-host`; la primera muestra puede tardar hasta un minuto.

## Despliegue inicial en Ubuntu EC2

El script `scripts/deploy-ec2.sh` instala dependencias, crea un usuario de sistema y configura un servicio `systemd`. Por seguridad, Uvicorn escucha solo en `127.0.0.1:8000`; este paso no abre puertos ni publica la app. Desde Session Manager, instala Git y clona el repo en la ruta esperada:

```bash
sudo apt-get update
sudo apt-get install -y git
sudo git clone https://github.com/Luisilloelpillo55/taskboard-ci-cd.git /opt/taskboard
sudo bash /opt/taskboard/scripts/deploy-ec2.sh
```

La comprobacion final del script consulta `/api/health` desde la propia instancia. Verifica el servicio con `sudo systemctl status taskboard --no-pager` y sus logs con `sudo journalctl -u taskboard -n 50 --no-pager`. No abras el acceso web ni ingreses contrasenas reales hasta configurar HTTPS; el servicio aun no tiene un proxy publico.

## Cuentas y sesiones

- El registro requiere un correo valido y una contrasena de al menos 12 caracteres.
- Las contrasenas se almacenan con Argon2id; nunca se guardan ni se devuelven en texto plano.
- Las sesiones duran siete dias. El token se guarda en una cookie `HttpOnly`, `SameSite=Lax`; en SQLite solo se conserva su hash.
- Para desarrollo local, `COOKIE_SECURE` usa `false`. En un despliegue HTTPS, configura `COOKIE_SECURE=true`; no lo actives si la aplicacion solo usa HTTP.
- Cada usuario solo puede consultar y modificar sus propias tareas. Tareas anteriores sin propietario se conservan en SQLite, pero no se muestran a cuentas nuevas.

La API de autenticacion ofrece `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout` y `GET /api/auth/me`. Las operaciones de tareas requieren una sesion activa.