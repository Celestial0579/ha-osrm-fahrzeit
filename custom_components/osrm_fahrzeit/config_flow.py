"""Einrichtung über die Oberfläche."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_LUFTLINIE_KMH,
    CONF_MAX_ALTER,
    CONF_MIN_ABSTAND,
    CONF_MIN_BEWEGUNG,
    CONF_NUR_UNTERWEGS,
    CONF_PAUSE,
    CONF_SERVER,
    CONF_TAGESLIMIT,
    CONF_TRACKER,
    CONF_ZIEL,
    DEFAULT_NAME,
    DEFAULT_SERVER,
    DOMAIN,
    STANDARD_OPTIONEN,
)
from .rechner import RoutenFehler, route_abfragen


def _zahl(minimum: int, maximum: int, einheit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(min=minimum, max=maximum, step=1, unit_of_measurement=einheit, mode=selector.NumberSelectorMode.BOX)
    )


class OsrmFahrzeitConfigFlow(ConfigFlow, domain=DOMAIN):
    """Person, Ziel und Server wählen."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fehler: dict[str, str] = {}
        if user_input is not None:
            ziel = self.hass.states.get(user_input[CONF_ZIEL])
            if ziel is None or not isinstance(ziel.attributes.get("latitude"), (int, float)):
                fehler[CONF_ZIEL] = "ziel_ohne_position"
            elif not str(user_input[CONF_SERVER]).startswith(("http://", "https://")):
                fehler[CONF_SERVER] = "ungueltige_adresse"
            else:
                pos = (float(ziel.attributes["latitude"]), float(ziel.attributes["longitude"]))
                try:
                    await route_abfragen(async_get_clientsession(self.hass), user_input[CONF_SERVER], pos, pos)
                except RoutenFehler:
                    fehler["base"] = "nicht_erreichbar"
            if not fehler:
                await self.async_set_unique_id(f"{user_input[CONF_TRACKER]}|{user_input[CONF_ZIEL]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={k: user_input[k] for k in (CONF_TRACKER, CONF_ZIEL, CONF_SERVER)},
                )
        vorgabe = user_input or {}
        return self.async_show_form(
            step_id="user",
            errors=fehler,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=vorgabe.get(CONF_NAME, DEFAULT_NAME)): str,
                    vol.Required(CONF_TRACKER, default=vorgabe.get(CONF_TRACKER, vol.UNDEFINED)): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=["person", "device_tracker"])
                    ),
                    vol.Required(CONF_ZIEL, default=vorgabe.get(CONF_ZIEL, "zone.home")): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="zone")
                    ),
                    vol.Required(CONF_SERVER, default=vorgabe.get(CONF_SERVER, DEFAULT_SERVER)): str,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OsrmFahrzeitOptionsFlow()


class OsrmFahrzeitOptionsFlow(OptionsFlow):
    """Bremse und Rückfall einstellen."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        o = {**STANDARD_OPTIONEN, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NUR_UNTERWEGS, default=o[CONF_NUR_UNTERWEGS]): bool,
                    vol.Required(CONF_MIN_BEWEGUNG, default=o[CONF_MIN_BEWEGUNG]): _zahl(50, 50000, "m"),
                    vol.Required(CONF_MAX_ALTER, default=o[CONF_MAX_ALTER]): _zahl(5, 1440, "min"),
                    vol.Required(CONF_MIN_ABSTAND, default=o[CONF_MIN_ABSTAND]): _zahl(1, 120, "min"),
                    vol.Required(CONF_PAUSE, default=o[CONF_PAUSE]): _zahl(1, 1440, "min"),
                    vol.Required(CONF_TAGESLIMIT, default=o[CONF_TAGESLIMIT]): _zahl(1, 5000, "Abfragen"),
                    vol.Required(CONF_LUFTLINIE_KMH, default=o[CONF_LUFTLINIE_KMH]): _zahl(10, 300, "km/h"),
                }
            ),
        )
