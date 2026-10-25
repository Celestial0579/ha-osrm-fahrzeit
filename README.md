# Fahrzeit (OSRM) für Home Assistant

Berechnet **Fahrzeit** und **Strecke** von einer Person (oder einem Tracker) zu einer Zone – etwa „Wie lange
brauche ich nach Hause?“ – über einen [OSRM](https://project-osrm.org/)-Routendienst. Mit eingebauter
**Bremse**, damit der Dienst nicht überlastet wird, und Kontrolllampe für Störungen.

*English summary below.*

## Was es liefert

| Entität | Bedeutung |
|---|---|
| **Fahrzeit** (min) | kürzeste Fahrzeit ohne Stau; Attribut `quelle`: OpenStreetMap, gespeichert, Luftlinie oder am Ziel |
| **Strecke** (km) | Straßenkilometer |
| **Routendienst gestört** | an, wenn die letzte Abfrage fehlschlug oder das Tageslimit erreicht ist; Attribute `zustand`, `letzte_erfolgreiche_abfrage`, `letzter_fehler`, `anfragen_heute` |
| **Jetzt abfragen** | fragt sofort neu ab (Pause und Tageslimit gelten weiter) |

## Bremse (über „Konfigurieren“ einstellbar)

- neue Abfrage nur nach **Bewegung** (Vorgabe 500 m) oder wenn der Wert **älter** ist als 60 Minuten
- **Mindestabstand** zwischen zwei Abfragen: 5 Minuten
- nach einem **Fehler** 30 Minuten Pause
- **Tageslimit** 150 Abfragen
- dazwischen Schätzung über die **Luftlinie** (Vorgabe 120 km/h – bewusst schnell, damit die Zeit eher
  unterschätzt wird)
- ist die Person **am Ziel**, wird nicht abgefragt (Fahrzeit 0)

## Einrichtung

1. HACS › drei Punkte › **Benutzerdefinierte Repositories** › diese Repository-URL, Typ **Integration**.
2. „Fahrzeit (OSRM)“ installieren, Home Assistant neu starten.
3. **Einstellungen › Geräte & Dienste › Integration hinzufügen › Fahrzeit (OSRM)**: Name, Person/Tracker,
   Ziel-Zone und Server wählen. Mehrere Einträge (andere Personen oder Ziele) sind möglich.

## Datenschutz und Nutzungsbedingungen

Vorgabe ist der Routendienst des **FOSSGIS e.V.** (`routing.openstreetmap.de`). Bei jeder Abfrage gehen
Standort und Zielposition an diesen Server; er protokolliert die Anfragen. Es gelten die
[Nutzungsbedingungen](https://www.fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/) (u. a. höchstens
eine Anfrage pro Sekunde, keine Massenabfragen, Quellenangabe). Die Bremse hält das ein. Wer das nicht möchte,
trägt einen eigenen OSRM-Server ein.

Daten: © OpenStreetMap-Mitwirkende (ODbL).

---

## English summary

Travel time and distance from a person/tracker to a zone via an OSRM routing service (default: FOSSGIS
`routing.openstreetmap.de`), with a built-in rate-limit brake (query only after movement or when stale, minimum
interval, pause after errors, daily cap; straight-line estimate in between) and a problem sensor. Set up from
the UI after installing via HACS as a custom repository (type *Integration*). Locations are sent to the
routing server; use your own OSRM server if you prefer.

Lizenz / License: MIT
