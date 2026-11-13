# 📖 Manual de Usuario — AgentOffice (Capítulo 4: Rendimiento y Métricas de los Agentes — Agent Usage & Stats)

> **Manual de Uso y Guía Visual para Usuarios de Negocio**  
> **Versión de la Aplicación:** AgentOffice v2.5 Cyber-Loft Engine  
> **Destinatarios:** Founders, Directores de Producto, Gestores de Operaciones y Responsables Financieros  
> **Acceso a la sección:** Clic en la pestaña **📊 Agent Usage & Stats** en la barra superior de navegación.  
> **Enlace directo en Notion:** [Ver página en Notion](https://app.notion.com/p/416be4dde97381bc9249fffa763f0441?pvs=204)

---

## 📑 Índice del Capítulo

1. [Propósito del Cuadro de Mando de Rendimiento (Agent Usage & Stats)](#1-propósito-del-cuadro-de-mando-de-rendimiento-agent-usage--stats)
2. [Cabecera de KPIs de Rendimiento del Grafo (Los 4 Indicadores Maestros)](#2-cabecera-de-kpis-de-rendimiento-del-grafo-los-4-indicadores-maestros)
3. [Matriz Operativa de Agentes (Grid de los 13 Especialistas Oficiales)](#3-matriz-operativa-de-agentes-grid-de-los-13-especialistas-oficiales)
4. [Anatomía de una Tarjeta de Rendimiento (Cómo Interpretar cada Métrica)](#4-anatomía-de-una-tarjeta-de-rendimiento-cómo-interpretar-cada-métrica)
5. [Los 4 Estados Operativos en Vivo (Badges)](#5-los-4-estados-operativos-en-vivo-badges)
6. [Análisis de Distribución del Esfuerzo (Peso en el Proyecto)](#6-análisis-de-distribución-del-esfuerzo-peso-en-el-proyecto)
7. [Casos Prácticos de Gestión y Toma de Decisiones](#7-casos-prácticos-de-gestión-y-toma-de-decisiones)
8. [Preguntas Frecuentes y Consejos de Optimización Operativa](#8-preguntas-frecuentes-y-consejos-de-optimización-operativa)

---

## 1. Propósito del Cuadro de Mando de Rendimiento (Agent Usage & Stats)

Mientras que las pestañas previas te permiten interactuar con el equipo (*💬 Interaction & Pipeline*) o leer sus informes completos (*🧠 Agent Thoughts*), la pestaña **`📊 Agent Usage & Stats`** actúa como el **tacómetro de rendimiento industrial y cuadro de eficiencia operativa** de la factoría.

Está diseñada específicamente para responder a las preguntas clave que todo directivo, inversor o responsable de producto se hace al gestionar una factoría de software autónoma:

- **¿Cuánto trabajo real ha completado el equipo?** Cuantifica el número exacto de tareas ejecutadas en LangGraph frente a un desarrollo tradicional por horas.
- **¿Qué tan rápido responde cada especialista?** Mide la latencia media por tarea para certificar que el software se construye a velocidad digital.
- **¿Cuál es la calidad del código a la primera?** Mide el porcentaje de aprobaciones en las compuertas de testing automático (QA PHP y QA Python).
- **¿Dónde se concentra el esfuerzo computacional?** Te muestra qué agentes soportan el mayor peso del producto para optimizar presupuestos y evitar cuellos de botella.

![Vista panorámica de Agent Usage & Stats](file:///C:/Users/Rafa/.gemini/antigravity/brain/e628ac3c-94d3-4a27-b3c8-37103dcd2f8f/10_tab_agent_usage_stats.png)

---

## 2. Cabecera de KPIs de Rendimiento del Grafo (Los 4 Indicadores Maestros)

En la parte superior de la pantalla se despliega una hilera con 4 tarjetas de mando (*Master KPI Cards*). Te ofrecen un diagnóstico instantáneo de la salud operativa de tu proyecto:

| Tarjeta KPI | Icono | Métrica Ejemplo | ¿Qué representa para tu negocio? | ¿Qué decisión te ayuda a tomar? |
| :--- | :---: | :---: | :--- | :--- |
| **TOTAL NODOS EJECUTADOS** | ⚡ | **26** | Número de nodos de LangGraph completados con éxito en la cadena de producción. | Evalúa el volumen total de tareas generadas. En un equipo humano tradicional, 26 hitos complejos equivaldrían a varias semanas de sprint. |
| **ITERACIÓN ACTUAL** | 🔄 | **v1** | Ciclo de iteración activo (`version_iteracion`). | Confirma si el proyecto se ha producido a la primera (`v1`) o si ha requerido rondas adicionales de refinamiento (`v2`, `v3`). |
| **TIEMPO MEDIO / NODO** | ⏱️ | **20.77s** | Duración media de procesamiento por especialista. | Verifica la agilidad del sistema. Te asegura que ningún especialista esté atascado en bucles infinitos y que las entregas fluyan en segundos. |
| **TASA ÉXITO QA** | 🛡️ | **60.0%** | Porcentaje combinado de pruebas de testing aprobadas sin fallos en su primera ejecución (PHP + Python). | Evalúa la exigencia del control de calidad. Un 60% inicial demuestra que los auditores son rigurosos y detectan fallos reales antes de lanzar a producción. |

> 💡 **Interpretación de Dirección sobre la Tasa de Éxito QA:** En auditoría de software, una tasa de éxito de QA del 100% a la primera suele ser sospechosa de pruebas superficiales. Una tasa del 60% indica que los auditores automáticos detectaron errores en el 40% de los primeros intentos, obligando a los programadores a corregir el código antes de emitir la aprobación definitiva.

---

## 3. Matriz Operativa de Agentes (Grid de los 13 Especialistas)

Debajo de los KPIs superiores se ubica la **Matriz Operativa de Agentes**, organizada en una cuadrícula moderna de 13 tarjetas individuales (una por cada especialista oficial del organigrama).

### Controles de la Cabecera de la Matriz:
- **Selector de Proyecto (`Proyecto: ...`):** Menú desplegable que te permite conmutar entre tus proyectos creados (ej. `validator-hq-saas (proj_88c9fd46)`). Las métricas se actualizan instantáneamente para reflejar el historial exacto del producto seleccionado.
- **Botón `🔄 Actualizar`:** Consulta la telemetría en tiempo real y refresca los contadores de tareas, tokens y barras de peso sin recargar tu navegador.

---

## 4. Anatomía de una Tarjeta de Rendimiento (Cómo Interpretar cada Métrica)

Cada tarjeta representa a un especialista y reúne 6 elementos informativos estratégicos:

```text
┌────────────────────────────────────────────────────────┐
│  🐘 Dev PHP (Laravel)                    [ APPROVED ]  │
│     agente_03_laravel                                  │
├────────────────────────────────────────────────────────┤
│  Invocaciones: 2                Tokens: 24.808         │
│  Duración Med: 0.50s            Aprobación: 100%       │
├────────────────────────────────────────────────────────┤
│  Peso en Proyecto:                                9.7% │
│  ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
└────────────────────────────────────────────────────────┘
```

1. **Icono y Nombre del Especialista:** Identificador visual de su área (ej. 👔 CEO, 📐 Arquitecto, ⚡ FastAPI, 🛡️ CISO).
2. **Código de Sistema:** Nombre técnico del nodo en la factoría (ej. `agente_03_laravel`).
3. **Insignia de Estado en Vivo (Badge):** Indica la situación operativa del agente en este instante.
4. **Invocaciones (Tasks Count):** Número de veces que el agente ha sido llamado a trabajar en este proyecto.
5. **Tokens Generados:** Volumen de trabajo cognitivo procesado por este especialista. A mayor número de tokens, mayor densidad técnica tiene su entregable.
6. **Duración Media:** Tiempo que tarda el agente en reflexionar y redactar su entrega.
7. **Tasa de Aprobación (%):** Porcentaje de entregables validados positivamente sin que la dirección o el CISO le exigieran un re-trabajo.
8. **Barra de Peso en el Proyecto (Token Share %):** Muestra gráficamente qué porcentaje del volumen total de trabajo del proyecto corresponde a este agente.

---

## 5. Los 4 Estados Operativos en Vivo (Badges)

Las tarjetas asignan a cada agente uno de los 4 estados oficiales del ciclo de producción:

| Estado (Badge) | Color Visual | ¿Qué significa para el usuario? | Acción recomendada |
| :--- | :--- | :--- | :--- |
| **`APPROVED`** | **Verde Esmeralda Sólido** | El especialista ha terminado sus entregables y han sido aprobados formalmente por las compuertas de calidad o por el CEO. | Ninguna acción requerida. Fase completada con éxito. |
| **`WORKING`** | **Cyan Brillante Pulsante** | El agente está trabajando activamente en este momento (redactando código, ejecutando tests o deliberando). | Esperar unos segundos a que termine su ciclo. Puedes supervisarlo en el *Activity Log*. |
| **`BLOCKED`** | **Rojo Carmesí** | El agente ha recibido un reporte de fallo de calidad o una alerta de seguridad que le impide avanzar sin corregir el problema. | Inspeccionar el informe del CISO o de QA en *🧠 Agent Thoughts* para ver la causa de la retención. |
| **`IDLE`** | **Gris Tenue** | El especialista está en reposo esperando que la cadena de producción llegue a su departamento. | Estado normal para agentes cuyas etapas previas aún no han concluido. |

---

## 6. Análisis de Distribución del Esfuerzo (Peso en el Proyecto)

Una de las mayores utilidades de esta pantalla para un Director de Proyecto o Founder es comprobar cómo se reparte el esfuerzo entre las 4 grandes áreas de la empresa:

```text
📊 Distribución Típica del Esfuerzo en un SaaS Validado:
────────────────────────────────────────────────────────
• Ingeniería y Construcción (FastAPI + Laravel + DevOps) : 37.9%  ███████████████████
• Garantía de Calidad y Ciberseguridad (QA + CISO)       : 16.5%  ████████
• Dirección, Estrategia y Negocio (CEO + PM + Sales)     : 23.2%  ███████████
• Diseño, Documentación y Marketing (UI/UX + Docs + Mkt) : 16.7%  ████████
```

- **Ingeniería y Construcción (Devs & DevOps):** Suelen acumular entre el 35% y el 45% del total de tokens debido a la densidad de generar código ejecutable, esquemas de bases de datos y scripts de Docker.
- **Dirección y Estrategia (CEO y PM):** Representan cerca del 20% al 25%, garantizando que la viabilidad comercial y el modelo de negocio estén rigurosamente definidos antes de programar.
- **Seguridad y QA:** Consumen un peso moderado en tokens pero tienen un impacto crítico en la fiabilidad del producto final.

---

## 7. Casos Prácticos de Gestión y Toma de Decisiones

### Caso A: Auditar la Exigencia de las Pruebas de Calidad
1. Accede a la pestaña **`📊 Agent Usage & Stats`**.
2. Observa la tarjeta superior **TASA ÉXITO QA** (ej. `60.0%`).
3. Desciende a las tarjetas de **QA PHP (Pest)** y **QA Python (Pytest)**.
4. Verás que QA PHP muestra `Aprobación: 50%` y QA Python `Aprobación: 66.7%` con 2 y 3 invocaciones respectivamente.
5. **Conclusión de negocio:** Sabes con certeza matemática que los agentes de pruebas encontraron discrepancias en la primera pasada, forzaron a los desarrolladores a corregirlas y no emitieron el aprobado hasta que el software estuvo blindado.

### Caso B: Certificar el Estado de la Factoría antes de Lanzar al Mercado
1. Selecciona tu proyecto en el desplegable superior.
2. Realiza un barrido visual rápido por las 13 tarjetas de la matriz.
3. Verifica que las 13 tarjetas exhiban la insignia verde esmeralda **`APPROVED`**.
4. Esto te certifica que ningún departamento quedó a medias y que la Dirección Ejecutiva (CEO) emitió el acta de **Lanzamiento Autorizado**.

### Caso C: Control Presupuestario de Consumo de Tokens
1. Revisa la barra de **Peso en Proyecto** de cada tarjeta.
2. Si detectas que un especialista secundario supera el 30% del esfuerzo del proyecto, puede indicar que sus instrucciones iniciales fueron demasiado abiertas.
3. Te permite afinar tus futuros mandatos en la consola *Request from Boss* para ser más conciso y ahorrar costes.

---

## 8. Preguntas Frecuentes y Consejos de Optimización Operativa

- **¿Por qué algunos agentes muestran duraciones medias muy bajas (ej. 0.50s) y otros varios minutos?**  
  Los especialistas de desarrollo y arquitectura en entornos optimizados o en Modo Rápido (Mock) devuelven sus especificaciones en fracciones de segundo. En cambio, agentes como el Diseñador UI/UX o el Especialista de Marketing, que generan flujos visuales completos y copys comerciales detallados con modelos LLM profundos, pueden requerir entre 60 y 180 segundos para entregar un trabajo de calidad industrial.

- **¿Se borran estas estadísticas si cambio de pestaña o cierro el navegador?**  
  No. Todas las métricas de ejecuciones, latencias, tokens y tasas de aprobación se guardan permanentemente en la base de datos de telemetría de la factoría digital. Al volver a abrir la aplicación o seleccionar el proyecto, el panel cargará su histórico completo al instante.

- **¿Qué diferencia hay entre esta pestaña y «💰 Token & Cost Monitor»?**  
  **Agent Usage & Stats** se centra en la *eficiencia y rendimiento humano/operativo* de los 13 especialistas (tiempos, aprobaciones, número de llamadas y reparto de trabajo). En cambio, la pestaña siguiente (*💰 Token & Cost Monitor*) se enfoca exclusivamente en la *contabilidad financiera*: desglose de gasto en dólares, modelos de lenguaje utilizados y cálculo exacto del dinero ahorrado.

- **¿Qué debo hacer si un agente permanece en estado «BLOCKED»?**  
  Un estado **`BLOCKED`** significa que el agente de seguridad (CISO) o los tests de calidad vetaron la entrega por detectar vulnerabilidades o errores críticos. Dirígete a la pestaña **`🧠 Agent Thoughts`**, selecciona el agente bloqueado y lee el apartado de correcciones exigidas para conocer los detalles del bloqueo.
