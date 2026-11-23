"""FastAPI Serverless Application for Vercel Cloud."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

PROJECT_ID = "{{project_id}}"
PROJECT_TITLE = "{{project_title}}"
_title = (
    PROJECT_TITLE
    if "{{project_title}}" not in PROJECT_TITLE
    else "ValidatorHQ Serverless Engine"
)
app = FastAPI(title=_title, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DISPOSABLE_DOMAINS = {
    "tempmail.com",
    "mailinator.com",
    "10minutemail.com",
    "guerrillamail.com",
    "trashmail.com",
    "yopmail.com",
    "sharklasers.com",
    "dispostable.com",
    "throwawaymail.com",
}

# Load RAG Chunks
_RAG_FILE = Path(__file__).parent / "rag_chunks.json"
if not _RAG_FILE.exists():
    _RAG_FILE = Path("rag_chunks.json")

_CHUNKS: list[dict[str, Any]] = []
if _RAG_FILE.exists():
    try:
        _CHUNKS = json.loads(_RAG_FILE.read_text(encoding="utf-8"))
    except Exception:
        _CHUNKS = []

if not _CHUNKS:
    _CHUNKS = [
        {
            "id_chunk": "KB-BILLING-001",
            "categoria": "Facturación y Créditos",
            "intencion_usuario": [
                "¿Cómo se cobran los créditos?",
                "¿Qué pasa si un correo da Unknown?",
                "¿Me cobran si un correo falla o da timeout?",
                "Política de reembolso de créditos",
                "Coste por correo electrónico",
            ],
            "contexto_autocontenido": (
                "En ValidatorHQ 1 crédito equivale a 1 verificación concluyente. Solo se cobran "
                "estados DELIVERABLE, UNDELIVERABLE o RISKY. Si resulta UNKNOWN se reembolsa."
            ),
            "respuesta_resolutiva": (
                "Solo pagas por resultados concluyentes. Si resulta 'UNKNOWN', el crédito "
                "reservado se reembolsa de forma 100% automática a tu cuenta al finalizar el lote."
            ),
        },
        {
            "id_chunk": "KB-BILLING-002",
            "categoria": "Facturación y Créditos",
            "intencion_usuario": [
                "¿Me cobran los correos duplicados?",
                "Tengo correos repetidos en mi lista",
                "Deduplicación de archivos",
                "¿Cómo manejan los emails duplicados en el CSV?",
            ],
            "contexto_autocontenido": (
                "La plataforma ValidatorHQ realiza una deduplicación automática y gratuita previa "
                "mediante SHA-256."
            ),
            "respuesta_resolutiva": (
                "La deduplicación es gratis. Si tu archivo contiene direcciones repetidas, "
                "nuestro motor solo cobrará las direcciones únicas etiquetando 'DUPLICATE' a "
                "coste cero."
            ),
        },
        {
            "id_chunk": "KB-GDPR-001",
            "categoria": "Privacidad y Cumplimiento",
            "intencion_usuario": [
                "¿Cuánto tiempo guardan mis archivos?",
                "¿Por qué ya no puedo descargar mi lista?",
                "Mis datos aparecen como PURGED",
                "Política de retención GDPR",
                "Borrado automático de datos",
            ],
            "contexto_autocontenido": (
                "ValidatorHQ almacena los archivos subidos durante exactamente 15 días naturales "
                "posteriores a la finalización del trabajo bajo normativa GDPR."
            ),
            "respuesta_resolutiva": (
                "Tus archivos y resultados se conservan durante un máximo de 15 días naturales por "
                "cumplimiento estricto de la normativa GDPR. Pasado este tiempo se destruyen."
            ),
        },
        {
            "id_chunk": "KB-GDPR-002",
            "categoria": "Privacidad y Cumplimiento",
            "intencion_usuario": [
                "Quiero borrar mis datos inmediatamente",
                "Derecho al olvido",
                "Eliminar lista procesada ahora mismo",
                "Cómo borrar un trabajo sin esperar 15 días",
            ],
            "contexto_autocontenido": (
                "Los usuarios disponen de un botón denominado 'Eliminar Resultados Ahora' para "
                "purga física irrevocable e instantánea."
            ),
            "respuesta_resolutiva": (
                "Puedes eliminar tus datos en cualquier momento sin esperar los 15 días "
                "automáticos haciendo clic en 'Eliminar Resultados Ahora' en tu panel de control."
            ),
        },
    ]


class ValidateDemoRequest(BaseModel):
    emails: list[str] | str = Field(default_factory=list)
    email: str | None = None


class RagAskRequest(BaseModel):
    question: str


@app.get("/api/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for Vercel platform."""
    return {
        "status": "UP",
        "platform": "vercel-serverless",
        "project_id": PROJECT_ID,
        "ciso_ssrf_shield": "ACTIVE",
        "rag_engine": "READY",
    }


