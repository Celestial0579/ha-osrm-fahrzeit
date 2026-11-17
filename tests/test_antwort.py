"""Antwort des Routendienstes: begrenzte Menge, keine Weiterleitungen (GHSA-5v4m-v9rj-87mw)."""

from __future__ import annotations

from aiohttp import web
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.osrm_fahrzeit import rechner as modul
from custom_components.osrm_fahrzeit.rechner import RoutenFehler, route_abfragen

START, ZIEL = (50.0, 8.0), (50.1, 8.1)  # erfundene Werte


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
