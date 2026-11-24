"""Beim Entfernen des Eintrags bleibt keine Position in .storage zurück (#9)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.osrm_fahrzeit import rechner as modul
from custom_components.osrm_fahrzeit.const import DOMAIN


async def test_entfernen_loescht_die_gespeicherte_position(hass: HomeAssistant, hass_storage: dict[str, Any]) -> None:
    eintrag = MockConfigEntry(
        domain=DOMAIN, title="Fahrzeit", data={"tracker": "person.a", "ziel": "zone.home", "server": "https://osrm.example/"}
    )
    eintrag.add_to_hass(hass)
    hass.states.async_set("zone.home", "0", {"latitude": 50.1, "longitude": 8.1})  # erfundene Werte
    hass.states.async_set("person.a", "not_home", {"latitude": 50.0, "longitude": 8.0})
    schluessel = f"{DOMAIN}.{eintrag.entry_id}"

    with patch.object(modul, "route_abfragen", AsyncMock(return_value=(600.0, 9000.0))):
        assert await hass.config_entries.async_setup(eintrag.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=5))
        await hass.async_block_till_done()
        assert hass_storage[schluessel]["data"]["la"] == 50.0  # die Position liegt wirklich im Speicher

        # Neue Abfrage: verzögertes Speichern steht noch aus, wenn der Eintrag entfernt wird.
        await eintrag.runtime_data.async_berechnen(erzwingen=True)
        await hass.config_entries.async_remove(eintrag.entry_id)
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()

    assert schluessel not in hass_storage


async def test_spaete_antwort_nach_dem_entfernen_schreibt_nichts(hass: HomeAssistant, hass_storage: dict[str, Any]) -> None:
    """#15: Eine Abfrage, deren Antwort erst nach dem Entfernen kommt, legt die Position nicht wieder ab."""
    import asyncio

    eintrag = MockConfigEntry(
        domain=DOMAIN, title="Fahrzeit", data={"tracker": "person.a", "ziel": "zone.home", "server": "https://osrm.example/"}
    )
    eintrag.add_to_hass(hass)
    hass.states.async_set("zone.home", "0", {"latitude": 50.1, "longitude": 8.1})  # erfundene Werte
    hass.states.async_set("person.a", "not_home", {"latitude": 50.0, "longitude": 8.0})
    schluessel = f"{DOMAIN}.{eintrag.entry_id}"
    freigabe = asyncio.Event()
    gefragt = asyncio.Event()

    async def langsam(*_: Any) -> tuple[float, float]:
        gefragt.set()
        try:
            await freigabe.wait()
        except asyncio.CancelledError:
            # Wie ein Routendienst, der trotz Abbruch noch antwortet: erst nach dem Entfernen weiter.
            await freigabe.wait()
        return 600.0, 9000.0

    with patch.object(modul, "route_abfragen", side_effect=langsam):
        assert await hass.config_entries.async_setup(eintrag.entry_id)
        await asyncio.wait_for(gefragt.wait(), 5)  # die Abfrage beim Start hängt
        entfernen = hass.async_create_task(hass.config_entries.async_remove(eintrag.entry_id))
        await asyncio.sleep(0.05)
        freigabe.set()
        await entfernen
        await hass.async_block_till_done()
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=30))
        await hass.async_block_till_done()

    assert schluessel not in hass_storage
