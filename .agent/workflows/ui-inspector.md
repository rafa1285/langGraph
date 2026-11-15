---
description: Inspecciona, repara y optimiza la interfaz web de Agent Office (index.html, dashboard.html, panel.js, office.js, dashboard.js, api.js y pixel.css).
---

# Workflow: Inspección y Optimización UI/UX Pixel-Art (`/ui-inspector`)

Este workflow operativo rige la revisión, refactorización y aseguramiento estético y funcional del frontal de **Agent Office** (Cyber-Loft 2D Engine y Dashboard de Operaciones).

---

## 1. Activación de Skills Requeridas

- **`vanilla-js-pixel-ui`** (Vanilla JS nativo ES6+, escape `_esc(s)`, centralización en `api.js` y `pixel.css`).
- **`cybersecurity-appsec-guardian`** (Prevención de DOM XSS y protección visual de credenciales).

---

## 2. Protocolo de Inspección Frontend

### Paso 1: Auditoría de Seguridad DOM y Manejo de Datos Dinámicos
1. **Inspección de `panel.js`, `office.js` y `dashboard.js`:**
   - Buscar cualquier asignación directa de `innerHTML`.
   - Confirmar que toda variable interpolada en plantillas de texto esté encapsulada con `_esc(variable)`.
   - Verificar que los textos estáticos o contadores numéricos empleen preferentemente `.textContent`.
2. **Protección de Inputs de Credenciales:**
   - Verificar que los campos destinados a API Keys o contraseñas se rendericen inicialmente como `type="password"`.
   - Asegurar que incluyan un botón o toggle interactivo (`👁️`) para permitir visualización temporal controlada.

### Paso 2: Centralización y Reactividad en Peticiones de Red
1. **Desacoplamiento de `fetch`:**
   - Confirmar que ningún manejador de interfaz invoque `fetch` directamente; todas las llamadas deben realizarse a través de los métodos de `API` en `app/static/js/api.js`.
2. **Estados de Carga y Bloqueo de Acciones Dobles:**
   - Verificar que botones de acción asíncrona (e.g. *Ping Modelo*, *Probar Herramienta*, *Aprovisionar n8n*, *Guardar Cambios*) apliquen:
     - `button.disabled = true;`
     - `button.textContent = '⏳ Cargando...';`
     - Restauración garantizada en el bloque `finally` con retroalimentación cromática en `#feedback-container` (verde para éxito, rojo para error).

### Paso 3: Modularidad No Destructiva de Scripts
1. **Registro Seguro de Eventos:**
   - Confirmar que se emplee `addEventListener('click', ...)` en lugar de propiedades destructivas tipo `onclick = ...`.
   - Asegurar que no se dupliquen identificadores (`id`) en el DOM entre diferentes paneles o pestañas.

### Paso 4: Coherencia Visual Cyber-Loft & Pixel-Art (`pixel.css`)
1. **Respeto a la Paleta y Tokens Retro 16-bit:**
   - Fondos oscuros profundos (`var(--bg-base)`, `var(--bg-panel)`).
   - Acentos cromáticos semánticos: verde neón (`--accent-green`), cyan cibernético (`--accent-cyan`), ámbar (`--accent-gold`) y rojo alerta (`--accent-red`).
   - Tipografía híbrida: `Press Start 2P` para encabezados retro y `Fira Code` / `Inter` para datos legibles.
   - Superposición de scanlines CRT (`#scanlines`) activa y no bloqueante para eventos de ratón (`pointer-events: none`).

---

## 3. Checklist de Cierre Visual

Al finalizar cualquier ajuste de interfaz:
- [ ] No hay excepciones ni errores no capturados en la consola del navegador (`F12`).
- [ ] Todas las variables dinámicas en el DOM están sanitizadas con `_esc(s)`.
- [ ] Los botones reflejan estados de carga y errores de red de forma clara.
- [ ] La estética Pixel-Art Cyber-Loft 16-bit permanece armónica en `index.html` y `dashboard.html`.
