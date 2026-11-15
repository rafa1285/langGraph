---
name: docs-diataxis-curator
description: Especialista en documentación técnica viva, manuales de usuario por capítulos, diagramas Mermaid, higiene de prompts y mantenimiento de .env.example en Agent Office.
---

# Docs & Diátaxis Framework Curator — Agent Office

Este manual y estándar de documentación técnica rige la creación, mantenimiento y sincronización de los artefactos documentales de **Agent Office**: manuales de usuario para negocio, especificaciones de arquitectura, diagramas Mermaid, catálogo de prompts, variables de entorno en `.env.example` y publicación en vivo en **Notion**.

Aplica a `docs/`, `prompts/`, `.env.example`, `README.md`, `app/services/notion_docs_sync.py` y a los manuales ejecutivos por capítulos.

---

## 1. El Framework Diátaxis en Agent Office

Toda la documentación técnica producida en el proyecto debe alinearse con uno de los 4 cuadrantes del **Framework Diátaxis**:

| Cuadrante | Orientación | Enfoque en Agent Office | Ejemplo en el Repositorio |
| :--- | :--- | :--- | :--- |
| **Tutoriales** | Práctica / Aprendizaje | Guías de inicio rápido (*Quickstart*) para nuevos operadores. | `README.md`, `start_local.ps1` / `start_local.sh`. |
| **Guías Prácticas (How-To)** | Tarea / Problema | Pasos específicos para resolver incidentes o flujos operativos. | Casos prácticos de resolución de vetos CISO. |
| **Referencia Técnica** | Información / Contrato | Esquemas Pydantic v2, endpoints REST, tablas SQLite, `.env.example`. | `AGENTS.md`, `docs/manual_*.md` (tablas de APIs y BD). |
| **Explicación / Arquitectura** | Comprensión / Concepto | Filosofía de la factoría, topología LangGraph, Circuit Breakers. | `manual_usuario_capitulo_5_security_circuit_breakers.md`. |

---

## 2. Regla 1: Sincronización Estricta Código-Configuración (`config.py` <-> `.env.example`)

La configuración de la aplicación en `app/core/config.py` (`Settings`) debe mantenerse en permanente sincronía con el archivo de plantilla `.env.example`.

### Directrices Innegociables:
1. **Registro Simultáneo:**
   - Si se añade un nuevo campo en `app/core/config.py`, es obligatorio incorporarlo de inmediato a `.env.example` con su descripción y tipo.
2. **Cero Secretos Reales en `.env.example`:**
   - Solo se permiten valores ficticios, ejemplos seguros o cadenas vacías (e.g. `GEMINI_API_KEY=dummy-key-for-tests`, `GROQ_API_KEY=`, `N8N_BASE_URL=http://localhost:5678`).
   - Jamás commitear credenciales productivas ni tokens personales.
3. **Agrupación Modular Comentada:**
   - Las variables deben organizarse en bloques temáticos coherentes (LLM Providers, Storage & Workspaces, n8n Automation, Notion MCP, Telemetría LangSmith, Canales de Comunicación).

---

## 3. Regla 2: Coherencia con Manuales por Capítulos y Diagramas Mermaid

Los manuales de usuario de Agent Office (ubicados en `docs/` o sincronizados con Notion) combinan rigor técnico con legibilidad ejecutiva para directivos y auditores.

### Estructura Canónica de Cada Capítulo:
1. **Encabezado Ejecutivo:** Metadatos claros (versión, destinatarios, ruta en la UI Cyber-Loft, enlace Notion).
2. **Propósito de Negocio:** Explicación en lenguaje directo de por qué la característica protege el presupuesto, el cumplimiento normativo o la calidad del software.
3. **Diagrama Mermaid Visual:**
   - Todo flujo o ciclo de vida debe ilustrarse con un diagrama `flowchart TD` o `flowchart LR` claro y auto-explicativo:
     ```mermaid
     flowchart TD
         A["Desarrollo"] --> B["QA Validation"]
         B -- "🚨 RECHAZADO" --> A
         B -- "APROBADO" --> C["CISO Security Gate"]
         C -- "🛡️ BLOQUEADO" --> A
         C -- "APROBADO" --> D["Lanzamiento"]
     ```
