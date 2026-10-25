"""Gemeinsame Basis der Entitäten."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import ATTRIBUTION, CONF_SERVER, DOMAIN
from .rechner import FahrzeitRechner


class FahrzeitEntitaet(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_attribution = ATTRIBUTION

    def __init__(self, rechner: FahrzeitRechner, schluessel: str) -> None:
        self._rechner = rechner
        self._attr_translation_key = schluessel
        self._attr_unique_id = f"{rechner.entry.entry_id}_{schluessel}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, rechner.entry.entry_id)},
            name=rechner.entry.title,
            manufacturer="OSRM",
            model=rechner.entry.data[CONF_SERVER],
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._rechner.zuhoerer_hinzufuegen(self._aktualisieren))

    @callback
    def _aktualisieren(self) -> None:
        self.async_write_ha_state()
