"""Automated UI Layout Collision and Geometric Bounding Box tests with Playwright."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Generator

import pytest
import uvicorn

from app.main import create_app

playwright_module = pytest.importorskip(
    "playwright.sync_api",
    reason="Playwright is required for UI layout collision tests.",
)
from playwright.sync_api import Browser, sync_playwright  # noqa: E402


def _find_free_port() -> int:
    """Locate an available ephemeral localhost TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def local_server_url() -> Generator[str, None, None]:
    """Launch a lightweight ephemeral Uvicorn server hosting the full FastAPI app and static UI."""
    port = _find_free_port()
    app = create_app()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait up to 5 seconds for server readiness
    url = f"http://127.0.0.1:{port}"
    start_time = time.time()
    ready = False
    while time.time() - start_time < 5.0:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                ready = True
                break
        except OSError:
            time.sleep(0.05)

    if not ready:
        pytest.fail("Failed to spin up local FastAPI test server for Playwright layout validation.")

    yield url
    server.should_exit = True
    thread.join(timeout=3.0)


@pytest.fixture(scope="module")
def browser_instance() -> Generator[Browser, None, None]:
    """Provide a headless Chromium instance for geometric bounding-box evaluation."""
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"Chromium binary not available on this host: {exc}")
        yield browser
        browser.close()


@pytest.mark.parametrize("width,height", [
    (1366, 768),   # Typical laptop / scaled display where bug manifested
    (1440, 900),   # Medium widescreen monitor
    (1920, 1080),  # Full HD standard desktop
])
def test_dashboard_top_toolbar_no_collision_with_right_ops_panel(
    local_server_url: str,
    browser_instance: Browser,
    width: int,
    height: int,
) -> None:
    """Confirm Right(Resume/Project Controls) <= Left(Right Ops Panel) on /dashboard."""
    page = browser_instance.new_page(viewport={"width": width, "height": height})
    try:
        page.goto(f"{local_server_url}/dashboard", wait_until="domcontentloaded")
        page.wait_for_selector("#btn-resume", state="visible", timeout=6000)
        page.wait_for_selector("#right-ops-panel", state="visible", timeout=6000)

        # Retrieve bounding client rectangles
        rect_resume = page.eval_on_selector(
            "#btn-resume", "el => el.getBoundingClientRect()"
        )
        rect_project_sel = page.eval_on_selector(
            "#project-selector", "el => el.getBoundingClientRect()"
        )
        rect_ops = page.eval_on_selector(
            "#right-ops-panel", "el => el.getBoundingClientRect()"
        )

        resume_right = float(rect_resume["right"])
        project_sel_right = float(rect_project_sel["right"])
        ops_left = float(rect_ops["left"])

        # Strict mathematical assertion: Right(Control) <= Left(Ops Panel)
        tolerance_px = 1.0  # sub-pixel rendering tolerance
        overlap_resume = resume_right - ops_left
        assert resume_right <= ops_left + tolerance_px, (
            f"Colisión espacial detectada en viewport {width}x{height}: "
            f"Botón '#btn-resume' (right={resume_right:.1f}px) invade '#right-ops-panel' "
            f"(left={ops_left:.1f}px) con solapamiento de {overlap_resume:.1f}px!"
        )

        overlap_project_sel = project_sel_right - ops_left
        assert project_sel_right <= ops_left + tolerance_px, (
            f"Colisión espacial detectada en viewport {width}x{height}: "
            f"Contenedor '#project-selector' (right={project_sel_right:.1f}px) invade "
            f"'#right-ops-panel' (left={ops_left:.1f}px) por {overlap_project_sel:.1f}px!"
        )
    finally:
        page.close()


@pytest.mark.parametrize("width,height", [
    (1366, 768),
    (1920, 1080),
])
def test_side_panel_layer_hierarchy_and_hud_containment(
    local_server_url: str,
    browser_instance: Browser,
    width: int,
    height: int,
) -> None:
    """Confirm side-panel has z-index strictly superior to toolbars and controls don't clip."""
    page = browser_instance.new_page(viewport={"width": width, "height": height})
    try:
        # Test on /dashboard
        page.goto(f"{local_server_url}/dashboard", wait_until="domcontentloaded")
        page.wait_for_selector("#btn-resume", state="visible", timeout=6000)
        page.wait_for_selector("#side-panel", state="attached", timeout=6000)

        # 1. Verify CSS z-index layer hierarchy on dashboard
        side_panel_z = page.eval_on_selector(
            "#side-panel",
            "el => parseInt(window.getComputedStyle(el).zIndex, 10) || 0",
        )
        toolbar_z = page.eval_on_selector(
            "#office-sub-toolbar",
            "el => parseInt(window.getComputedStyle(el).zIndex, 10) || 0",
        )
        assert side_panel_z >= 1000, f"Expected #side-panel z-index >= 1000, got {side_panel_z}"
        assert side_panel_z > toolbar_z, (
            f"Jerarquía de capas inválida en /dashboard: #side-panel z-index ({side_panel_z}) "
            f"debe ser estrictamente superior a #office-sub-toolbar ({toolbar_z})"
        )

        # 2. Open side panel and verify controls in viewport don't push outside body boundaries
        page.evaluate("""() => {
            const sp = document.getElementById('side-panel');
            if (sp) {
                sp.classList.remove('hidden');
                sp.classList.add('open');
                document.body.classList.add('side-panel-open');
            }
        }""")

        rect_resume = page.eval_on_selector("#btn-resume", "el => el.getBoundingClientRect()")
        body_width = page.eval_on_selector("body", "el => el.clientWidth")

        assert float(rect_resume["right"]) <= float(body_width) + 2.0, (
            f"El botón '#btn-resume' excede el ancho de la ventana: "
            f"{rect_resume['right']:.1f}px > {body_width:.1f}px"
        )

        # Test on /office (index.html with #top-hud-bar)
        page.goto(f"{local_server_url}/office", wait_until="domcontentloaded")
        page.wait_for_selector("#top-hud-bar", state="visible", timeout=6000)
        page.wait_for_selector("#side-panel", state="attached", timeout=6000)

        office_side_z = page.eval_on_selector(
            "#side-panel",
            "el => parseInt(window.getComputedStyle(el).zIndex, 10) || 0",
        )
        hud_z = page.eval_on_selector(
            "#top-hud-bar",
            "el => parseInt(window.getComputedStyle(el).zIndex, 10) || 0",
        )
        assert office_side_z >= 1000, f"Expected #side-panel z-index >= 1000, got {office_side_z}"
        assert office_side_z > hud_z, (
            f"Jerarquía de capas inválida en /office: #side-panel z-index ({office_side_z}) "
            f"debe ser estrictamente superior a #top-hud-bar ({hud_z})"
        )
    finally:
        page.close()
