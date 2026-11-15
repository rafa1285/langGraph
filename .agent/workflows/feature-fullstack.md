---
description: Implementa una funcionalidad completa end-to-end en Agent Office (SQLite idempotente + Schemas Pydantic v2 + FastAPI + Servicios asíncronos + Frontal Cyber-Loft Pixel-Art + Tests Pytest).
---

# Workflow: Desarrollo Full-Stack End-to-End (`/feature-fullstack`)

Este workflow operativo guía la implementación completa de una nueva funcionalidad en **Agent Office**, abarcando desde el modelado de datos en SQLite y FastAPI hasta la interfaz gráfica Pixel-Art en Vanilla JS y su batería de pruebas 100% offline.

---

## 1. Activación de Skills Requeridas

- **`fastapi-sqlite-core`** (Estándar RORO, Pydantic v2 y persistencia en SQLite).
- **`cybersecurity-appsec-guardian`** (Prevención de fuga de credenciales, Path Traversal, SSRF y XSS).
- **`vanilla-js-pixel-ui`** (Vanilla JS nativo, `_esc(s)`, tokens de `pixel.css` y centralización en `api.js`).
- **`pytest-zero-network-qa`** (Pruebas en 3 capas, mocks herméticos y no-regresión).

---

## 2. Flujo de Implementación Paso a Paso

### Paso 1: Contratos RORO y Esquemas Pydantic v2
1. Definir los contratos de petición y respuesta en el módulo correspondiente dentro de `app/schemas/` (`office.py`, `api.py`, `telemetry.py` o nuevo sub-esquema):
   - Emplear exclusivamente sintaxis Pydantic v2: `ConfigDict(extra="forbid")`, `@field_validator`.
   - Tipado nativo de Python 3.12 (`list[str]`, `dict[str, Any]`, `X | None`).
   - Cero uso de tipos de Pydantic v1.

### Paso 2: Persistencia Idempotente en SQLite (`office_store.py`)
1. Incorporar las nuevas entidades a `app/services/office_store.py`:
   - Para tablas nuevas: `CREATE TABLE IF NOT EXISTS nueva_tabla (...)`.
   - Para columnas en tablas preexistentes: comprobar existencia con `PRAGMA table_info(...)` y aplicar `ALTER TABLE ... ADD COLUMN ...`.
   - Asegurar el uso de WAL y busy timeout en la conexión.
   - Utilizar sentencias SQL 100% parametrizadas con `?`.

### Paso 3: Lógica de Negocio y Endpoints REST (FastAPI)
1. Implementar los servicios asíncronos en `app/services/`:
   - Todas las funciones públicas deben ser corrutinas `async def`.
   - Operaciones de I/O de disco delegadas con `await asyncio.to_thread(...)`.
   - Timeouts explícitos en clientes HTTP (`httpx.AsyncClient(timeout=...)`).
2. Exponer los endpoints REST en `app/api/routes_office.py` o router correspondiente:
   - Recibir y retornar objetos de esquema (patrón RORO).
   - Validar códigos de estado HTTP semánticos (`200 OK`, `201 Created`, `404 Not Found`).
   - Enmascarar cualquier secreto en respuestas de lectura (`has_api_key: bool`).

### Paso 4: Frontal Vanilla JS & Sistema de Diseño Pixel-Art
1. Añadir los métodos correspondientes en `app/static/js/api.js`:
   - Centralizar todas las llamadas `fetch` con parseo estructurado de respuestas y errores.
2. Construir o ampliar la vista en `app/static/js/panel.js` o `office.js`:
   - Modularidad no destructiva: registrar *event listeners* con `addEventListener` sin sobrescribir manejadores previos.
   - Asignar textos con `textContent` o sanitizar toda interpolación en `innerHTML` con `_esc(s)`.
   - Manejar estados de carga en botones interactivos (`disabled = true`, `⏳ Procesando...`).
   - Respetar los tokens visuales y clases retro de `app/static/css/pixel.css` (`.pixel-btn`, `.telemetry-card`, etc.).

### Paso 5: Pruebas Automatizadas en 3 Capas (Pytest 100% Offline)
1. Crear la suite de pruebas en `tests/` cubriendo:
   - **Capa 1 (Store & Schemas):** Pruebas unitarias de serialización y lectura/escritura en SQLite aislado (`tmp_path`).
   - **Capa 2 (API REST):** Peticiones con `AsyncClient(transport=ASGITransport(app=app))` validando respuestas y manejo de errores `422`.
   - **Capa 3 (Resiliencia):** Simulación de errores de red o cuota (`429`, timeouts) mediante `MockLLMGateway` o `AsyncMock`.

---

## 3. Triple Verificación de Cierre

Antes de finalizar la tarea, es obligatorio ejecutar:

```powershell
ruff check .
mypy --strict app/
pytest
```
Verificar que no existan advertencias ni regresiones en ninguna de las fases previas del sistema.
