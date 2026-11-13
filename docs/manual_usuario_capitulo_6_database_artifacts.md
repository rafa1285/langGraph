# 📖 Manual de Usuario — AgentOffice (Capítulo 6: Base de Datos y Explorador de Artefactos — Database & Artifacts)

> **Manual de Uso y Guía Visual para Usuarios de Negocio**  
> **Versión de la Aplicación:** AgentOffice v2.5 Cyber-Loft Engine  
> **Destinatarios:** Founders, Directores de Producto, Gestores de Operaciones, Auditores de Datos y Responsables de Negocio  
> **Acceso a la sección:** Clic en la pestaña **🗄️ Database & Artifacts** en la barra superior de navegación.  
> **Enlace directo en Notion:** [Ver página en Notion](https://app.notion.com/p/416be4dde973815991cac1f06e72839f?pvs=204)  
> **Captura de pantalla oficial:** Verificable en la interfaz interactiva o en el archivo adjunto `13_tab_database_inspector.png`.

---

## 📑 Índice del Capítulo

1. [Propósito del Inspector de Datos y Explorador de Artefactos](#1-propósito-del-inspector-de-datos-y-explorador-de-artefactos)
2. [Arquitectura Visual del Panel Dividido (Split Layout de Doble Inspección)](#2-arquitectura-visual-del-panel-dividido-split-layout-de-doble-inspección)
3. [Panel Izquierdo: Inspector de Base de Datos SQLite (office_data.sqlite)](#3-panel-izquierdo-inspector-de-base-de-datos-sqlite-office_datasqlite)
4. [Búsqueda Universal Instantánea y Paginación Inteligente](#4-búsqueda-universal-instantánea-y-paginación-inteligente)
5. [Panel Derecho: Explorador de Artefactos del Proyecto (Workspace Artifacts)](#5-panel-derecho-explorador-de-artefactos-del-proyecto-workspace-artifacts)
6. [Visor de Entregables, Clasificación por Iconos y Botón 📋 Copiar](#6-visor-de-entregables-clasificación-por-iconos-y-botón--copiar)
7. [Caso Práctico Real: Cómo Auditar y Exportar los Activos de validator-hq-saas](#7-caso-práctico-real-cómo-auditar-y-exportar-los-activos-de-validator-hq-saas)
8. [Preguntas Frecuentes y Guía de Decisiones para Negocio (FAQ)](#8-preguntas-frecuentes-y-guía-de-decisiones-para-negocio-faq)

---

## 1. Propósito del Inspector de Datos y Explorador de Artefactos

Cuando una factoría digital de software trabaja para tu empresa, no basta con observar cómo los agentes deliberan o vigilar sus costes en tokens. En algún momento, todo directivo, inversor o responsable de operaciones necesita responder a dos preguntas fundamentales de negocio:

1. **¿Dónde queda constancia notarial de todo lo sucedido?** ¿Dónde está la base de datos inmutable que almacena cada correo enviado, cada prompt formulado y cada decisión acordada entre los 13 especialistas?
2. **¿Dónde están los entregables reales que he contratado?** ¿Dónde se guardan los archivos físicos, el código fuente, las especificaciones de producto, los planes de marketing y los contratos de arquitectura generados?

Para dar una respuesta inmediata, transparente y sin intermediarios a estas cuestiones se diseñó la pestaña **`🗄️ Database & Artifacts`**.

Esta pantalla actúa como la **Notaría Digital y la Biblioteca de Activos** de tu factoría. En ella se unifican dos capacidades de alto valor:

- **Transparencia y Trazabilidad Absoluta:** Puedes inspeccionar directamente el motor de base de datos corporativo (`office_data.sqlite`) con más de 1.250 registros de deliberación y 1.370 correos electrónicos, sin necesidad de saber comandos de programación ni SQL.
- **Acceso Inmediato a la Propiedad Intelectual:** Puedes explorar el disco de tu proyecto (con cientos de archivos organizados), previsualizar cualquier documento con un clic y copiar su contenido para llevártelo a tus informes ejecutivos, presentaciones a inversores o herramientas corporativas.

![Vista del Inspector de Base de Datos y Explorador de Artefactos](file:///C:/Users/Rafa/.gemini/antigravity/brain/e628ac3c-94d3-4a27-b3c8-37103dcd2f8f/13_tab_database_inspector.png)

---

## 2. Arquitectura Visual del Panel Dividido (Split Layout)

Para maximizar tu productividad y evitar tener que saltar entre diferentes ventanas o aplicaciones, la interfaz se estructura en dos grandes módulos complementarios dispuestos en paralelo (**6 columnas frente a 6 columnas**):

```text
┌────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 🗄️ Database Inspector & Workspace Artifacts                                                                            │
│    Inspección directa de tablas SQLite y explorador de archivos generados en los proyectos.                            │
├──────────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┤
│ 📂 TABLAS SQLITE (office_data.sqlite)                    │ 📁 WORKSPACE ARTIFACTS                                      │
│ Tabla: [ agent_conversations (1253 filas) ▼ ]            │ Proyecto: [ validator-hq-saas (proj_88c9fd46) ▼ ]           │
│ Buscar: [ Ingrese texto a buscar... ]                    │ [ 233 archivos de proyecto ]                                │
├──────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ [ id ] [ project_id ] [ step_index ] [ speaker ] [ ver.. │ 📄 01_agente_01_pm.md                    [ 6.4 KB ] (Activo)│
│                                                          │ 📄 02_agente_02_architect.md             [ 10.2 KB ]        │
│ [Tabla de Datos Paginada - 25 filas por vista]           │ 📄 03_agente_03_laravel.md               [ 56.1 KB ]        │
│                                                          │ 📄 03_agente_04_fastapi.md               [ 52.3 KB ]        │
│                                                          │ 📄 04_agente_11_ui_ux.md                 [ 18.9 KB ]        │
├──────────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
│ Controles: [ ◀ Ant ] Pág. 1 / 51 [ Sig ▶ ]               │ [ Visor de Contenido del Archivo Seleccionado ]             │
│ Registros: 1 - 25 de 1253                                │ [ 📋 Copiar ]                                               │
└──────────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────┘
```

Esta distribución te permite correlacionar al instante un registro de la base de datos (por ejemplo, el paso donde el Arquitecto aprobó la especificación) con el archivo físico correspondiente generado en el disco de trabajo.

---

## 3. Panel Izquierdo: Inspector de Base de Datos SQLite (office_data.sqlite)

El panel izquierdo te da acceso directo y seguro (en modo **estricto de solo lectura**) al corazón de datos de AgentOffice.

### Tablas Principales Disponibles:
1. **`agent_conversations` (1.253 filas):**  
   El diario de sesiones de la factoría. Cada fila representa una interacción de razonamiento, indicando qué agente habló (`speaker`), en qué paso (`step_index`), cuál fue su veredicto (`verdict`) y cuántos tokens consumió.
2. **`agent_emails` (1.379 filas):**  
   El buzón de correo corporativo entre agentes. Registra los memorandos formales intercambiados (emisor, receptor, asunto, contenido y timestamp exacto).
3. **`projects`:**  
   El inventario oficial de iniciativas empresariales creadas en la factoría, con su identificador único (`project_id`), nombre y fecha de alta.
4. **`system_events`:**  
   El registro de eventos del sistema, inicios de ciclo, cambios de estado y verificaciones de salud.

### Contador Dinámico de Filas:
Al abrir el desplegable de tablas, notarás que cada opción muestra su volumen real de registros entre paréntesis (por ejemplo: `agent_conversations (1253 filas)`). Esto te permite saber inmediatamente qué tablas concentran la actividad de tu empresa.

---

## 4. Búsqueda Universal Instantánea y Paginación Inteligente

Para que puedas auditar cientos o miles de filas en milisegundos sin congelar tu navegador:

- **Buscador en Tiempo Real (`#db-search-input`):**  
  Escribe cualquier término (como el nombre de un agente, un identificador de proyecto, una palabra clave o el código de un paso) y la tabla filtrará al vuelo los resultados, recalculando el total de coincidencias.
- **Paginación Inteligente de 25 en 25 Filas:**  
  La interfaz muestra los datos en bloques manejables de 25 registros por página.
  - Botón **`◀ Ant`**: Retrocede a la página previa (se desactiva automáticamente si estás en la página 1).
  - Indicador Central: Muestra la posición actual (por ejemplo: `Pág. 1 / 51`).
  - Botón **`Sig ▶`**: Avanza a la siguiente página (se desactiva en la última página).
  - Resumen Numérico: Indica con precisión el rango de filas visibles (ejemplo: `Registros: 1 - 25 de 1253`).

---

## 5. Panel Derecho: Explorador de Artefactos del Proyecto (Workspace Artifacts)

El panel derecho te conecta con el disco de almacenamiento donde se guardan físicamente los resultados de trabajo de los agentes.

### Características Clave:
- **Detección Automática de Proyecto Activo:**  
  Al abrir la pestaña, el selector selecciona automáticamente el proyecto en curso (por ejemplo, `validator-hq-saas`), cargando su árbol de entregables de inmediato.
- **Contador Global de Activos:**  
  Un distintivo superior te indica cuántos archivos componen el proyecto (por ejemplo: `233 archivos de proyecto`).
- **Clasificación Visual por Tipo de Archivo:**  
  Cada documento cuenta con un icono intuitivo para que identifiques su naturaleza de un vistazo:
  - 📄 **Markdown (`.md`):** Especificaciones funcionales, análisis de negocio, planes de prueba y manuales.
  - ⚙️ **Configuraciones (`.json`, `.yml`, `.yaml`):** Parámetros del sistema y esquemas de datos.
  - 🐍 **Código Python (`.py`):** Servicios backend y suites de pruebas Pytest.
  - 🐘 **Código PHP (`.php`):** Controladores de negocio y suites de pruebas Pest.
  - 🐳 **Infraestructura (`Dockerfile`, `.env`):** Recetas de despliegue y variables de entorno.
- **Tamaño de Archivo Formateado:**  
  Junto a cada archivo verás su peso en disco (ej. `6.4 KB`, `56.1 KB`), permitiéndote detectar qué documentos contienen especificaciones exhaustivas.
- **Resaltado Interactivo:**  
  El archivo que estés inspeccionando se resalta en azul cian con borde iluminado, para que nunca pierdas el contexto de qué entregable estás leyendo.

---

## 6. Visor de Entregables, Clasificación por Iconos y Botón 📋 Copiar

Al pulsar sobre cualquier archivo de la lista, el visor inferior muestra instantáneamente su contenido íntegro sin que tengas que abrir un editor de código externo.

### Botón de Copia Rápida (`📋 Copiar`):
En la esquina superior derecha del visor encontrarás el botón **`📋 Copiar`**. 
- Al hacer clic, el contenido completo del documento se copia al portapapeles de tu equipo.
- El botón cambia de color a verde esmeralda y muestra el mensaje **`✅ Copiado`** durante 2 segundos para darte confirmación visual inequívoca.
- Es la vía más rápida para transferir especificaciones a Notion, Jira, Slack o correos electrónicos para el equipo directivo.

---

## 7. Caso Práctico Real: Cómo Auditar y Exportar los Activos de `validator-hq-saas`

Imaginemos que el Director de Producto o un Inversor solicita una copia inmediata del **Plan Funcional del Product Manager** del proyecto `validator-hq-saas`:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        FLUJO DE AUDITORÍA Y EXPORTACIÓN RÁPIDA                         │
│                                                                                        │
│  [Paso 1: Entrar a Database & Artifacts]                                               │
│                           │                                                            │
│                           ▼                                                            │
│  [Paso 2: Comprobar Base de Datos]   ──► 1.253 conversaciones y 1.379 emails auditados │
│                                          (Confirmación de trazabilidad legal)          │
│                           │                                                            │
│                           ▼                                                            │
│  [Paso 3: Explorar Entregables]      ──► 233 archivos de proyecto listados             │
│                                          (Localización de 01_agente_01_pm.md)          │
│                           │                                                            │
│                           ▼                                                            │
│  [Paso 4: Copiar Plan de Producto]   ──► Clic en 📋 Copiar (Feedback ✅ Copiado)       │
│                                          (Listo para presentar al Comité de Dirección) │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Paso a Paso Ejecutado:
1. **Verificación de Trazabilidad:** El responsable entra en `🗄️ Database & Artifacts`. En el panel izquierdo selecciona la tabla `agent_conversations` y confirma que existen 1.253 registros que avalan todas las deliberaciones del ciclo.
2. **Inspección del Workspace:** En el panel derecho comprueba que el selector de proyecto está en `validator-hq-saas (proj_88c9fd46)` y que hay 233 archivos creados en el espacio de trabajo.
3. **Revisión del Documento Funcional:** Examina el documento `01_agente_01_pm.md` en el visor derecho y lee el encabezado YAML donde figura la puntuación perfecta de 100 puntos y el veredicto `APROBADO`.
4. **Exportación con un Clic:** Pulsa `📋 Copiar`, abre su herramienta de gestión corporativa y pega la especificación funcional completa sin necesidad de solicitar la ayuda de ningún programador.

---

## 8. Preguntas Frecuentes y Guía de Decisiones para Negocio (FAQ)

### ¿Corro el riesgo de borrar o alterar la base de datos o los archivos desde esta pantalla?
**No, en absoluto.** La pestaña `Database & Artifacts` opera en modo **estrictamente de solo lectura (*read-only inspection*)**. Los botones de búsqueda, paginación y copia de contenidos no ejecutan ninguna instrucción de modificación ni borrado (`DELETE`, `UPDATE` o `DROP`). Su propósito es 100% de supervisión, auditoría y consulta segura.

### ¿Por qué algunos archivos son mucho más pesados que otros?
Los archivos `.md` de especificación y arquitectura (como `03_agente_03_laravel.md` de 56 KB o `03_agente_04_fastapi.md` de 52 KB) contienen contratos completos de API, estructuras de base de datos y ejemplos de código detallados generados por los agentes técnicos. Es una señal de que el trabajo no es un simple resumen conceptual, sino una especificación técnica de grado producción.

### ¿Puedo utilizar los registros de `agent_emails` para justificar decisiones de diseño ante clientes o inversores?
**Sí.** La tabla `agent_emails` es el equivalente digital a la cadena de correos corporativos de un equipo senior. Si un cliente pregunta por qué se eligió una arquitectura asíncrona o por qué se reforzó el cortafuegos, puedes buscar la conversación exacta donde el Arquitecto y el CISO justificaron la decisión con argumentos técnicos y de seguridad.

### ¿Qué ocurre si selecciono un archivo de código (`.py` o `.php`) en el explorador?
El visor derecho te mostrará el código fuente íntegro con su sangrado y estructura original. Aunque no seas programador, podrás comprobar si las funciones implementadas coinciden con lo acordado en los documentos de producto y copiarlo cuando lo requieras.
