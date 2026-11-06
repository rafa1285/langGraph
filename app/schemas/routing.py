"""Routing and delivery schemas for the agent graph."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class AgentID(StrEnum):
    """Unique identifiers for agents and barrier nodes in the pipeline."""

    AGENTE_00_CEO = "agente_00_ceo"
    AGENTE_01_PM = "agente_01_pm"
    AGENTE_02_ARCHITECT = "agente_02_architect"
    AGENTE_03_LARAVEL = "agente_03_laravel"
    AGENTE_04_FASTAPI = "agente_04_fastapi"
    AGENTE_05_QA_PHP = "agente_05_qa_php"
    AGENTE_06_QA_PYTHON = "agente_06_qa_python"
    QA_SYNC_BARRIER = "qa_sync_barrier"
    AGENTE_07_DEVOPS = "agente_07_devops"
    AGENTE_10_CISO = "agente_10_ciso"
    AGENTE_08_DOCS = "agente_08_docs"
    AGENTE_09_GROWTH = "agente_09_growth"
    AGENTE_11_UI_UX = "agente_11_ui_ux"
    AGENTE_12_MARKETING = "agente_12_marketing"
    AGENTE_13_SALES_ANALYTICS = "agente_13_sales_analytics"
    AGENTE_14_QA_UI_UX = "agente_14_qa_ui_ux"
    END_PIPELINE = "end_pipeline"


class DeliverableStatus(StrEnum):
    """Lifecycle status states for deliverables across the factory pipeline."""

    PENDIENTE = "PENDIENTE"
    CHARTER_NEGOCIO_LISTO = "CHARTER_NEGOCIO_LISTO"
    PRE_SDD_LISTO = "PRE_SDD_LISTO"
    APROBADO_PARA_DESARROLLO = "APROBADO_PARA_DESARROLLO"
    SISTEMA_DISENO_UI_LISTO = "SISTEMA_DISENO_UI_LISTO"
    AUDITORIA_UI_UX_APROBADA = "AUDITORIA_UI_UX_APROBADA"
    RECHAZADO_PARA_REFACTOR_UI_UX = "RECHAZADO_PARA_REFACTOR_UI_UX"
    IMPLEMENTADO_PARA_REVISION = "IMPLEMENTADO_PARA_REVISION"
    RECHAZADO_PARA_REFACTOR = "RECHAZADO_PARA_REFACTOR"
    APROBADO_PARA_DESPLIEGUE = "APROBADO_PARA_DESPLIEGUE"
    INFRAESTRUCTURA_LISTA_PARA_PRODUCCION = "INFRAESTRUCTURA_LISTA_PARA_PRODUCCION"
    BLOQUEADO_POR_CIBERSEGURIDAD = "BLOQUEADO_POR_CIBERSEGURIDAD"
    BLINDADO_APTO_PRODUCCION = "BLINDADO_APTO_PRODUCCION"
    DOCUMENTACION_Y_RAG_LISTOS = "DOCUMENTACION_Y_RAG_LISTOS"
    ESTRATEGIA_CAPTACION_LISTA = "ESTRATEGIA_CAPTACION_LISTA"
    EMBUDO_Y_METRICAS_LISTOS = "EMBUDO_Y_METRICAS_LISTOS"
    LANZAMIENTO_AUTORIZADO = "LANZAMIENTO_AUTORIZADO"
    CICLO_DE_SOFTWARE_COMPLETADO_100 = "CICLO_DE_SOFTWARE_COMPLETADO_100"
    CIRCUIT_BREAKER_HALT = "CIRCUIT_BREAKER_HALT"


class RoutingHeader(BaseModel):
    """Header extracted or emitted by agents to direct graph routing."""

    model_config = ConfigDict(extra="forbid")

    origen: str
    destino_siguiente: str
    estado_entregable: DeliverableStatus
    veredicto: str | None = None
    puntuacion: int | None = None
    culpable_detectado: AgentID | None = None


class StepExecutionRecord(BaseModel):
    """Audit log entry recorded for each agent execution step."""

    model_config = ConfigDict(extra="forbid")

    step_number: int
    agent_id: AgentID
    status: DeliverableStatus
    target_next: str
    artifact_path: str
    timestamp_iso: str