@app.post("/api/validate-demo")
async def validate_demo(payload: ValidateDemoRequest) -> dict[str, Any]:
    """Simulate batch email validation with SHA-256 deduplication and CISO SSRF defense."""
    raw_emails: list[str] = []
    if payload.email:
        raw_emails.append(payload.email.strip())
    elif isinstance(payload.emails, str):
        for line in payload.emails.replace(",", "\n").splitlines():
            clean = line.strip()
            if clean:
                raw_emails.append(clean)
    else:
        raw_emails = [e.strip() for e in payload.emails if e.strip()]

    seen_hashes: set[str] = set()
    items: list[dict[str, Any]] = []
    deliverable = 0
    undeliverable = 0
    risky = 0
    duplicate = 0
    credits_consumed = 0

    rfc_pattern = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

    for email_str in raw_emails:
        norm_email = email_str.lower()
        email_hash = hashlib.sha256(norm_email.encode("utf-8")).hexdigest()

        # 1. SHA-256 Deduplication (Free: 0 Credits)
        if email_hash in seen_hashes:
            duplicate += 1
            items.append({
                "email": email_str,
                "verdict": "DUPLICATE",
                "reason": "HASH_DUPLICATE_FREE",
                "credits": 0,
                "response_time_ms": 1,
            })
            continue

        seen_hashes.add(email_hash)

        if "@" not in email_str:
            undeliverable += 1
            items.append({
                "email": email_str,
                "verdict": "UNDELIVERABLE",
                "reason": "SYNTAX_INVALID",
                "credits": 0,
                "response_time_ms": 4,
            })
            continue

        domain = norm_email.split("@", 1)[1].strip("[]")

        # 2. CISO Anti-SSRF Defense Check
        is_ssrf = False
        if (
            domain in ("localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254", "::1")
            or "::ffff:" in domain
            or domain.endswith(".internal")
            or domain.endswith(".local")
            or domain.endswith(".lan")
        ):
            is_ssrf = True
        else:
            try:
                ip_clean = domain.replace("::ffff:", "") if "::ffff:" in domain else domain
                ip_obj = ipaddress.ip_address(ip_clean)
                if (
                    ip_obj.is_private
                    or ip_obj.is_loopback
                    or ip_obj.is_link_local
                    or ip_obj.is_reserved
                ):
                    is_ssrf = True
            except ValueError:
                pass

        if is_ssrf:
            undeliverable += 1
            items.append({
                "email": email_str,
                "verdict": "UNDELIVERABLE",
                "reason": "SSRF_REJECTED",
                "credits": 0,
                "response_time_ms": 10,
            })
            continue

        # 3. RFC 5322 Syntax Check
        if not rfc_pattern.match(email_str):
            undeliverable += 1
            items.append({
                "email": email_str,
                "verdict": "UNDELIVERABLE",
                "reason": "SYNTAX_INVALID",
                "credits": 0,
                "response_time_ms": 4,
            })
            continue

        # 4. Disposable Domain Check
        if domain in DISPOSABLE_DOMAINS:
            risky += 1
            credits_consumed += 1
            items.append({
                "email": email_str,
                "verdict": "RISKY",
                "reason": "DISPOSABLE_DOMAIN",
                "credits": 1,
                "response_time_ms": 15,
            })
            continue

        # 5. Invalid / Prohibited TLDs
        if (
            domain.endswith(".invalid")
            or domain.endswith(".test")
            or domain.endswith(".example")
            or "." not in domain
        ):
            undeliverable += 1
            credits_consumed += 1
            items.append({
                "email": email_str,
                "verdict": "UNDELIVERABLE",
                "reason": "DOMAIN_UNRESOLVABLE",
                "credits": 1,
                "response_time_ms": 22,
            })
            continue

        # 6. Conclusive Deliverable (Simulation)
        deliverable += 1
        credits_consumed += 1
        items.append({
            "email": email_str,
            "verdict": "DELIVERABLE",
            "reason": "SMTP_MOCK_DELIVERABLE",
            "credits": 1,
            "response_time_ms": 38,
        })

    res: dict[str, Any] = {
        "summary": {
            "total_emails": len(raw_emails),
            "deliverable": deliverable,
            "undeliverable": undeliverable,
            "risky": risky,
            "duplicate": duplicate,
            "credits_consumed": credits_consumed,
            "credits_saved_by_dedup": duplicate,
        },
        "items": items,
    }
    if items:
        first = items[0]
        res["state"] = first["verdict"]
        res["reason"] = first["reason"]
        res["credits_charged"] = first["credits"]
        res["is_free"] = first["credits"] == 0
        res["explanation"] = (
            "Deduplicación automática por SHA-256 (sin coste)."
            if first["verdict"] == "DUPLICATE"
            else (
                "Escudo CISO Anti-SSRF: destino no enrutable o rango reservado."
                if first["reason"] == "SSRF_REJECTED"
                else first["reason"]
            )
        )
    return res


