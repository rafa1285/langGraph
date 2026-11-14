# Matriz de Modelos de Inteligencia Artificial y Cadenas de Fallback por Agente — AgentOffice

> **Estado Oficial:** Vigente y sincronizado con `app/services/office_store.py` (`DEFAULT_AGENT_CHAINS`) y `app/services/llm_gateway.py`.  
> **Sincronización Notion:** [🤖 Matriz de Modelos de Inteligencia Artificial y Cadenas de Fallback por Agente](https://app.notion.com/p/418be4dde9738106a660e49c74c2a610).

---

## 1. Filosofía de Enrutamiento Multimodelo y Cero Caídas (Zero-Downtime)

**AgentOffice** implementa una arquitectura desacoplada de proveedores LLM coordinada a través de un **LLM Gateway** dinámico. El objetivo es garantizar resiliencia absoluta ante caídas de servicio, picos de latencia o agotamiento de cuotas gratuitas (*Rate Limits / HTTP 429*):

1. **Prioridad 1 (Modelo Primario):** Ajuste cognitivo óptimo según la especialidad del agente (Razonamiento profundo, Generación de código, Testing o Persuasión comercial).
2. **Prioridades 2 y 3 (Fallbacks Gratuitos Activos):** Alternativas de alta capacidad y baja latencia (Google Gemini, Groq, Mistral AI) que asumen el relevo sin intervención manual.
3. **Prioridades 4 y 5 (Fallbacks de Respaldo Premium):** Modelos de frontera empresarial (Anthropic Claude 3.5 Sonnet, OpenAI GPT-4o / o3-mini, DeepSeek) preparados para contingencias mayores.

---

## 2. Matriz Maestra de Asignación por Agente

| Agente | Nombre Visual | Modelo Primario (P1) | Proveedor P1 | Cadena de Fallback (P2 → P5) | Temperatura | Max Tokens | Justificación Técnica |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| `agente_00_ceo` | 👔 CEO | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq | P2: `gemini-3.5-flash-lite`<br>P3: `qwen/qwen3-32b`<br>P4: `gpt-4o-mini` (inactivo)<br>P5: `gpt-4o` (inactivo) | `0.1` | 8.192 | Gobernanza ejecutiva, fijación de márgenes unitarios y auditoría de cierre Zero-Touch. |
| `agente_01_pm` | 📋 Product Manager | `gemini-3.6-flash` | Google AI | P2: `llama-3.3-70b-versatile` (Groq)<br>P3: `mistral-large-latest` (Mistral)<br>P4: `gpt-4o-mini` (inactivo) | `0.2` | 8.192 | Análisis de producto, recorte estricto del MVP y criterios de aceptación Gherkin. |
| `agente_02_architect` | 📐 Software Architect | `gemini-3.5-pro` | Google AI | P2: `gemini-3.6-flash`<br>P3: `mistral-large-latest`<br>P4: `claude-3-5-sonnet` (inactivo)<br>P5: `o3-mini` (inactivo) | `0.1` | 8.192 | Diseño de sistemas escalables, arquitectura hexagonal y contratos OpenAPI. |
| `agente_11_ui_ux` | 🎨 UI/UX Designer | `gemini-3.5-pro` | Google AI | P2: `gemini-3.6-flash`<br>P3: `codestral-latest` (Mistral)<br>P4: `claude-3-5-sonnet` (inactivo) | `0.2` | 8.192 | Diseño de sistemas visuales, paletas cromáticas accesibles y layouts semánticos. |
| `agente_03_laravel` | 🐘 Dev PHP (Laravel) | `gemini-3.6-flash` | Google AI | P2: `codestral-latest` (Mistral)<br>P3: `qwen/qwen3-32b` (Groq)<br>P4: `claude-3-5-sonnet` (inactivo)<br>P5: `deepseek-chat` (inactivo) | `0.1` | 8.192 | Generación de código PHP 8.4 estrictamente tipado, modelos Eloquent y Jobs idempotentes. |
| `agente_04_fastapi` | ⚡ Dev Python (FastAPI) | `gemini-3.6-flash` | Google AI | P2: `codestral-latest` (Mistral)<br>P3: `qwen/qwen3-32b` (Groq)<br>P4: `claude-3-5-sonnet` (inactivo)<br>P5: `deepseek-chat` (inactivo) | `0.1` | 8.192 | Microservicios 100% asíncronos en Python 3.12+, esquemas Pydantic v2 y Mypy strict. |
| `agente_05_qa_php` | 🔬 QA PHP (Pest) | `qwen/qwen3-32b` | Groq | P2: `codestral-latest` (Mistral)<br>P3: `gemini-3.5-flash-lite`<br>P4: `deepseek-chat` (inactivo)<br>P5: `gpt-4o-mini` (inactivo) | `0.1` | 4.096 | Detección rigurosa de errores de tipado, análisis Larastan Nivel 9 y tests Pest. |
| `agente_06_qa_python` | 🐍 QA Python (Pytest) | `qwen/qwen3-32b` | Groq | P2: `codestral-latest` (Mistral)<br>P3: `gemini-3.5-flash-lite`<br>P4: `deepseek-chat` (inactivo)<br>P5: `gpt-4o-mini` (inactivo) | `0.1` | 4.096 | Detección de bloqueos de Event Loop, memory leaks y suites completas pytest-asyncio. |
| `agente_14_qa_ui_ux` | 🎯 QA UI/UX | `gemini-3.6-flash` | Google AI | P2: `qwen/qwen3-32b` (Groq)<br>P3: `gemini-3.5-flash-lite`<br>P4: `gemini-3.5-flash` (inactivo) | `0.1` | 4.096 | Auditoría de coherencia visual, accesibilidad WCAG y responsividad. |
| `agente_07_devops` | ⚙️ DevOps & Docker | `codestral-latest` | Mistral AI | P2: `qwen/qwen3-32b` (Groq)<br>P3: `gemini-3.5-flash-lite`<br>P4: `gpt-4o-mini` (inactivo) | `0.1` | 4.096 | Dockerfiles multi-stage non-root, Docker Compose de producción y flujos CI/CD. |
| `agente_10_ciso` | 🛡️ CISO Security | `gemini-3.5-pro` | Google AI | P2: `mistral-large-latest` (Mistral)<br>P3: `qwen/qwen3-32b` (Groq)<br>P4: `o3-mini` (inactivo)<br>P5: `claude-3-5-sonnet` (inactivo) | `0.1` | 8.192 | Pentesting de caja blanca, auditoría OWASP Top 10, prevención de SSRF e IDOR. |
| `agente_08_docs` | 📚 Docs & RAG | `gemini-3.6-flash` | Google AI | P2: `gemini-3.5-flash-lite`<br>P3: `mistral-large-latest`<br>P4: `gemini-3.5-flash` (inactivo) | `0.2` | 4.096 | Manuales de usuario Self-Service, guías de despliegue y chunks RAG autocontenidos. |
| `agente_09_growth` | 🌱 Growth (Legacy) | `llama-3.3-70b-versatile` | Groq | P2: `mistral-large-latest`<br>P3: `llama-3.1-8b-instant`<br>P4: `gpt-4o-mini` (inactivo) | `0.4` | 4.096 | Embudos de conversión Zero-Touch, landing pages y secuencias de retención. |
| `agente_12_marketing` | 📣 Growth Marketing | `llama-3.3-70b-versatile` | Groq | P2: `mistral-large-latest`<br>P3: `llama-3.1-8b-instant`<br>P4: `gpt-4o-mini` (inactivo) | `0.3` | 4.096 | SEO programático, robots.txt, sitemaps, JSON-LD y copywriting persuasivo PAS. |
| `agente_13_sales_analytics` | 💹 Sales & BI | `gemini-3.6-flash` | Google AI | P2: `mistral-large-latest`<br>P3: `gemini-3.5-flash-lite`<br>P4: `gpt-4o-mini` (inactivo) | `0.2` | 4.096 | Integración de pasarelas de pago autoservicio (Stripe) y métricas de monetización SaaS. |

---

## 3. Catálogo de Modelos Homologados (`DEFAULT_CATALOG_MODELS`)

| Model ID | Display Name | Provider | API Key Env | Tier | Temp Default | Max Tokens |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| `gemini-3.5-pro` | Gemini 3.5 Pro | Google | `GEMINI_API_KEY` | Free | 0.2 | 8.192 |
| `gemini-3.6-flash` | Gemini 3.6 Flash | Google | `GEMINI_API_KEY` | Free | 0.2 | 8.192 |
| `gemini-3.5-flash-lite` | Gemini 3.5 Flash Lite | Google | `GEMINI_API_KEY` | Free | 0.2 | 4.096 |
| `gemini-3.5-flash` | Gemini 3.5 Flash | Google | `GEMINI_API_KEY` | Free | 0.2 | 8.192 |
| `mistral-large-latest` | Mistral Large Latest | Mistral AI | `MISTRAL_API_KEY` | Free | 0.2 | 4.096 |
| `codestral-latest` | Codestral Latest | Mistral AI | `MISTRAL_API_KEY` | Free | 0.1 | 8.192 |
| `qwen/qwen3-32b` | Qwen 3 32B (Groq) | Groq | `GROQ_API_KEY` | Free | 0.2 | 4.096 |
| `llama-3.3-70b-versatile` | Llama 3.3 70B (Groq) | Groq | `GROQ_API_KEY` | Free | 0.2 | 4.096 |
| `llama-3.1-8b-instant` | Llama 3.1 8B (Groq) | Groq | `GROQ_API_KEY` | Free | 0.2 | 4.096 |
| `meta-llama/llama-4-scout-17b-16e-instruct` | Llama 4 Scout 17B | Groq | `GROQ_API_KEY` | Free | 0.2 | 4.096 |
| `claude-3-5-sonnet-latest` | Claude 3.5 Sonnet | Anthropic | `ANTHROPIC_API_KEY` | Paid | 0.2 | 8.192 |
| `o3-mini` | o3-mini | OpenAI | `OPENAI_API_KEY` | Paid | 1.0 | 8.192 |
| `gpt-4o-mini` | GPT-4o Mini | OpenAI | `OPENAI_API_KEY` | Paid | 0.2 | 4.096 |
| `gpt-4o` | GPT-4o | OpenAI | `OPENAI_API_KEY` | Paid | 0.2 | 4.096 |
| `deepseek-chat` | DeepSeek Chat (V3) | DeepSeek | `DEEPSEEK_API_KEY` | Paid | 0.2 | 4.096 |

---

## 4. Configuración y Personalización Local

Los modelos y parámetros pueden ajustarse sin modificar el código fuente a través del archivo `.env`:

```bash
# Sobrescribir modelo por defecto
DEFAULT_LLM_MODEL="gemini-3.5-flash"

# Sobrescribir modelos individuales por agente (JSON format)
AGENT_MODEL_OVERRIDES='{"agente_02_architect": "gemini-3.5-pro", "agente_10_ciso": "claude-3-5-sonnet-latest"}'

# Demora de seguridad contra Rate Limits (segundos entre llamadas)
RATE_LIMIT_DELAY_SECONDS=6.0
```
