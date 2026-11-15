---
name: fastapi-sqlite-core
description: Experto en el backend Python/FastAPI, esquemas Pydantic v2, persistencia SQLite en office_store.py y enrutamiento LLM en llm_gateway.py de Agent Office.
---

# FastAPI & SQLite Core Specialist — Agent Office

Este manual de procedimiento y estándar de ingeniería define las directrices obligatorias para el desarrollo, refactorización y mantenimiento del núcleo backend de **Agent Office** (Software Factory LangGraph Backend).

Aplica a todo el código contenido en `app/` (dentro de `langGraph/app/` o en la raíz según el entorno de ejecución), específicamente a la API REST, esquemas de datos, persistencia en SQLite y la capa de pasarela de modelos de lenguaje (LLM Gateway).

---

## 1. Módulos Bajo Alcance de esta Skill

La presente skill gobierna los siguientes componentes de la arquitectura:

- **Configuración Central:** `app/core/config.py` (`Settings` vía `pydantic-settings`).
- **Esquemas RORO Pydantic v2:**
  - `app/schemas/office.py` (modelos de oficina, catálogo LLM, emails internos, marketing).
  - `app/schemas/api.py` (contratos de petición/respuesta de proyectos y generación).
  - `app/schemas/routing.py` (identificadores de agentes `AgentID`, estados `DeliverableStatus`).
  - `app/schemas/telemetry.py` (eventos de observabilidad, Circuit Breakers, costos, KPIs).
  - `app/schemas/chat.py`, `app/schemas/file_edit.py`, `app/schemas/brownfield.py`.
- **Persistencia SQLite:** `app/services/office_store.py` (`office_data.sqlite`).
- **Pasarela de Modelos LLM:** `app/services/llm_gateway.py` (`GeminiLLMGateway`, `LLMGatewayProtocol`).
- **Integraciones y Servicios de Soporte:** `app/services/marketing_tools.py`, `app/services/n8n_service.py`, `app/services/workspace_writer.py`.
- **Rutas FastAPI:** `app/api/routes_office.py`, `app/api/routes_telemetry.py`, `app/api/routes.py`.

---

## 2. Regla 1: Patrón RORO (*Receive an Object, Return an Object*) y Pydantic v2 Puro

Toda función pública de servicio y endpoint REST debe recibir y retornar objetos estructurados fuertemente tipados.

### Directrices de Tipado y Esquemas:
1. **Pydantic v2 Obligatorio:**
   - Usar `ConfigDict` para configuración de modelos (e.g., `model_config = ConfigDict(extra="forbid")`).
   - Usar validadores modernos `@field_validator("campo", mode="before" | "after")` con métodos de clase (`@classmethod`).
   - Serialización mediante `.model_dump()` o `.model_dump_json()`; deserialización mediante `.model_validate(obj)`.
   - **TERMINANTEMENTE PROHIBIDO:** Sintaxis deprecada de Pydantic v1 (`class Config:`, `.dict()`, `.json()`, `@validator`).

2. **Tipado Estricto Python 3.12+ Nativo:**
   - Usar tipos genéricos nativos: `list[str]`, `dict[str, Any]`, `set[int]`, `tuple[str, ...]`.
   - Usar el operador de unión de tipos `|` para nulos y alternativas: `str | None`, `int | float`.
   - Prohibido el uso de `from typing import List, Dict, Set, Optional, Union`.
   - Cero tolerancia al uso indiscriminado de `Any`: todo tipo debe estar explícitamente anotado para superar `mypy --strict app/`.

3. **Ejemplo Canónico RORO:**
   ```python
   # app/schemas/office.py
   from pydantic import BaseModel, ConfigDict, Field

   class AgentExecutionRequest(BaseModel):
       model_config = ConfigDict(extra="forbid")
       project_id: str = Field(..., min_length=1, description="ID único del proyecto")
       prompt_override: str | None = Field(default=None, description="Prompt alternativo")

   class AgentExecutionResponse(BaseModel):
       model_config = ConfigDict(extra="forbid")
       success: bool
       output_path: str
       execution_duration_ms: int
   ```

---

## 3. Regla 2: Persistencia SQLite Idempotente y Robusta (`office_store.py`)

La base de datos `office_data.sqlite` (gestionada en `app/services/office_store.py`) almacena el histórico de conversaciones de agentes, buzón de correos internos, configuración dinámica de modelos LLM y perfiles de marketing.

### Directrices de Persistencia:
1. **Creación Idempotente:**
   - Todas las tablas deben inicializarse con `CREATE TABLE IF NOT EXISTS`.
   - Todos los índices deben crearse con `CREATE INDEX IF NOT EXISTS`.
   - Ninguna inicialización o migración puede eliminar (`DROP`), truncar o vaciar tablas existentes.

2. **Migraciones Seguras en Vivo:**
   - Si se añade una nueva columna a una tabla existente, debe verificarse previamente mediante `PRAGMA table_info(nombre_tabla);`.
   - Solo si la columna no existe, se aplica `ALTER TABLE nombre_tabla ADD COLUMN nombre_columna TIPO NOT NULL DEFAULT valor;`.
   - Patrón obligatorio de referencia:
     ```python
     async with db.execute("PRAGMA table_info(agent_conversations);") as cur:
         existing_cols = [row[1] for row in await cur.fetchall()]
         if "nueva_columna" not in existing_cols:
             await db.execute(
                 "ALTER TABLE agent_conversations "
                 "ADD COLUMN nueva_columna INTEGER NOT NULL DEFAULT 0;"
             )
     ```

