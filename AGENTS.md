# AGENTS.md — Arquitectura Maestra y Gobernanza de Agentes | Agent Office

> **Factoría de Software Autónomo con LangGraph, FastAPI y Google Antigravity**  
> **Versión del Sistema:** Agent Office v2.5 (Cyber-Loft Engine)  
> **Ámbito de Aplicación:** Raíz del proyecto y subdirectorio `langGraph/`

Este documento constituye el **índice de arquitectura maestro** y el reglamento de ingeniería de **Agent Office**. Define el mapa integral de módulos, las directrices innegociables de desarrollo, la matriz de activación para el catálogo completo de **7 Skills de Google Antigravity** alojadas en `.agent/skills/` y los **6 Agentes Ejecutores (Workflows Operativos)** alojados en `.agent/workflows/`.

---

## 1. Visión General y Estructura del Repositorio

Agent Office es un sistema de factoría de software autónoma compuesto por una cadena de montaje de 13 agentes de inteligencia artificial coordinados mediante LangGraph, respaldado por un backend en FastAPI, persistencia asíncrona en SQLite y un cuadro de mando 2D interactivo en Vanilla JS.

### Mapa de Directorios y Ubicación de Módulos:
El código fuente operativo del backend reside en el subdirectorio `langGraph/` (con enlaces de trabajo hacia la raíz):

