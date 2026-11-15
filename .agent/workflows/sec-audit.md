---
description: Ejecuta una auditoría profunda de ciberseguridad (AppSec, credenciales, SQLi, Path Traversal CWE-22, SSRF, DOM XSS, Circuit Breakers y Docker) sobre Agent Office y corrige vulnerabilidades sin romper tests.
---

# Workflow: Auditoría de Ciberseguridad AppSec & DevSecOps (`/sec-audit`)

Este workflow operativo ejecuta una inspección integral y sistemática de ciberseguridad sobre el código fuente, la persistencia, la red y la interfaz de **Agent Office**, asegurando el cumplimiento de las políticas OWASP Top 10 y los mandatos del CISO.

---

## 1. Activación de Skills Requeridas

Antes de comenzar, el agente orquestador debe activar y aplicar las directrices de:
- **`cybersecurity-appsec-guardian`** (Directivas de blindaje AppSec, DevSecOps y Circuit Breakers).
- **`fastapi-sqlite-core`** (Consultas parametrizadas, persistencia idempotente y robustez RORO).
- **`pytest-zero-network-qa`** (Mocks 100% offline y verificación de no-regresión).

---

## 2. Fase de Auditoría y Verificación por Capas

### Paso 1: Auditoría de Secretos y Persistencia SQLite
1. **Inspección de Configuración y Modelos:**
   - Revisar `app/core/config.py` y `app/schemas/` para verificar que ninguna clave de API (`GEMINI_API_KEY`, `N8N_API_KEY`, tokens) esté hardcodeada ni tenga valores por defecto no autorizados.
2. **Higienización de Endpoints GET:**
   - Inspeccionar `app/api/routes_office.py`, `app/api/routes.py` y `app/api/routes_telemetry.py`.
   - Confirmar que ningún endpoint devuelve secretos en texto plano; las credenciales deben representarse como booleanos (`has_api_key: bool`) o valores enmascarados (`****`).
3. **Parametrización en Base de Datos y Tabla Blanca:**
   - En `app/services/office_store.py`, verificar que toda consulta SQL utilice el operador de sustitución parametrizada `?`.
   - Confirmar que los endpoints de telemetría e inspección validen el acceso contra `_ALLOWED_DB_TABLES`.

### Paso 2: Auditoría de Confinamiento en Disco (Path Traversal CWE-22) y Red (SSRF)
1. **Confinamiento en `workspaces/`:**
   - Revisar `app/services/workspace_writer.py`, `code_materializer.py`, `file_edit_service.py` y `brownfield_service.py`.
   - Verificar que toda ruta calculada o recibida aplique la resolución canónica:
     ```python
     workspace_root = (self.workspaces_dir / project_id).resolve()
     target_path = (workspace_root / file_path).resolve()
     if not target_path.is_relative_to(workspace_root):
         raise ValueError("Acceso denegado: fuera del workspace")
     ```
   - Validar que se bloqueen secuencias `../`, rutas absolutas externas y extensiones fuera de `VALID_EXTENSIONS`.
2. **Mitigación de SSRF en Webhooks y n8n:**
   - Revisar `app/services/n8n_service.py` y `app/services/marketing_tools.py`.
   - Validar que los destinos webhooks y URLs de API empleen exclusivamente esquemas `http://` o `https://`.
   - Asegurar que todo cliente `httpx.AsyncClient` cuente con `timeout <= 10.0` y no siga redirecciones inseguras.

### Paso 3: Auditoría del Frontal Web (DOM XSS y Credenciales)
1. **Sanitización del DOM:**
   - Inspeccionar `app/static/js/panel.js`, `office.js` y `dashboard.js`.
   - Verificar que no exista inyección de variables dinámicas procedentes de LLMs o del backend mediante `innerHTML` sin escapar con `_esc(s)`.
   - Priorizar siempre el uso de `textContent`.
2. **Protección de Inputs Sensibles:**
   - Confirmar que todo campo de API Key o contraseña utilice `type="password"` con alternancia controlada (`toggle`).

### Paso 4: Auditoría de Gobernanza CISO y Circuit Breakers
1. **Respeto a los Interruptores Automáticos:**
   - Verificar en `app/graph/router.py` y `app/graph/nodes.py` que el límite de 3 iteraciones (*Anti-Loop Circuit Breaker*) se mantenga intacto.
   - Confirmar que los vetos del CISO (`Agente 10`) y los evaluadores de QA (`Agente 05` y `Agente 06`) sean de obligado cumplimiento antes de autorizar el despliegue.

---

## 3. Corrección y Verificación de Cierre

1. Si se detecta alguna desviación o vulnerabilidad:
   - Aplicar el parche mínimo necesario respetando la arquitectura existente.
2. Ejecutar la triple verificación de calidad en terminal:
   ```powershell
   ruff check .
   mypy --strict app/
   pytest
   ```
3. Generar un informe ejecutivo de auditoría resumiendo los hallazgos por nivel de severidad (*Crítico*, *Alto*, *Medio*, *Bajo*) y el estado final de las comprobaciones.
