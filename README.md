# Taskboard

Aplicacion web en espanol para crear, consultar, avanzar y eliminar tareas. Este es el punto de partida del proyecto de CI/CD, pruebas automatizadas y observabilidad.

## Requisitos

- Python 3.10 o posterior
- Node.js 20 o posterior
- npm
- Docker Desktop (opcional para ejecutar la version en contenedor localmente)

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

### Ejecutar en Docker

Con Docker Desktop iniciado, copia `.env.example` a `.env` y ejecuta:

```powershell
Copy-Item .env.example .env
docker compose --project-directory . -f deploy/compose.yaml up --build
```

La aplicacion queda en `http://127.0.0.1:8000` y los datos se guardan en el volumen Docker `taskboard-data`. Para detenerla usa `docker compose --project-directory . -f deploy/compose.yaml down`; no agregues `-v` si quieres conservar la base de datos. El perfil `demo` de Cloudflare no se inicia por defecto.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest -q --html=api-test-report.html --self-contained-html --cov=app --cov-report=term-missing --cov-report=html:backend-coverage
npm run test:e2e
npm run report
```

Playwright inicia una instancia local aislada en el puerto `8001` y usa `data/taskboard-e2e.db`, sin modificar la base normal de desarrollo.
Para ver las pruebas de interfaz en una ventana de Chromium, ejecuta `npm run test:e2e:headed`; `npm run test:e2e` permanece en modo headless para CI. La suite Playwright contiene pruebas de API (sin mostrar datos de backend en pantalla) y de navegador; ambas aparecen en el mismo reporte HTML. Las capturas de las vistas principales se adjuntan a sus pruebas y pueden abrirse desde el reporte con `npm run report`. Pytest se conserva para pruebas internas del backend y medicion de cobertura; genera `api-test-report.html` y `backend-coverage/index.html`. GitHub Actions ejecuta ambas suites en cada `push` y `pull request` hacia `main`, y publica los tres reportes (`api-test-report`, `backend-coverage` y `playwright-report`) como artefactos durante 7 dias. Cuando se configuran el rol OIDC y las variables de despliegue indicadas abajo, un `push` exitoso a `main` tambien despliega por SSM.

### Despliegue continuo con Docker, GHCR y GitHub Actions

En `main`, GitHub Actions ejecuta Pytest y Playwright; solo si ambas suites pasan, construye y publica la imagen Docker en GHCR y luego despliega por AWS Systems Manager. La imagen se etiqueta con el SHA del commit y con `latest`. EC2 descarga la imagen publica; no necesita credenciales de GHCR, claves de acceso AWS en GitHub ni puertos publicos de entrada. El job de despliegue usa la misma configuracion OIDC y SSM descrita abajo.

Despues de la primera publicacion, configura la visibilidad de `taskboard-ci-cd` en **GitHub → Packages → paquete → Package settings → Change visibility → Public**. GHCR no hace publica automaticamente una imagen por el hecho de que el repositorio sea publico. El job de despliegue tambien exige la variable `GHCR_IMAGE_PUBLIC=true`: creala solo despues de comprobar que el paquete es publico. Asi el primer push publica la imagen, pero no intenta descargarla anonimamente mientras siga privada. No publiques `.env`, contrasenas, tokens de OpenObserve ni credenciales de AWS dentro de la imagen o del repositorio.

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
   - `GHCR_IMAGE_PUBLIC`: asigna `true` unicamente despues de hacer publica la imagen en GHCR.

La instancia debe conservar su rol `TaskboardEC2SSMRole` con `AmazonSSMManagedInstanceCore`. En el primer push, el workflow prueba y publica la imagen; el despliegue queda omitido hasta que GHCR sea publico y existan las tres variables anteriores. Despues de habilitarlo, puedes ejecutar `workflow_dispatch` en `main` para desplegar sin esperar otro cambio de codigo.

### Eventos CI/CD en OpenObserve

Para registrar cada resultado de pruebas y cada intento de despliegue, configura en **Settings → Secrets and variables → Actions**:

- Variables `OPENOBSERVE_URL` (URL base HTTPS, sin ruta), `OPENOBSERVE_ORG` y `OPENOBSERVE_STREAM` (por ejemplo, `ci_events`).
- Secret `OPENOBSERVE_AUTHORIZATION` con el valor completo `Basic ...` requerido por OpenObserve. No pegues este valor en el chat ni lo guardes en el repositorio.

Los jobs `report-ci` y `report-deploy` envian registros JSON al endpoint `_json` e incluyen tipo de evento, resultado, SHA, rama, actor, repositorio, intento y enlace al run; el evento de despliegue tambien incluye los resultados de tests e imagen. Si no se configuran las cuatro entradas, los eventos se omiten. Un fallo al reportar se muestra como fallo en su job, pero no cambia el gate de pruebas ni detiene un despliegue independiente.

## Observabilidad con OpenTelemetry

La aplicacion puede exportar trazas, metricas HTTP y logs mediante OTLP/HTTP. La instrumentacion se activa solo cuando `OTEL_EXPORTER_OTLP_ENDPOINT` tiene un valor; sin ese valor la aplicacion sigue funcionando localmente sin intentar conectarse a un colector.

Configura estas variables en el entorno del proceso, nunca en el repositorio:

- `OTEL_SERVICE_NAME=taskboard`
- `OTEL_EXPORTER_OTLP_ENDPOINT`: endpoint base OTLP/HTTP proporcionado por OpenObserve.
- `OTEL_EXPORTER_OTLP_HEADERS`: encabezados de autenticacion requeridos por el servicio.

No agregues tokens, claves ni encabezados reales a `.env.example`, archivos versionados, capturas publicas ni logs. El formato exacto del endpoint y la autenticacion se completa al crear el espacio de OpenObserve.

### Metricas del host EC2

Las metricas HTTP de Taskboard las envia la aplicacion; para CPU, memoria, disco, filesystem, carga, red y paging se usa OpenTelemetry Collector Contrib. El collector consulta el host cada 60 segundos y exporta por HTTPS al mismo endpoint OTLP y al stream `default`. No abre puertos de entrada. Para el panel de RAM usa `system_memory_utilization`, una gauge de fraccion entre 0 y 1 con atributo `state`; `system_memory_usage` es una suma acumulativa y no debe promediarse como lectura instantanea. Las metricas de red son contadores de bytes: para mostrar ancho de banda en un dashboard hay que aplicar una tasa por segundo.

El instalador obtiene el valor `Authorization` de `OTEL_EXPORTER_OTLP_HEADERS` y lo guarda en `/etc/taskboard/otelcol.env`, un archivo local protegido que no se versiona. No compartas ni guardes credenciales en el repositorio. Despliega el collector:

```bash
sudo chmod 600 /etc/taskboard/taskboard.env
sudo bash /opt/taskboard/scripts/install-hostmetrics-collector.sh
sudo systemctl is-active taskboard-hostmetrics
```

El instalador descarga una version fijada de OpenTelemetry Collector Contrib, verifica su SHA-256, valida la configuracion y crea un servicio `systemd` dedicado. En OpenObserve, busca las metricas del recurso `service_name=taskboard-ec2-host`; la primera muestra puede tardar hasta un minuto.

La temperatura no esta incluida en la configuracion del Collector. Comprueba desde Session Manager si la VM expone sensores termicos:

```bash
found=0
for sensor in /sys/class/thermal/thermal_zone*/temp; do
  if [ -r "$sensor" ]; then
    awk -v file="$sensor" '{ printf "%s: %.1f C\n", file, $1 / 1000 }' "$sensor"
    found=1
  fi
