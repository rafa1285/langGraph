"""Unit tests for Phase 2 services: prompt loader, output parser, and workspace writer."""

from pathlib import Path

import pytest

from app.schemas.routing import AgentID, DeliverableStatus
from app.services.output_parser import AgentOutputParser
from app.services.prompt_loader import AGENT_PROMPT_MAP, PromptLoader
from app.services.workspace_writer import WorkspaceWriter


@pytest.mark.asyncio
async def test_prompt_loader_ensure_and_load(tmp_path: Path) -> None:
    """Test that PromptLoader creates missing prompt files and loads them."""
    loader = PromptLoader(prompts_dir=tmp_path)
    loader.ensure_prompt_files_exist()

    # All 10 files must exist
    for _agent_id, filename in AGENT_PROMPT_MAP.items():
        assert (tmp_path / filename).exists()

    # Load prompt for PM
    prompt_pm = await loader.load_prompt(AgentID.AGENTE_01_PM)
    assert "Agente 01: Product Manager" in prompt_pm
    assert "RECORDATORIO DE CONTRATO OBLIGATORIO DE CABECERA YAML" in prompt_pm
    assert 'origen: "agente_01_pm"' in prompt_pm
    assert 'destino_siguiente: "agente_02_architect"' in prompt_pm

    # Check that in-memory cache works
    cached_prompt = await loader.load_prompt(AgentID.AGENTE_01_PM)
    assert cached_prompt is prompt_pm

    # Load prompt for CISO
    prompt_ciso = await loader.load_prompt(AgentID.AGENTE_10_CISO)
    assert "Agente 10: Chief Information Security Officer" in prompt_ciso
    assert 'origen: "agente_10_ciso"' in prompt_ciso


def test_output_parser_clean_yaml_extraction() -> None:
    """Test extracting clean triple-dash YAML headers."""
    raw_output = """---
origen: "agente_01_pm"
destino_siguiente: "agente_02_architect"
estado_entregable: "PRE_SDD_LISTO"
veredicto: "APROBADO"
puntuacion: 100
culpable_detectado: null
---

# Documento Pre-SDD
Contenido del documento técnico aquí...
"""
    header = AgentOutputParser.parse_routing_header(AgentID.AGENTE_01_PM, raw_output)
    assert header.origen == "agente_01_pm"
    assert header.destino_siguiente == "agente_02_architect"
    assert header.estado_entregable == DeliverableStatus.PRE_SDD_LISTO
    assert header.veredicto == "APROBADO"
    assert header.puntuacion == 100
    assert header.culpable_detectado is None


def test_output_parser_markdown_fence_and_key_normalization() -> None:
    """Test parsing YAML inside markdown fences with accents and unusual key casings."""
    raw_output = """```yaml
Origen: "agente_03_laravel"
Destino Siguiente: "agente_05_qa_php"
Estado Entregable: "IMPLEMENTADO_PARA_REVISION"
Veredicto: "IMPLEMENTADO"
Puntuación: 90
Culpable Detectado: null
```

## Código implementado
Lógica de controladores y migraciones en PHP.
"""
    header = AgentOutputParser.parse_routing_header(AgentID.AGENTE_03_LARAVEL, raw_output)
    assert header.origen == "agente_03_laravel"
    assert header.destino_siguiente == "agente_05_qa_php"
    assert header.estado_entregable == DeliverableStatus.IMPLEMENTADO_PARA_REVISION
    assert header.veredicto == "IMPLEMENTADO"
    assert header.puntuacion == 90
    assert header.culpable_detectado is None


