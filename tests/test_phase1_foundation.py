"""Tests for Phase 1 foundational schemas, configuration, state, and reducers."""

from app.core.config import Settings
from app.graph.state import (
    append_execution_records,
    create_initial_state,
    merge_retry_counts,
)
from app.schemas.routing import (
    AgentID,
    DeliverableStatus,
    RoutingHeader,
    StepExecutionRecord,
)


def test_routing_header_and_deliverable_status() -> None:
    """Test validation and serialization of routing headers."""
    header = RoutingHeader(
        origen="agente_01_pm",
        destino_siguiente="agente_02_architect",
        estado_entregable=DeliverableStatus.PRE_SDD_LISTO,
        veredicto="APROBADO",
        puntuacion=95,
        culpable_detectado=None,
    )

    dumped = header.model_dump()
    assert dumped["origen"] == "agente_01_pm"
    assert dumped["destino_siguiente"] == "agente_02_architect"
    assert dumped["estado_entregable"] == DeliverableStatus.PRE_SDD_LISTO
    assert dumped["puntuacion"] == 95

    validated = RoutingHeader.model_validate(dumped)
    assert validated.estado_entregable == DeliverableStatus.PRE_SDD_LISTO


def test_agent_temperatures() -> None:
    """Verify strictly specified temperatures per agent ID."""
    cfg = Settings(GEMINI_API_KEY="test-key")

    # 0.2 for PM and DOCS
    assert cfg.get_agent_temperature(AgentID.AGENTE_01_PM) == 0.2
    assert cfg.get_agent_temperature(AgentID.AGENTE_08_DOCS) == 0.2

    # 0.4 for GROWTH
    assert cfg.get_agent_temperature(AgentID.AGENTE_09_GROWTH) == 0.4

    # 0.1 for all others
    low_temp_agents = [
        AgentID.AGENTE_02_ARCHITECT,
        AgentID.AGENTE_03_LARAVEL,
        AgentID.AGENTE_04_FASTAPI,
        AgentID.AGENTE_05_QA_PHP,
        AgentID.AGENTE_06_QA_PYTHON,
        AgentID.AGENTE_07_DEVOPS,
        AgentID.AGENTE_10_CISO,
    ]
    for agent_id in low_temp_agents:
        assert cfg.get_agent_temperature(agent_id) == 0.1


def test_agent_model_selection_and_override() -> None:
    """Verify default model fallback and override mechanisms."""
    cfg_default = Settings(GEMINI_API_KEY="test-key", DEFAULT_LLM_MODEL="gemini-2.5-flash")
    assert cfg_default.get_agent_model(AgentID.AGENTE_01_PM) == "gemini-2.5-flash"

    cfg_overridden = Settings(
        GEMINI_API_KEY="test-key",
        DEFAULT_LLM_MODEL="gemini-2.5-flash",
        AGENT_MODEL_OVERRIDES={"agente_01_pm": "gemini-1.5-pro"},
    )
    assert cfg_overridden.get_agent_model(AgentID.AGENTE_01_PM) == "gemini-1.5-pro"
    assert cfg_overridden.get_agent_model(AgentID.AGENTE_02_ARCHITECT) == "gemini-2.5-flash"


def test_merge_retry_counts_pure_reducer() -> None:
    """Verify retry count reducer merges values correctly without mutating inputs."""
    initial: dict[str, int] = {"qa_php": 1, "qa_python": 0, "ciso": 0}
    update: dict[str, int] = {"qa_python": 2}

    merged = merge_retry_counts(initial, update)

    assert merged == {"qa_php": 1, "qa_python": 2, "ciso": 0}
    assert initial == {"qa_php": 1, "qa_python": 0, "ciso": 0}
    assert update == {"qa_python": 2}


def test_append_execution_records_pure_reducer() -> None:
    """Verify execution history reducer concatenates entries in order."""
    r1 = StepExecutionRecord(
        step_number=1,
        agent_id=AgentID.AGENTE_01_PM,
        status=DeliverableStatus.PRE_SDD_LISTO,
        target_next="agente_02_architect",
        artifact_path="workspaces/proj-1/pre_sdd.md",
        timestamp_iso="2026-10-31T09:00:00Z",
    )
    r2 = StepExecutionRecord(
        step_number=2,
        agent_id=AgentID.AGENTE_02_ARCHITECT,
        status=DeliverableStatus.APROBADO_PARA_DESARROLLO,
        target_next="agente_03_laravel",
        artifact_path="workspaces/proj-1/sdd_architecture.md",
        timestamp_iso="2026-10-31T09:05:00Z",
    )

    combined = append_execution_records([r1], [r2])

    assert len(combined) == 2
    assert combined[0].step_number == 1
    assert combined[1].step_number == 2


def test_create_initial_state() -> None:
    """Verify complete initial state initialization."""
    state = create_initial_state(
        project_id="test-proj-001",
        idea_inicial="Crear un CRM SaaS para clínicas dentales",
    )

    assert state["project_id"] == "test-proj-001"
    assert state["idea_inicial"] == "Crear un CRM SaaS para clínicas dentales"
    assert state["pre_sdd_doc"] == ""
    assert state["sdd_arquitectura"] == ""
    assert state["requiere_php"] is True
    assert state["requiere_python"] is True
    assert state["codigo_php"] == ""
    assert state["codigo_python"] == ""
    assert state["reporte_qa_php"] == ""
    assert state["reporte_qa_python"] == ""
    assert state["infraestructura_docker"] == ""
    assert state["dictamen_ciso"] == ""
    assert state["documentacion_rag"] == ""
    assert state["estrategia_growth"] == ""
    assert state["status_qa_php"] == DeliverableStatus.PENDIENTE
    assert state["status_qa_python"] == DeliverableStatus.PENDIENTE
    assert state["status_ciso"] == DeliverableStatus.PENDIENTE
    assert state["ciso_culprit"] is None
    assert state["halt_reason"] is None
    assert state["retry_counts"] == {"qa_php": 0, "qa_python": 0, "ciso": 0}
    assert state["execution_history"] == []
