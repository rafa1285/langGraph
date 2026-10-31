# REGLAS INNEGOCIABLES DE INGENIERÍA — SOFTWARE FACTORY BACKEND

1. **Stack Estricto**:
   - Python 3.12+
   - FastAPI
   - LangGraph (`StateGraph`)
   - `langchain-google-genai`
   - `langgraph-checkpoint-sqlite`
   - Pydantic v2
   - `aiosqlite`
   - `PyYAML`

2. **Tipado Estricto**:
   - Todo el código debe pasar `mypy --strict app/` sin errores.
   - Prohibido usar `Any` injustificado.
   - Sintaxis nativa de Python 3.12 obligatoria (`list[str]`, `dict[str, int]`, `X | None`, `Annotated`).

3. **Pydantic v2 Puro**:
   - Uso exclusivo de `ConfigDict`, `@field_validator`, `model_dump()`, `model_validate()`.
   - Prohibida la sintaxis deprecada de Pydantic v1 (`class Config:`, `.dict()`, `@validator`).

4. **Asincronía Pura**:
   - Todos los nodos de LangGraph, endpoints de FastAPI y operaciones de I/O deben ser `async def` no bloqueantes.
   - Para operaciones de disco y llamadas síncronas bloqueantes, usar `asyncio.to_thread`.

5. **Prohibición de Código Incompleto (Zero Placeholders)**:
   - Prohibido usar `# TODO`, `pass` en funciones operativas o comentarios de elisión tipo `# ... resto del código`.
   - Entregar siempre archivos completos y funcionales.

6. **Verificación de Cierre de Fase**:
   - Al terminar cada fase o iteración, ejecutar obligatoriamente en terminal:
     - `ruff check .`
     - `mypy --strict app/`
     - `pytest`
   - Corregir cualquier advertencia o error antes de dar la fase por completada.