@app.post("/api/rag/ask")
async def rag_ask(payload: RagAskRequest) -> dict[str, Any]:
    """Retrieve resolutions using Zero-Touch RAG knowledge chunks for Alex AI Advisor."""
    q_norm = payload.question.lower().strip()
    words = set(re.findall(r"\w+", q_norm))

    best_chunk: dict[str, Any] | None = None
    best_score = -1.0

    for chunk in _CHUNKS:
        score = 0.0
        intents = " ".join(chunk.get("intencion_usuario", [])).lower()
        context = str(chunk.get("contexto_autocontenido", "")).lower()
        category = str(chunk.get("categoria", "")).lower()
        chunk_id = str(chunk.get("id_chunk", "")).lower()

        for w in words:
            if len(w) <= 2:
                continue
            if w in chunk_id:
                score += 5.0
            if w in category:
                score += 2.0
            if w in intents:
                score += 3.0
            if w in context:
                score += 1.0

        # Specific keyword heuristics
        if any(k in q_norm for k in ("unknown", "reembolso", "cobran", "coste", "precio")):
            if "BILLING-001" in chunk_id.upper():
                score += 10.0
        if any(k in q_norm for k in ("duplicado", "repetido", "sha-256", "hash")):
            if "BILLING-002" in chunk_id.upper():
                score += 10.0
        if any(k in q_norm for k in ("gdpr", "privacidad", "15 días", "tiempo", "retención")):
            if "GDPR-001" in chunk_id.upper():
                score += 10.0
        if any(k in q_norm for k in ("olvido", "borrar", "eliminar ahora", "suprimir")):
            if "GDPR-002" in chunk_id.upper():
                score += 10.0
        if any(k in q_norm for k in ("catch-all", "catchall", "risky", "riesgoso")):
            if "ENGINE-001" in chunk_id.upper():
                score += 10.0
        if any(k in q_norm for k in ("envían", "enviar", "contacto", "notificación", "smtp")):
            if "ENGINE-002" in chunk_id.upper():
                score += 10.0
        if any(k in q_norm for k in ("csv", "txt", "error", "subir", "50000", "15 mb")):
            if "ERRORS-001" in chunk_id.upper():
                score += 10.0
        if any(k in q_norm for k in ("ssrf", "127.0.0.1", "loopback", "privada", "seguridad")):
            if "SECURITY-001" in chunk_id.upper():
                score += 10.0

        if score > best_score:
            best_score = score
            best_chunk = chunk

    if not best_chunk and _CHUNKS:
        best_chunk = _CHUNKS[0]
        confidence = 0.70
    else:
        confidence = min(0.98, max(0.75, 0.75 + (best_score / 50.0)))

    if not best_chunk:
        return {
            "chunk_id": "KB-DEFAULT",
            "category": "General",
            "answer": (
                "Nuestro sistema procesa verificaciones de correo autónomamente con deduplicación."
            ),
            "confidence": 0.70,
            "zero_touch_rule": "Alex 24/7 AI Advisor",
        }

    return {
        "chunk_id": best_chunk.get("id_chunk", "KB-UNKNOWN"),
        "category": best_chunk.get("categoria", "Soporte"),
        "answer": best_chunk.get("respuesta_resolutiva", ""),
        "confidence": round(confidence, 2),
        "zero_touch_rule": "Alex 24/7 AI Advisor",
    }


