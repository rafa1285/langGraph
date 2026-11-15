---
description: Audita la cobertura de pruebas, crea tests unitarios/integración en 3 capas con mocks 100% offline y verifica cero regresiones en todas las fases de pytest.
---

# Workflow: Auditoría de QA, Caos y No-Regresión (`/qa-audit`)

Este workflow operativo rige la ejecución, diseño y verificación de suites de pruebas automatizadas en **Agent Office**, asegurando que cada componente cuente con cobertura en 3 capas sin fugas de red ni contaminación de datos.

---

## 1. Activación de Skills Requeridas

- **`pytest-zero-network-qa`** (Protocolo Zero-Network, fixtures aislados con `tmp_path` y triple verificación).
- **`fastapi-sqlite-core`** (Validación de contratos Pydantic v2 y asincronía).

---

## 2. Procedimiento de Auditoría de Pruebas

### Paso 1: Análisis de Código Modificado
1. Identificar módulos nuevos o alterados en `app/` (`schemas/`, `services/`, `api/`, `graph/`).
2. Comprobar si existen tests asociados en `tests/` y determinar posibles huecos de cobertura.

### Paso 2: Diseño de Pruebas en 3 Capas (100% Offline)
1. **Capa 1: Persistencia y Esquemas:**
   - Crear o ampliar tests que validen esquemas Pydantic v2 (`model_validate()`, `@field_validator`) e inserciones/lecturas en `OfficeStore` usando bases de datos efímeras creadas en `tmp_path`.
2. **Capa 2: Endpoints REST (FastAPI):**
   - Configurar cliente asíncrono con transporte en memoria:
     ```python
     transport = ASGITransport(app=app)
     async with AsyncClient(transport=transport, base_url="http://testserver") as client:
         res = await client.get("/api/v1/projects")
         assert res.status_code == 200
     ```
   - Validar casos de éxito (`200 OK`, `201 Created`), errores de validación (`422 Unprocessable Entity`) y ausencia de credenciales en respuestas `GET`.
3. **Capa 3: Resiliencia, Fallbacks y Caos:**
   - Utilizar `MockLLMGateway` o `unittest.mock.patch` con `AsyncMock` para simular fallos de red:
     - Error `HTTP 429 (Rate Limit)`.
     - Error `HTTP 401 / 403` (falta de API Key).
     - Error `HTTP 500 / 503` (caída temporal de proveedor).
     - `httpx.TimeoutException` (latencia excesiva).
   - Confirmar que el sistema conmuta al modelo de contingencia o activa el Circuit Breaker sin interrumpir el servidor.

### Paso 3: Aislamiento de Entorno
1. Garantizar que en cada fixture de prueba:
   ```python
   settings.USE_MOCK_LLM = True
   settings.OFFICE_DB_PATH = str(tmp_path / "test_office.sqlite")
   settings.WORKSPACES_DIR = str(tmp_path / "workspaces")
   ```
2. Prohibir cualquier acceso a `workspaces/office_data.sqlite` o llamadas reales a internet.

---

## 3. Triple Verificación de Cierre Obligatoria

Ejecutar la secuencia completa de validación técnica:

```powershell
# 1. Linting y formato
ruff check .

# 2. Tipado estricto
mypy --strict app/

# 3. Suite completa de regresión (todas las fases 1 a 19)
pytest
```

El informe final debe certificar **0 fallos, 0 errores de tipado y 0 advertencias de regresión**.
