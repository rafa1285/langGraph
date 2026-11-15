---
description: Configura, valida y sincroniza la integración entre Agent Office, workflows JSON de n8n (CreateWorkflowPublicDto) y contenedores en docker-compose.yml.
---

# Workflow: Sincronización n8n & Infraestructura Docker (`/n8n-docker-sync`)

Este workflow operativo rige la configuración, auditoría y puesta a punto de la automatización multi-canal con **n8n** y su infraestructura contenerizada en **Docker Compose**.

---

## 1. Activación de Skills Requeridas

- **`n8n-integration-expert`** (Generación de flujos JSON, API REST v1 y aislamiento por webhook).
- **`docker-compose-infra`** (Topología de contenedores, persistencia SQLite WAL y networking dual).
- **`cybersecurity-appsec-guardian`** (Blindaje SSRF, validación de esquemas HTTP y permisos de archivos).

---

## 2. Flujo de Validación y Sincronización

### Paso 1: Auditoría de Contenedores y Variables de Entorno
1. **Revisión de `docker-compose.yml`:**
   - Confirmar que el servicio `agentoffice` expone el puerto `8080:8080` y monta los volúmenes persistentes `./workspaces:/app/workspaces`, `./prompts:/app/prompts:ro` y `./app:/app/app`.
   - Confirmar que el servicio `n8n` corre la imagen `n8nio/n8n:latest`, expone el puerto `5678:5678`, monta el volumen nombrado `n8n_data:/home/node/.n8n` y se agrupa bajo el perfil `automation`.
2. **Topología de Red Dual:**
   - Comprobar que en `app/core/config.py` y en las variables de entorno de Docker:
     - `N8N_BASE_URL` apunte a `http://n8n:5678` (red bridge interna para llamadas FastAPI).
     - `WEBHOOK_URL` apunte a `http://localhost:5678/` (para consumo desde el host del usuario).
3. **Verificación de `Dockerfile` y `.dockerignore`:**
   - Verificar imagen base `python:3.12-slim`, capas limpias con `--no-install-recommends` y exclusión de `.env` y `.venv` en `.dockerignore`.

### Paso 2: Validación de Workflows JSON de n8n
1. **Cumplimiento de `CreateWorkflowPublicDto`:**
   - En `app/services/n8n_service.py`, verificar que los workflows generados contengan las claves requeridas `name`, `nodes`, `connections`, `settings` y `tags`.
   - Asegurar que al emitir la petición a `POST /api/v1/workflows` se filtren únicamente los campos aceptados por la API pública de n8n.
2. **Aislamiento de Webhooks por Proyecto:**
   - El nodo disparador `n8n-nodes-base.webhook` debe tener configurado:
     - `webhookId: f"marketing-{project_id}"`
     - `path: f"marketing-{project_id}"`
     - `httpMethod: "POST"`
     - `responseMode: "onReceived"`
3. **Flujo de Publicación Automática:**
   - Confirmar que tras la creación exitosa del workflow se ejecute la llamada de activación:
     `POST {base_url}/api/v1/workflows/{workflow_id}/publish`.
4. **Materialización Segura en Disco:**
   - Confirmar que el JSON se escriba en `workspaces/{project_id}/marketing/n8n_workflow_{project_id}.json` utilizando `Path.resolve()` y validando `is_relative_to(workspace_root)`.

### Paso 3: Pruebas de Integración y Mocks Offline
1. Ejecutar la suite de pruebas de integración de n8n y herramientas de marketing con mocks:
   ```powershell
   pytest tests/test_n8n_marketing_integration.py tests/test_marketing_execution_ondemand.py
   ```
2. Validar tipado y formato:
   ```powershell
   mypy --strict app/services/n8n_service.py
   ruff check app/services/n8n_service.py
   ```

---

## 3. Comandos de Despliegue Local Rápido

Para iniciar el entorno completo de forma manual:

```powershell
# Iniciar Agent Office junto con el motor n8n
docker compose --profile automation up -d --build

# Verificar estado y healthchecks
docker compose ps
```
