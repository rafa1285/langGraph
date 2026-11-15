---
description: Sincroniza la documentación en langGraph/docs/, .env.example, diagramas Mermaid, catálogos de prompts y publica en vivo en Notion el manual corporativo de Agent Office.
---

# Workflow: Sincronización Documental Diátaxis & Notion (`/docs-sync`)

Este workflow operativo rige la actualización, alineación y curaduría continua de toda la documentación técnica, variables de entorno de ejemplo, diagramas de arquitectura, catálogo de prompts y la publicación en vivo en el espacio de trabajo corporativo de **Notion**.

---

## 1. Activación de Skills Requeridas

- **`docs-diataxis-curator`** (Framework Diátaxis, sincronización `config.py` <-> `.env.example`, diagramas Mermaid, sincronización Notion e higiene de prompts).
- **`fastapi-sqlite-core`** (Verificación de esquemas, persistencia y modelos tipados).
- **`cybersecurity-appsec-guardian`** (Higiene de credenciales y protección contra fuga de tokens).
- **`pytest-zero-network-qa`** (Testing 100% offline y verificación de no-regresión).

---

## 2. Flujo de Sincronización Documental Dual

### Paso 1: Sincronización de Variables de Configuración (`.env.example`)
1. **Auditoría de `app/core/config.py`:**
   - Comparar todos los atributos declarados en `Settings` con el contenido de `langGraph/.env.example`.
   - Si se añade, renombra o altera una variable de entorno, reflejarla de inmediato en `.env.example`.
2. **Higiene de Secretos:**
   - Verificar que ningún valor en `.env.example` contenga contraseñas o tokens reales; usar valores de ejemplo seguros (`dummy-key-for-tests`, valores vacíos o URLs locales).
   - Añadir comentarios descriptivos para cada bloque funcional (LLMs, Bases de datos, n8n, Notion, WhatsApp, LangSmith).

### Paso 2: Curaduría de Manuales Ejecutivos por Capítulos (`docs/`)
1. **Alineación con el Framework Diátaxis:**
   - Asegurar que los documentos en `docs/` se adapten al cuadrante adecuado: Tutoriales, Guías Prácticas (How-To), Referencia Técnica o Explicaciones Conceptuales.
2. **Estructura Canónica de Capítulos:**
   - Seguir el formato probado en `manual_usuario_capitulo_5_security_circuit_breakers.md`:
     - Metadatos de cabecera (destinatarios, versión, pestaña de la UI, enlace Notion).
     - Justificación de negocio / compliance normativo.
     - Diagramas Mermaid visuales (`flowchart TD` / `flowchart LR`).
     - Desglose de controles de pantalla con sus semáforos cromáticos.
     - Casos prácticos reales basados en proyectos de la factoría.
     - Sección de preguntas frecuentes y tabla de contingencia / troubleshooting.

### Paso 3: Protección Contractual de Prompts del Sistema (`prompts/`)
1. **Revisión de `prompts/00_ceo.md` a `prompts/14_qa_ui_ux.md`:**
   - Confirmar que ningún prompt haya perdido su delimitador `---` de encabezado YAML.
   - Verificar que los campos obligatorios del protocolo de enrutamiento sigan presentes:
     `origen`, `destino_siguiente`, `estado_entregable`, `veredicto`, `puntuacion`, `culpable_detectado`.
   - Asegurar que los formatos de ruta de código requeridos por `code_materializer.py` permanezcan documentados con precisión.

### Paso 4: Publicación en Vivo en Notion (`notion_docs_sync.py`)
1. **Ejecución del Sincronizador Nativo:**
   - Invocar `NotionDocsSyncService` (`app/services/notion_docs_sync.py`) pasando el directorio `langGraph/docs` y el índice maestro `AGENTS.md`.
   - El servicio convierte el Markdown a bloques nativos de Notion, preserva diagramas Mermaid como bloques `code` con `"language": "mermaid"` y pagina en lotes de `<= 100` bloques.
2. **Idempotencia:**
   - Las páginas existentes bajo `NOTION_PARENT_PAGE_ID` se actualizan in-place sin duplicar la estructura del espacio de trabajo.
   - Mostrar el informe con los títulos, IDs y URLs generadas en Notion.

---

## 3. Checklist de Cierre Documental

Antes de dar por concluida una actualización documental:
- [ ] `.env.example` incluye todas las variables de `app/core/config.py` sin claves reales.
- [ ] Los diagramas Mermaid son sintácticamente válidos y legibles.
- [ ] Las rutas de archivo referenciadas existen y son exactas.
- [ ] Los prompts en `prompts/` preservan los contratos y etiquetas requeridas por los analizadores de salida.
- [ ] La sincronización en vivo con Notion se ha completado exitosamente con páginas actualizadas/creadas.
- [ ] La suite de pruebas `tests/test_notion_docs_sync.py` se ejecuta 100% offline y en verde.
