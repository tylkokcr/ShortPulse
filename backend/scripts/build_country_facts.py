"""Build app/assets/geo/facts.json: each country's population, area and
capital, for the "what if?" identity card (engines/maps.py).

Numbers on a card are the one part of a video a model must not write: in
the first two real cards it filled the rows with a stock exchange and a
river, and left the population out. So they come from Natural Earth
(public domain), the same source as the outlines:

    python scripts/build_country_facts.py ne_50m_admin_0_countries.geojson \\
        ne_50m_populated_places.geojson

both from github.com/nvkelso/natural-earth-vector (geojson/).

Population is Natural Earth's POP_EST (with its year). Area is computed
from the 1:50m polygons on a sphere, holes subtracted — within a percent
or two of the official figures, and shown rounded. The capital is the
Admin-0 capital, named in English, Turkish, Polish and German.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "assets" / "geo" / "facts.json"
R_KM = 6371.0088
# Where Natural Earth lists several Admin-0 capitals, the one a card names.
PREFERRED_CAPITAL = {"ZAF": "Pretoria"}


def _ring_area(ring: list[list[float]]) -> float:
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(ring, ring[1:] + ring[:1], strict=True):
        total += math.radians(lon2 - lon1) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total) * R_KM**2 / 2


def _area(geometry: dict) -> float:
    polygons = (
        [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    )
    return sum(_ring_area(p[0]) - sum(_ring_area(h) for h in p[1:]) for p in polygons)


def main(countries_path: str, places_path: str) -> None:
    capitals: dict[str, dict] = {}
    for f in json.loads(Path(places_path).read_text())["features"]:
        p = f["properties"]
        a3 = p.get("ADM0_A3")
        if p.get("FEATURECLA") == "Admin-0 capital" and a3:
            if PREFERRED_CAPITAL.get(a3, p["NAME"]) == p["NAME"]:
                capitals.setdefault(a3, p)
    facts = {}
    for f in json.loads(Path(countries_path).read_text())["features"]:
        p = f["properties"]
        a3 = p["ADM0_A3"]
        cap = capitals.get(a3)
        facts[a3] = {
            "population": int(p["POP_EST"]) if p.get("POP_EST") else None,
            "population_year": p.get("POP_YEAR"),
            "area_km2": round(_area(f["geometry"])),
            "capital": (
                {lang: cap.get(f"NAME_{lang.upper()}") or cap["NAME"] for lang in ("en", "tr", "pl", "de")}
                if cap
                else None
            ),
        }
    OUT.write_text(json.dumps(facts, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    print(f"{len(facts)} countries, {sum(1 for v in facts.values() if v['capital'])} with a capital")


if __name__ == "__main__":
    main(*sys.argv[1:3])
