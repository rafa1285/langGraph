"""Tests for Phase 19 — WhatsApp transport layer, session store, intake agent and orchestrator."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import Response

# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------

SAMPLE_WEBHOOK_BODY: dict[str, Any] = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "12345",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15550000000",
                            "phone_number_id": "987654321",
                        },
                        "contacts": [{"profile": {"name": "Test User"}, "wa_id": "5491112223333"}],
                        "messages": [
                            {
                                "from": "5491112223333",
                                "id": "wamid.test123",
                                "timestamp": "1700000000",
                                "text": {"body": "Hola mundo"},
                                "type": "text",
                            }
                        ],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}

SAMPLE_EMPTY_WEBHOOK_BODY: dict[str, Any] = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "12345",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "statuses": [{"id": "wamid.status", "status": "delivered"}],
                    },
                    "field": "messages",
                }
            ],
        }
    ],
}


# ---------------------------------------------------------------------------
# WhatsApp Service tests (Fase 1)
# ---------------------------------------------------------------------------


class TestWhatsAppServiceParse:
    def test_parse_valid_incoming_message(self) -> None:
        from app.services.whatsapp_service import WhatsAppService

        svc = WhatsAppService(phone_number_id="pid", access_token="tok")
        result = svc.parse_incoming_message(SAMPLE_WEBHOOK_BODY)

        assert result is not None
        assert result["sender"] == "5491112223333"
        assert result["text"] == "Hola mundo"
        assert result["message_id"] == "wamid.test123"
        assert result["timestamp"] == "1700000000"
        assert result["type"] == "text"

    def test_parse_payload_without_messages_returns_none(self) -> None:
        from app.services.whatsapp_service import WhatsAppService

        svc = WhatsAppService(phone_number_id="pid", access_token="tok")
        result = svc.parse_incoming_message(SAMPLE_EMPTY_WEBHOOK_BODY)

        assert result is None

    def test_parse_empty_payload_returns_none(self) -> None:
        from app.services.whatsapp_service import WhatsAppService

        svc = WhatsAppService(phone_number_id="pid", access_token="tok")
        result = svc.parse_incoming_message({})

        assert result is None


class TestWhatsAppServiceSend:
    async def test_send_text_message_calls_api(self) -> None:
        from app.services.whatsapp_service import WhatsAppService

        mock_response = MagicMock(spec=Response)
        mock_response.json.return_value = {"messages": [{"id": "wamid.sent"}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        svc = WhatsAppService(
            phone_number_id="pid123", access_token="tok456", http_client=mock_client
        )
        result = await svc.send_text_message("5491234567890", "Hola!")

        assert result == {"messages": [{"id": "wamid.sent"}]}
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "pid123/messages" in call_kwargs[0][0]

    async def test_send_text_message_chunks_long_body(self) -> None:
        from app.services.whatsapp_service import WhatsAppService

        mock_response = MagicMock(spec=Response)
        mock_response.json.return_value = {"messages": [{"id": "wamid.chunk"}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        # 8001 chars → 3 chunks (4000 + 4000 + 1)
        long_body = "x" * 8001

        svc = WhatsAppService(phone_number_id="pid", access_token="tok", http_client=mock_client)
        await svc.send_text_message("5491234567890", long_body)

        assert mock_client.post.call_count == 3

    async def test_send_text_message_two_chunks_exactly(self) -> None:
        from app.services.whatsapp_service import WhatsAppService

        mock_response = MagicMock(spec=Response)
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        body_4001 = "a" * 4001
        svc = WhatsAppService(phone_number_id="pid", access_token="tok", http_client=mock_client)
        await svc.send_text_message("123", body_4001)

        assert mock_client.post.call_count == 2


# ---------------------------------------------------------------------------
# Webhook route tests (Fase 1)
# ---------------------------------------------------------------------------


class TestWebhookVerifyGet:
    def test_valid_verification_returns_challenge(self) -> None:
        from fastapi import FastAPI

        from app.api.routes_whatsapp import router

        with patch("app.core.config.settings") as mock_core_settings, \
             patch("app.api.routes_whatsapp.settings", mock_core_settings):
            mock_core_settings.WHATSAPP_VERIFY_TOKEN = "my_token"
            mock_core_settings.WHATSAPP_APP_SECRET = None

            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.get(
                "/webhook/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "my_token",
                    "hub.challenge": "123456",
                },
            )
            assert response.status_code == 200
            assert response.json() == 123456

    def test_invalid_token_returns_403(self) -> None:
        from fastapi import FastAPI

        from app.api.routes_whatsapp import router

        with patch("app.core.config.settings") as mock_core_settings, \
             patch("app.api.routes_whatsapp.settings", mock_core_settings):
            mock_core_settings.WHATSAPP_VERIFY_TOKEN = "correct_token"
            mock_core_settings.WHATSAPP_APP_SECRET = None

            app = FastAPI()
            app.include_router(router)
            client = TestClient(app)

            response = client.get(
                "/webhook/whatsapp",
                params={
                    "hub.mode": "subscribe",
                    "hub.verify_token": "wrong_token",
                    "hub.challenge": "999",
                },
            )
            assert response.status_code == 403


# ---------------------------------------------------------------------------
# HMAC signature tests (Fase 5)
# ---------------------------------------------------------------------------


class TestWhatsAppSignatureVerification:
    def _make_request(self, body: bytes, signature: str | None, app_secret: str | None) -> Any:
        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=body)
        headers: dict[str, str] = {}
        if signature is not None:
            headers["X-Hub-Signature-256"] = signature
        mock_request.headers = headers
        return mock_request

    async def test_valid_hmac_does_not_raise(self) -> None:
        from app.middleware.whatsapp_security import verify_whatsapp_signature

        secret = "supersecret"
        body = b'{"test": "payload"}'
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        signature = f"sha256={digest}"

        mock_request = self._make_request(body, signature, secret)

        with patch("app.middleware.whatsapp_security.settings") as mock_settings:
            mock_settings.WHATSAPP_APP_SECRET = secret
            await verify_whatsapp_signature(mock_request)

    async def test_invalid_hmac_raises_401(self) -> None:
        from app.middleware.whatsapp_security import verify_whatsapp_signature

        secret = "supersecret"
        body = b'{"test": "payload"}'

        mock_request = self._make_request(body, "sha256=invalidsignature", secret)

        with patch("app.middleware.whatsapp_security.settings") as mock_settings:
            mock_settings.WHATSAPP_APP_SECRET = secret
            with pytest.raises(HTTPException) as exc_info:
                await verify_whatsapp_signature(mock_request)
            assert exc_info.value.status_code == 401

    async def test_no_app_secret_skips_check(self) -> None:
        from app.middleware.whatsapp_security import verify_whatsapp_signature

        with patch("app.middleware.whatsapp_security.settings") as mock_settings:
            mock_settings.WHATSAPP_APP_SECRET = None
            mock_request = self._make_request(b"body", None, None)
            await verify_whatsapp_signature(mock_request)


# ---------------------------------------------------------------------------
# Session Store tests (Fase 2)
# ---------------------------------------------------------------------------


class TestWhatsAppSessionStore:
    async def test_session_lifecycle(self, tmp_path: Any) -> None:
        from app.services.session_store import SessionPhase, WhatsAppSessionStore

        db_file = str(tmp_path / "test_sessions.sqlite")
        store = WhatsAppSessionStore(db_path=db_file)

        # 1. Non-existent session
        assert await store.get_session("123456") is None

        # 2. Insert session
        await store.upsert_session(
            phone="123456",
            project_id="proj_abc",
            phase=SessionPhase.INTAKE.value,
            conversation_history=[{"role": "user", "content": "Hola"}],
            intake_answers={"key": "val"},
        )

        session = await store.get_session("123456")
        assert session is not None
        assert session["phone_number"] == "123456"
        assert session["project_id"] == "proj_abc"
        assert session["phase"] == SessionPhase.INTAKE.value
        assert len(session["conversation_history"]) == 1
        assert session["intake_answers"] == {"key": "val"}

        # 3. Update session
        await store.upsert_session(
            phone="123456",
            project_id="proj_abc",
            phase=SessionPhase.BUILDING.value,
        )
        updated = await store.get_session("123456")
        assert updated is not None
        assert updated["phase"] == SessionPhase.BUILDING.value

        # 4. Delete session
        await store.delete_session("123456")
        assert await store.get_session("123456") is None


# ---------------------------------------------------------------------------
# Intake Agent tests (Fase 2)
# ---------------------------------------------------------------------------


class TestIntakeAgent:
    async def test_intake_process_ongoing_conversation(self) -> None:
        from app.services.intake_agent import IntakeAgent

        mock_llm = AsyncMock()
        mock_llm.invoke_agent = AsyncMock(return_value="¿Cuál es el objetivo principal de la app?")

        agent = IntakeAgent(llm_gateway=mock_llm)
        reply, is_complete, refined_idea = await agent.process_message(
            "Quiero crear una app de tareas", []
        )

        assert is_complete is False
        assert refined_idea == ""
        assert "¿Cuál es el objetivo principal" in reply

    async def test_intake_process_completed(self) -> None:
        from app.services.intake_agent import IntakeAgent

        llm_reply = (
            "Excelente, tenemos todo listo.\n"
            "✅ REQUISITOS_COMPLETOS\n"
            "# TaskFlow\nApp de tareas en tiempo real."
        )
        mock_llm = AsyncMock()
        mock_llm.invoke_agent = AsyncMock(return_value=llm_reply)

        agent = IntakeAgent(llm_gateway=mock_llm)
        reply, is_complete, refined_idea = await agent.process_message(
            "Sí, con eso es suficiente", [{"role": "user", "content": "Detalles"}]
        )

        assert is_complete is True
        assert "# TaskFlow" in refined_idea

    async def test_intake_process_cancelled(self) -> None:
        from app.services.intake_agent import IntakeAgent

        llm_reply = "Entendido, proceso detenido.\n❌ CANCELADO"
        mock_llm = AsyncMock()
        mock_llm.invoke_agent = AsyncMock(return_value=llm_reply)

        agent = IntakeAgent(llm_gateway=mock_llm)
        _reply, is_complete, refined_idea = await agent.process_message(
            "cancelar", []
        )

        assert is_complete is False
        assert refined_idea == ""


# ---------------------------------------------------------------------------
# WhatsApp Orchestrator tests (Fase 3 & Fase 4)
# ---------------------------------------------------------------------------


class TestWhatsAppOrchestrator:
    async def test_reset_command(self, tmp_path: Any) -> None:
        from app.services.session_store import SessionPhase, WhatsAppSessionStore
        from app.services.whatsapp_orchestrator import WhatsAppOrchestrator

        db_file = str(tmp_path / "orch_test.sqlite")
        store = WhatsAppSessionStore(db_path=db_file)
        await store.upsert_session(phone="555123", phase=SessionPhase.BUILDING.value)

        mock_wa = AsyncMock()
        orch = WhatsAppOrchestrator(wa_service=mock_wa, session_store=store)

        await orch.handle_incoming({"sender": "555123", "text": "/reset"})

        assert await store.get_session("555123") is None
        mock_wa.send_text_message.assert_called_once()
        assert "reiniciada" in mock_wa.send_text_message.call_args[0][1]

    async def test_status_command(self, tmp_path: Any) -> None:
        from app.services.session_store import SessionPhase, WhatsAppSessionStore
        from app.services.whatsapp_orchestrator import WhatsAppOrchestrator

        db_file = str(tmp_path / "orch_test_status.sqlite")
        store = WhatsAppSessionStore(db_path=db_file)
        await store.upsert_session(
            phone="555999",
            project_id="proj_test123",
            phase=SessionPhase.BUILDING.value,
        )

        mock_wa = AsyncMock()
        orch = WhatsAppOrchestrator(wa_service=mock_wa, session_store=store)

        await orch.handle_incoming({"sender": "555999", "text": "/estado"})

        mock_wa.send_text_message.assert_called_once()
        call_msg = mock_wa.send_text_message.call_args[0][1]
        assert "proj_test123" in call_msg
        assert "BUILDING" in call_msg

    async def test_intake_ongoing_flow(self, tmp_path: Any) -> None:
        from app.services.session_store import SessionPhase, WhatsAppSessionStore
        from app.services.whatsapp_orchestrator import WhatsAppOrchestrator

        db_file = str(tmp_path / "orch_test_flow.sqlite")
        store = WhatsAppSessionStore(db_path=db_file)

        mock_wa = AsyncMock()
        mock_intake = AsyncMock()
        mock_intake.process_message = AsyncMock(
            return_value=("¿Qué nombre le pondrás?", False, "")
        )

        orch = WhatsAppOrchestrator(
            wa_service=mock_wa,
            session_store=store,
            intake_agent=mock_intake,
        )

        await orch.handle_incoming({"sender": "555001", "text": "Quiero una app de CRM"})

        mock_wa.send_text_message.assert_called_once()
        assert "¿Qué nombre le pondrás?" in mock_wa.send_text_message.call_args[0][1]

        session = await store.get_session("555001")
        assert session is not None
        assert session["phase"] == SessionPhase.INTAKE.value
        assert len(session["conversation_history"]) == 2

    async def test_intake_complete_triggers_pipeline(self, tmp_path: Any) -> None:
        from app.services.session_store import SessionPhase, WhatsAppSessionStore
        from app.services.whatsapp_orchestrator import WhatsAppOrchestrator

        db_file = str(tmp_path / "orch_test_trigger.sqlite")
        store = WhatsAppSessionStore(db_path=db_file)

        mock_wa = AsyncMock()
        mock_intake = AsyncMock()
        mock_intake.process_message = AsyncMock(
            return_value=(
                "Requisitos listos.\n✅ REQUISITOS_COMPLETOS\n# Idea refinada",
                True,
                "# Idea refinada",
            )
        )

        orch = WhatsAppOrchestrator(
            wa_service=mock_wa,
            session_store=store,
            intake_agent=mock_intake,
        )

        with patch.object(orch, "_run_pipeline_and_notify", new_callable=AsyncMock) as mock_run:
            await orch.handle_incoming({"sender": "555777", "text": "Todo perfecto, comencemos"})

            mock_run.assert_called_once()
            session = await store.get_session("555777")
            assert session is not None
            assert session["phase"] == SessionPhase.BUILDING.value
            assert session["project_id"] is not None

    async def test_run_pipeline_and_notify_success(self, tmp_path: Any) -> None:
        from app.services.session_store import SessionPhase, WhatsAppSessionStore
        from app.services.whatsapp_orchestrator import WhatsAppOrchestrator

        db_file = str(tmp_path / "orch_test_run.sqlite")
        store = WhatsAppSessionStore(db_path=db_file)
        await store.upsert_session(
            phone="555888",
            project_id="proj_xyz12345",
            phase=SessionPhase.BUILDING.value,
        )

        mock_wa = AsyncMock()
        orch = WhatsAppOrchestrator(wa_service=mock_wa, session_store=store)

        # Mock stream_project generator
        async def fake_stream(*args: Any, **kwargs: Any) -> Any:
            yield {"agente_00_ceo_charter": {}}
            yield {"agente_01_pm": {}}
            yield {"agente_08_docs": {}}

        mock_orchestrator_instance = AsyncMock()
        mock_orchestrator_instance.initialize = AsyncMock()
        mock_orchestrator_instance.stream_project = fake_stream
        mock_orchestrator_instance.get_project_state = AsyncMock(
            return_value={"documentacion_rag": "# Manual de usuario"}
        )
        mock_orchestrator_instance.close = AsyncMock()

        mock_deployer_instance = AsyncMock()
        mock_deployer_instance.deploy_to_vercel = AsyncMock(
            return_value={
                "success": True,
                "deployment_url": "https://test-app.vercel.app",
            }
        )

        patch_orch = patch(
            "app.services.orchestrator_service.OrchestratorService",
            return_value=mock_orchestrator_instance,
        )
        patch_deployer = patch(
            "app.services.vercel_deployer.VercelDeployerService",
            return_value=mock_deployer_instance,
        )

        with patch_orch, patch_deployer:
            await orch._run_pipeline_and_notify("555888", "proj_xyz12345", "Test idea")

        session = await store.get_session("555888")
        assert session is not None
        assert session["phase"] == SessionPhase.COMPLETED.value

        # Check final message contains Vercel URL
        last_message = mock_wa.send_text_message.call_args_list[-1][0][1]
        assert "https://test-app.vercel.app" in last_message
        assert "Manual de usuario" in last_message
