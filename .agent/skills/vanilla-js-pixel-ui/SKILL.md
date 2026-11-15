---
name: vanilla-js-pixel-ui
description: Especialista en el frontal Vanilla JS (panel.js, office.js, api.js, dashboard.js) y el sistema de diseño Pixel-Art (pixel.css) de Agent Office.
---

# Vanilla JS & Pixel-Art UI Specialist — Agent Office

Este manual y guía de estilo de interfaz gobierna el desarrollo del frontend de **Agent Office**: el cuadro de mando 2D en Pixel-Art (Cyber-Loft Engine) y el panel de control de agentes.

Aplica a todo el código alojado en `app/static/`:
- **Estilos y Tokens de Diseño:** `app/static/css/pixel.css`.
- **Estructura HTML:** `app/static/index.html` y `app/static/dashboard.html`.
- **Módulos JavaScript ES6+:**
  - `app/static/js/panel.js` (lógica de pestañas, formularios, marketing y chat).
  - `app/static/js/office.js` (mapa 2D de la oficina, avatares, escritorios y estados).
  - `app/static/js/dashboard.js` (KPIs en tiempo real, telemetría y matriz CISO).
  - `app/static/js/api.js` (cliente HTTP centralizado).
  - `app/static/js/main.js` (punto de entrada e inicialización de módulos).

---

## 1. Regla 1: Stack Estricto Vanilla JS y Cero Dependencias Pesadas

El frontal principal de Agent Office (`index.html`) está diseñado como una aplicación web nativa ultraligera, de renderizado instantáneo y estética retro 16-bit Cyber-Loft.

### Directrices de Implementación:
1. **ES6+ Puro sin Frameworks:**
   - Prohibido introducir React, Vue, Svelte, Angular, JSX o compiladores/bundlers (Webpack, Vite, Babel) en el frontal de Agent Office.
   - Usar módulos JavaScript nativos (`<script type="module" src="...">`).
2. **Manipulación Limpia del DOM:**
   - Utilizar APIs estándar del navegador: `document.getElementById`, `document.querySelector`, `addEventListener`.
3. **Cero Placeholders:**
   - Prohibido dejar bloques con `// TODO`, `// FIXME` o código elidido en los controladores de eventos.

---

## 2. Regla 2: Prevención Estricta de XSS con `_esc(s)` y `textContent`

Dado que el panel visualiza textos generados por agentes de IA, nombres de repositorios y descripciones de usuario, existe riesgo latente de Cross-Site Scripting (XSS).

### Directrices Obligatorias:
1. **Uso Prioritario de `textContent`:**
   - Para actualizar etiquetas, contadores, estados o alertas sin formato enriquecido, utilizar siempre `.textContent`:
     ```javascript
     statusBadge.textContent = '🟢 ACTIVO';
     counterEl.textContent = String(totalCount);
     ```
2. **Sanitización Innegociable para `innerHTML`:**
   - Cuando sea estrictamente indispensable generar HTML dinámico mediante plantillas literales (`template literals`), **toda variable interpolada debe ser escapada** mediante la función estándar `_esc(s)` presente en `panel.js`:
     ```javascript
     function _esc(s) {
       return String(s ?? '')
         .replace(/&/g, '&amp;')
         .replace(/</g, '&lt;')
         .replace(/>/g, '&gt;')
         .replace(/"/g, '&quot;')
         .replace(/'/g, '&#39;');
     }
     ```
   - Ejemplo de uso correcto:
     ```javascript
     container.innerHTML = `
       <div class="project-card">
         <span class="project-name">${_esc(project.name)}</span>
         <span class="project-status">${_esc(project.status)}</span>
       </div>
     `;
     ```
   - **Prohibido:** `${project.name}` directo dentro de `innerHTML` sin escapar.

---

## 3. Regla 3: Centralización en `api.js` y Experiencia de Usuario Reactiva

Ningún archivo de vista (`panel.js`, `office.js`, `dashboard.js`) debe invocar `fetch()` directamente.

1. **Todas las Rutas en `api.js`:**
   - Cualquier nuevo endpoint de FastAPI debe envolverse en un método de la clase/objeto `API` en `app/static/js/api.js`.
   - Control uniforme de códigos de estado HTTP y parseo seguro de respuestas JSON.
2. **Gestión de Estados de Carga y Feedback:**
   - Todo botón que realice una petición de red debe alternar a estado de espera deshabilitado (`disabled = true`, `textContent = '⏳ GUARDANDO...'` o `cargando...`) y restaurarse en el bloque `finally`.
   - Mostrar mensajes de retroalimentación claros en contenedores dedicados (`#feedback-container`).
3. **Manejo Seguro de Credenciales en la UI:**
   - Campos de API Keys, contraseñas y tokens deben renderizarse con `type="password"`.
   - Incluir botón o icono de alternancia de visibilidad (`👁️`) para permitir al usuario inspeccionar el valor de forma controlada.

---

## 4. Regla 4: Sistema de Diseño Pixel-Art y Modularidad No Destructiva

El archivo `app/static/css/pixel.css` define la identidad visual única de Agent Office:

### Tokens y Clases Principales:
- **Colores Base:**
  - Fondo general: `var(--bg-base)` (`#080c14`)
  - Paneles: `var(--bg-panel)` (`rgba(15, 23, 42, 0.96)`)
  - Bordes cibernéticos: `var(--border-cyber)` (`#1e293b`), neón: `var(--border-neon)` (`rgba(16, 185, 129, 0.4)`)
- **Acentos Semánticos:**
  - Verde Esmeralda: `var(--accent-green)` (`#10b981`)
  - Cyan: `var(--accent-cyan)` (`#06b6d4`)
  - Dorado: `var(--accent-gold)` (`#f59e0b`)
  - Rojo: `var(--accent-red)` (`#ef4444`)
- **Tipografía Híbrida:**
  - Títulos y acentos retro: `var(--font-pixel)` (`'Press Start 2P', monospace`)
  - Código y terminales: `var(--font-mono)` (`'Fira Code', 'JetBrains Mono', monospace`)
  - Lectura general: `var(--font-sans)` (`'Inter', sans-serif`)
- **Componentes Pixel-Art:**
  - Botones retro: `.pixel-btn`, `.pixel-btn.secondary`, `.pixel-btn.icon`
  - Tarjetas y chips: `.telemetry-card`, `.kpi-chip`, `.hud-live-badge`
  - Efectos visuales: `#scanlines` (filtro CRT scanline superpuesto)

### Modularidad No Destructiva en `panel.js`:
- Al añadir nuevas pestañas o paneles laterales en `panel.js`:
  1. No modificar ni sobrescribir los selectores ni IDs existentes (`#tab-office`, `#tab-projects`, `#tab-marketing`, etc.).
  2. Registrar eventos mediante `addEventListener` sin usar propiedades directas tipo `element.onclick = ...` para evitar anular manejadores previos.
  3. Mantener el aislamiento de estado entre pestañas.

---

## 5. Checklist de Verificación Frontend

Al realizar cambios en la interfaz gráfica:

- [ ] ¿El código JavaScript corre sin errores en la consola del navegador (`F12`)?
- [ ] ¿Todas las llamadas HTTP se canalizan a través de `API` en `api.js`?
- [ ] ¿Se utiliza `_esc(s)` en todas las variables dinámicas insertadas con `innerHTML`?
- [ ] ¿Los botones de acción reflejan estados de carga y errores de red?
- [ ] ¿Se preserva la estética Pixel-Art y la paleta de colores de `pixel.css`?