4. **Anatomía de Pantalla / Controles de UI:** Desglose de botones, chips, métricas y badges con sus estados cromáticos (`✅ RESOLVED`, `🟢 NORMAL`, `⚠️ TRIPPED`).
5. **Casos Prácticos Reales:** Ejemplos basados en proyectos existentes (como `validator-hq-saas` o `proj_88c9fd46`).
6. **Preguntas Frecuentes y Guía de Decisiones (FAQ & Troubleshooting):** Tabla de contingencia y preguntas clave para la dirección de producto.

---

## 4. Regla 3: Flujo Dual de Sincronización en Vivo a Notion (`notion_docs_sync.py`)

Agent Office mantiene una estrategia documental híbrida: persistencia local en `langGraph/docs/` y publicación nativa en vivo en el workspace corporativo de **Notion**.

### Directrices de Publicación en Notion:
1. **Servicio Oficial de Sincronización:**
   - El módulo `app/services/notion_docs_sync.py` (`NotionDocsSyncService`) convierte los archivos `.md` en bloques nativos de la API de Notion (`v1/blocks`).
   - Renderizado nativo de diagramas: los bloques ```` ```mermaid ```` se publican como bloques `code` con `"language": "mermaid"` para renderizado visual interactivo en Notion.
2. **Paginación y Fragmentación Automática:**
   - Textos extensos fragmentados en trozos de `<= 2.000` caracteres (`split_text_chunks`).
   - Envío de bloques en lotes de `<= 100` por petición (`PATCH /v1/blocks/{page_id}/children`).
3. **Idempotencia y Anti-Duplicados:**
   - El servicio busca las páginas existentes bajo `NOTION_PARENT_PAGE_ID` por título o capítulo; si la página ya existe, actualiza sus bloques sin crear páginas duplicadas.
   - Si no existe, crea la subpágina bajo la raíz del espacio de trabajo.

---

## 5. Regla 4: Protección de Contratos Sintácticos en `prompts/`

Los archivos en `prompts/` (`00_ceo.md` a `14_qa_ui_ux.md`) no son simples textos; actúan como **especificaciones de protocolo** consumidas por autómatas en `app/services/output_parser.py` y `app/services/code_materializer.py`.

### Reglas de Higiene de Prompts:
1. **Inmutabilidad del Bloque YAML Routing Header:**
   - Los prompts deben mantener inalterada la instrucción de emitir el encabezado YAML delimitado por `---`:
     ```yaml
     ---
     origen: agente_XX_nombre
     destino_siguiente: agente_YY_nombre
     estado_entregable: ESTADO_CANONICO_VALIDO
     veredicto: APROBADO | RECHAZADO | BLOQUEADO
     puntuacion: 0-100
     culpable_detectado: agente_ZZ | null
     ---
     ```
2. **Compatibilidad con `code_materializer.py`:**
   - En prompts de desarrolladores (`03_laravel_dev.md`, `04_fastapi_dev.md`, `07_devops.md`), las directrices para emitir bloques de código deben especificar claramente el formato de ruta de archivo (`### File: path/to/file` o ````lenguaje path/to/file````), permitiendo la extracción determinista en `build/`.

---

## 6. Checklist de Verificación Documental

Antes de dar por concluida una actualización documental:

- [ ] ¿Toda nueva variable de `config.py` está presente y comentada en `.env.example`?
- [ ] ¿Los diagramas Mermaid renderizan limpiamente sin errores de sintaxis?
- [ ] ¿Las rutas de archivo mencionadas en los manuales son 100% exactas y verificables?
- [ ] ¿Los prompts en `prompts/` preservan los contratos y etiquetas requeridas por los analizadores de salida?
- [ ] ¿La sincronización con Notion (`notion_docs_sync.py`) se ejecuta sin duplicar páginas y en lotes `<= 100` bloques?
