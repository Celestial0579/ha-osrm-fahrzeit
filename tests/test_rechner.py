"""Abfrage, Bremse, Hochrechnung und Schranke ohne öffentlichen Routendienst."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

from aiohttp import web
from pytest_homeassistant_custom_component.common import MockConfigEntry
import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.osrm_fahrzeit import rechner as modul
from custom_components.osrm_fahrzeit.const import DOMAIN
from custom_components.osrm_fahrzeit.rechner import FahrzeitRechner, RoutenFehler, route_abfragen

START, ZIEL = (52.516275, 13.377704), (52.366667, 13.503333)  # Brandenburger Tor, Flughafen BER


@pytest.fixture
async def dienst(aiohttp_server):
    antworten = {
        "gut": web.json_response({"code": "Ok", "routes": [{"duration": 600, "distance": 9000}]}),
        "liste": web.json_response([]),
        "null": web.json_response(None),
        "ohne": web.json_response({"code": "Ok", "routes": [{}]}),
        "noroute": web.json_response({"code": "NoRoute", "routes": []}),
    }

    async def route(request: web.Request) -> web.StreamResponse:
        art = request.app["zustand"]["art"]
        if art == "schleife":
            raise web.HTTPFound(location=str(request.rel_url))
        if art == "429":
            return web.Response(status=429)
        return antworten[art]

    app = web.Application()
    app["zustand"] = {"art": "gut"}
    app.router.add_get("/route/v1/driving/{rest}", route)
    return await aiohttp_server(app)


@pytest.mark.usefixtures("socket_enabled")
async def test_route_abfragen(hass: HomeAssistant, dienst) -> None:
    sitzung, server = async_get_clientsession(hass), f"http://127.0.0.1:{dienst.port}"
    assert await route_abfragen(sitzung, server, START, ZIEL) == (600.0, 9000.0)
    for art, text in (("liste", "unerwartete Antwort"), ("null", "unerwartete Antwort"), ("ohne", "unerwartete Antwort"),
                      ("noroute", "NoRoute"), ("429", "HTTP 429"), ("schleife", "TooManyRedirects")):
        dienst.app["zustand"]["art"] = art
        with pytest.raises(RoutenFehler) as fehler:
            await route_abfragen(sitzung, server, START, ZIEL)
        assert text in str(fehler.value)
        assert "52.51" not in str(fehler.value) and "13.37" not in str(fehler.value)  # kein Standort


def _eintrag(hass: HomeAssistant, server: str = "https://nutzer:geheim@osrm.example/") -> MockConfigEntry:
    eintrag = MockConfigEntry(domain=DOMAIN, title="Fahrzeit", data={"tracker": "person.a", "ziel": "zone.home", "server": server})
    eintrag.add_to_hass(hass)
    hass.states.async_set("zone.home", "0", {"latitude": ZIEL[0], "longitude": ZIEL[1]})
    hass.states.async_set("person.a", "not_home", {"latitude": START[0], "longitude": START[1]})
    return eintrag


async def test_fehler_setzt_die_bremse(hass: HomeAssistant) -> None:
    rechner = FahrzeitRechner(hass, _eintrag(hass))
    with patch.object(modul, "route_abfragen", AsyncMock(side_effect=RoutenFehler("unerwartete Antwort"))) as abfrage:
        await rechner.async_berechnen()
        await rechner.async_berechnen()
    assert abfrage.await_count == 1  # danach Pause, keine zweite Abfrage
    assert rechner.gestoert and rechner.anfragen_heute == 1
    assert rechner.quelle == "Luftlinie"


async def test_hochrechnung_zwischen_zwei_abfragen(hass: HomeAssistant) -> None:
    rechner = FahrzeitRechner(hass, _eintrag(hass))
    with patch.object(modul, "route_abfragen", AsyncMock(return_value=(1500.0, 20000.0))):
        await rechner.async_berechnen()
    assert (rechner.minuten, rechner.km, rechner.quelle) == (25.0, 20.0, "OpenStreetMap")
    # 2 km weiter (Bewegung), aber Mindestabstand: keine Abfrage, sondern hochgerechnet.
    hass.states.async_set("person.a", "not_home", {"latitude": START[0] + 0.02, "longitude": START[1]})
    with patch.object(modul, "route_abfragen", AsyncMock()) as abfrage:
        await rechner.async_berechnen()
    abfrage.assert_not_awaited()
    assert rechner.quelle == "OpenStreetMap (hochgerechnet)"
    assert rechner.minuten > 15  # nicht die rohe Luftlinie bei 120 km/h
    await rechner.async_stop()


async def test_am_ziel_wird_nicht_abgefragt(hass: HomeAssistant) -> None:
    rechner = FahrzeitRechner(hass, _eintrag(hass))
    hass.states.async_set("person.a", "home", {"latitude": ZIEL[0], "longitude": ZIEL[1]})
    with patch.object(modul, "route_abfragen", AsyncMock()) as abfrage:
        await rechner.async_berechnen()
    abfrage.assert_not_awaited()
    assert (rechner.minuten, rechner.quelle) == (0.0, "am Ziel")


async def test_schranke_je_server(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modul, "MIN_ABSTAND_SERVER", 0.2)
    zeiten: list[float] = []

    async def abfrage() -> None:
        async with modul.schranke(hass, "https://osrm.example/"):
            zeiten.append(time.monotonic())

    await asyncio.gather(abfrage(), abfrage(), abfrage())
    assert all(b - a >= 0.19 for a, b in zip(zeiten, zeiten[1:]))
    assert modul.schranke(hass, "https://osrm.example") is modul.schranke(hass, "https://osrm.example/")


async def test_geraet_ohne_zugangsdaten(hass: HomeAssistant) -> None:
    eintrag = _eintrag(hass)
    with patch.object(modul, "route_abfragen", AsyncMock(return_value=(60.0, 1000.0))):
        assert await hass.config_entries.async_setup(eintrag.entry_id)
        await hass.async_block_till_done()
    geraet = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, eintrag.entry_id), eintrag.entry_id)
    assert geraet.model == "osrm.example"
    assert await hass.config_entries.async_unload(eintrag.entry_id)


def test_user_agent_nennt_die_fassung() -> None:
    assert f"/{modul.FASSUNG} " in modul.USER_AGENT
