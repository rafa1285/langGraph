"""Intake Agent: conversational WhatsApp agent that gathers project requirements."""

from app.core.config import settings
from app.schemas.routing import AgentID
from app.services.llm_gateway import (
    GeminiLLMGateway,
    LLMGatewayProtocol,
    MockLLMGateway,
)

INTAKE_SYSTEM_PROMPT = """Eres el Agente de Recepción de AgentOffice Software Factory 🏭.

Tu misión es recopilar los requisitos del proyecto del usuario a través de WhatsApp.

## Reglas de comportamiento
- Sé **conciso y amigable** — estamos en WhatsApp, mensajes cortos y directos.
- Haz **UNA sola pregunta** por mensaje.
- Usa emojis **moderadamente** (1-2 por mensaje).
- Adapta el ritmo de la conversación; no hay un número fijo de preguntas.

## Información que debes recopilar
1. Nombre del proyecto
2. Descripción funcional (qué hace, qué problema resuelve)
3. Público objetivo (quién lo usará)
4. Features principales (mínimo 3 funcionalidades concretas)
5. Stack tecnológico preferido (o si confían en la fábrica para decidir)
6. Necesidades especiales: APIs externas, base de datos, autenticación

## Decisión de completitud
Tú decides dinámicamente cuándo tienes suficiente información para arrancar el proyecto. \
No hay un número fijo de preguntas; cuando consideres que la información es suficiente \
para que el equipo comience a trabajar, emite el marcador de finalización.

## Marcadores especiales — úsalos EXACTAMENTE así

Cuando tengas suficiente información, responde EXACTAMENTE con:
```
✅ REQUISITOS_COMPLETOS
[resumen estructurado en markdown con todas las secciones: nombre, descripción, \
público objetivo, features, stack, integraciones]
```

Si el usuario dice "cancelar", "parar" o "stop", responde EXACTAMENTE con:
```
❌ CANCELADO
```

## Contexto de conversación actual

Historial previo:
{conversation_history}

Mensaje actual del usuario:
{user_message}

Responde ahora con tu siguiente mensaje o con uno de los marcadores especiales.
"""


class IntakeAgent:
    """Conversational agent that collects project requirements over WhatsApp."""

    def __init__(self, llm_gateway: LLMGatewayProtocol | None = None) -> None:
        """Initialise with an optional gateway; uses config to pick the default."""
        if llm_gateway is not None:
            self.llm: LLMGatewayProtocol = llm_gateway
        elif settings.USE_MOCK_LLM:
            self.llm = MockLLMGateway()
        else:
            self.llm = GeminiLLMGateway()

    async def process_message(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]],
    ) -> tuple[str, bool, str]:
        """Process an incoming WhatsApp message and return the agent reply.

        Parameters
        ----------
        user_message:
            The raw text sent by the user.
        conversation_history:
            List of ``{"role": "user"|"agent", "content": "..."}`` dicts
            representing the conversation so far (excluding the current message).

        Returns
        -------
        tuple[str, bool, str]
            ``(reply_text, is_requirements_complete, refined_idea)``

            - *reply_text*: the agent's response to send back via WhatsApp.
            - *is_requirements_complete*: ``True`` when the LLM emitted
              ``✅ REQUISITOS_COMPLETOS``.
            - *refined_idea*: the structured markdown summary that follows the
              completion marker; empty string when not complete.
        """
        # Build a human-readable history block for the prompt
        history_lines: list[str] = []
        for entry in conversation_history:
            role = entry.get("role", "")
            content = entry.get("content", "")
            if role == "user":
                history_lines.append(f"Usuario: {content}")
            elif role == "agent":
                history_lines.append(f"Agente: {content}")
            else:
                history_lines.append(f"{role}: {content}")

        history_text: str = (
            "\n".join(history_lines) if history_lines else "(sin historial previo)"
        )

        system_prompt: str = INTAKE_SYSTEM_PROMPT.format(
            conversation_history=history_text,
            user_message=user_message,
        )

        response: str = await self.llm.invoke_agent(
            AgentID.AGENTE_01_PM,
            system_prompt,
            user_message,
        )

        # --- Detect completion marker ---
        completion_marker = "✅ REQUISITOS_COMPLETOS"
        cancel_marker = "❌ CANCELADO"

        if completion_marker in response:
            parts = response.split(completion_marker, maxsplit=1)
            refined_idea: str = parts[1].strip() if len(parts) > 1 else ""
            return response, True, refined_idea

        if cancel_marker in response:
            return response, False, ""

        return response, False, ""
