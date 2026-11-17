"""Antwort des Routendienstes: begrenzte Menge, auch gepackt, keine Weiterleitungen (GHSA-5v4m-v9rj-87mw)."""

from __future__ import annotations

import tracemalloc
import zlib

from aiohttp import web
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.osrm_fahrzeit import rechner as modul
from custom_components.osrm_fahrzeit.rechner import RoutenFehler, route_abfragen

START, ZIEL = (50.0, 8.0), (50.1, 8.1)  # erfundene Werte
ENTPACKT = 64 * 2**20  # Größe der gepackten Bombe nach dem Entpacken, das Tausendfache der Grenze


def _bombe(kodierung: str) -> bytes:
    """Packt ENTPACKT Bytes Nullen stückweise, ohne sie je ganz im Speicher zu halten."""
    stueck = b"0" * 2**20
    if kodierung == "zstd":
        zstd = pytest.importorskip("compression.zstd")
        packer = zstd.ZstdCompressor()
    else:
        packer = zlib.compressobj(9, zlib.DEFLATED, 31 if kodierung == "gzip" else 15)
    return b"".join([packer.compress(stueck) for _ in range(ENTPACKT // len(stueck))] + [packer.flush()])


@pytest.fixture
async def dienst(aiohttp_server):
    aufrufe: list[str] = []

    async def route(request: web.Request) -> web.StreamResponse:
        aufrufe.append(request.path)
        art = request.app["zustand"]["art"]
        if art == "riesig":  # ohne Content-Length, endloses Array
            antwort = web.StreamResponse()
            await antwort.prepare(request)
            await antwort.write(b'{"code": "Ok", "routes": [')
            for _ in range(200):
                await antwort.write(b"0," * 4096)
            return antwort
        if art == "weiter":
            raise web.HTTPFound("http://192.168.178.1/relay/0?turn=on")
        if art == "gepackt":  # wenige KB auf der Leitung, entpackt ENTPACKT Bytes
            zustand = request.app["zustand"]
            return web.Response(
                body=zustand["daten"],
                headers={"Content-Encoding": zustand["kodierung"], "Content-Type": "application/json"},
            )
        return web.json_response({"code": "Ok", "routes": [{"duration": 600, "distance": 9000}]})

    app = web.Application()
    app["zustand"] = {"art": "gut"}
    app.router.add_get("/route/v1/driving/{rest}", route)
    server = await aiohttp_server(app)
    server.aufrufe = aufrufe
    return server


@pytest.mark.usefixtures("socket_enabled")
async def test_uebergrosse_antwort_wird_abgebrochen(hass: HomeAssistant, dienst) -> None:
    dienst.app["zustand"]["art"] = "riesig"
    with pytest.raises(RoutenFehler, match="zu groß"):
        await route_abfragen(async_get_clientsession(hass), f"http://127.0.0.1:{dienst.port}", START, ZIEL)


@pytest.mark.usefixtures("socket_enabled")
@pytest.mark.parametrize("kodierung", ["gzip", "deflate", "zstd"])
async def test_gepackte_bombe_bleibt_klein(hass: HomeAssistant, dienst, kodierung: str) -> None:
    """Die Grenze gilt für die entpackten Daten, und aiohttp (ab 3.13.3) entpackt nur schrittweise."""
    dienst.app["zustand"].update(art="gepackt", kodierung=kodierung, daten=_bombe(kodierung))
    sitzung = async_get_clientsession(hass)
    lief_schon = tracemalloc.is_tracing()
    if not lief_schon:
        tracemalloc.start()
    tracemalloc.reset_peak()
    vorher, _ = tracemalloc.get_traced_memory()
    try:
        with pytest.raises(RoutenFehler, match="zu groß"):
            await route_abfragen(sitzung, f"http://127.0.0.1:{dienst.port}", START, ZIEL)
        _, spitze = tracemalloc.get_traced_memory()
    finally:
        if not lief_schon:
            tracemalloc.stop()
    assert spitze - vorher < 8 * 2**20  # ohne schrittweises Entpacken wären es über 64 MiB


@pytest.mark.usefixtures("socket_enabled")
async def test_weiterleitung_wird_nicht_verfolgt(hass: HomeAssistant, dienst) -> None:
    dienst.app["zustand"]["art"] = "weiter"
    with pytest.raises(RoutenFehler, match="HTTP 302") as fehler:
        await route_abfragen(async_get_clientsession(hass), f"http://127.0.0.1:{dienst.port}", START, ZIEL)
    assert len(dienst.aufrufe) == 1
    assert "192.168" not in str(fehler.value)


@pytest.mark.usefixtures("socket_enabled")
async def test_normale_antwort_unter_der_grenze(hass: HomeAssistant, dienst) -> None:
    assert await route_abfragen(async_get_clientsession(hass), f"http://127.0.0.1:{dienst.port}/", START, ZIEL) == (
        600.0,
        9000.0,
    )
    assert modul.MAX_ANTWORT >= 16384
