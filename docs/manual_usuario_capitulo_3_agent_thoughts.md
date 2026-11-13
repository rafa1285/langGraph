# 📖 Manual de Usuario — AgentOffice (Capítulo 3: Sala de Reflexión y Entregables — Agent Thoughts)

> **Manual de Uso y Guía Visual para Usuarios de Negocio**  
> **Versión de la Aplicación:** AgentOffice v2.5 Cyber-Loft Engine  
> **Destinatarios:** Founders, Directores de Producto, Gestores de Operaciones y Auditores de Negocio  
> **Acceso a la sección:** Clic en la pestaña **🧠 Agent Thoughts** en la barra superior de navegación.  
> **Enlace directo en Notion:** [Ver página en Notion](https://app.notion.com/p/416be4dde9738121a20ddaeef6beea74?pvs=204)

---

## 📑 Índice del Capítulo

1. [Propósito de la Sala de Deliberación y Entregables (Agent Thoughts)](#1-propósito-de-la-sala-de-deliberación-y-entregables-agent-thoughts)
2. [Barra Superior de Control y Sincronización de Proyectos](#2-barra-superior-de-control-y-sincronización-de-proyectos)
3. [Panel Lateral Izquierdo: Directorio Ergonómico de los 13 Especialistas](#3-panel-lateral-izquierdo-directorio-ergonómico-de-los-13-especialistas)
4. [Ficha Técnica de Metadatos (YAML) y Gestión del Espacio](#4-ficha-técnica-de-metadatos-yaml-y-gestión-del-espacio)
5. [Visor Inteligente por Apartados Plegables (Acordeón de Lectura Cómoda)](#5-visor-inteligente-por-apartados-plegables-acordeón-de-lectura-cómoda)
6. [Barra de Acciones Globales: Desplegar Todo, Plegar Todo y Copiar Entregable](#6-barra-de-acciones-globales-desplegar-todo-plegar-todo-y-copiar-entregable)
7. [Selector de Iteraciones y Pasos de Revisión Multi-etapa](#7-selector-de-iteraciones-y-pasos-de-revisión-multi-etapa)
8. [Casos Prácticos de Inspección Paso a Paso](#8-casos-prácticos-de-inspección-paso-a-paso)
9. [Preguntas Frecuentes y Consejos de Dirección](#9-preguntas-frecuentes-y-consejos-de-dirección)

---

## 1. Propósito de la Sala de Deliberación y Entregables (Agent Thoughts)

En el **Activity Log** (Capítulo 2), los mensajes se resumen en una o dos frases breves para que puedas ver el avance global del proyecto a gran velocidad sin saturar la pantalla.

Sin embargo, cuando necesitas tomar decisiones estratégicas —como validar los precios fijados por el CEO, revisar los contratos de microservicios propuestos por el Arquitecto o auditar las medidas de protección del CISO antes de salir al mercado—, necesitas leer el **documento íntegro** y comprender **por qué** el especialista tomó esas decisiones.

La pestaña **`🧠 Agent Thoughts`** es la "lupa de inspección ejecutiva" de la factoría. Te permite:

- **Inspeccionar el razonamiento profundo:** Leer la deliberación interna completa y sin recortes de cada agente.
- **Consultar los entregables oficiales definitivos:** Acceder a las especificaciones de producto, diagramas, esquemas de diseño y actas de autorización.
- **Navegar con comodidad sin scroll infinito:** Gracias al sistema de **apartados plegables**, los documentos de miles de líneas se organizan en bloques temáticos que puedes abrir y cerrar a tu ritmo.
- **Exportar con un solo clic:** Copiar cualquier informe completo con el botón `📋 Copy Output` para compartirlo con socios, inversores o en tus herramientas de gestión.

![Vista general de Agent Thoughts](file:///C:/Users/Rafa/.gemini/antigravity/brain/e628ac3c-94d3-4a27-b3c8-37103dcd2f8f/08_tab_thoughts_fullscreen.png)

---

## 2. Barra Superior de Control y Sincronización de Proyectos

En la parte superior de la sala encontrarás una barra de mando horizontal fija:

1. **Cabecera Descriptiva:**
   - **`Agent Deliberation & Internal Thoughts Stream`**: Te confirma que estás en la sala de auditoría cognitiva.
   - Subtítulo explicativo: *"Inspecciona a fondo el razonamiento, metadatos YAML y entregables completos generados por los 13 agentes."*
2. **Selector de Proyectos (`Proyecto: ...`):**
   - Menú desplegable que muestra todos los productos disponibles (por ejemplo, `validator-hq-saas (proj_88c9fd46)`).
   - Al seleccionar un proyecto distinto, la lista de agentes y todos los documentos se actualizan al instante para mostrar el trabajo correspondiente a ese producto.
3. **Botón `🔄 Actualizar`:**
   - Consulta el estado más reciente del proyecto en curso. Si un agente acaba de finalizar su tarea en segundo plano, al pulsar este botón verás su nuevo documento inmediatamente sin necesidad de recargar toda la página en el navegador.

---

## 3. Panel Lateral Izquierdo: Directorio Ergonómico de los 13 Especialistas

En la columna izquierda se ubica el catálogo interactivo del equipo. Ha sido diseñado específicamente para aprovechar el **100% de la altura visible de tu pantalla**, de modo que los 13 especialistas del organigrama están a la vista simultáneamente, sin molestos desplazamientos verticales en la mayoría de resoluciones.

### Los 13 Especialistas Oficiales de la Factoría:

| Icono y Nombre Visual | Identificador | Rol en el Proyecto | ¿Qué tipo de entregable produce? |
| :--- | :--- | :--- | :--- |
| 👔 **CEO** | `agente_00_ceo` | Dirección Ejecutiva | **Charter de Negocio** (fijación de precios y márgenes) y **Signoff** (acta final de lanzamiento autorizado). |
| 📋 **Product Manager** | `agente_01_pm` | Dirección de Producto | **Sprint Backlog** y matriz de historias de usuario priorizadas. |
| 📐 **Software Architect** | `agente_02_architect` | Arquitectura de Software | **Diseño Técnico del Sistema (SDD)** y contratos formales de APIs. |
| 🎨 **UI/UX Designer** | `agente_11_ui_ux` | Diseño y Experiencia | **Design System**, paleta tipográfica y flujos de pantallas. |
| 🐘 **Dev PHP (Laravel)** | `agente_03_laravel` | Desarrollo Backend Core | Código fuente del servidor, modelos de datos y endpoints de negocio. |
| ⚡ **Dev Python (FastAPI)** | `agente_04_fastapi` | Microservicios Asíncronos | Servicios de alta velocidad y procesamiento en segundo plano. |
| 🔬 **QA PHP (Pest)** | `agente_05_qa_php` | Calidad y Testing PHP | Informe de pruebas automatizadas y cobertura de código. |
| 🐍 **QA Python (Pytest)** | `agente_06_qa_python` | Calidad y Testing Python | Pruebas de integración, asincronía y verificación funcional. |
| ⚙️ **DevOps & Docker** | `agente_07_devops` | Infraestructura | Ficheros Docker Compose, variables de entorno y validación de despliegue. |
| 🛡️ **CISO Security** | `agente_10_ciso` | Ciberseguridad | Auditoría forense OWASP, blindaje de contraseñas y mitigación de vulnerabilidades. |
| 📚 **Docs & RAG** | `agente_08_docs` | Documentación | Manual de despliegue técnico y guías de uso para clientes. |
| 📣 **Marketing** | `agente_12_marketing` | Crecimiento y Adquisición | Estrategia de captación de tráfico (TOFU/MOFU), copys y propuesta de valor. |
| 💹 **Sales & Analytics** | `agente_13_sales_analytics` | Analítica y Monetización | Embudo de conversión, proyecciones de facturación y métricas SaaS. |

### Indicadores y Comportamiento de cada Agente:

- **Distintivo de Documentos (`X docs`):** Una píldora verde esmeralda (ej. `3 docs`, `1 doc`) indica cuántos informes ha producido ese especialista para el proyecto seleccionado.
- **Distintivo `Inactivo` (Gris tenue):** Señala que ese agente todavía no ha intervenido en el proyecto activo o no forma parte de su alcance.
- **Selección Activa:** Al hacer clic sobre cualquier agente, su botón se ilumina con un marco cian brillante y el panel derecho muestra de inmediato su trabajo.
- **Contador Global (`26 entregables`):** Situado en la cabecera del panel izquierdo, te indica la suma total de entregables oficiales archivados en este proyecto.

---

## 4. Ficha Técnica de Metadatos (YAML) y Gestión del Espacio

Al seleccionar un agente, la parte superior de la columna derecha despliega una **Ficha Técnica de Control** que resume las condiciones operativas bajo las que se emitió el documento:

| Campo de la Ficha | ¿Qué significa para ti? | Ejemplo |
| :--- | :--- | :--- |
| **`ID_PROYECTO`** | Código identificador del software en el que se trabaja. | `proj_88c9fd46` |
| **`VERSION_ITERACION`** | Versión de trabajo. Permite saber si es el primer borrador o una iteración tras una revisión de calidad. | `v1`, `v2` |
| **`AGENTE_EMISOR`** | Especialista autor del informe o entregable. | `agente_02_architect` |
| **`AGENTE_RECEPTOR`** | Miembro del equipo o destinatario al que se delega el siguiente paso de trabajo. | `agente_03_laravel, agente_04_fastapi` |
| **`ESTADO`** | Veredicto formal del entregable. | `APROBADO_PARA_DESARROLLO`, `CHARTER_NEGOCIO_LISTO` |
| **`PRIORIDAD`** | Nivel de urgencia asignado a este trabajo. | `ALTA`, `MEDIA`, `CRÍTICA` |
| **`TIMESTAMP`** | Fecha y hora exacta de registro del documento. | `2026-11-01 16:13:13 UTC` |

### 🎛️ Control de Espacio: Botón «Ocultar Ficha / Mostrar Ficha»

En la esquina derecha de la caja de metadatos encontrarás el botón **`Ocultar Ficha`** (o `Mostrar Ficha`):
- **Al pulsar `Ocultar Ficha`:** La caja de metadatos se repliega suavemente hacia arriba.
- **¿Para qué sirve?** Te permite maximizar el área visible del visor principal, otorgándote una pantalla prácticamente completa para leer textos largos sin elementos secundarios que te distraigan.
- Puedes volver a desplegar la ficha en cualquier momento pulsando de nuevo el botón.

---

## 5. Visor Inteligente por Apartados Plegables (Acordeón de Lectura Cómoda)

Los documentos generados por el equipo de inteligencia artificial son sumamente exhaustivos. Un plan de arquitectura o una auditoría de seguridad puede superar con creces las 20 páginas de texto. Leer un documento tan largo en un visor tradicional obliga a realizar desplazamientos interminables de ratón y dificulta encontrar apartados concretos.

Para solucionar esto, AgentOffice cuenta con un **sistema de apartados plegables tipo acordeón**:

![Visor estructurado por apartados plegables](file:///C:/Users/Rafa/.gemini/antigravity/brain/e628ac3c-94d3-4a27-b3c8-37103dcd2f8f/09_tab_thoughts_collapsible_sections.png)

### ¿Cómo funciona la lectura por apartados?

1. **Segmentación Temática Automática:**
   - La aplicación detecta los grandes capítulos y apartados de cada informe (por ejemplo: *1. Resumen Ejecutivo*, *2. Requisitos Funcionales*, *3. Contratos de API*, *4. Protocolos de Seguridad*) y crea una tarjeta independiente para cada uno.
2. **Cabecera Clicable con Chevron (`▼` / `▶`):**
   - **`▼` (Desplegado):** El apartado está abierto y puedes leer su contenido.
   - **`▶` (Plegado):** El apartado está cerrado para no ocupar espacio visual.
   - Para abrir o cerrar un apartado concreto, simplemente haz clic sobre su barra de título.
3. **Etiqueta de Volumen de Contenido:**
   - Cada apartado muestra una pequeña insignia con el número de caracteres que contiene (por ejemplo, `1.450 chars`). Así sabes de antemano la extensión de esa sección antes de abrirla.
4. **Protección de Bloques de Código y Tablas:**
   - Si el entregable contiene fragmentos de código, archivos de configuración o tablas de datos, se muestran en cajas oscuras protegidas con tipografía monoespaciada para garantizar una lectura limpia y profesional.

---

## 6. Barra de Acciones Globales: Desplegar Todo, Plegar Todo y Copiar Entregable

Justo en la cabecera del visor de documentos dispones de tres botones de control rápido:

- **Botón `⬇️ Desplegar Todo`:** Abre simultáneamente todas las secciones del documento con un solo clic. Ideal si quieres realizar una búsqueda rápida en tu navegador (con `Ctrl + F`) por todo el texto completo.
- **Botón `⬆️ Plegar Todo`:** Pliega todas las secciones al instante. Deja a la vista únicamente la lista ordenada de títulos de los apartados, transformando el documento en un índice rápido para que localices el capítulo exacto que te interesa.
- **Botón `📋 Copy Output`:** Copia al portapapeles de tu ordenador el documento Markdown íntegro, incluyendo encabezados, tablas y formatos. Al hacer clic, el botón cambiará temporalmente a **`✓ ¡Copiado!`** en verde para confirmarte que el texto ya está en tu portapapeles listo para pegarlo en Notion, Word, Google Docs, Slack o un correo electrónico.

> 💡 **Consejo Ejecutivo:** Para una lectura ágil, pulsa primero **⬆️ Plegar Todo** para contemplar la estructura global del entregable, y luego haz clic únicamente en los 2 o 3 apartados que quieras auditar.

---

## 7. Selector de Iteraciones y Pasos de Revisión Multi-etapa

En proyectos exigentes, es habitual que algunos agentes intervengan más de una vez. Por ejemplo:
- Si el especialista de calidad (**QA**) detecta un fallo, el desarrollador interviene una segunda vez para corregirlo.
- El **CISO** puede revisar el código en una primera pasada y emitir un segundo informe de blindaje definitivo tras aplicar los parches.
- El **CEO** interviene al inicio (**Paso #1 / Apertura Charter**) y al final del ciclo (**Paso #7 / Cierre Signoff de Lanzamiento**).

Cuando seleccionas un especialista que ha intervenido en múltiples ocasiones, el visor incorpora en su cabecera un **Selector de Iteraciones** (por ejemplo: `Paso #2 • Veredicto: APROBADO (7983 tokens)` y `Paso #11 • Veredicto: CORRECCION (5420 tokens)`).

Al hacer clic en un paso u otro, podrás comprobar la evolución del trabajo del especialista: qué propuso en la primera versión y qué mejoras implementó en las siguientes vueltas.

---

## 8. Casos Prácticos de Inspección Paso a Paso

### Caso A: Validar la Propuesta de Negocio y Precios del CEO
1. Haz clic en la pestaña **`🧠 Agent Thoughts`**.
2. En la columna izquierda, pulsa sobre **`👔 CEO`** (`agente_00_ceo`).
3. Comprueba que el selector de paso indique el primer hito (**Charter de Negocio**).
4. En el visor, haz clic sobre el apartado **`1. Resumen Ejecutivo y Propuesta de Valor`** y sobre **`4. Unit Economics y Modelo de Monetización`**.
5. Valida que el precio de suscripción y el margen bruto propuesto (≥ 80%) se ajusten a tus objetivos de rentabilidad.

### Caso B: Compartir los Contratos de API con Colaboradores Externos
1. En el panel izquierdo, selecciona **`📐 Software Architect`** (`agente_02_architect`).
2. Pulsa el botón **`📋 Copy Output`**.
3. El botón mostrará **`✓ ¡Copiado!`**.
4. Abre tu procesador de textos o herramienta de notas preferida y pulsa `Ctrl + V`. Tendrás la especificación técnica completa con sus rutas y modelos de datos exactamente formateados.

### Caso C: Auditar el Blindaje de Seguridad antes de Salir a Producción
1. En el panel izquierdo, haz clic sobre **`🛡️ CISO Security`** (`agente_10_ciso`).
2. En la Ficha Técnica YAML, verifica que el campo **`ESTADO`** indique **`BLINDADO`** o **`APROBADO`**.
3. Abre el apartado de **`Matriz de Riesgos OWASP`** para comprobar que no existen credenciales expuestas ni brechas de inyección.

---

## 9. Preguntas Frecuentes y Consejos de Dirección

- **¿Por qué algunos agentes muestran la etiqueta «Inactivo» en gris?**  
  Significa que para el proyecto que tienes seleccionado en el menú superior, ese especialista todavía no ha intervenido o el ciclo de trabajo no requirió su participación. En cuanto el flujo de trabajo avance hasta su etapa, el agente cambiará automáticamente a verde mostrando su contador de documentos.

- **¿Puedo modificar o editar los textos directamente desde este visor?**  
  No. La pestaña **`🧠 Agent Thoughts`** es una sala de auditoría y lectura de razonamientos diseñada para garantizar la integridad histórica de lo que pensó y decidió el equipo de IA. Si necesitas modificar un archivo real del proyecto (código, Dockerfile o documentación), dirígete a la pestaña **`🎮 2D Office`** o al panel lateral de archivos y utiliza la herramienta **`✏️ EDITAR ARCHIVO`**.

- **¿Qué diferencia hay entre este visor y el «Activity Log» de la pestaña anterior?**  
  El **Activity Log** (pestaña *💬 Interaction & Pipeline*) es un registro de eventos cronológicos cortos pensado para seguir la velocidad del motor de trabajo. En cambio, **Agent Thoughts** es la biblioteca documental completa: aquí puedes leer los informes enteros de 10 páginas, analizar tablas extensas y copiar los entregables finales.

- **¿Cómo sé cuántos tokens consumió la redacción de un entregable concreto?**  
  En la cabecera de cada entregable, junto al número de paso y el veredicto, el visor te indica el volumen exacto de tokens procesados (por ejemplo, `[7983 tokens]`). Esto te permite saber qué especialistas requieren más esfuerzo cognitivo y evaluar la eficiencia del equipo.
