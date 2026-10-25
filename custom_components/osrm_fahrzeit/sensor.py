"""Sensoren: Fahrzeit und Strecke."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import FahrzeitEntitaet
from .rechner import FahrzeitRechner


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    rechner: FahrzeitRechner = entry.runtime_data
    async_add_entities([DauerSensor(rechner), StreckeSensor(rechner)])


class DauerSensor(FahrzeitEntitaet, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_icon = "mdi:car-clock"

    def __init__(self, rechner: FahrzeitRechner) -> None:
        super().__init__(rechner, "dauer")

    @property
    def native_value(self) -> float | None:
        return self._rechner.minuten

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        letzte = self._rechner.zeitpunkt("t")
        return {
            "quelle": self._rechner.quelle,
            "letzte_abfrage": letzte.isoformat() if letzte else None,
            "anfragen_heute": self._rechner.anfragen_heute,
        }


class StreckeSensor(FahrzeitEntitaet, SensorEntity):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:map-marker-distance"

    def __init__(self, rechner: FahrzeitRechner) -> None:
        super().__init__(rechner, "strecke")

    @property
    def native_value(self) -> float | None:
        return self._rechner.km
