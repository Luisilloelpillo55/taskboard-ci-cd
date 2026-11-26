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
.\.venv\Scripts\python.exe -m pytest -q --html=api-test-report.html --self-contained-html --cov=app --cov-report=term-missing --cov-report=html:backend-coverage
npm run test:e2e
npm run report
```

Playwright inicia una instancia local aislada en el puerto `8001` y usa `data/taskboard-e2e.db`, sin modificar la base normal de desarrollo.
Para ver las pruebas de interfaz en una ventana de Chromium, ejecuta `npm run test:e2e:headed`; `npm run test:e2e` permanece en modo headless para CI. La suite Playwright contiene pruebas de API (sin mostrar datos de backend en pantalla) y de navegador; ambas aparecen en el mismo reporte HTML. Las capturas de las vistas principales se adjuntan a sus pruebas y pueden abrirse desde el reporte con `npm run report`. Pytest se conserva para pruebas internas del backend y medicion de cobertura; genera `api-test-report.html` y `backend-coverage/index.html`. GitHub Actions ejecuta ambas suites en cada `push` y `pull request` hacia `main`, y publica los tres reportes (`api-test-report`, `backend-coverage` y `playwright-report`) como artefactos durante 7 dias. Cuando se configuran el rol OIDC y las variables de despliegue indicadas abajo, un `push` exitoso a `main` tambien despliega por SSM.

### Despliegue continuo privado con GitHub Actions

El job de despliegue solo corre en `main`, despues de que pasan las pruebas, y accede a EC2 mediante AWS Systems Manager. No requiere claves de acceso AWS en GitHub ni puertos publicos de entrada.

1. En IAM, crea (si aun no existe) el proveedor OIDC `https://token.actions.githubusercontent.com`, con audiencia `sts.amazonaws.com`.
2. Crea el rol `GitHubTaskboardDeployRole` con esta politica de confianza. Sustituye `<AWS_ACCOUNT_ID>` por el ID de tu cuenta:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::<AWS_ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub": "repo:Luisilloelpillo55/taskboard-ci-cd:ref:refs/heads/main"
      }
    }
  }]
}
```

3. Adjunta al rol esta politica de permisos. Sustituye `<AWS_ACCOUNT_ID>` y `<EC2_INSTANCE_ID>` por los valores de la cuenta y la instancia:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": [
        "arn:aws:ssm:us-east-2::document/AWS-RunShellScript",
        "arn:aws:ec2:us-east-2:<AWS_ACCOUNT_ID>:instance/<EC2_INSTANCE_ID>"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "ssm:GetCommandInvocation",
      "Resource": "*"
    }
  ]
}
```

4. En GitHub, abre **Settings → Secrets and variables → Actions → Variables** y crea:
   - `AWS_DEPLOY_ROLE_ARN`: ARN del rol `GitHubTaskboardDeployRole`.
   - `EC2_INSTANCE_ID`: ID de la instancia `Proyecto2`.

La instancia debe conservar su rol `TaskboardEC2SSMRole` con `AmazonSSMManagedInstanceCore`. Sin ambas variables, el job de despliegue queda omitido; al configurarlas, un `push` a `main` o la ejecucion manual del workflow despliega la aplicacion y comprueba su health endpoint.

## Observabilidad con OpenTelemetry

La aplicacion puede exportar trazas, metricas HTTP y logs mediante OTLP/HTTP. La instrumentacion se activa solo cuando `OTEL_EXPORTER_OTLP_ENDPOINT` tiene un valor; sin ese valor la aplicacion sigue funcionando localmente sin intentar conectarse a un colector.

Configura estas variables en el entorno del proceso, nunca en el repositorio:

- `OTEL_SERVICE_NAME=taskboard`
- `OTEL_EXPORTER_OTLP_ENDPOINT`: endpoint base OTLP/HTTP proporcionado por OpenObserve.
- `OTEL_EXPORTER_OTLP_HEADERS`: encabezados de autenticacion requeridos por el servicio.

No agregues tokens, claves ni encabezados reales a `.env.example`, archivos versionados, capturas publicas ni logs. El formato exacto del endpoint y la autenticacion se completa al crear el espacio de OpenObserve.

### Metricas del host EC2

Las metricas HTTP de Taskboard las envia la aplicacion; para CPU, memoria, disco, filesystem, carga, red y paging se usa OpenTelemetry Collector Contrib. El collector consulta el host cada 60 segundos y exporta por HTTPS al mismo endpoint OTLP y al stream `default`. No abre puertos de entrada.

El instalador obtiene el valor `Authorization` de `OTEL_EXPORTER_OTLP_HEADERS` y lo guarda en `/etc/taskboard/otelcol.env`, un archivo local protegido que no se versiona. No compartas ni guardes credenciales en el repositorio. Despliega el collector:

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

La API de autenticacion ofrece registro, inicio/cierre de sesion y lectura del usuario actual (`POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`). Una persona autenticada puede actualizar su correo o contraseña con `PATCH /api/auth/me` y eliminar su cuenta con `DELETE /api/auth/me`; ambas operaciones requieren la contraseña actual. Al cambiar la contraseña se revocan las otras sesiones. Al eliminar la cuenta se eliminan tambien sus tareas y sesiones. No hay un panel administrativo ni acceso para listar o modificar cuentas ajenas. Las operaciones de tareas tambien requieren una sesion activa.
