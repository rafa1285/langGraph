"""Output parsing service for extracting routing headers and analyzing architectural SDD."""

import re
import unicodedata

import yaml

from app.schemas.routing import AgentID, DeliverableStatus, RoutingHeader


class AgentOutputParser:
    """Robust parser for agent markdown outputs, routing headers, and stack detection."""

    @classmethod
    def _normalize_key(cls, key: str) -> str:
        """Normalize YAML keys by lowercasing, removing accents, and replacing spaces/hyphens."""
        normalized = unicodedata.normalize("NFKD", key).encode("ASCII", "ignore").decode("utf-8")
        clean = normalized.lower().strip().replace(" ", "_").replace("-", "_")
        return clean

    @classmethod
    def _resolve_ciso_culprit(cls, target_text: str) -> AgentID:
        """Determine culprit agent ID for CISO security blocks based on target text."""
        lower_target = target_text.lower()
        if any(k in lower_target for k in ("agente 03", "agente_03", "03", "laravel", "php")):
            return AgentID.AGENTE_03_LARAVEL
        if any(k in lower_target for k in ("agente 04", "agente_04", "04", "fastapi", "python")):
            return AgentID.AGENTE_04_FASTAPI
        if any(k in lower_target for k in ("agente 07", "agente_07", "07", "devops", "docker")):
            return AgentID.AGENTE_07_DEVOPS
        return AgentID.AGENTE_07_DEVOPS

    @classmethod
    def _match_deliverable_status(cls, agent_id: AgentID, raw_status: str) -> DeliverableStatus:
        """Resolve deliverable status string or shorthand into a strict DeliverableStatus enum."""
        clean_upper = raw_status.strip().upper().replace(" ", "_").replace("-", "_")

        # 1. Exact match against enum member names or values
        for member in DeliverableStatus:
            if clean_upper == member.value or clean_upper == member.name:
                return member

        # 2. Contextual shorthand mapping by keywords and emitting agent
        if "RECHAZADO" in clean_upper:
            return DeliverableStatus.RECHAZADO_PARA_REFACTOR
        if "BLOQUEADO" in clean_upper:
            return DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
        if "BLINDADO" in clean_upper:
            return DeliverableStatus.BLINDADO_APTO_PRODUCCION
        if "IMPLEMENTADO" in clean_upper:
            return DeliverableStatus.IMPLEMENTADO_PARA_REVISION

        if "APROBADO" in clean_upper:
            match agent_id:
                case AgentID.AGENTE_00_CEO:
                    if any(k in clean_upper for k in ("LANZAMIENTO", "ACTA", "CIERRE", "SIGNOFF")):
                        return DeliverableStatus.LANZAMIENTO_AUTORIZADO
                    return DeliverableStatus.CHARTER_NEGOCIO_LISTO
                case AgentID.AGENTE_01_PM:
                    return DeliverableStatus.PRE_SDD_LISTO
                case AgentID.AGENTE_02_ARCHITECT:
                    return DeliverableStatus.APROBADO_PARA_DESARROLLO
                case AgentID.AGENTE_11_UI_UX:
                    return DeliverableStatus.SISTEMA_DISENO_UI_LISTO
                case AgentID.AGENTE_05_QA_PHP | AgentID.AGENTE_06_QA_PYTHON:
                    return DeliverableStatus.APROBADO_PARA_DESPLIEGUE
                case AgentID.AGENTE_07_DEVOPS:
                    return DeliverableStatus.INFRAESTRUCTURA_LISTA_PARA_PRODUCCION
                case AgentID.AGENTE_10_CISO:
                    return DeliverableStatus.BLINDADO_APTO_PRODUCCION
                case AgentID.AGENTE_08_DOCS:
                    return DeliverableStatus.DOCUMENTACION_Y_RAG_LISTOS
                case AgentID.AGENTE_09_GROWTH:
                    return DeliverableStatus.CICLO_DE_SOFTWARE_COMPLETADO_100
                case AgentID.AGENTE_12_MARKETING:
                    return DeliverableStatus.ESTRATEGIA_CAPTACION_LISTA
                case AgentID.AGENTE_13_SALES_ANALYTICS:
                    return DeliverableStatus.EMBUDO_Y_METRICAS_LISTOS
                case _:
                    return DeliverableStatus.APROBADO_PARA_DESPLIEGUE

        # Default fallback per agent role
        match agent_id:
            case AgentID.AGENTE_00_CEO:
                return DeliverableStatus.CHARTER_NEGOCIO_LISTO
            case AgentID.AGENTE_01_PM:
                return DeliverableStatus.PRE_SDD_LISTO
            case AgentID.AGENTE_02_ARCHITECT:
                return DeliverableStatus.APROBADO_PARA_DESARROLLO
            case AgentID.AGENTE_11_UI_UX:
                return DeliverableStatus.SISTEMA_DISENO_UI_LISTO
            case AgentID.AGENTE_03_LARAVEL | AgentID.AGENTE_04_FASTAPI:
                return DeliverableStatus.IMPLEMENTADO_PARA_REVISION
            case AgentID.AGENTE_05_QA_PHP | AgentID.AGENTE_06_QA_PYTHON:
                return DeliverableStatus.APROBADO_PARA_DESPLIEGUE
            case AgentID.AGENTE_07_DEVOPS:
                return DeliverableStatus.INFRAESTRUCTURA_LISTA_PARA_PRODUCCION
            case AgentID.AGENTE_10_CISO:
                return DeliverableStatus.BLINDADO_APTO_PRODUCCION
            case AgentID.AGENTE_08_DOCS:
                return DeliverableStatus.DOCUMENTACION_Y_RAG_LISTOS
            case AgentID.AGENTE_09_GROWTH:
                return DeliverableStatus.CICLO_DE_SOFTWARE_COMPLETADO_100
            case AgentID.AGENTE_12_MARKETING:
                return DeliverableStatus.ESTRATEGIA_CAPTACION_LISTA
            case AgentID.AGENTE_13_SALES_ANALYTICS:
                return DeliverableStatus.EMBUDO_Y_METRICAS_LISTOS
            case _:
                return DeliverableStatus.CICLO_DE_SOFTWARE_COMPLETADO_100

    @classmethod
    def _build_fallback_header(cls, agent_id: AgentID, raw_output: str) -> RoutingHeader:
        """Deterministic immortal fallback header generated when YAML is missing or malformed."""
        text_upper = raw_output.upper()

        match agent_id:
            case AgentID.AGENTE_00_CEO:
                if any(
                    k in text_upper
                    for k in ("LANZAMIENTO", "ACTA", "CIERRE", "CISO", "SIGNOFF", "AUTORIZADO")
                ):
                    return RoutingHeader(
                        origen=agent_id.value,
                        destino_siguiente=AgentID.END_PIPELINE.value,
                        estado_entregable=DeliverableStatus.LANZAMIENTO_AUTORIZADO,
                        veredicto="APROBADO",
                        puntuacion=100,
                        culpable_detectado=None,
                    )
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.AGENTE_01_PM.value,
                    estado_entregable=DeliverableStatus.CHARTER_NEGOCIO_LISTO,
                    veredicto="APROBADO",
                    puntuacion=100,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_01_PM:
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.AGENTE_02_ARCHITECT.value,
                    estado_entregable=DeliverableStatus.PRE_SDD_LISTO,
                    veredicto="APROBADO",
                    puntuacion=100,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_02_ARCHITECT:
                next_dest = (
                    f"{AgentID.AGENTE_03_LARAVEL.value}, {AgentID.AGENTE_04_FASTAPI.value}"
                )
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=next_dest,
                    estado_entregable=DeliverableStatus.APROBADO_PARA_DESARROLLO,
                    veredicto="APROBADO",
                    puntuacion=100,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_03_LARAVEL:
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.AGENTE_05_QA_PHP.value,
                    estado_entregable=DeliverableStatus.IMPLEMENTADO_PARA_REVISION,
                    veredicto="IMPLEMENTADO",
                    puntuacion=None,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_04_FASTAPI:
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.AGENTE_06_QA_PYTHON.value,
                    estado_entregable=DeliverableStatus.IMPLEMENTADO_PARA_REVISION,
                    veredicto="IMPLEMENTADO",
                    puntuacion=None,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_05_QA_PHP:
                if "RECHAZADO" in text_upper or "FALLIDO" in text_upper:
                    return RoutingHeader(
                        origen=agent_id.value,
                        destino_siguiente=AgentID.AGENTE_03_LARAVEL.value,
                        estado_entregable=DeliverableStatus.RECHAZADO_PARA_REFACTOR,
                        veredicto="RECHAZADO",
                        puntuacion=40,
                        culpable_detectado=None,
                    )
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.QA_SYNC_BARRIER.value,
                    estado_entregable=DeliverableStatus.APROBADO_PARA_DESPLIEGUE,
                    veredicto="APROBADO",
                    puntuacion=95,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_06_QA_PYTHON:
                if "RECHAZADO" in text_upper or "FALLIDO" in text_upper:
                    return RoutingHeader(
                        origen=agent_id.value,
                        destino_siguiente=AgentID.AGENTE_04_FASTAPI.value,
                        estado_entregable=DeliverableStatus.RECHAZADO_PARA_REFACTOR,
                        veredicto="RECHAZADO",
                        puntuacion=40,
                        culpable_detectado=None,
                    )
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.QA_SYNC_BARRIER.value,
                    estado_entregable=DeliverableStatus.APROBADO_PARA_DESPLIEGUE,
                    veredicto="APROBADO",
                    puntuacion=95,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_07_DEVOPS:
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.AGENTE_10_CISO.value,
                    estado_entregable=DeliverableStatus.INFRAESTRUCTURA_LISTA_PARA_PRODUCCION,
                    veredicto="APROBADO",
                    puntuacion=100,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_10_CISO:
                is_blocked = (
                    "BLOQUEADO" in text_upper
                    or "RECHAZADO" in text_upper
                    or "VULNERABILIDAD" in text_upper
                )
                if is_blocked:
                    culprit = cls._resolve_ciso_culprit(raw_output)
                    return RoutingHeader(
                        origen=agent_id.value,
                        destino_siguiente=culprit.value,
                        estado_entregable=DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD,
                        veredicto="BLOQUEADO",
                        puntuacion=30,
                        culpable_detectado=culprit,
                    )
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.AGENTE_08_DOCS.value,
                    estado_entregable=DeliverableStatus.BLINDADO_APTO_PRODUCCION,
                    veredicto="BLINDADO",
                    puntuacion=98,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_08_DOCS:
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.AGENTE_09_GROWTH.value,
                    estado_entregable=DeliverableStatus.DOCUMENTACION_Y_RAG_LISTOS,
                    veredicto="APROBADO",
                    puntuacion=100,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_09_GROWTH:
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.END_PIPELINE.value,
                    estado_entregable=DeliverableStatus.CICLO_DE_SOFTWARE_COMPLETADO_100,
                    veredicto="APROBADO",
                    puntuacion=100,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_11_UI_UX:
                next_dest = (
                    f"{AgentID.AGENTE_03_LARAVEL.value}, {AgentID.AGENTE_04_FASTAPI.value}"
                )
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=next_dest,
                    estado_entregable=DeliverableStatus.SISTEMA_DISENO_UI_LISTO,
                    veredicto="APROBADO",
                    puntuacion=100,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_12_MARKETING:
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.AGENTE_13_SALES_ANALYTICS.value,
                    estado_entregable=DeliverableStatus.ESTRATEGIA_CAPTACION_LISTA,
                    veredicto="APROBADO",
                    puntuacion=100,
                    culpable_detectado=None,
                )
            case AgentID.AGENTE_13_SALES_ANALYTICS:
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.AGENTE_00_CEO.value,
                    estado_entregable=DeliverableStatus.EMBUDO_Y_METRICAS_LISTOS,
                    veredicto="APROBADO",
                    puntuacion=100,
                    culpable_detectado=None,
                )
            case _:
                return RoutingHeader(
                    origen=agent_id.value,
                    destino_siguiente=AgentID.END_PIPELINE.value,
                    estado_entregable=DeliverableStatus.CICLO_DE_SOFTWARE_COMPLETADO_100,
                    veredicto="APROBADO",
                    puntuacion=100,
                    culpable_detectado=None,
                )

    @classmethod
    def parse_routing_header(cls, agent_id: AgentID, raw_output: str) -> RoutingHeader:
        """Parse routing header from raw agent output with deterministic immortal fallback."""
        yaml_content: str | None = None

        # a) Search for first YAML block delimited by `---` or ```yaml
        dash_match = re.search(r"^\s*---\s*\n(.*?)\n---", raw_output, re.DOTALL)
        if dash_match:
            yaml_content = dash_match.group(1)
        else:
            fence_match = re.search(
                r"```(?:yaml|yml)?\s*\n(.*?)\n```",
                raw_output,
                re.DOTALL | re.IGNORECASE,
            )
            if fence_match:
                yaml_content = fence_match.group(1)
            else:
                dot_match = re.search(r"^\s*---\s*\n(.*?)\n\.\.\.", raw_output, re.DOTALL)
                if dot_match:
                    yaml_content = dot_match.group(1)

        if yaml_content is None:
            return cls._build_fallback_header(agent_id, raw_output)

        # b) Parse with yaml.safe_load and normalize keys
        try:
            parsed = yaml.safe_load(yaml_content)
            if not isinstance(parsed, dict):
                return cls._build_fallback_header(agent_id, raw_output)

            normalized_dict: dict[str, object] = {
                cls._normalize_key(str(k)): v for k, v in parsed.items()
            }

            # Map aliases
            origen = str(
                normalized_dict.get("origen")
                or normalized_dict.get("source")
                or normalized_dict.get("agent_id")
                or agent_id.value
            )
            destino_siguiente = str(
                normalized_dict.get("destino_siguiente")
                or normalized_dict.get("destino")
                or normalized_dict.get("next_agent")
                or normalized_dict.get("siguiente_agente")
                or ""
            )
            raw_status = str(
                normalized_dict.get("estado_entregable")
                or normalized_dict.get("estado")
                or normalized_dict.get("status")
                or ""
            )

            estado_entregable = cls._match_deliverable_status(agent_id, raw_status)

            veredicto_raw = normalized_dict.get("veredicto") or normalized_dict.get("verdict")
            veredicto = str(veredicto_raw) if veredicto_raw is not None else None

            puntuacion_raw = normalized_dict.get("puntuacion") or normalized_dict.get("score")
            puntuacion: int | None = None
            if isinstance(puntuacion_raw, (int, float)):
                puntuacion = int(puntuacion_raw)
            elif isinstance(puntuacion_raw, str) and puntuacion_raw.strip().isdigit():
                puntuacion = int(puntuacion_raw.strip())

            culpable_raw = normalized_dict.get("culpable_detectado") or normalized_dict.get(
                "culpable"
            )
            culpable_detectado: AgentID | None = None
            if isinstance(culpable_raw, str) and culpable_raw.strip().lower() not in (
                "null",
                "none",
                "",
                "~",
            ):
                culpable_detectado = cls._resolve_ciso_culprit(culpable_raw)

            # d) For AGENTE_10_CISO when blocked, determine culprit automatically
            # from destino_siguiente
            if (
                agent_id == AgentID.AGENTE_10_CISO
                and estado_entregable == DeliverableStatus.BLOQUEADO_POR_CIBERSEGURIDAD
            ):
                culpable_detectado = cls._resolve_ciso_culprit(destino_siguiente)
                if not destino_siguiente or destino_siguiente.lower() in ("null", "none"):
                    destino_siguiente = culpable_detectado.value

            return RoutingHeader(
                origen=origen,
                destino_siguiente=destino_siguiente,
                estado_entregable=estado_entregable,
                veredicto=veredicto,
                puntuacion=puntuacion,
                culpable_detectado=culpable_detectado,
            )
        except Exception:
            return cls._build_fallback_header(agent_id, raw_output)

    @classmethod
    def detect_required_stacks(cls, sdd_markdown: str) -> tuple[bool, bool]:
        """Analyze Architect SDD (section 5) to return (requiere_php, requiere_python)."""
        sec5_match = re.search(
            r"(?:^#+\s*5[.\s].*?)(?=(?:^#+\s*[6-9]|\Z))",
            sdd_markdown,
            re.DOTALL | re.MULTILINE | re.IGNORECASE,
        )
        search_text = sec5_match.group(0) if sec5_match else sdd_markdown

        negation_regex = re.compile(
            r"\b(n/a|no\s+aplica|ninguna|ninguno|no\s+requiere|sin\s+tareas|none)\b",
            re.IGNORECASE,
        )

        def is_stack_negated(keywords: list[str]) -> bool:
            # 1. Line-by-line inspection
            for line in search_text.splitlines():
                line_lower = line.lower()
                if any(kw in line_lower for kw in keywords):
                    if negation_regex.search(line):
                        return True

            # 2. Block-based inspection (header followed by content)
            for kw in keywords:
                block_pattern = re.compile(
                    rf"(?:^#+[^\n]*\b{kw}\b[^\n]*\n)(.*?)(?=(?:^#+|\Z))",
                    re.DOTALL | re.MULTILINE | re.IGNORECASE,
                )
                for m in block_pattern.finditer(search_text):
                    block_content = m.group(1).strip()
                    lines = [ln.strip() for ln in block_content.splitlines() if ln.strip()]
                    if lines and negation_regex.search(lines[0]):
                        return True
                    if len(block_content) < 80 and negation_regex.search(block_content):
                        return True

            return False

        php_negated = is_stack_negated(["php", "laravel"])
        python_negated = is_stack_negated(["python", "fastapi"])

        requiere_php = not php_negated
        requiere_python = not python_negated

        # Safeguard: if both False due to ambiguity, force (True, True)
        if not requiere_php and not requiere_python:
            return (True, True)

        return (requiere_php, requiere_python)
