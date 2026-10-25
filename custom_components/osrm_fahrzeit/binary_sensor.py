"""Kontrolllampe: Routendienst gestört."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import FahrzeitEntitaet
from .rechner import FahrzeitRechner


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([GestoertSensor(entry.runtime_data)])


def _lokal(rechner: FahrzeitRechner, schluessel: str, leer: str) -> str:
    zeit = rechner.zeitpunkt(schluessel)
    return dt_util.as_local(zeit).strftime("%d.%m. %H:%M") if zeit else leer


class GestoertSensor(FahrzeitEntitaet, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:map-marker-path"

    def __init__(self, rechner: FahrzeitRechner) -> None:
        super().__init__(rechner, "gestoert")

    @property
    def is_on(self) -> bool:
        return self._rechner.gestoert

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "zustand": self._rechner.zustand,
            "letzte_erfolgreiche_abfrage": _lokal(self._rechner, "t", "noch keine"),
            "letzter_fehler": _lokal(self._rechner, "ft", "keiner") if self._rechner.pause_bis else "keiner",
            "fehlertext": self._rechner.letzter_fehlertext if self._rechner.pause_bis else None,
            "anfragen_heute": self._rechner.anfragen_heute,
        }
