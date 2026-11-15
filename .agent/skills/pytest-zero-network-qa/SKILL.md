---
name: pytest-zero-network-qa
description: Guardián de calidad, tipado estricto y testing en pytest para Agent Office. Garantiza cero llamadas de red reales durante los tests, aislamiento de SQLite y protección de las 18+ fases de regresión.
---

# Pytest Zero-Network QA & Regression Guardian — Agent Office

Este manual de ingeniería y protocolo de pruebas automatizadas rige el aseguramiento de calidad (QA), las políticas de no-regresión y el diseño de tests para **Agent Office**.

Aplica de forma directa al directorio `tests/`, la configuración de fixtures en `conftest.py`, el uso de dobles de prueba (`MockLLMGateway`, `AsyncMock`) y la validación en CI/CD local con `pytest`.

---

## 1. Módulos y Suites de Prueba Bajo Alcance

El framework de pruebas de Agent Office valida el ciclo de vida completo de la factoría de software autónoma:

- **Fases Fundacionales y de Servicios (Fases 1 a 8):**
  - `tests/test_phase1_foundation.py` a `test_phase8_notion_mcp.py` (esquemas Pydantic v2, nodos LangGraph, StateGraph, persistencia y RAG).
- **APIs, Telemetría y Oficina (Fases 9 a 19):**
  - `tests/test_phase9_office_api.py`, `test_phase10_integrations.py`, `test_phase11_vercel_deployer.py`, `test_telemetry_routes.py`, `test_phase16_chat_service.py`, `test_phase17_file_edit.py`, `test_phase18_brownfield.py`, `test_phase19_whatsapp.py`.
- **Especialistas y Nodos Críticos:**
  - `tests/test_node_00_ceo.py`, `tests/test_ceo_tools.py`, `tests/test_ceo_node_integration.py`.
- **Integraciones de Marketing y Automatización:**
  - `tests/test_n8n_marketing_integration.py`, `tests/test_marketing_execution_ondemand.py`, `tests/test_phase_marketing_lifecycle.py`.
- **Resiliencia, Concurrencia y Caos:**
  - `tests/test_stress_chaos.py`, `tests/test_dashboard_streaming.py`, `tests/test_llm_routing_and_ping.py`.

---

## 2. Regla 1: Regla de Oro — Cero Red en Tests (100% Offline / Mocks)

Está **estrictamente prohibido** que cualquier prueba automatizada en `tests/` realice peticiones de red reales. Los tests deben ejecutarse a máxima velocidad, sin consumir cuotas de APIs de pago y en entornos completamente desconectados (Air-Gapped).

### Protocolo de Simulación:
1. **Modelos de Lenguaje (LLMs):**
   - Nunca llamar a los endpoints reales de Google Gemini, Groq, Mistral, OpenAI, Anthropic ni DeepSeek.
   - Activar siempre `settings.USE_MOCK_LLM = True` o inyectar `MockLLMGateway`:
     ```python
     from app.services.llm_gateway import MockLLMGateway
     gateway = MockLLMGateway()
     ```
2. **Servicios de Red y Mensajería Externa:**
   - Para llamadas HTTP externas con `httpx.AsyncClient` (e.g. n8n REST API, Resend, Vercel, Notion, WhatsApp), interceptar obligatoriamente con `unittest.mock.patch`, `AsyncMock` o `respx`:
     ```python
     from unittest.mock import AsyncMock, patch

     with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
         mock_post.return_value.status_code = 201
         mock_post.return_value.json.return_value = {"id": "wf_test_123"}
         # Ejecución del test...
     ```
3. **Servidores SMTP/IMAP y DNS:**
   - Simular envíos de correo mediante `MailService` con backend `OfficeStore` en memoria o dobles de prueba sin aperturas de sockets reales (`socket.connect`).

---

## 3. Regla 2: Aislamiento Hermético de SQLite y Workspaces

Ningún test puede escribir, alterar ni consultar los archivos reales de producción `workspaces/office_data.sqlite`, `office_state.db` o la carpeta `workspaces/`.

### Patrón Obligatorio con `tmp_path`:
Todo test que interactúe con base de datos o disco debe recibir el fixture `tmp_path: Path` de pytest:

```python
import pytest
from pathlib import Path
from app.core.config import settings
from app.services.office_store import OfficeStore
from app.services.workspace_writer import WorkspaceWriter

@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    test_db = tmp_path / "test_office_data.sqlite"
    test_workspaces = tmp_path / "workspaces"
    test_workspaces.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "OFFICE_DB_PATH", str(test_db))
    monkeypatch.setattr(settings, "WORKSPACES_DIR", str(test_workspaces))
    monkeypatch.setattr(settings, "USE_MOCK_LLM", True)

    store = OfficeStore(db_path=test_db)
    writer = WorkspaceWriter(base_dir=test_workspaces)
    return {"store": store, "writer": writer, "tmp_path": tmp_path}
```

---

## 4. Regla 3: Cobertura Obligatoria en 3 Capas para Nuevas Funcionalidades

Toda nueva capacidad, servicio o endpoint incorporado a Agent Office debe acompañarse de una suite que cubra las 3 capas:

### Capa 1: Persistencia & Esquemas RORO
- **Ubicación:** `tests/test_office_store.py` o módulo específico.
- **Validaciones:**
  - Esquema Pydantic v2 estricto (`model_validate`, `model_dump`, validadores `@field_validator`).
  - Creación de tablas e inserciones idempotentes en SQLite (`CREATE TABLE IF NOT EXISTS`).
  - Filtrado, serialización JSON y lectura consistente.

### Capa 2: API REST & Transporte FastAPI
- **Ubicación:** `tests/test_routes_*.py`.
- **Validaciones:**
  - Peticiones asíncronas con `AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")`.
  - Códigos de respuesta exitosos (`200 OK`, `201 Created`).
  - Validación de esquemas inválidos (`422 Unprocessable Entity`).
  - **Seguridad AppSec:** Confirmar que endpoints `GET` nunca devuelven claves o tokens en plano (`has_api_key: true`, valores `****`).

### Capa 3: Lógica de Servicio, Fallback & Resiliencia
- **Ubicación:** `tests/test_llm_routing_*.py` o tests de servicio.
- **Validaciones:**
  - Simulación de fallos controlados: errores `HTTP 429 Rate Limit`, `401 Unauthorized`, `500 Internal Error` y `httpx.TimeoutException`.
  - Verificación de conmutación a modelo secundario (*fallback chain*) sin detención del servidor.
  - Activación correcta de Circuit Breakers al alcanzar el tope de 3 intentos en el router LangGraph.

---

## 5. Regla 4: Triple Verificación de Cierre de Fase

Ningún desarrollo, refactorización o corrección de defectos se considera apto para merge o entrega sin haber ejecutado y superado de forma consecutiva:

```powershell
# 1. Chequeo de formateo y estilo de código
ruff check .

# 2. Análisis estático de tipos estricto (cero advertencias)
mypy --strict app/

# 3. Suite completa de regresión (0 errores, 0 fugas de red)
pytest
```

Si algún test de fases previas (Fase 1 a 19) falla, el cambio es considerado **regresión crítica** y debe subsanarse de inmediato antes de continuar.