done
if [ "$found" -eq 0 ]; then
  echo "El sistema invitado no expone sensores de temperatura."
fi
```

No se deben inventar lecturas si EC2 no expone un sensor accesible. Los dashboards y alertas de OpenObserve todavia deben crearse/verificarse en la cuenta; los eventos `ci_events`, metricas de aplicacion y host son las fuentes para ello.

## Despliegue inicial en Ubuntu EC2

El script `scripts/deploy-ec2.sh` instala Docker Compose, crea un usuario de sistema y migra el servicio anterior a un contenedor. La base SQLite persiste en `/var/lib/taskboard`; el proceso del contenedor no es root y el puerto publicado queda limitado a `127.0.0.1:8000`. El script no modifica el grupo de seguridad. Desde Session Manager, instala Git y clona el repo en la ruta esperada:

```bash
sudo apt-get update
sudo apt-get install -y git
sudo git clone https://github.com/Luisilloelpillo55/taskboard-ci-cd.git /opt/taskboard
sudo env TASKBOARD_IMAGE=ghcr.io/luisilloelpillo55/taskboard-ci-cd:latest \
  bash /opt/taskboard/scripts/deploy-ec2.sh
```

En el flujo CI, SSM entrega al script la etiqueta inmutable del commit probado, no `latest`. La comprobacion consulta `/api/health` desde la instancia. Inspecciona el contenedor con `sudo docker compose --project-directory /opt/taskboard -f /opt/taskboard/deploy/compose.yaml ps` y los logs con el mismo comando seguido de `logs --tail=50 taskboard`.

### Enlace HTTPS temporal para la demostracion (sin dominio)

No abras puertos entrantes en el grupo de seguridad ni publiques el login directamente por HTTP. Con el contenedor sano y una vez publicada la imagen, un Quick Tunnel crea una URL HTTPS temporal sin PIN de Cloudflare. La aplicacion conserva su propio registro e inicio de sesion; cualquier persona con la URL puede visitar la pagina y crear una cuenta. Desde Session Manager ejecuta:

```bash
sudo docker compose --project-directory /opt/taskboard \
  -f /opt/taskboard/deploy/compose.yaml --profile demo up -d cloudflared
