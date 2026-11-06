"""Chat service: 1-on-1 multi-turn conversation with individual agents."""

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.chat import (
    ChatHistoryResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ChatTurn,
)
from app.schemas.routing import AgentID
from app.services.llm_gateway import LLMGatewayProtocol
from app.services.office_store import OfficeStore
from app.services.prompt_loader import PromptLoader

_HISTORY_LIMIT = 10


class ChatService:
    """Orchestrates 1-on-1 chat with a specific agent, with persistent history."""

    def __init__(
        self,
        llm_gateway: LLMGatewayProtocol,
        prompt_loader: PromptLoader,
        office_store: OfficeStore,
    ) -> None:
        self._llm = llm_gateway
        self._prompt_loader = prompt_loader
        self._store = office_store

    async def send_message(
        self,
        agent_id: AgentID,
        request: ChatMessageRequest,
    ) -> ChatMessageResponse:
        """Send a user message to an agent and return its response.

        Steps:
        1. Load agent system prompt (cached).
        2. Load prior turns from DB (up to _HISTORY_LIMIT).
        3. Build multi-turn user_payload.
        4. Call LLM in chat mode without YAML routing header.
        5. Persist both user and agent turns.
        6. Return response.
        """
        system_prompt = await self._prompt_loader.load_prompt(agent_id)

        prior_turns: list[ChatTurn] = await self._store.get_chat_history(
            request.session_id, limit=_HISTORY_LIMIT
        )

        history_lines: list[str] = []
        for turn in prior_turns:
            prefix = "USUARIO" if turn.role == "user" else f"AGENTE ({turn.agent_id})"
            history_lines.append(f"{prefix}: {turn.content}")

        if history_lines:
            history_text = "\n".join(history_lines)
            user_payload = (
                f"=== HISTORIAL DE CONVERSACIÓN ===\n{history_text}\n\n"
                f"=== MENSAJE ACTUAL ===\n{request.message}"
            )
        else:
            user_payload = request.message

        chat_system_prompt = (
            f"{system_prompt}\n\n"
            "=== MODO CHAT DIRECTO ===\n"
            "Estás en modo de conversación directa 1-a-1 con el usuario (no en pipeline).\n"
            "NO incluyas bloque YAML de enrutamiento en tu respuesta.\n"
            "Responde de forma natural, clara y útil según tu rol profesional.\n"
            "Puedes usar Markdown para formatear tu respuesta."
        )

        llm_response = await self._llm.invoke_agent(
            agent_id=agent_id,
            system_prompt=chat_system_prompt,
            user_payload=user_payload,
        )

        now_iso = datetime.now(UTC).isoformat()

        await self._store.save_chat_turn(
            turn_id=str(uuid4()),
            session_id=request.session_id,
            agent_id=agent_id.value,
            project_id=request.project_id,
            role="user",
            content=request.message,
        )
        await self._store.save_chat_turn(
            turn_id=str(uuid4()),
            session_id=request.session_id,
            agent_id=agent_id.value,
            project_id=request.project_id,
            role="agent",
            content=llm_response,
        )

        return ChatMessageResponse(
            agent_id=agent_id.value,
            response=llm_response,
            session_id=request.session_id,
            timestamp_iso=now_iso,
        )

    async def get_history(
        self, agent_id: AgentID, session_id: str
    ) -> ChatHistoryResponse:
        """Retrieve chat history for a session filtered to this agent."""
        turns = await self._store.get_chat_history(session_id, limit=50)
        agent_turns = [t for t in turns if t.agent_id == agent_id.value]
        return ChatHistoryResponse(
            session_id=session_id,
            agent_id=agent_id.value,
            turns=agent_turns,
            total=len(agent_turns),
        )
