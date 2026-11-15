---
name: n8n-integration-expert
description: Especialista en diseño de workflows JSON de n8n, aprovisionamiento asíncrono vía API REST (/api/v1/workflows) y conexión por Webhooks multi-proyecto en Agent Office.
---

# n8n Automation & Workflow Integration Expert — Agent Office

Este manual de ingeniería y guía de implementación rige la arquitectura de flujos de automatización, integración con la API REST v1 de **n8n** y conectores por Webhook dentro de la factoría autónoma **Agent Office**.

Aplica de forma directa al servicio de orquestación de marketing y automatizaciones en `app/services/n8n_service.py`, endpoints en `app/api/routes_office.py` y cliente frontend en `app/static/js/api.js` y `panel.js`.

---

## 1. Módulos y Flujos Bajo Alcance

- **Generador y Provisionador n8n:** `app/services/n8n_service.py` (`generate_project_n8n_workflow`, `provision_workflow_in_n8n`).
- **Esquemas RORO de Marketing y n8n:** `app/schemas/office.py` (`N8NProvisionRequest`, `N8NProvisionResponse`, `ProjectMarketingProfile`).
- **Persistencia de Webhooks:** `app/services/office_store.py` (`project_marketing_configs`).
- **Almacenamiento Local de Workflows:** `workspaces/{project_id}/marketing/n8n_workflow_{project_id}.json`.
- **Rutas FastAPI:** `app/api/routes_office.py` (`POST /api/office/marketing/projects/{project_id}/n8n-provision`).
- **Interfaz Gráfica:** `app/static/js/panel.js` (sección n8n en pestaña de Marketing) y `app/static/js/api.js`.

---

## 2. Regla 1: Esquema JSON Canónico Oficial de n8n

Todo flujo de n8n generado mediante código Python debe apegarse estrictamente a la especificación de esquemas de **n8n API v1/v2 Public DTO (`CreateWorkflowPublicDto`)** y catálogos de `awesome-n8n-templates`:

### Estructura de Claves Requeridas:
```json
{
  "name": "AgentOffice Marketing - {project_name}",
  "nodes": [
    {
      "id": "node_webhook_ingest",
      "name": "Webhook Ingesta Marketing",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 1,
      "position": [240, 300],
      "webhookId": "marketing-{project_id}",
      "parameters": {
        "path": "marketing-{project_id}",
        "httpMethod": "POST",
        "responseMode": "onReceived",
        "responseData": "allEntries"
      }
    }
  ],
  "connections": {
    "Webhook Ingesta Marketing": {
      "main": [
        [
          { "node": "Discord Webhook", "type": "main", "index": 0 },
          { "node": "X Twitter Post", "type": "main", "index": 0 }
        ]
      ]
    }
  },
  "settings": {
    "executionOrder": "v1"
  },
  "tags": [
    { "name": "agentoffice" },
    { "name": "marketing" }
  ]
}
```

### Tipado Estricto Python 3.12 (`mypy --strict`):
- Los diccionarios y listas que componen la estructura del workflow deben tiparse explícitamente (`dict[str, Any]`, `list[dict[str, Any]]`).
- Al enviar el payload a la API REST de n8n, filtrar exclusivamente los campos validados por `CreateWorkflowPublicDto`:
  ```python
  allowed_api_fields: set[str] = {
      "name", "nodes", "connections", "settings", "nodeGroups",
      "staticData", "pinData", "projectId", "parentFolderId", "shared", "description"
  }
  api_payload = {k: v for k, v in workflow_json.items() if k in allowed_api_fields}
  ```

---

## 3. Regla 2: Aislamiento Hermético Multi-Proyecto

En Agent Office conviven múltiples proyectos autónomos (`proj_xxx`). Los flujos de n8n deben garantizar segregación absoluta:

1. **Rutas Únicas de Webhook:**
   - La propiedad `path` del nodo `n8n-nodes-base.webhook` debe ser única por proyecto:
     `"path": f"marketing-{project_id}"`
   - El identificador del webhook (`webhookId`) debe coincidir para evitar colisiones en la tabla de rutas de n8n.
2. **Segregación de Credenciales:**
   - Cada nodo secundario (Twitter, Discord, Telegram, LinkedIn, Reddit, Dev.to) debe resolver sus tokens desde la configuración individual del proyecto (`profile.channels[x].credentials`) o variables globales de fallback.
   - Prohibido compartir credenciales de marketing o tokens de canales entre diferentes `project_id`.

---

## 4. Regla 3: Asincronía Pura, Timeouts y Protección SSRF

Cualquier comunicación HTTP con instancias de n8n (locales o remotas) debe operar bajo estrictas directivas de resiliencia:

1. **Cliente Asíncrono no Bloqueante:**
   - Utilizar obligatoriamente `httpx.AsyncClient` dentro de funciones `async def`.
   - Timeout máximo explícito de **10 segundos** (por defecto `timeout=6.0` en provisioning).
2. **Defensa contra SSRF (Server-Side Request Forgery):**
   - Validar que `n8n_base_url` utilice exclusivamente esquemas `http://` o `https://`.
   - Prohibir esquemas como `file://`, `ftp://` o `gopher://`.
3. **Manejo Resiliente de Estados:**
   - Si n8n no está disponible o el usuario no configuró `N8N_API_KEY`:
     - El servicio **no debe lanzar una excepción no controlada**.
     - Debe generar la URL local por defecto (`f"{base_url}/webhook/marketing-{project_id}"`).
     - Debe retornar `live_n8n_connected: False` con un mensaje descriptivo en la respuesta RORO.
4. **Activación Automática (Auto-Publish):**
   - Tras crear el workflow exitosamente con `POST /api/v1/workflows`, emitir una petición subsiguiente para activarlo:
     `POST {base_url}/api/v1/workflows/{workflow_id}/publish`
     para que el webhook quede activo en n8n de inmediato.

---

## 5. Regla 4: Materialización Segura en Disco (`workspaces/`)

Todo workflow generado debe quedar respaldado en el sistema de archivos local para que el usuario pueda descargarlo manualmente si prefiere importar el JSON en su consola de n8n:

1. **Confinamiento de Ruta Seguro:**
   - Resolver la ruta contra el directorio base de workspaces para impedir Path Traversal:
     ```python
     workspace_root = Path(workspaces_dir or settings.WORKSPACES_DIR).resolve()
     project_marketing_dir = (workspace_root / project_id / "marketing").resolve()
     if not project_marketing_dir.is_relative_to(workspace_root):
         raise ValueError(f"Directorio inseguro para proyecto {project_id}")
     project_marketing_dir.mkdir(parents=True, exist_ok=True)
     ```
2. **Archivos Generados:**
   - `n8n_workflow_{project_id}.json`: Copia específica identificada por proyecto.
   - `n8n_workflow.json`: Puntero estándar para integración local.
   - Codificación UTF-8 estricta (`encoding="utf-8"`) con `json.dumps(..., indent=2, ensure_ascii=False)`.

---

## 6. Procedimiento de Verificación y Diagnóstico

Para auditar la integración de n8n, verificar:

```powershell
# 1. Ejecutar tests de integración de n8n y marketing
pytest tests/test_n8n_marketing_integration.py tests/test_marketing_execution_ondemand.py

# 2. Comprobación estricta de tipos
mypy --strict app/services/n8n_service.py

# 3. Comprobación de linting
ruff check app/services/n8n_service.py
```
