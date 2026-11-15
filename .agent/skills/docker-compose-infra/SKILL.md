---
name: docker-compose-infra
description: Experto en Docker, docker-compose.yml, redes entre contenedores (Agent Office + n8n), persistencia de volúmenes SQLite (WAL) y despliegues en local_deployer.py / vercel_deployer.py.
---

# Docker Compose & Infrastructure Specialist — Agent Office

Este manual técnico define los estándares de contenedorización, orquestación con Docker Compose, arquitectura de redes inter-servicio y políticas de persistencia para la plataforma **Agent Office**.

Gobierna directamente los archivos `docker-compose.yml`, `Dockerfile`, `.dockerignore`, `app/services/local_deployer.py` y `app/services/vercel_deployer.py`.

---

## 1. Topología de Infraestructura de Agent Office

El ecosistema de Agent Office se organiza en una arquitectura de microservicios contenerizada:

```text
Host / Navegador del Usuario
  ├── Port 8080  ────────► [agentoffice_app] (FastAPI + LangGraph + Vanilla JS)
  │                              │ (Red Bridge Interna: 'http://n8n:5678')
  │                              ▼
  └── Port 5678  ────────► [agentoffice_n8n] (n8n Automation Engine)
                                 │
                            [n8n_data] (Volumen Persistente)
```

- **Servicio Principal (`agentoffice`):** Corre en Python 3.12-slim con Uvicorn en el puerto `8080`.
- **Servicio de Automatización (`n8n`):** Corre la imagen oficial `n8nio/n8n:latest` en el puerto `5678`, activable bajo demanda con el perfil `--profile automation`.

---

## 2. Regla 1: Persistencia Garantizada y Manejo SQLite WAL

Dado que Agent Office utiliza SQLite tanto para el catálogo y buzón (`office_data.sqlite`) como para los checkpoints de LangGraph (`office_state.db` / `checkpoints.sqlite`), la persistencia en disco es crítica:

1. **Persistencia de Volúmenes de Aplicación:**
   - En `docker-compose.yml`, el directorio `./workspaces` debe estar montado como volumen persistente:
     ```yaml
     volumes:
       - ./workspaces:/app/workspaces
       - ./prompts:/app/prompts:ro
       - ./app:/app/app
     ```
2. **Archivos SQLite WAL y SHM:**
   - La base de datos opera bajo `PRAGMA journal_mode = WAL;`.
   - SQLite genera dinámicamente los archivos complementarios `office_data.sqlite-wal` y `office_data.sqlite-shm`.
   - **Prohibido:** Montar volúmenes que apunten a un archivo individual de SQLite (e.g. `./office_data.sqlite:/app/office_data.sqlite`), ya que rompería la sincronización de los bloqueos de memoria compartida (`-shm`) y el registro transaccional (`-wal`). Se debe montar siempre el directorio contenedor (`workspaces/`).
3. **Persistencia de n8n:**
   - El volumen nombrado `n8n_data` debe mapearse a `/home/node/.n8n` para conservar workflows, credenciales y ejecuciones entre reinicios de contenedor:
     ```yaml
     volumes:
       - n8n_data:/home/node/.n8n
     ```

---

## 3. Regla 2: Networking Dual (Red Interna Docker vs Host del Usuario)

Existe una distinción fundamental entre el tráfico entre contenedores y el tráfico que proviene del navegador del usuario:

1. **Llamadas Backend-to-Backend (FastAPI -> n8n):**
   - Cuando el backend de FastAPI en `app/services/n8n_service.py` provisiona flujos o despacha webhooks, debe comunicarse mediante el DNS interno de la red Docker:
     `N8N_BASE_URL=http://n8n:5678`
2. **Llamadas Browser-to-Host (Navegador -> n8n):**
   - Cuando el usuario final interactúa con la interfaz web o un webhook es disparado desde un servicio externo fuera de Docker, la URL debe resolver al host:
     `WEBHOOK_URL=http://localhost:5678/`
3. **Configuración en `docker-compose.yml`:**
   ```yaml
   services:
     agentoffice:
       environment:
         - N8N_BASE_URL=http://n8n:5678
     n8n:
       environment:
         - N8N_HOST=localhost
         - N8N_PORT=5678
         - N8N_PROTOCOL=http
         - WEBHOOK_URL=http://localhost:5678/
   ```

---

## 4. Regla 3: Hardening de Contenedores y Buenas Prácticas DevSecOps

1. **Imágenes Base Ligeras y Seguras:**
   - Utilizar exclusivamente imágenes oficiales mínimas: `python:3.12-slim` para el backend.
   - Limpiar caches de paquetes de sistema en la misma capa de instalación:
     `RUN apt-get update && apt-get install -y --no-install-recommends curl git && rm -rf /var/lib/apt/lists/*`
2. **Configuración de `.dockerignore` Estricto:**
   - Bloquear la inclusión en la imagen de secretos, entornos virtuales y tests:
     ```text
     __pycache__/
     *.pyc
     .venv/
     .env
     .git/
     tests/
     workspaces/*
     !workspaces/.gitkeep
     ```
3. **Healthchecks Obligatorios:**
   - Todo servicio debe implementar una directiva de salud no bloqueante con arranque progresivo (`start_period`):
     ```yaml
     healthcheck:
       test: ["CMD", "curl", "-f", "http://127.0.0.1:8080/health"]
       interval: 15s
       timeout: 5s
       retries: 3
       start_period: 10s
     ```

---

## 5. Regla 4: Despliegues Locales y Cloud (Deployers)

Agent Office incluye servicios de automatización de despliegue:

1. **`LocalSandboxDeployer` (`app/services/local_deployer.py`):**
   - Valida la sintaxis de archivos `docker-compose.yml` o `docker-compose.prod.yml` en la carpeta `build/` de los proyectos creados por la factoría.
   - Genera scripts de inicialización desatendida (`start_local.ps1` para Windows y `start_local.sh` para Linux/macOS) que copian `.env.example` y ejecutan `docker compose up -d --build`.
2. **`VercelDeployerService` (`app/services/vercel_deployer.py`):**
   - Empaqueta el frontend y funciones serverless para proyectos destinados a despliegue en Vercel Cloud, asegurando la inyección segura de variables de entorno y cabeceras CORS.

---

## 6. Procedimiento de Verificación y Diagnóstico Docker

```powershell
# 1. Validar la sintaxis del compose
docker compose config

# 2. Iniciar Agent Office junto con n8n
docker compose --profile automation up -d

# 3. Comprobar salud de los contenedores
docker compose ps

# 4. Inspeccionar logs del backend
docker compose logs -f agentoffice
```