def test_output_parser_fallback_on_missing_yaml() -> None:
    """Test deterministic immortal fallback when the model produces no YAML header."""
    raw_pm = "He preparado el siguiente Pre-SDD con todas las historias de usuario necesarias."
    header_pm = AgentOutputParser.parse_routing_header(AgentID.AGENTE_01_PM, raw_pm)
    assert header_pm.origen == "agente_01_pm"
    assert header_pm.destino_siguiente == "agente_02_architect"
    assert header_pm.estado_entregable == DeliverableStatus.PRE_SDD_LISTO

    # QA PHP rejected
    raw_qa_php_rejected = "El código ha sido RECHAZADO debido a fallos en pruebas unitarias."
    header_qa_rej = AgentOutputParser.parse_routing_header(
        AgentID.AGENTE_05_QA_PHP,
        raw_qa_php_rejected,
    )
    assert header_qa_rej.estado_entregable == DeliverableStatus.RECHAZADO_PARA_REFACTOR
    assert header_qa_rej.destino_siguiente == "agente_03_laravel"

    # QA PHP approved
    raw_qa_php_app = "Todo el código está APROBADO con cobertura al 100%."
    header_qa_app = AgentOutputParser.parse_routing_header(
        AgentID.AGENTE_05_QA_PHP,
        raw_qa_php_app,
    )
    assert header_qa_app.estado_entregable == DeliverableStatus.APROBADO_PARA_DESPLIEGUE
    assert header_qa_app.destino_siguiente == "qa_sync_barrier"

    # QA Python rejected
    raw_qa_py_rejected = "RECHAZADO: Faltan anotaciones de tipos en los endpoints."
    header_qa_py_rej = AgentOutputParser.parse_routing_header(
        AgentID.AGENTE_06_QA_PYTHON,
        raw_qa_py_rejected,
    )
    assert header_qa_py_rej.estado_entregable == DeliverableStatus.RECHAZADO_PARA_REFACTOR
    assert header_qa_py_rej.destino_siguiente == "agente_04_fastapi"

    # DevOps
    raw_devops = "Infraestructura Docker generada con éxito."
    header_devops = AgentOutputParser.parse_routing_header(AgentID.AGENTE_07_DEVOPS, raw_devops)
    status_devops = DeliverableStatus.INFRAESTRUCTURA_LISTA_PARA_PRODUCCION
    assert header_devops.estado_entregable == status_devops
    assert header_devops.destino_siguiente == "agente_10_ciso"


def test_output_parser_fallback_on_malformed_yaml() -> None:
    """Test that malformed/corrupted YAML triggers deterministic fallback without raising errors."""
    corrupted_yaml = """---
origen: [broken :::: yaml
destino_siguiente:
---
Cuerpo del texto sin formato estructurado.
"""
    header = AgentOutputParser.parse_routing_header(AgentID.AGENTE_08_DOCS, corrupted_yaml)
    assert header.origen == "agente_08_docs"
    assert header.destino_siguiente == "agente_09_growth"
    assert header.estado_entregable == DeliverableStatus.DOCUMENTACION_Y_RAG_LISTOS


