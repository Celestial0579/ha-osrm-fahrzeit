"""Fahrzeit-Berechnung mit Bremse gegen Ratenlimits."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import time
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

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
    DOMAIN,
    NACHFUEHREN_MINUTEN,
    STANDARD_OPTIONEN,
)

_LOGGER = logging.getLogger(__name__)
USER_AGENT = "HomeAssistant-osrm_fahrzeit/0.1 (+https://github.com/Celestial0579/ha-osrm-fahrzeit)"


class RoutenFehler(Exception):
    """Der Routendienst hat keine verwertbare Antwort geliefert."""


async def route_abfragen(
    sitzung: aiohttp.ClientSession, server: str, start: tuple[float, float], ziel: tuple[float, float]
) -> tuple[float, float]:
    """Fahrzeit (s) und Strecke (m) von start nach ziel, jeweils (Breite, Länge)."""
    url = (
        f"{server.rstrip('/')}/route/v1/driving/"
        f"{start[1]:.6f},{start[0]:.6f};{ziel[1]:.6f},{ziel[0]:.6f}"
        "?overview=false&alternatives=false&steps=false"
    )
    try:
        async with sitzung.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=aiohttp.ClientTimeout(total=20)
        ) as antwort:
            if antwort.status != 200:
                raise RoutenFehler(f"HTTP {antwort.status}")
            daten = await antwort.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError) as err:
        raise RoutenFehler(str(err) or type(err).__name__) from err
    routen = daten.get("routes") or []
    if daten.get("code") != "Ok" or not routen:
        raise RoutenFehler(str(daten.get("code") or "keine Route"))
    return float(routen[0]["duration"]), float(routen[0]["distance"])


class FahrzeitRechner:
    """Hält Fahrzeit und Strecke vom Tracker zum Ziel aktuell."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.minuten: float | None = None
        self.km: float | None = None
        self.quelle = "unbekannt"
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._daten: dict[str, Any] = {}
        self._zuhoerer: list[Callable[[], None]] = []
        self._abmelden: list[CALLBACK_TYPE] = []
        self._nachlauf: CALLBACK_TYPE | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ Einstellungen
    def opt(self, schluessel: str) -> Any:
        return self.entry.options.get(schluessel, STANDARD_OPTIONEN[schluessel])

    @property
    def tracker(self) -> str:
        return self.entry.data[CONF_TRACKER]

    @property
    def ziel(self) -> str:
        return self.entry.data[CONF_ZIEL]

    # ------------------------------------------------------------ Zustand
    def _heute(self) -> str:
        return dt_util.now().date().isoformat()

    @property
    def anfragen_heute(self) -> int:
        return int(self._daten.get("n", 0)) if self._daten.get("d") == self._heute() else 0

    @property
    def pause_bis(self) -> float:
        return float(self._daten.get("s") or 0)

    @property
    def tageslimit_erreicht(self) -> bool:
        return self.anfragen_heute >= int(self.opt(CONF_TAGESLIMIT))

    @property
    def gestoert(self) -> bool:
        return self.pause_bis > 0 or self.tageslimit_erreicht

    @property
    def zustand(self) -> str:
        if self.tageslimit_erreicht:
            return "Tageslimit erreicht, bis Mitternacht Schätzung über Luftlinie"
        if self.pause_bis > time.time():
            bis = dt_util.as_local(dt_util.utc_from_timestamp(self.pause_bis)).strftime("%H:%M")
            return f"Letzte Abfrage fehlgeschlagen, Pause bis {bis} Uhr, solange Luftlinie"
        if self.pause_bis > 0:
            return "Letzte Abfrage fehlgeschlagen, neuer Versuch bei der nächsten Standortmeldung"
        if self._daten.get("t"):
            return "OK"
        return "Noch keine Abfrage"

    def zeitpunkt(self, schluessel: str) -> datetime | None:
        wert = self._daten.get(schluessel)
        return dt_util.utc_from_timestamp(float(wert)) if wert else None

    @property
    def letzter_fehlertext(self) -> str | None:
        return self._daten.get("f")

    def zuhoerer_hinzufuegen(self, rueckruf: Callable[[], None]) -> Callable[[], None]:
        self._zuhoerer.append(rueckruf)
        return lambda: self._zuhoerer.remove(rueckruf)

    # ------------------------------------------------------------ Lebenszyklus
    async def async_start(self) -> None:
        self._daten = await self._store.async_load() or {}
        if isinstance(self._daten.get("m"), (int, float)):
            self.minuten, self.km, self.quelle = self._daten["m"], self._daten.get("km"), "OpenStreetMap (gespeichert)"
        self._abmelden.append(
            async_track_state_change_event(self.hass, [self.tracker, self.ziel], self._bei_aenderung)
        )
        self._abmelden.append(
            async_track_time_interval(self.hass, self._takt, timedelta(minutes=NACHFUEHREN_MINUTEN))
        )
        self.hass.async_create_background_task(self.async_berechnen(), f"{DOMAIN}_start")

    async def async_stop(self) -> None:
        for abmelden in self._abmelden:
            abmelden()
        self._abmelden.clear()
        if self._nachlauf is not None:
            self._nachlauf()
            self._nachlauf = None

    @callback
    def _bei_aenderung(self, _ereignis: Event) -> None:
        if not self._lock.locked():
            self.hass.async_create_background_task(self.async_berechnen(), f"{DOMAIN}_aenderung")

    async def _takt(self, _jetzt: datetime) -> None:
        await self.async_berechnen()

    # ------------------------------------------------------------ Berechnung
    async def async_berechnen(self, erzwingen: bool = False) -> None:
        async with self._lock:
            await self._berechnen(erzwingen)
        self._melden()

    async def _berechnen(self, erzwingen: bool) -> None:
        tracker = self.hass.states.get(self.tracker)
        ziel = self.hass.states.get(self.ziel)
        if ziel is None or not isinstance(ziel.attributes.get("latitude"), (int, float)):
            self.minuten, self.km, self.quelle = None, None, "Ziel unbekannt"
            return
        ziel_pos = (float(ziel.attributes["latitude"]), float(ziel.attributes["longitude"]))
        if tracker is None:
            self.minuten, self.km, self.quelle = None, None, "kein Standort"
            return
        if self.opt(CONF_NUR_UNTERWEGS) and self._am_ziel(tracker.state, ziel):
            self.minuten, self.km, self.quelle = 0.0, 0.0, "am Ziel"
            return
        lat, lon = tracker.attributes.get("latitude"), tracker.attributes.get("longitude")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            self.minuten, self.km, self.quelle = None, None, "kein Standort"
            return
        jetzt = time.time()
        letzte_pos = (self._daten.get("la"), self._daten.get("lo"))
        bewegt = letzte_pos[0] is None or (
            distance(lat, lon, letzte_pos[0], letzte_pos[1]) or 0
        ) > float(self.opt(CONF_MIN_BEWEGUNG))
        veraltet = not self._daten.get("t") or jetzt - float(self._daten["t"]) > 60 * float(self.opt(CONF_MAX_ALTER))
        rest_abstand = 60 * float(self.opt(CONF_MIN_ABSTAND)) - (jetzt - float(self._daten.get("q") or 0))
        darf = self.pause_bis <= jetzt and not self.tageslimit_erreicht

        if darf and (erzwingen or bewegt or veraltet):
            if rest_abstand > 0 and not erzwingen:
                self._spaeter(rest_abstand)
            else:
                await self._abfragen((float(lat), float(lon)), ziel_pos, jetzt)
                return
        if not bewegt and isinstance(self._daten.get("m"), (int, float)):
            self.minuten, self.km, self.quelle = self._daten["m"], self._daten.get("km"), "OpenStreetMap (gespeichert)"
            return
        luftlinie_km = (distance(lat, lon, ziel_pos[0], ziel_pos[1]) or 0) / 1000
        self.minuten = round(luftlinie_km / float(self.opt(CONF_LUFTLINIE_KMH)) * 60, 1)
        self.km = round(luftlinie_km, 1)
        self.quelle = "Luftlinie"

    async def _abfragen(self, start: tuple[float, float], ziel: tuple[float, float], jetzt: float) -> None:
        heute = self._heute()
        anzahl = self.anfragen_heute + 1
        try:
            sekunden, meter = await route_abfragen(
                async_get_clientsession(self.hass), self.entry.data[CONF_SERVER], start, ziel
            )
        except RoutenFehler as err:
            _LOGGER.warning("Routendienst: %s – Pause %s min", err, self.opt(CONF_PAUSE))
            self._daten.update(q=jetzt, d=heute, n=anzahl, s=jetzt + 60 * float(self.opt(CONF_PAUSE)), f=str(err)[:200], ft=jetzt)
            self._speichern()
            luftlinie_km = (distance(start[0], start[1], ziel[0], ziel[1]) or 0) / 1000
            self.minuten = round(luftlinie_km / float(self.opt(CONF_LUFTLINIE_KMH)) * 60, 1)
            self.km = round(luftlinie_km, 1)
            self.quelle = "Luftlinie"
            return
        self.minuten, self.km, self.quelle = round(sekunden / 60, 1), round(meter / 1000, 1), "OpenStreetMap"
        self._daten.update(
            la=round(start[0], 5), lo=round(start[1], 5), t=jetzt, q=jetzt, m=self.minuten, km=self.km,
            d=heute, n=anzahl, s=0,
        )
        self._speichern()

    def _am_ziel(self, zustand: str, ziel: Any) -> bool:
        if self.ziel == "zone.home":
            return zustand == "home"
        return zustand in (ziel.name, ziel.object_id)

    def _spaeter(self, sekunden: float) -> None:
        if self._nachlauf is not None:
            return

        @callback
        def _ausloesen(_jetzt: datetime) -> None:
            self._nachlauf = None
            self.hass.async_create_background_task(self.async_berechnen(), f"{DOMAIN}_nachlauf")

        self._nachlauf = async_call_later(self.hass, max(sekunden, 1) + 1, _ausloesen)

    def _speichern(self) -> None:
        self._store.async_delay_save(lambda: self._daten, 2)

    @callback
    def _melden(self) -> None:
        for rueckruf in list(self._zuhoerer):
            rueckruf()