3. **PRAGMAs de Concurrencia y Rendimiento:**
   - En cada conexión (`aiosqlite.connect`), asegurar la configuración obligatoria de WAL:
     ```python
     await db.execute("PRAGMA journal_mode = WAL;")
     await db.execute("PRAGMA synchronous = NORMAL;")
     await db.execute("PRAGMA busy_timeout = 5000;")
     ```

4. **Consultas 100% Parametrizadas:**
   - Utilizar exclusivamente el comodín `?` de SQLite para insertar, filtrar o actualizar datos.
   - Prohibido concatenar variables con `f-strings` o formateo de cadenas dentro de sentencias SQL.

---

## 4. Regla 3: Resiliencia en Servicios y LLM Gateway (`llm_gateway.py`)

El flujo de trabajo autónomo de Agent Office no puede interrumpirse por fallos de red, caídas de proveedores de IA o micro-desconexiones en webhooks externos.

### Directrices de Resiliencia:
1. **Protocolo y Multi-Modelo Fallback:**
   - Todas las implementaciones de pasarela deben cumplir `LLMGatewayProtocol` (`invoke_agent`, `ping_model`, `ping_agent_chain`).
   - Si un modelo asignado falla (HTTP 429, 500, timeout o cuota agotada), `llm_gateway.py` debe conmutar automáticamente al siguiente modelo activo configurado en `agent_llm_configs` / `llm_models_catalog`.
   - La última opción de contingencia siempre debe intentar el modelo por defecto definido en `settings.DEFAULT_LLM_MODEL`.

2. **Timeouts Explícitos y Clientes HTTP:**
   - Toda llamada HTTP externa mediante `httpx.AsyncClient` debe definir un timeout explícito y restrictivo (e.g., `timeout=10.0` para diagnóstico/LLMs, `timeout=6.0` para n8n).
   - Prohibido usar `httpx` o `requests` sin timeout configurado.

3. **Manejo Estructurado de Excepciones HTTP:**
   - En `llm_gateway.py`, `marketing_tools.py` y `n8n_service.py`, capturar específicamente:
     - `httpx.TimeoutException`: Degradar servicio o conmutar modelo registrando warning.
     - `HTTP 429 (Rate Limit)`: Respetar pausas o activar fallback a proveedor secundario.
     - `HTTP 401 / 403`: Marcar proveedor/herramienta como no configurada (`has_api_key = False`) sin colapsar el proceso principal.
     - `HTTP 5xx`: Reintentar según `max_retries` o reportar error controlado al nodo llamador.

4. **Integración con Telemetría:**
   - Cada fallo, conmutación por fallback o latencia debe registrarse en las métricas de `app/api/routes_telemetry.py` sin interrumpir la experiencia de usuario en el panel frontend.

---

## 5. Regla 4: Retrocompatibilidad y Contratos de Grafo

El orquestador central se apoya en LangGraph (`StateGraph`). Cualquier cambio en los servicios o esquemas debe preservar intacta la interfaz consumida por los nodos y el router.

1. **Firmas Públicas Inmutables:**
   - Prohibido modificar las firmas de los nodos en `app/graph/nodes.py` ni la lógica de enrutamiento condicional de `app/graph/router.py`.
   - Si se añade nueva funcionalidad a un servicio (`OfficeStore`, `GeminiLLMGateway`, `WorkspaceWriter`), hacerlo mediante parámetros opcionales con valores por defecto seguros.

2. **Estado Compartido del Grafo (`GraphState`):**
   - El modelo de estado `GraphState` definido en `app/graph/state.py` es el contrato canónico. Nuevos campos deben ser de tipo `Optional` / `| None` con valor por defecto `None` para no invalidar checkpoints previos guardados en `checkpoints.sqlite`.

3. **Asincronía Pura y Cero Bloqueos:**
   - Todo endpoint de FastAPI y todo nodo de LangGraph debe declararse como `async def`.
   - Operaciones de disco síncronas (e.g., `workspace_writer.py` o extracción en `code_materializer.py`) deben delegarse obligatoriamente a hilos secundarios con `await asyncio.to_thread(...)`.

4. **Política Zero Placeholders:**
   - Queda estrictamente prohibido entregar código incompleto, esqueletos con `# TODO`, `pass` en funciones productivas o comentarios como `# ... resto del código ...`.
   - Todo módulo modificado o añadido debe quedar funcional al 100%.

---

## 6. Procedimiento de Verificación de Calidad

Antes de considerar concluida cualquier tarea que afecte a estos componentes, es obligatorio verificar el entorno ejecutando:

```powershell
# 1. Linting y chequeo de estilo
ruff check .

# 2. Análisis estático de tipos estricto
mypy --strict app/

# 3. Suite de pruebas automatizadas
pytest
```
Todo error o advertencia debe quedar subsanado sin comprometer la tipificación ni la cobertura de tests.