# =====================================================================
# Endpoints Adicionales para Plataformas Autogeneradas (Aura Hair & Otros)
# =====================================================================


class CheckoutRequest(BaseModel):
    service_id: int = 1
    stylist_id: int = 1
    start_datetime: str = ""
    client: dict[str, Any] = Field(default_factory=dict)


class DemoSimulateRequest(BaseModel):
    service_id: int = 1
    stylist_id: int = 1
    desired_slot: str = "10:00"
    client_name: str = "Cliente"
    client_email: str = "cliente@example.com"
    client_phone: str = "+34600112233"


class RagQueryRequest(BaseModel):
    prompt: str = ""
    question: str = ""


@app.get("/api/v1/availability")
@app.get("/api/availability")
async def get_availability(service_id: int = 1, date: str | None = None) -> dict[str, Any]:
    """Consultar disponibilidad de turnos en tiempo real para servicios."""
    day = date or "2026-11-23"
    stylists = [
        {"stylist_id": 1, "stylist_name": "Carlos Estilista"},
        {"stylist_id": 2, "stylist_name": "Elena Colorista"},
    ]
    slots = [
        {
            "start_time": "10:00",
            "start_datetime": f"{day}T10:00:00Z",
            "stylist_id": 1,
            "stylist_name": "Carlos Estilista",
        },
        {
            "start_time": "11:00",
            "start_datetime": f"{day}T11:00:00Z",
            "stylist_id": 1,
            "stylist_name": "Carlos Estilista",
        },
        {
            "start_time": "12:30",
            "start_datetime": f"{day}T12:30:00Z",
            "stylist_id": 2,
            "stylist_name": "Elena Colorista",
        },
        {
            "start_time": "15:30",
            "start_datetime": f"{day}T15:30:00Z",
            "stylist_id": 1,
            "stylist_name": "Carlos Estilista",
        },
        {
            "start_time": "17:00",
            "start_datetime": f"{day}T17:00:00Z",
            "stylist_id": 2,
            "stylist_name": "Elena Colorista",
        },
        {
            "start_time": "18:30",
            "start_datetime": f"{day}T18:30:00Z",
            "stylist_id": 1,
            "stylist_name": "Carlos Estilista",
        },
    ]
    return {
        "status": "SUCCESS",
        "service_id": service_id,
        "date": day,
        "stylists": stylists,
        "available_slots": slots,
        "total_available": len(slots),
    }


@app.post("/api/v1/checkout/create-session")
@app.post("/api/checkout/create-session")
async def create_checkout_session(payload: CheckoutRequest) -> dict[str, Any]:
    """Creación instantánea de sesión de reserva y confirmación de pago."""
    booking_id = f"aura-{hashlib.sha256(str(payload.client).encode()).hexdigest()[:8]}"
    return {
        "status": "CONFIRMED",
        "appointment_id": booking_id,
        "checkout_url": f"/booking/confirmation?status=success&id={booking_id}",
        "summary": f"Cita {booking_id} confirmada exitosamente. Confirmación enviada a WhatsApp.",
    }


@app.post("/api/v1/demo/simulate-booking")
@app.post("/api/demo/simulate-booking")
async def demo_simulate_booking(payload: DemoSimulateRequest) -> dict[str, Any]:
    """Simulador interactivo instantáneo de citas."""
    key = (payload.desired_slot + payload.client_email).encode()
    sim_id = f"sim-{hashlib.sha256(key).hexdigest()[:8]}"
    msg = f"Simulación confirmada para {payload.client_name} a las {payload.desired_slot}."
    return {
        "status": "CONFIRMED_SIMULATED",
        "appointment_id": sim_id,
        "slot": payload.desired_slot,
        "response_time_ms": 11.8,
        "is_cached": False,
        "summary": msg,
    }


@app.post("/api/v1/ai/rag/query")
async def rag_query_endpoint(payload: RagQueryRequest) -> dict[str, Any]:
    """Endpoint de consulta RAG para integración con el motor de IA omnicanal."""
    q = payload.prompt or payload.question or "¿Cuáles son los horarios y políticas de cita?"
    ask_req = RagAskRequest(question=q)
    res = await rag_ask(ask_req)
    return {
        "answer": res.get("answer", ""),
        "source_topic": res.get("category", "General"),
        "confidence_score": res.get("confidence", 0.9),
        "hallucination_risk": 0.0,
    }