```text
agentoffice/
├── .agent/
│   ├── skills/
│   │   ├── fastapi-sqlite-core/
│   │   │   └── SKILL.md                 # Estándar FastAPI, Pydantic v2, SQLite y LLM Gateway
│   │   ├── cybersecurity-appsec-guardian/
│   │   │   └── SKILL.md                 # Auditoría AppSec, DevSecOps y Circuit Breakers
│   │   ├── n8n-integration-expert/
│   │   │   └── SKILL.md                 # Workflows JSON n8n, API REST v1 y Webhooks
│   │   ├── docker-compose-infra/
│   │   │   └── SKILL.md                 # Docker Compose, redes bridge, SQLite WAL y deployers
│   │   ├── vanilla-js-pixel-ui/
│   │   │   └── SKILL.md                 # Frontal Vanilla JS ES6+, Pixel-Art y seguridad DOM
│   │   ├── pytest-zero-network-qa/
│   │   │   └── SKILL.md                 # Guardián de calidad, mocks 100% offline y no-regresión
│   │   └── docs-diataxis-curator/
│   │       └── SKILL.md                 # Documentación Diátaxis, manuales de usuario y sincronización
│   └── workflows/
│       ├── sec-audit.md                 # /sec-audit: Auditoría profunda de Ciberseguridad AppSec
│       ├── feature-fullstack.md         # /feature-fullstack: Desarrollo Full-Stack End-to-End
│       ├── n8n-docker-sync.md           # /n8n-docker-sync: Sincronización n8n & Infra Docker
│       ├── qa-audit.md                  # /qa-audit: Auditoría de QA, Caos y No-Regresión
│       ├── ui-inspector.md              # /ui-inspector: Inspección y Optimización UI Pixel-Art
│       └── docs-sync.md                 # /docs-sync: Sincronización Documental Diátaxis
├── AGENTS.md                            # Índice maestro de arquitectura y gobernanza (este archivo)
├── prompts/                             # Catálogo de prompts de agentes y directrices del sistema
├── workspaces/                          # Espacio de trabajo compartido y persistencia
└── langGraph/                           # Núcleo del Backend FastAPI + LangGraph
    ├── app/
    │   ├── core/
    │   │   └── config.py                # Configuración global tipada (Pydantic Settings)
    │   ├── schemas/                     # Contratos RORO Pydantic v2
    │   │   ├── office.py                # Estados de oficina, catálogo LLM, emails internos
    │   │   ├── api.py                   # Peticiones y respuestas de creación/ejecución
    │   │   ├── routing.py               # Identificadores de agentes (AgentID) y entregables
    │   │   ├── telemetry.py             # Eventos en tiempo real, KPIs y Circuit Breakers
    │   │   ├── chat.py                  # Interacciones de chat con agentes
    │   │   ├── file_edit.py             # Propuestas y aplicación de cambios de código
    │   │   └── brownfield.py            # Auditoría e ingesta de repositorios existentes
    │   ├── services/                    # Capa de servicios y lógica de negocio
    │   │   ├── office_store.py          # Persistencia SQLite (office_data.sqlite)
    │   │   ├── llm_gateway.py           # Pasarela de LLMs con fallback multimodelo
    │   │   ├── workspace_writer.py      # Escritura asíncrona de entregables en disco
    │   │   ├── code_materializer.py     # Extracción y materialización de código ejecutable
    │   │   ├── file_edit_service.py     # Edición de archivos segura en workspace
    │   │   ├── brownfield_service.py    # Auditoría e inspección de repositorios
    │   │   ├── marketing_tools.py       # Herramientas de marketing multicanal
    │   │   ├── n8n_service.py           # Integración y aprovisionamiento de n8n
    │   │   ├── chat_service.py          # Orquestación de conversaciones con agentes
    │   │   ├── orchestrator_service.py  # Despacho de ejecuciones en LangGraph
    │   │   ├── local_deployer.py        # Validación y despliegue local con Docker
    │   │   ├── vercel_deployer.py       # Despliegue de paquetes en Vercel Cloud
    │   │   └── dashboard_service.py     # Transmisión SSE de telemetría y eventos
    │   ├── graph/                       # Cadena de montaje autónoma LangGraph
    │   │   ├── workflow.py              # Definición del StateGraph del ciclo de vida
    │   │   ├── nodes.py                 # Nodos operativos de los agentes y compuertas
    │   │   ├── router.py                # Enrutador condicional y control de bucles
    │   │   └── state.py                 # Contrato del estado compartido (GraphState)
    │   ├── api/                         # Capa de transporte REST (FastAPI)
    │   │   ├── routes_office.py         # Endpoints de oficina, catálogo y marketing
    │   │   ├── routes_telemetry.py      # Endpoints de observabilidad, SSE y base de datos
    │   │   └── routes.py                # Endpoints base y ciclo de vida de proyectos
    │   └── static/                      # Cuadro de mando visual Vanilla JS (Cyber-Loft 2D)
    │       ├── js/panel.js              # Lógica de pestañas, formularios y marketing
    │       ├── js/office.js             # Visualización del mapa 2D y avatares
    │       ├── js/dashboard.js          # Métricas en tiempo real, KPIs y Circuit Breakers
    │       ├── js/api.js                # Cliente HTTP para el backend FastAPI
    │       ├── js/main.js               # Punto de entrada e inicialización de módulos
    │       └── css/pixel.css            # Sistema de diseño Pixel-Art retro 16-bit
    ├── docs/                            # Manuales y especificaciones de arquitectura
    │   └── manual_usuario_capitulo_5_security_circuit_breakers.md
    └── tests/                           # Suite de pruebas automatizadas con pytest (Fases 1 a 19)
```

---

## 2. Matriz de Activación de las 7 Skills en Google Antigravity

Antigravity evalúa el contexto de la tarea y la descripción de cada skill ubicada en `.agent/skills/` para cargarlas bajo demanda (*Progressive Disclosure*). A continuación se establece la matriz oficial de decisión:

| Skill | Ubicación | Cuándo debe cargarse | Responsabilidad principal |
| :--- | :--- | :--- | :--- |
| **`fastapi-sqlite-core`** | [`.agent/skills/fastapi-sqlite-core/SKILL.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/skills/fastapi-sqlite-core/SKILL.md) | Al trabajar en `app/core/`, `app/schemas/`, `app/services/office_store.py`, `app/services/llm_gateway.py` o endpoints de `app/api/`. | Implementación del patrón RORO, Pydantic v2 estricto, persistencia idempotente en SQLite y resiliencia en la pasarela multi-modelo. |
| **`cybersecurity-appsec-guardian`** | [`.agent/skills/cybersecurity-appsec-guardian/SKILL.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/skills/cybersecurity-appsec-guardian/SKILL.md) | Al manejar credenciales/secretos, escribir en disco, realizar consultas SQL, llamar a webhooks/red, manipular el DOM en JS o alterar compuertas de seguridad. | Blindaje contra Path Traversal, SSRF, XSS, SQL Injection, fuga de API Keys y respeto a los Circuit Breakers del CISO. |
| **`n8n-integration-expert`** | [`.agent/skills/n8n-integration-expert/SKILL.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/skills/n8n-integration-expert/SKILL.md) | Al diseñar o modificar flujos de automatización n8n, llamadas a `/api/v1/workflows`, nodos webhook de proyectos en `app/services/n8n_service.py` o integraciones de marketing. | Diseño de workflows JSON válidos (`CreateWorkflowPublicDto`), aislamiento por proyecto, llamadas asíncronas con timeout y materialización segura. |
| **`docker-compose-infra`** | [`.agent/skills/docker-compose-infra/SKILL.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/skills/docker-compose-infra/SKILL.md) | Al gestionar `docker-compose.yml`, `Dockerfile`, `.dockerignore`, redes entre contenedores (FastAPI + n8n), persistencia de volúmenes SQLite o lógica en `local_deployer.py` / `vercel_deployer.py`. | Garantía de persistencia para SQLite (WAL) y n8n, networking dual (red bridge vs host), hardening de contenedores y healthchecks. |
| **`vanilla-js-pixel-ui`** | [`.agent/skills/vanilla-js-pixel-ui/SKILL.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/skills/vanilla-js-pixel-ui/SKILL.md) | Al modificar la interfaz web en `app/static/` (`panel.js`, `office.js`, `dashboard.js`, `api.js`, `pixel.css`, `index.html`, `dashboard.html`). | Stack estricto Vanilla JS ES6+ (cero frameworks), escape XSS con `_esc(s)`, centralización de llamadas en `api.js` y diseño Pixel-Art Cyber-Loft. |
| **`pytest-zero-network-qa`** | [`.agent/skills/pytest-zero-network-qa/SKILL.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/skills/pytest-zero-network-qa/SKILL.md) | Al crear o modificar pruebas en `tests/`, verificar no-regresión de fases (Fases 1-19), simular errores HTTP o aislar SQLite con `tmp_path`. | Mocks 100% offline (cero peticiones de red reales), cobertura en 3 capas (BD, API, Resiliencia) y triple verificación de cierre. |
| **`docs-diataxis-curator`** | [`.agent/skills/docs-diataxis-curator/SKILL.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/skills/docs-diataxis-curator/SKILL.md) | Al actualizar manuales en `docs/`, prompts en `prompts/`, variables en `.env.example`, o crear diagramas Mermaid de arquitectura. | Framework Diátaxis, sincronización `config.py` <-> `.env.example`, higiene y contratos sintácticos en prompts de agentes. |

---

## 3. Catálogo de Agentes Ejecutores y Workflows Operativos (`.agent/workflows/`)

Los **Workflows Operativos** representan rutinas de ejecución autónoma accesibles mediante comandos directos (`/<workflow>`) o despacho de tareas especializadas:

| Comando / Workflow | Archivo | Propósito Operativo | Skills Activadas |
| :--- | :--- | :--- | :--- |
| **`/sec-audit`** | [`.agent/workflows/sec-audit.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/workflows/sec-audit.md) | Auditoría profunda de ciberseguridad (secretos, SQLi, Path Traversal, SSRF, XSS, Circuit Breakers y Docker). | `cybersecurity-appsec-guardian`, `fastapi-sqlite-core`, `pytest-zero-network-qa` |
| **`/feature-fullstack`** | [`.agent/workflows/feature-fullstack.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/workflows/feature-fullstack.md) | Implementación de funcionalidad completa end-to-end (SQLite + Schemas + FastAPI + Servicios + Frontal Cyber-Loft + Tests 3 capas). | `fastapi-sqlite-core`, `cybersecurity-appsec-guardian`, `vanilla-js-pixel-ui`, `pytest-zero-network-qa` |
| **`/n8n-docker-sync`** | [`.agent/workflows/n8n-docker-sync.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/workflows/n8n-docker-sync.md) | Sincronización y validación de workflows n8n (`CreateWorkflowPublicDto`), webhooks aislados y contenedores Docker Compose. | `n8n-integration-expert`, `docker-compose-infra`, `cybersecurity-appsec-guardian` |
| **`/qa-audit`** | [`.agent/workflows/qa-audit.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/workflows/qa-audit.md) | Auditoría de cobertura, tests en 3 capas 100% offline (sin red) y verificación de no-regresión (Fases 1-19). | `pytest-zero-network-qa`, `fastapi-sqlite-core` |
| **`/ui-inspector`** | [`.agent/workflows/ui-inspector.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/workflows/ui-inspector.md) | Inspección, refactorización y aseguramiento estético Pixel-Art y funcional del frontal Cyber-Loft en Vanilla JS. | `vanilla-js-pixel-ui`, `cybersecurity-appsec-guardian` |
| **`/docs-sync`** | [`.agent/workflows/docs-sync.md`](file:///c:/Proyectos%20Docker/agentoffice/.agent/workflows/docs-sync.md) | Sincronización continua de `.env.example`, manuales por capítulos (Diátaxis), diagramas Mermaid y contratos de `prompts/`. | `docs-diataxis-curator`, `fastapi-sqlite-core` |

---

## 4. Reglas Innegociables de Ingeniería

Cualquier agente de inteligencia artificial o desarrollador que opere en este repositorio debe cumplir estrictamente las siguientes normas:

1. **Stack Tecnológico Estricto:**
   - Python 3.12+
   - FastAPI
   - LangGraph (`StateGraph`)
   - `langchain-google-genai`
   - `langgraph-checkpoint-sqlite`
   - Pydantic v2
   - `aiosqlite`
   - `PyYAML`

2. **Tipado Estricto (Strict Typing):**
   - Todo el código backend debe superar la verificación de `mypy --strict app/` sin excepciones ni advertencias.
   - Prohibido el uso de `Any` no justificado.
   - Sintaxis nativa de tipos de Python 3.12 (`list[str]`, `dict[str, int]`, `X | None`, `Annotated`). Prohibido importar `List`, `Dict`, `Optional` de `typing`.

3. **Pydantic v2 Puro:**
   - Uso exclusivo de `ConfigDict`, `@field_validator`, `.model_dump()`, `.model_validate()`.
   - Prohibida terminantemente la sintaxis obsoleta de Pydantic v1 (`class Config:`, `.dict()`, `.json()`, `@validator`).

4. **Asincronía Pura y Cero Bloqueos:**
   - Todos los nodos del grafo LangGraph, endpoints de FastAPI y operaciones de red/base de datos deben ser corrutinas `async def` no bloqueantes.
   - Para operaciones de disco o funciones síncronas de CPU intensiva, es mandatorio utilizar `await asyncio.to_thread(...)`.

5. **Política Zero Placeholders:**
   - Prohibido dejar `# TODO`, funciones con `pass` en lógica operativa o comentarios de elisión tipo `# ... resto del código ...`.
   - Cada entrega debe contener archivos completos, compilables y funcionales.

6. **Seguridad y Circuit Breakers Intocables:**
   - El límite de 3 iteraciones en el router del grafo (*Anti-Loop Circuit Breaker*) no puede anularse ni alterarse.
   - El veto del Agente 10 (CISO) y de los validadores de QA (Agentes 05 y 06) es de obligado cumplimiento para la transición a fases de despliegue.
   - Las consultas a bases de datos deben ser 100% parametrizadas (`?`) y el frontal JS debe escapar todo contenido dinámico con `_esc(s)`.

7. **Verificación Obligatoria de Cierre de Fase:**
   - Tras cualquier cambio funcional, es obligatorio ejecutar en la terminal:
     1. `ruff check .`
     2. `mypy --strict app/`
     3. `pytest`
   - No se dará por cerrada ninguna fase o iteración si existen errores en cualquiera de estas tres verificaciones.