def test_ciso_culprit_detection_in_security_blocks() -> None:
    """Test CISO security blockage culprit identification across PHP, Python, and DevOps."""
    # 1. Culprit Laravel / PHP
    raw_ciso_php = """---
origen: "agente_10_ciso"
destino_siguiente: "Agente 03 (Laravel)"
estado_entregable: "BLOQUEADO_POR_CIBERSEGURIDAD"
veredicto: "BLOQUEADO"
puntuacion: 20
culpable_detectado: null
---
Se han encontrado inyecciones SQL en los controladores de PHP Laravel.
"""
    header_php = AgentOutputParser.parse_routing_header(AgentID.AGENTE_10_CISO, raw_ciso_php)
    assert header_php.estado_entregable == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
    assert header_php.culpable_detectado == AgentID.AGENTE_03_LARAVEL

    # 2. Culprit FastAPI / Python
    raw_ciso_python = """---
origen: "agente_10_ciso"
destino_siguiente: "Agente 04 - FastAPI"
estado_entregable: "BLOQUEADO_POR_CIBERSEGURIDAD"
veredicto: "BLOQUEADO"
puntuacion: 25
---
Fallo crítico de deserialización en Python FastAPI.
"""
    header_py = AgentOutputParser.parse_routing_header(AgentID.AGENTE_10_CISO, raw_ciso_python)
    assert header_py.estado_entregable == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
    assert header_py.culpable_detectado == AgentID.AGENTE_04_FASTAPI

    # 3. Culprit DevOps / Docker
    raw_ciso_devops = """---
origen: "agente_10_ciso"
destino_siguiente: "DevOps Docker"
estado_entregable: "BLOQUEADO_POR_CIBERSEGURIDAD"
veredicto: "BLOQUEADO"
puntuacion: 10
---
Contenedores corriendo como root sin aislamiento de red.
"""
    header_devops = AgentOutputParser.parse_routing_header(AgentID.AGENTE_10_CISO, raw_ciso_devops)
    assert header_devops.estado_entregable == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
    assert header_devops.culpable_detectado == AgentID.AGENTE_07_DEVOPS

    # 4. Safe default to DevOps when unmentioned
    raw_ciso_generic = """---
origen: "agente_10_ciso"
destino_siguiente: "Indeterminado"
estado_entregable: "BLOQUEADO_POR_CIBERSEGURIDAD"
veredicto: "BLOQUEADO"
---
Vulnerabilidad general.
"""
    header_generic = AgentOutputParser.parse_routing_header(
        AgentID.AGENTE_10_CISO,
        raw_ciso_generic,
    )
    assert header_generic.culpable_detectado == AgentID.AGENTE_07_DEVOPS

    # 5. Blindado (No blockage)
    raw_ciso_approved = """---
origen: "agente_10_ciso"
destino_siguiente: "agente_08_docs"
estado_entregable: "BLINDADO_APTO_PRODUCCION"
veredicto: "BLINDADO"
puntuacion: 98
---
Auditoría limpia y blindada.
"""
    header_ok = AgentOutputParser.parse_routing_header(AgentID.AGENTE_10_CISO, raw_ciso_approved)
    assert header_ok.estado_entregable == DeliverableStatus.BLINDADO_APTO_PRODUCCION
    assert header_ok.culpable_detectado is None


def test_detect_required_stacks_in_sdd() -> None:
    """Test detection of PHP and Python stack requirements from the Architect SDD."""
    # Case 1: Both stacks required
    sdd_both = """# Software Design Document
## 5. Reparto de tareas
### 5.1 Backend PHP (Laravel)
- Modelos de base de datos relacionales y autenticación OAuth2.
### 5.2 Backend Python (FastAPI)
- Pipelines de embeddings e integración con Gemini LLM.
"""
    assert AgentOutputParser.detect_required_stacks(sdd_both) == (True, True)

    # Case 2: Only Python required (PHP is N/A)
    sdd_only_python = """# SDD
## 5. Reparto de tareas
- Backend PHP / Laravel: N/A
- Backend Python / FastAPI: Implementar la API completa en FastAPI.
"""
    assert AgentOutputParser.detect_required_stacks(sdd_only_python) == (False, True)

    # Case 3: Only PHP required (Python is No aplica)
    sdd_only_php = """# SDD
## 5. Reparto de tareas
- Tareas Backend PHP (Laravel): Sistema de facturación y CRM completo.
- Tareas Backend Python (FastAPI): No aplica
"""
    assert AgentOutputParser.detect_required_stacks(sdd_only_php) == (True, False)

    # Case 4: Ambiguity safeguard (both marked N/A -> forces (True, True))
    sdd_ambiguous = """# SDD
## 5. Reparto de tareas
- Backend PHP: Ninguna
- Backend Python: Ninguna
"""
    assert AgentOutputParser.detect_required_stacks(sdd_ambiguous) == (True, True)


@pytest.mark.asyncio
async def test_workspace_writer_save_deliverable(tmp_path: Path) -> None:
    """Test asynchronous writing of deliverable files into workspaces."""
    writer = WorkspaceWriter(base_dir=tmp_path)
    content = "# Entregable Agente 01\n\nEspecificación de requisitos."

    rel_path = await writer.save_deliverable(
        project_id="test_proj_42",
        step_number=1,
        agent_id=AgentID.AGENTE_01_PM,
        content=content,
    )

    # Verify return format
    assert "01_agente_01_pm.md" in rel_path
    assert not Path(rel_path).is_absolute()

    # Verify physical file on disk
    expected_file = tmp_path / "test_proj_42" / "01_agente_01_pm.md"
    assert expected_file.exists()
    assert expected_file.read_text(encoding="utf-8") == content
