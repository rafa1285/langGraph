---
name: cybersecurity-appsec-guardian
description: Auditor de Ciberseguridad AppSec y DevSecOps para Agent Office. Se activa al tocar manejo de credenciales, bases de datos, escritura de archivos en disco, llamadas HTTP externas, contenedores o renderizado en el DOM.
---

# Cybersecurity AppSec & DevSecOps Guardian — Agent Office

Este estándar de seguridad de aplicaciones (AppSec) y operaciones seguras (DevSecOps) es de **cumplimiento obligatorio** para cualquier modificación en la factoría de software autónoma **Agent Office**. 

Inspirado en los marcos **OWASP API Security Top 10**, **OWASP Top 10 for LLM Applications**, las directrices de seguridad de **Trail of Bits** y el **Capítulo 5 del Manual de Usuario: Security & Circuit Breakers**.

---

## 1. Activación y Alcance de Auditoría

Esta skill se activa de forma prioritaria siempre que un agente o desarrollador interactúe con:
- Manejo, almacenamiento o lectura de secretos y tokens (`.env`, `Settings`, base de datos).
- Operaciones de persistencia o consulta en SQLite (`office_store.py`, `checkpoints.sqlite`).
- Creación, edición, eliminación o extracción de archivos en disco (`workspace_writer.py`, `code_materializer.py`, `file_edit_service.py`, `brownfield_service.py`).
- Peticiones de red HTTP salientes, webhooks o aprovisionamiento automatizado (`llm_gateway.py`, `n8n_service.py`, `marketing_tools.py`).
- Modificaciones en la interfaz visual Vanilla JS y renderizado en el DOM (`app/static/js/panel.js`, `office.js`, `dashboard.js`).
- Modificaciones en el flujo de orquestación (`app/graph/nodes.py`, `app/graph/router.py`) que involucren compuertas de calidad o cortafuegos (Circuit Breakers).

---

## 2. Directiva 1: Protección de Secretos y Credenciales Multi-Proyecto

El backend gestiona credenciales sensibles de múltiples proveedores (Gemini, OpenAI, Anthropic, Groq, Mistral, GitHub, Vercel, Resend, n8n, WhatsApp, SMTP/IMAP).

### Reglas Innegociables:
1. **Cero Hardcoding:**
   - Prohibido incluir llaves de API, tokens, contraseñas o firmas criptográficas directamente en el código fuente.
   - Todos los secretos deben cargarse vía variables de entorno mediante `app/core/config.py` (`Settings`).
2. **Higienización de Respuestas API (Zero Credential Leakage):**
   - En ningún endpoint `GET` de `app/api/routes_office.py`, `routes_telemetry.py` o `routes.py` se debe devolver una clave en texto plano.
   - Para verificar disponibilidad de claves, devolver un indicador booleano (`has_api_key: bool`) o un valor enmascarado (`api_key_masked: "sk-...****"`).
   - Referencia de diseño en `app/services/office_store.py`:
     ```python
     def has_env_key(api_key_env: str) -> bool:
         """Retorna True/False sin exponer el valor de la clave."""
         val = getattr(settings, api_key_env, None) or os.environ.get(api_key_env)
         return bool(val and str(val).strip())
     ```
3. **Cero Secretos en Logs y Telemetría:**
   - Queda terminantemente prohibido registrar en logs (`logger.info`, `logger.error`, `logger.debug`) o en eventos de telemetría de `app/api/routes_telemetry.py` cabeceras como `Authorization`, `X-N8N-API-KEY`, parámetros `api_key` o payloads que contengan contraseñas.

---

## 3. Directiva 2: Prevención de Path Traversal y Escritura Arbitraria

Dado que los modelos de lenguaje (LLMs) generan rutas de archivos de código fuente, existe el riesgo crítico de **Path Traversal / Arbitrary File Overwrite** (CWE-22 / CWE-73).

### Reglas Innegociables:
1. **Normalización y Confinamiento Hermético:**
   - En `app/services/workspace_writer.py`, `code_materializer.py`, `file_edit_service.py` y `brownfield_service.py`, toda ruta debe resolverse a su forma canónica absoluta usando `.resolve()`.
   - Se debe verificar explícitamente que la ruta objetivo pertenezca al directorio permitido del proyecto (`target_path.is_relative_to(workspace_root)`).
   - Patrón obligatorio de referencia (extraído de `file_edit_service.py`):
     ```python
     workspace_root = (self.workspaces_dir / project_id).resolve()
     target_path = (workspace_root / file_path).resolve()
     if not target_path.is_relative_to(workspace_root):
         raise ValueError(f"Acceso denegado: la ruta '{file_path}' está fuera del workspace del proyecto.")
     ```