sudo docker compose --project-directory /opt/taskboard \
  -f /opt/taskboard/deploy/compose.yaml logs -f cloudflared
```

Abre la URL `https://....trycloudflare.com` que aparece en los logs e inicia sesion o crea una cuenta de Taskboard. Para apagar el acceso:

```bash
sudo docker compose --project-directory /opt/taskboard \
  -f /opt/taskboard/deploy/compose.yaml stop cloudflared
```

Quick Tunnels son solo para pruebas: no tienen garantia de disponibilidad, la URL cambia al reiniciar el tunel y deja de funcionar al detenerlo. Sin PIN, cualquier persona que conozca la URL puede alcanzar la pagina, pero cada cuenta solo puede ver sus propias tareas. La cookie `Secure` se mantiene activada en EC2. El trafico externo entra por HTTPS a Cloudflare; la instancia acepta solo conexiones salientes del tunel y no requiere abrir puertos de entrada.

## Cuentas y sesiones

- El registro requiere un correo valido y una contrasena de al menos 12 caracteres.
- Las contrasenas se almacenan con Argon2id; nunca se guardan ni se devuelven en texto plano.
- Las sesiones duran siete dias. El token se guarda en una cookie `HttpOnly`, `SameSite=Lax`; en SQLite solo se conserva su hash.
- Para desarrollo local, `COOKIE_SECURE` usa `false`. En un despliegue HTTPS, configura `COOKIE_SECURE=true`; no lo actives si la aplicacion solo usa HTTP.
- Cada usuario solo puede consultar y modificar sus propias tareas. Tareas anteriores sin propietario se conservan en SQLite, pero no se muestran a cuentas nuevas.

La API de autenticacion ofrece registro, inicio/cierre de sesion y lectura del usuario actual (`POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`). Una persona autenticada puede actualizar su correo o contraseña con `PATCH /api/auth/me` y eliminar su cuenta con `DELETE /api/auth/me`; ambas operaciones requieren la contraseña actual. Al cambiar la contraseña se revocan las otras sesiones. Al eliminar la cuenta se eliminan tambien sus tareas y sesiones. No hay un panel administrativo ni acceso para listar o modificar cuentas ajenas. Las operaciones de tareas tambien requieren una sesion activa.
