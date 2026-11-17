"""Fahrzeit (OSRM): Fahrzeit und Strecke von einer Person zu einer Zone."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .rechner import FahrzeitRechner

PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

type OsrmFahrzeitConfigEntry = ConfigEntry[FahrzeitRechner]


async def async_setup_entry(hass: HomeAssistant, entry: OsrmFahrzeitConfigEntry) -> bool:
    rechner = FahrzeitRechner(hass, entry)
    entry.runtime_data = rechner
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await rechner.async_start()
    entry.async_on_unload(entry.add_update_listener(_optionen_geaendert))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OsrmFahrzeitConfigEntry) -> bool:
    if ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_stop()
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: OsrmFahrzeitConfigEntry) -> None:
    """Mit dem Eintrag auch die gespeicherte letzte Position löschen (#9)."""
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def _optionen_geaendert(hass: HomeAssistant, entry: OsrmFahrzeitConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