2. **Bloqueo Preventivo de Secuencias Maliciosas:**
   - Rechazar de inmediato cualquier ruta que contenga secuencias `..`, rutas absolutas (`/etc/`, `C:\Windows\`) o esquemas URI (`http://`, `file://`).
3. **Restricción de Extensiones Permitidas:**
   - En `code_materializer.py`, solo se deben materializar archivos con extensiones explícitamente permitidas (`VALID_EXTENSIONS`: `.py`, `.php`, `.json`, `.yml`, `.md`, `.js`, etc.).
   - Rechazar binarios ejecutables arbitrarios (`.exe`, `.dll`, `.so`, `.sh` no autorizados).

---

## 4. Directiva 3: Prevención de SSRF e Inyección en Webhooks y n8n

Agent Office permite al usuario y a agentes configurar webhooks salientes (Telegram, Discord, n8n, etc.).

### Reglas Innegociables:
1. **Validación Estricta de Esquemas:**
   - Toda URL externa provista (`webhook_url`, `n8n_base_url`, `repo_url`) debe validarse garantizando que inicie estrictamente por `http://` o `https://`.
   - Prohibido permitir esquemas como `file://`, `gopher://`, `ftp://` o `ldap://`.
2. **Timeouts Obligatorios y Restrictivos:**
   - Toda llamada con `httpx.AsyncClient` debe tener un límite de tiempo estricto (máximo de 6 a 10 segundos).
3. **Bloqueo de Redirecciones Abiertas:**
   - Deshabilitar el seguimiento automático e indiscriminado de redirecciones (`follow_redirects=False` o verificación del dominio de destino).

---

## 5. Directiva 4: Prevención de Cross-Site Scripting (XSS) en Vanilla JS UI

El frontal de Agent Office (`app/static/js/panel.js`, `office.js`, `dashboard.js`) renderiza respuestas generadas por agentes de IA, nombres de proyectos, eventos de telemetría y mensajes de chat.

### Reglas Innegociables:
1. **Prohibición de `innerHTML` con Datos Dinámicos no Sanitizados:**
   - Nunca inyectar contenido proveniente de un LLM o del usuario directamente mediante `element.innerHTML = data`.
2. **Uso de `textContent` por Defecto:**
   - Siempre que se rendericen cadenas de texto, contadores, estados o alertas, asignar a través de `.textContent`.
3. **Sanitización Obligatoria con Función de Escape:**
   - Cuando sea estrictamente necesario construir HTML dinámico con variables, pasar todo valor no estático por la función de escape canónica `_esc(str)` o `escapeHtml(str)`:
     ```javascript
     // Función estándar presente en panel.js
     function _esc(s) {
       return String(s ?? '')
         .replace(/&/g, '&amp;')
         .replace(/</g, '&lt;')
         .replace(/>/g, '&gt;')
         .replace(/"/g, '&quot;')
         .replace(/'/g, '&#39;');
     }
     ```

---

## 6. Directiva 5: SQL Injection y Seguridad en Persistencia SQLite

1. **Consultas Parametrizadas al 100%:**
   - En `app/services/office_store.py`, toda sentencia `SELECT`, `INSERT`, `UPDATE` o `DELETE` debe utilizar comodines `?` para el paso de argumentos.
   - Prohibido el uso de interpolación de cadenas (`f"SELECT ... WHERE id = '{user_id}'"`).
2. **Lista Blanca de Tablas para Inspección Dinámica:**
   - En endpoints de diagnóstico de base de datos (`app/api/routes_telemetry.py`), el acceso a tablas debe validarse contra una lista blanca inmutable (`_ALLOWED_DB_TABLES`), impidiendo la lectura de tablas del sistema SQLite (`sqlite_master` maliciosa o tablas internas no autorizadas).

---

## 7. Directiva 6: Respeto a los Security Circuit Breakers y Gobernanza CISO

Agent Office incorpora una arquitectura de gobernanza automatizada documentada en `docs/manual_usuario_capitulo_5_security_circuit_breakers.md`.

### Principios Intocables del Grafo:
1. **Límite Máximo Anti-Bucle (Circuit Breaker de 3 Loops):**
   - El router de LangGraph (`app/graph/router.py`) y las compuertas de calidad (`qa_gate_node`, `ciso_gate_node`) imponen un tope estricto de **3 iteraciones**.
   - Si un desarrollo no pasa las pruebas tras 3 intentos, el interruptor automático salta (`TRIPPED`), congelando el proyecto en estado `BLOQUEADO_POR_CIBERSEGURIDAD` o `RECHAZADO` para evitar consumo descontrolado de tokens o degradación del sistema.
2. **Veto Vinculante e Incorruptible:**
   - Las decisiones del **Agente 10 (CISO Security)** y de los validadores de calidad (**Agente 05 QA PHP** y **Agente 06 QA Python**) son vinculantes.
   - Ninguna línea de código puede pasar a la fase de DevOps (`Agente 07`) o entrega sin el veredicto explícito `APROBADO`.
3. **Pista de Auditoría Forense Inmutable:**
   - Cada veredicto, puntuación de seguridad (score 0-100) y agente responsable del veto (`culprit`) debe quedar registrado en `agent_conversations` en SQLite para auditorías de cumplimiento normativo (RGPD y EU AI Act).
4. **Aislamiento de Datos por Proyecto:**
   - Cada espacio de trabajo en `workspaces/{project_id}` debe permanecer hermético y segregado del resto de proyectos de la factoría.

---

## 8. Checklist de Verificación DevSecOps

Antes de dar el visto bueno a cualquier cambio de código, el auditor debe confirmar:

- [ ] ¿Hay alguna credencial, clave o token en texto plano en el código o en los tests?
- [ ] ¿Las nuevas rutas de archivos están protegidas contra Path Traversal con `.resolve()` e `is_relative_to()`?
- [ ] ¿Todas las peticiones HTTP externas cuentan con timeouts explícitos de 10 segundos o menos?
- [ ] ¿Las consultas SQL son 100% parametrizadas con `?`?
- [ ] ¿El frontend Vanilla JS evita `innerHTML` sin escapar para datos dinámicos?
- [ ] ¿Se mantienen intactos los Circuit Breakers y el límite de 3 loops del grafo?
