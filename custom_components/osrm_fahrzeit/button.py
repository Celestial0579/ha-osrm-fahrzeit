"""Knopf: jetzt neu abfragen."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import FahrzeitEntitaet
from .rechner import FahrzeitRechner


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([AbfragenKnopf(entry.runtime_data)])


class AbfragenKnopf(FahrzeitEntitaet, ButtonEntity):
    """Fragt sofort neu ab (Pause und Tageslimit gelten weiter)."""

    _attr_icon = "mdi:refresh"

    def __init__(self, rechner: FahrzeitRechner) -> None:
        super().__init__(rechner, "abfragen")

    async def async_press(self) -> None:
        await self._rechner.async_berechnen(erzwingen=True)
