# Manual de Usuario — Factoría Digital AgentOffice

**Capítulo 7:** Pasarela de Clientes y Centro de Control de WhatsApp (`📱 WhatsApp Hub`)  
**Versión de la Aplicación:** AgentOffice v2.5 Cyber-Loft Engine  
**Destinatarios:** Founders, Directores de Producto, Gestores de Operaciones, Administradores de Sistemas y Equipos de Atención al Cliente  
**Acceso a la sección:** Clic en la pestaña **`📱 WhatsApp Hub`** en la barra superior de navegación o mediante URL directa: [`http://127.0.0.1:8080/#tab-whatsapp`](http://127.0.0.1:8080/#tab-whatsapp)

---

## 📑 Índice del Capítulo

1. [Propósito del WhatsApp Hub y Pasarela Conversacional](#1-propósito-del-whatsapp-hub-y-pasarela-conversacional)
2. [Banner Superior de Telemetría y Diagnóstico Meta](#2-banner-superior-de-telemetría-y-diagnóstico-meta)
3. [Formulario de Configuración de Credenciales (.env)](#3-formulario-de-configuración-de-credenciales-env)
4. [Asistente de Integración con Meta Developer Console (Webhook Helper)](#4-asistente-de-integración-con-meta-developer-console-webhook-helper)
5. [Sandbox Interactivo / Simulador WhatsApp (Pruebas sin Coste)](#5-sandbox-interactivo--simulador-whatsapp-pruebas-sin-coste)
6. [Gestor de Sesiones Activas en SQLite (`whatsapp_sessions`)](#6-gestor-de-sesiones-activas-en-sqlite-whatsapp_sessions)
7. [Experiencia del Cliente Final en WhatsApp (Flujo End-to-End)](#7-experiencia-del-cliente-final-en-whatsapp-flujo-end-to-end)
8. [Casos Prácticos de Configuración y Gestión](#8-casos-prácticos-de-configuración-y-gestión)
9. [Preguntas Frecuentes y Solución de Problemas (Troubleshooting)](#9-preguntas-frecuentes-y-solución-de-problemas-troubleshooting)

---

## 1. Propósito del WhatsApp Hub y Pasarela Conversacional

Mientras que las demás pestañas de **AgentOffice** están orientadas a la interacción interna del fundador con los agentes (mediante consolas web, visualización 2D de oficinas o cuadros de mando analíticos), la pestaña **`📱 WhatsApp Hub`** (`http://127.0.0.1:8080/#tab-whatsapp`) es el **puente directo de cara al mundo exterior**.

Transforma la factoría de software en un servicio accesible desde el bolsillo de cualquier cliente o fundador:

* **Adquisición y Requisitos Autónomos:** Cualquier persona autorizada puede enviar una idea de software a través de un mensaje de WhatsApp convencional.
* **Agente de Admisión Inteligente (`Intake Agent`):** Un agente de IA especializado recibe el mensaje inicial, mantiene una breve conversación clarificadora para acotar el alcance del MVP, los usuarios objetivo y los flujos críticos, y valida que la idea sea viable.
* **Disparo Automático del Pipeline de LangGraph:** Una vez refinados los requisitos, el sistema crea automáticamente el proyecto en la factoría y pone a trabajar a los 15 agentes en segundo plano.
* **Telemetría y Notificaciones Push en Tiempo Real:** El usuario recibe en su WhatsApp actualizaciones automáticas con emojis de cada fase superada (aprobación del CEO, contratos del Arquitecto, compilación de código, auditorías de seguridad CISO y despliegue en Vercel).
* **Control Integral desde el Navegador:** El panel web permite configurar credenciales de Meta Cloud API, simular conversaciones en un sandbox sin gastar cuota de mensajes, auditar sesiones activas y reiniciar estados.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FLUJO CONVERSACIONAL                            │
│                                                                        │
│  [ Cliente en WhatsApp ]                                               │
│            │                                                           │
│            ▼ (Meta Cloud API v21.0 Webhook)                            │
│  [ POST /webhook/whatsapp ] ──► Verificación HMAC-SHA256                │
│            │                                                           │
│            ▼                                                           │
│  [ WhatsApp Orchestrator ]                                             │
│            │                                                           │
│            ├──► Fase INTAKE ──► [ Intake Agent ] (Aclara requisitos)   │
│            │                                                           │
│            └──► Fase BUILDING ──► [ LangGraph Software Factory ]       │
│                                           │ (15 Agentes Autónomos)     │
│                                           ▼                            │
│                                   [ Despliegue Vercel ]                │
│                                           │                            │
│                                           ▼                            │
│                     Notificación de éxito y URL por WhatsApp           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Banner Superior de Telemetría y Diagnóstico Meta

Al acceder a `http://127.0.0.1:8080/#tab-whatsapp`, la parte superior muestra un cuadro de estado en tiempo real diseñado para certificar la salud de la integración:

### 2.1 Componentes del Banner:

1. **Insignia de Estado (`Status Badge`):**
   * **`🟢 LIVE / ACTIVA` (Verde esmeralda):** La pasarela está habilitada y cuenta con credenciales válidas cargadas en memoria. Los mensajes entrantes se procesan normalmente.
   * **`⚪ DESACTIVADA` (Gris tenue):** La pasarela está deshabilitada en los ajustes. Las peticiones entrantes recibirán una respuesta inmediata de suspensión sin consumir procesamiento.
   * **`🟡 PENDIENTE DE CONFIGURACIÓN` (Ámbar):** Falta introducir el *Phone Number ID* o el *Access Token* de Meta.
2. **Contador de Sesiones Activas (`KPI Sessions`):**  
   Muestra el número total de conversaciones registradas en la tabla SQLite `whatsapp_sessions`. Cada sesión representa un número de teléfono que ha interactuado con la factoría.
3. **Botón `🔄 Probar Ping Meta`:**  
   Ejecuta una petición de diagnóstico directa contra la API de Meta Graph (`GET https://graph.facebook.com/v21.0/{phone_number_id}`). Verifica en menos de 2 segundos si el token tiene permisos vigentes y si el identificador telefónico existe.
4. **Caja de Alerta de Diagnóstico (`Diagnostic Alert`):**  
   Si el ping tiene éxito, se ilumina en verde confirmando el nombre de la cuenta de WhatsApp Business. Si falla, muestra en rojo el código de error devuelto por Meta (ej: *Error 190: Invalid OAuth access token*).

---

## 3. Formulario de Configuración de Credenciales (.env)

Ubicado en la columna izquierda (7 columnas del grid), este formulario permite administrar las credenciales de la **API de la nube de WhatsApp (Meta Cloud API v21.0)** sin tener que editar manualmente el archivo `.env` en el servidor:

| Campo de Configuración | Variable de Entorno | Descripción y Buenas Prácticas |
| :--- | :--- | :--- |
| **Activar Pasarela de WhatsApp** | `WHATSAPP_ENABLED` | Interruptor toggle maestro. Si está desactivado, el servidor rechaza el procesamiento de webhooks para mantenimiento. |
| **Phone Number ID** | `WHATSAPP_PHONE_NUMBER_ID` | Identificador único del número emisor en Meta (ej: `109283746501928`). Se obtiene en *Meta for Developers > WhatsApp > Configuración de la API*. |
| **Meta Access Token** | `WHATSAPP_ACCESS_TOKEN` | Token de portador (Bearer). Se recomienda utilizar un **System User Token permanente** generado desde Meta Business Manager para evitar caducidades cada 24 horas. |
| **Webhook Verify Token** | `WHATSAPP_VERIFY_TOKEN` | Cadena secreta acordada con Meta para el saludo inicial (*handshake*). Por defecto: `agentoffice_verify_2026`. |
| **Meta App Secret** | `WHATSAPP_APP_SECRET` | Clave secreta de la aplicación de Meta. Se utiliza para calcular la firma criptográfica HMAC-SHA256 (`x-hub-signature-256`) y validar la autenticidad de cada mensaje entrante. |
| **Whitelist de Teléfonos Autorizados** | `WHATSAPP_ALLOWED_PHONES` | Lista de números en formato internacional E.164 separados por comas (ej: `+34600123456, +34611222333`). Si se deja vacía, el sistema es público; si se especifica, solo responde a esos números. |

### Botones de Acción:
* **`💾 Guardar Configuración`:** Valida los campos, actualiza el archivo `.env` de forma atómica y recarga las variables en memoria en caliente.
* **`🔄 Recargar Valores`:** Lee los valores actuales de disco y resetea el formulario.

> [!IMPORTANT]
> Nunca compartas capturas de pantalla de esta pestaña con el token visible. El formulario enmascara la contraseña por seguridad.

---

## 4. Asistente de Integración con Meta Developer Console (Webhook Helper)

Ubicado en la columna derecha, proporciona las herramientas necesarias para enlazar la factoría con los servidores de Meta:

### 4.1 Datos de Enlace para Meta:
* **URL de Devolución de Llamada (Webhook Callback URL):**  
  Calculada dinámicamente como `https://<tu-dominio>/webhook/whatsapp`.  
  Dispone de un botón `📋 Copiar` para pegarla directamente en la consola de Meta.
* **Token de Verificación:**  
  Muestra el token activo con botón de copia rápida.

### 4.2 Botón `🧪 Probar Verificación Handshake (GET)`:
Antes de configurar Meta, pulsa este botón. La factoría ejecutará una llamada interna idéntica a la que realiza Meta (`hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`). Si la respuesta es exitosa, te garantiza que cuando pulses "Verificar y Guardar" en Meta Developers, el apretón de manos pasará al instante.

### 4.3 Guía Rápida de Configuración en Meta:
1. Accede a [Meta for Developers](https://developers.facebook.com/) e ingresa a tu aplicación.
2. En el menú lateral, dirígete a **WhatsApp > Configuración**.
3. En la sección **Webhook**, pulsa en **Editar**.
4. Pega la URL del Webhook y el Verify Token copiados de este panel.
5. Pulsa **Verificar y Guardar**.
6. En la tabla de campos del Webhook, busca el campo **`messages`** y pulsa **Suscribirse**.

> [!TIP]
> Si ejecutas AgentOffice en local (`http://127.0.0.1:8080`), Meta no podrá contactar con tu ordenador directamente. Utiliza una herramienta de túnel seguro como **Cloudflare Tunnel** (`cloudflared tunnel --url http://localhost:8080`) o **ngrok** (`ngrok http 8080`) para obtener una URL pública HTTPS y pegarla en Meta.

---

## 5. Sandbox Interactivo / Simulador WhatsApp (Pruebas sin Coste)

La **Sección 2** de la pantalla es un entorno de pruebas aislado diseñado para validar la experiencia de usuario y afinar los diálogos del **Intake Agent** sin necesidad de conectar Meta ni gastar mensajes reales:

```txt
┌────────────────────────────────────────────────────────────────────────┐
│  🧪 SIMULADOR INTERACTIVO (SANDBOX)                                    │
├──────────────────────────────────┬─────────────────────────────────────┤
│  Teléfono Emulado:               │  Respuesta Intake Agent: [OK]       │
│  [ +34600123456 ]                │  ┌────────────────────────────────┐ │
│                                  │  │ ¡Hola! 👋 Me parece una gran   │ │
│  Mensaje del Cliente:            │  │ idea. Para estructurar tu MVP, │ │
│  ┌─────────────────────────────┐ │  │ ¿los clientes pagarán suscrip- │ │
│  │ Quiero un SaaS de facturas  │ │  │ ción o pago por factura?       │ │
│  │ automáticas con Stripe...   │ │  └────────────────────────────────┘ │
│  └─────────────────────────────┘ │                                     │
│  [ 🚀 Simular Mensaje ]  [ 🔄 /reset ]                                 │
└──────────────────────────────────┴─────────────────────────────────────┘
```

### 5.1 Cómo utilizar el Simulador:
1. **Teléfono Emulado:** Introduce el número ficticio con el que deseas probar (por defecto `+34600123456`).
2. **Mensaje del Cliente:** Escribe la propuesta de software como si fueras un usuario escribiendo desde su móvil.  
   *Ejemplo:* *"Hola, quiero una aplicación para gestionar citas en clínicas veterinarias con avisos por SMS."*
3. **Pulsar `🚀 Simular Mensaje Entrante`:**  
   El mensaje se envía al endpoint `/api/v1/whatsapp/simulate`. El **Intake Agent** procesa la intención, registra la conversación en SQLite y devuelve la contestación en la consola de la derecha.
4. **Continuar el diálogo:** Puedes responder a las preguntas del agente sucesivamente. Cuando el agente considere que los requisitos están completos, iniciará el proyecto.
5. **Botón `🔄 /reset`:** Envía el comando `/reset` para vaciar el historial de ese número y comenzar un flujo nuevo.

---

## 6. Gestor de Sesiones Activas en SQLite (`whatsapp_sessions`)

La **Sección 3** ofrece un cuadro de mando con todas las conversaciones vivas registradas en la base de datos de la factoría:

### 6.1 Columnas de la Tabla:
* **Teléfono:** Número del cliente en formato internacional E.164.
* **Fase (`SessionPhase`):**
  * `INTAKE` (Cian): En proceso de conversación inicial y levantamiento de requisitos.
  * `BUILDING` (Amarillo): El mandato ha sido entregado a LangGraph y los 15 agentes están programando el software.
  * `DEPLOYING` (Púrpura): La aplicación ha superado las pruebas y se está publicando en Vercel.
  * `COMPLETED` (Verde esmeralda): Software finalizado y entregado al usuario.
* **Proyecto ID:** Código del proyecto en la factoría (ej: `proj_88c9fd46`) asociado a esa conversación.
* **Mensajes:** Número total de turnos de chat intercambiados con ese cliente.
* **Última Actividad:** Fecha y hora exacta de la última interacción.
* **Acciones:**
  * **Botón `👁️ Ver` (`viewWhatsAppSession`):** Despliega una ventana emergente (*modal*) con la transcripción completa del chat entre el usuario y la factoría.
  * **Botón `🗑️ Reset` (`resetWhatsAppSession`):** Elimina la sesión de la base de datos, permitiendo que ese número empiece desde cero si quedó atascado.

---

## 7. Experiencia del Cliente Final en WhatsApp (Flujo End-to-End)

El valor diferencial de AgentOffice radica en lo simple que resulta para el usuario no técnico encargar software:

### Paso 1: Primer Contacto
El cliente escribe a tu número de WhatsApp Business:
> **Cliente:** "Hola! Necesito una web para mi academia de idiomas donde los alumnos puedan reservar clases de 45 minutos y pagar con tarjeta."

### Paso 2: Entrevista de Cualificación con el Intake Agent
El agente responde en menos de 5 segundos con una contestación empática y estructurada:
> **AgentOffice:** "¡Hola! 👋 Qué gran proyecto. Para definir el alcance exacto de tu software, respóndeme a estas dos preguntas rápidas:  
> 1. ¿Manejarás suscripciones mensuales o bonos de clases sueltas?  
> 2. ¿Habrá varios profesores o solo impartirás tú las clases?"

### Paso 3: Confirmación y Puesta en Marcha
El usuario contesta:
> **Cliente:** "Serán bonos de 5 y 10 clases, y por ahora seré yo el único profesor."

El agente analiza la información, detecta que los requisitos para el MVP son sólidos y confirma el lanzamiento:
> **AgentOffice:** "🎯 ¡Perfecto! Requisitos entendidos: MVP de academia unipersonal con bonos de 5 y 10 clases y pasarela Stripe.  
> 🚀 **Lanzando factoría digital...** Nuestro equipo de 15 agentes de IA ya está construyendo tu plataforma. Te iré avisando de cada hito."

### Paso 4: Notificaciones de Hitos en Vivo
El orquestador de WhatsApp envía alertas automáticas conforme los agentes cierran sus compuertas:
* 👔 **CEO:** Charter de negocio formalizado con margen superior al 80%.
* 📐 **Arquitecto:** Contratos de API REST y esquema de base de datos aprobados.
* ⚡ **Desarrolladores:** Código backend Laravel y FastAPI compilado.
* 🛡️ **CISO:** Auditoría de ciberseguridad superada con dictamen `BLINDADO`.
* 🚀 **DevOps & Vercel:** Despliegue completado con éxito.

### Paso 5: Entrega Final
> **AgentOffice:** "✅ **¡Tu aplicación está lista para usar!**  
> 🔗 **Acceso en vivo:** https://academia-idiomas-saas.vercel.app  
> 📚 **Documentación técnica:** https://academia-idiomas-saas.vercel.app/docs.html  
> Escribe `/nuevo` cuando quieras encargar otro proyecto."

---

## 8. Casos Prácticos de Configuración y Gestión

### Caso A: Habilitar la pasarela para un grupo VIP de clientes
1. Accede a `http://127.0.0.1:8080/#tab-whatsapp`.
2. Marca la casilla **Activar Pasarela de WhatsApp**.
3. En el campo **Whitelist de Teléfonos Autorizados**, introduce únicamente los teléfonos de tus clientes de prueba: `+34600111222, +34699333444`.
4. Pulsa **Guardar Configuración**.
5. Cualquier mensaje procedente de un número desconocido será ignorado por el sistema, protegiendo tus cuotas de computación.

### Caso B: Simular una idea antes de anunciarla al público
1. Dirígete a la **Sección 2 (Simulador Interactivo)**.
2. Introduce un teléfono de prueba (`+34600000001`).
3. Escribe una idea compleja: *"Plataforma multi-tenant para inmobiliarias que genera contratos de alquiler en PDF con firma digital"*.
4. Pulsa **Simular Mensaje Entrante**.
5. Lee la respuesta del **Intake Agent** en la consola para comprobar si comprende el modelo de negocio y formula las preguntas adecuadas.
6. Si deseas reintentar con otra variante, pulsa el botón rojo **`/reset`**.

### Caso C: Desbloquear a un cliente que escribió datos erróneos
1. En la **Sección 3 (Sesiones Activas)**, localiza el teléfono del cliente en la tabla.
2. Pulsa el botón **`👁️ Ver`** para leer qué escribió.
3. Si el usuario se equivocó o desea cambiar de idea, pulsa el botón **`🗑️ Reset`**.
4. La sesión se eliminará de SQLite y el cliente recibirá una nueva bienvenida la próxima vez que escriba.

---

## 9. Preguntas Frecuentes y Solución de Problemas (Troubleshooting)

### ¿Qué debo hacer si Meta devuelve «Error 190: Invalid OAuth access token»?
Significa que el token de Meta ha caducado. Los tokens temporales del panel de desarrolladores caducan cada 24 horas. Para producción, debes crear un **Usuario del Sistema** en *Meta Business Suite > Configuración del Negocio > Usuarios del Sistema*, generarle un token permanente con los permisos `whatsapp_business_messaging` y pegarlo en este formulario.

### ¿Por qué el botón «Probar Verificación Handshake» responde con error 403?
El token que has escrito en el campo **Webhook Verify Token** no coincide con el que espera el servidor. Asegúrate de pulsar primero **Guardar Configuración** tras cambiar el Verify Token antes de probar el apretón de manos.

### ¿Se pueden enviar audios, imágenes o documentos por WhatsApp?
En la versión actual v2.5, el **Intake Agent** procesa mensajes de texto y notas estructuradas. Si un usuario envía un sticker o un archivo multimedia, el agente le solicitará amablemente que describa su idea mediante texto para evitar ambigüedades en la fase de análisis.

### ¿Cómo sabe el cliente el avance de su proyecto si cierra WhatsApp?
El cliente no necesita mantener WhatsApp abierto. El **WhatsApp Orchestrator** se ejecuta de forma asíncrona en el backend. Cuando un agente de LangGraph completa una compuerta crítica, despacha una notificación push directamente al chat del cliente.
