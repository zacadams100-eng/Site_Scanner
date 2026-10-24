"""
Build fictional fixture layers around a fictional site, for tests and demo.

Every name here is made up ("Fixture Wood SSSI"). Sheets built from these
are watermarked TEST DATA by the renderer.
"""

import json
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon, box, mapping

from sheet.geometry import to_wgs

# A ~6 ha field, in BNG metres, somewhere in the Surrey Hills grid square.
CX, CY = 516_500, 150_200
SITE = Polygon([(CX - 120, CY - 110), (CX + 140, CY - 130), (CX + 150, CY + 100),
                (CX - 20, CY + 140), (CX - 130, CY + 60)])


def _fc(features):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": props, "geometry": mapping(to_wgs(g))} for g, props in features]}


def build(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    data = {
        "sssi": [(Polygon([(CX + 600, CY + 300), (CX + 1500, CY + 450), (CX + 1400, CY + 1300),
                           (CX + 700, CY + 1100)]), {"name": "Fixture Down SSSI"})],
        "sac": [(box(CX + 4000, CY - 3000, CX + 7000, CY + 1000), {"name": "Fixture Hills SAC"})],
        "spa": [],
        "national_landscape": [(box(CX - 6000, CY - 400, CX + 8000, CY + 9000),
                                {"name": "Fixture Hills National Landscape"})],
        "ancient_woodland": [(Polygon([(CX - 700, CY - 500), (CX - 300, CY - 450), (CX - 350, CY - 150),
                                       (CX - 750, CY - 200)]), {"name": "Fixture Copse"})],
        "priority_habitat": [(Polygon([(CX - 40, CY - 60), (CX + 90, CY - 70), (CX + 80, CY + 40),
                                       (CX - 30, CY + 50)]), {"Main_Habit": "Lowland meadows"}),
                             (box(CX + 300, CY - 600, CX + 650, CY - 350), {"Main_Habit": "Deciduous woodland"})],
        "flood_zone": [(LineString([(CX - 1500, CY - 900), (CX - 200, CY - 700), (CX + 1600, CY - 1000)]).buffer(120),
                        {"name": "", "flood-risk-level": "3"})],
        "main_river": [(LineString([(CX - 1500, CY - 900), (CX - 200, CY - 700), (CX + 1600, CY - 1000)]),
                        {"watercourse_name": "Fixture Brook"})],
        "surface_water": [(Point(CX + 60, CY + 20).buffer(25), {}), (Point(CX + 200, CY - 180).buffer(15), {})],
        "conservation_area": [(box(CX - 1200, CY + 500, CX - 500, CY + 1100), {"name": "Fixture Village"})],
        "listed_building": [(Point(CX - 800, CY + 800), {"name": "The Old Forge", "listed-building-grade": "II"}),
                            (Point(CX - 650, CY + 700), {"name": "Church of St Fixture", "listed-building-grade": "I"})],
        "tpo_tree": [(Point(CX + 145, CY + 20), {"name": "T1 Oak"})],
        "green_belt": [(box(CX - 5000, CY - 5000, CX + 5000, CY + 5000), {"name": "Metropolitan Green Belt"})],
        "sssi_irz": [(box(CX - 3000, CY - 3000, CX + 3000, CY + 3000), {"SSSI_NAME": "Fixture Down"})],
        "alc": [(box(CX - 2000, CY - 2000, CX + 2000, CY + 2000), {"agricultural-land-classification-grade": "Grade 3"})],
        "woodland": [(Polygon([(CX - 700, CY - 500), (CX - 300, CY - 450), (CX - 350, CY - 150),
                               (CX - 750, CY - 200)]), {"IFT_IOA": "Broadleaved"})],
    }
    # every other layer: answered, nothing there
    from sheet.layers import LAYERS
    for l in LAYERS:
        if l.id in ("ramsar",):
            continue   # leave one missing on purpose: must come out NOT ASSESSED
        feats = data.get(l.id, [])
        (folder / f"{l.id}.geojson").write_text(json.dumps(_fc(feats)))
    return folder


def site_geojson():
    return {"type": "Feature", "properties": {}, "geometry": mapping(to_wgs(SITE))}


if __name__ == "__main__":
    # python -m tests.fixtures_build demo-fixtures
    #   then CONTOUR_FIXTURES=demo-fixtures uvicorn sheet.api:app --port 8000
    # The fictional site sits near 516,500 E, 150,200 N, just west of Dorking.
    import sys
    print(build(Path(sys.argv[1] if len(sys.argv) > 1 else "demo-fixtures")))
