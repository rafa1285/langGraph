"""Deterministic tools and free connectors for Agent 00 (CEO).

Provides $0.00 zero-dependency validation, parsing, and notifications
for Micro-SaaS governance, unit economics, and executive communication.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

FORBIDDEN_ZERO_TOUCH_TERMS: list[str] = [
    "contactar con ventas",
    "contact sales",
    "agendar llamada",
    "agendar demo",
    "book a demo",
    "schedule a call",
    "presupuesto a medida",
    "onboarding manual",
    "soporte humano",
]


class CeoArtifactsDict(dict[str, Any]):
    """Artifacts dictionary supporting both canonical names and filepath aliases."""

    _ALIASES: dict[str, str] = {
        "config/business_charter.json": "business_charter",
        "config/release_manifest.json": "release_manifest",
        "config/executive_comms.json": "executive_comms",
    }

    def __getitem__(self, key: str) -> Any:
        return super().__getitem__(self._ALIASES.get(key, key))

    def get(self, key: str, default: Any = None) -> Any:
        return super().get(self._ALIASES.get(key, key), default)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str) and key in self._ALIASES:
            return self._ALIASES[key] in self
        return super().__contains__(key)


def verify_unit_economics_math(charter_dict: dict[str, Any]) -> dict[str, Any]:
    """Audit pricing tiers for Stripe fees, COGS limits, and net margin compliance.

    Verifies that all tiers meet >= 80% net margin after deducting Stripe fees
    (2.9% + $0.30) and COGS, and that human_touchpoints_allowed is False and
    max_ttfv_seconds <= 60.

    Returns:
        dict: {"valid": bool, "tiers_audit": list, "violations": list}
    """
    violations: list[str] = []
    tiers_audit: list[dict[str, Any]] = []

    # 1. Top-level Zero-Touch Governance Checks
    if charter_dict.get("human_touchpoints_allowed") is not False:
        violations.append(
            "Violation: human_touchpoints_allowed must be explicitly False (Zero-Touch Doctrine)."
        )

    ttfv = charter_dict.get("max_ttfv_seconds")
    if ttfv is None or not isinstance(ttfv, (int, float)) or ttfv > 60:
        violations.append(
            f"Violation: max_ttfv_seconds ({ttfv}) exceeds the 60s Zero-Touch limit."
        )

    # 2. Extract and Validate Tiers
    raw_tiers = charter_dict.get("tiers")
    if not isinstance(raw_tiers, list) or not raw_tiers:
        raw_tiers = charter_dict.get("pricing_model", {}).get("tiers", [])

    if not isinstance(raw_tiers, list) or not raw_tiers:
        violations.append("Violation: No pricing tiers found in business charter.")
        return {
            "valid": False,
            "tiers_audit": [],
            "violations": violations,
        }

    for tier in raw_tiers:
        if not isinstance(tier, dict):
            continue

        tier_id = str(tier.get("id") or tier.get("name") or "tier_unknown")
        tier_name = str(tier.get("name") or tier_id)

        try:
            price_usd = float(tier.get("price_usd", 0.0))
        except (ValueError, TypeError):
            price_usd = 0.0

        try:
            max_cogs_usd = float(tier.get("max_cogs_usd", 0.0))
        except (ValueError, TypeError):
            max_cogs_usd = 0.0

        stripe_fee = price_usd * 0.029 + 0.30
        if price_usd > 0:
            net_margin_pct = ((price_usd - stripe_fee - max_cogs_usd) / price_usd) * 100.0
        else:
            net_margin_pct = 0.0

        tier_compliant = True
        if net_margin_pct < 80.0:
            tier_compliant = False
            violations.append(
                f"Tier '{tier_name}' net margin {net_margin_pct:.2f}% is below 80.0% "
                f"(Price: ${price_usd:.2f}, Fee: ${stripe_fee:.2f}, COGS: ${max_cogs_usd:.2f})."
            )

        if tier.get("human_touchpoints_allowed") is True:
            tier_compliant = False
            violations.append(
                f"Tier '{tier_name}' specifies human_touchpoints_allowed=True (forbidden)."
            )

        tier_ttfv = tier.get("max_ttfv_seconds")
        if tier_ttfv is not None and isinstance(tier_ttfv, (int, float)) and tier_ttfv > 60:
            tier_compliant = False
            violations.append(
                f"Tier '{tier_name}' max_ttfv_seconds ({tier_ttfv}) exceeds 60s limit."
            )

        tiers_audit.append(
            {
                "id": tier_id,
                "name": tier_name,
                "price_usd": price_usd,
                "stripe_fee": round(stripe_fee, 4),
                "max_cogs_usd": max_cogs_usd,
                "net_margin_pct": round(net_margin_pct, 2),
                "compliant": tier_compliant,
            }
        )

    return {
        "valid": len(violations) == 0,
        "tiers_audit": tiers_audit,
        "violations": violations,
    }


def auto_fix_tier_margins(charter_dict: dict[str, Any]) -> dict[str, Any]:
    """Auto-adjust max_cogs_usd to guarantee exactly 85% net margin for deficient tiers.

    If any tier falls below the 80% threshold, recalculates and lowers max_cogs_usd so that:
    net_margin_pct = ((price_usd - stripe_fee - max_cogs_usd) / price_usd) * 100 == 85.0%
    """
    fixed: dict[str, Any] = copy.deepcopy(charter_dict)
    fixed["human_touchpoints_allowed"] = False
    fixed["max_ttfv_seconds"] = min(int(fixed.get("max_ttfv_seconds", 60) or 60), 60)

    raw_tiers = fixed.get("tiers")
    if not isinstance(raw_tiers, list):
        pricing_model = fixed.get("pricing_model")
        if isinstance(pricing_model, dict) and isinstance(pricing_model.get("tiers"), list):
            raw_tiers = pricing_model["tiers"]
        else:
            raw_tiers = []

    for tier in raw_tiers:
        if not isinstance(tier, dict):
            continue

        try:
            price_usd = float(tier.get("price_usd", 0.0))
        except (ValueError, TypeError):
            price_usd = 0.0

        try:
            max_cogs_usd = float(tier.get("max_cogs_usd", 0.0))
        except (ValueError, TypeError):
            max_cogs_usd = 0.0

        if price_usd <= 0:
            continue

        stripe_fee = price_usd * 0.029 + 0.30
        net_margin_pct = ((price_usd - stripe_fee - max_cogs_usd) / price_usd) * 100.0

        if net_margin_pct < 80.0:
            # Target 85.0% net margin:
            # 0.85 = (price_usd - stripe_fee - max_cogs_usd) / price_usd
            # max_cogs_usd = 0.15 * price_usd - stripe_fee
            target_cogs = max(0.0, price_usd * 0.15 - stripe_fee)
            tier["max_cogs_usd"] = round(target_cogs, 2)

    return fixed


def scan_zero_touch_compliance(payload_text: str) -> dict[str, Any]:
    """Scan deliverable text for terms violating the 100% Zero-Touch Doctrine.

    Searches case-insensitively for forbidden human-sales or high-touch patterns.

    Returns:
        dict: {"compliant": bool, "detected_forbidden_terms": list}
    """
    if not payload_text:
        return {"compliant": True, "detected_forbidden_terms": []}

    detected: list[str] = []
    for term in FORBIDDEN_ZERO_TOUCH_TERMS:
        words = [re.escape(w) for w in term.split()]
        pattern = r"\b" + r"\s+".join(words) + r"\b"
        if re.search(pattern, payload_text, re.IGNORECASE):
            detected.append(term)

    return {
        "compliant": len(detected) == 0,
        "detected_forbidden_terms": detected,
    }


def _extract_single_json_artifact(text: str, filename: str) -> dict[str, Any] | None:
    """Safely extract and parse a single JSON block associated with a given filepath."""
    marker_pattern = re.compile(
        rf"(?:#|//|--|/\*|<!--)?\s*(?:filepath:\s*)?{re.escape(filename)}",
        re.IGNORECASE,
    )
    match = marker_pattern.search(text)
    if not match:
        return None

    # Search forward from match for the opening brace of JSON
    search_start = match.end()
    brace_index = text.find("{", search_start)
    if brace_index == -1:
        # Fallback: check slightly before marker in case filepath was on second line of fence
        reverse_brace = text.rfind("{", 0, match.start())
        if reverse_brace != -1 and (match.start() - reverse_brace) < 150:
            brace_index = reverse_brace
        else:
            return None

    json_candidate = text[brace_index:]
    decoder = json.JSONDecoder()

    # Attempt 1: Raw decode directly from opening brace
    try:
        obj, _ = decoder.raw_decode(json_candidate)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Attempt 2: Strip inline single-line comments and retry
    cleaned_candidate = re.sub(r"^\s*//.*$", "", json_candidate, flags=re.MULTILINE)
    try:
        obj, _ = decoder.raw_decode(cleaned_candidate)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Attempt 3: Match nearest markdown code block enclosing filepath
    block_pattern = re.compile(
        rf"```(?:json)?\s*[\r\n]+[^\r\n]*{re.escape(filename)}[^\r\n]*[\r\n]+(.*?)```",
        re.DOTALL | re.IGNORECASE,
    )
    m_block = block_pattern.search(text)
    if m_block:
        raw_code = m_block.group(1).strip()
        cleaned_code = re.sub(r"^\s*//.*$", "", raw_code, flags=re.MULTILINE).strip()
        try:
            parsed = json.loads(cleaned_code)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return None


def extract_ceo_artifacts(markdown_text: str) -> dict[str, Any]:
    """Safely extract all 3 CEO JSON artifacts from deliverable text.

    Returns:
        dict: CeoArtifactsDict containing 'business_charter', 'release_manifest',
              and 'executive_comms' (or None if not present).
    """
    charter = _extract_single_json_artifact(markdown_text, "config/business_charter.json")
    manifest = _extract_single_json_artifact(markdown_text, "config/release_manifest.json")
    comms = _extract_single_json_artifact(markdown_text, "config/executive_comms.json")

    artifacts = CeoArtifactsDict()
    artifacts["business_charter"] = charter
    artifacts["release_manifest"] = manifest
    artifacts["executive_comms"] = comms
    return artifacts


def sync_ceo_executive_comms(comms_dict: dict[str, Any]) -> dict[str, Any]:
    """Synchronize executive communications with Notion and Resend via standard library.

    Operates in graceful fallback mode: if environment variables are missing
    or network requests fail, logs informative message and continues without
    raising exceptions.

    Returns:
        dict: {"notion_synced": bool, "email_sent": bool, "status": str}
    """
    if not isinstance(comms_dict, dict):
        return {
            "notion_synced": False,
            "email_sent": False,
            "status": "skipped_or_fallback",
        }

    notion_synced = False
    email_sent = False

    # 1. Notion API Connector (urllib standard library)
    notion_api_key = os.environ.get("NOTION_API_KEY") or getattr(settings, "NOTION_API_KEY", "")
    notion_db_id = os.environ.get("NOTION_CEO_DATABASE_ID") or getattr(
        settings, "NOTION_CEO_DATABASE_ID", ""
    )

    notion_page = comms_dict.get("notion_page")
    if notion_api_key and notion_db_id and isinstance(notion_page, dict):
        title = str(notion_page.get("title") or "CEO Strategic Document")
        summary_callout = str(notion_page.get("summary_callout") or "")
        markdown_body = str(notion_page.get("markdown_body") or "")

        children: list[dict[str, Any]] = []
        if summary_callout:
            children.append(
                {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": summary_callout[:1900]},
                            }
                        ],
                        "icon": {"type": "emoji", "emoji": "📋"},
                    },
                }
            )

        if markdown_body:
            paragraphs = [p.strip() for p in markdown_body.split("\n\n") if p.strip()]
            if not paragraphs:
                paragraphs = [markdown_body.strip()]
            for p in paragraphs:
                while p and len(children) < 95:
                    chunk = p[:1900]
                    children.append(
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [
                                    {
                                        "type": "text",
                                        "text": {"content": chunk},
                                    }
                                ]
                            },
                        }
                    )
                    p = p[1900:]

        notion_payload = {
            "parent": {"database_id": notion_db_id},
            "properties": {
                "title": {
                    "title": [
                        {
                            "type": "text",
                            "text": {"content": title[:1900]},
                        }
                    ]
                }
            },
            "children": children,
        }

        try:
            req_data = json.dumps(notion_payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.notion.com/v1/pages",
                data=req_data,
                headers={
                    "Authorization": f"Bearer {notion_api_key}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                    "User-Agent": "AgentOffice-CEO/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    notion_synced = True
                    logger.info("Notion executive page synced successfully for '%s'", title)
        except Exception as exc:
            logger.info("Notion connector graceful fallback (call skipped or failed): %s", exc)
            notion_synced = False
    else:
        logger.info("Notion connector skipped: credentials not provided in environment.")

    # 2. Resend API Connector (urllib standard library)
    resend_api_key = os.environ.get("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", "")
    founder_email = os.environ.get("FOUNDER_ALERT_EMAIL") or getattr(
        settings, "FOUNDER_ALERT_EMAIL", ""
    )

    email_notif = comms_dict.get("email_notification")
    send_requested = isinstance(email_notif, dict) and bool(email_notif.get("send", False))

    if resend_api_key and founder_email and send_requested and isinstance(email_notif, dict):
        subject = str(email_notif.get("subject") or "AgentOffice CEO Notification")
        body_text = str(email_notif.get("body_text") or "")

        resend_payload = {
            "from": "AgentOffice CEO <onboarding@resend.dev>",
            "to": [founder_email],
            "subject": subject,
            "text": body_text,
        }

        try:
            req_data = json.dumps(resend_payload).encode("utf-8")
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=req_data,
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "AgentOffice-CEO/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 201):
                    email_sent = True
                    logger.info("Resend executive email delivered to '%s'", founder_email)
        except Exception as exc:
            logger.info("Resend connector graceful fallback (call skipped or failed): %s", exc)
            email_sent = False
    else:
        logger.info("Resend connector skipped: credentials not provided or send is False.")

    if notion_synced or email_sent:
        status = "synced"
    else:
        status = "skipped_or_fallback"

    return {
        "notion_synced": notion_synced,
        "email_sent": email_sent,
        "status": status,
    }
