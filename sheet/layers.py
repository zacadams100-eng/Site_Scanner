"""
The 30 layers on a Contour desk-study sheet.

This replaces Site Scanner's ~120-factor catalogue for this product. Those
factors were satellite statistics (NDVI, air temperature, price per m2) —
useful for land investment, but not what an ecologist puts on a desk-study
map. Every layer here is an official vector dataset from a public body,
under the Open Government Licence, queried live at the moment a sheet is made.

Each layer has its own search radius, following common desk-study practice:
international sites are searched further out than heritage features, because
their consultation triggers reach further. Radii are product defaults, not
regulatory thresholds — the sheet says so.

Three source kinds:
  planning  — planning.data.gov.uk entity API (one endpoint, many datasets)
  arcgis    — ArcGIS REST FeatureServer query (Natural England / Defra / EA)

To add or drop a layer, edit this list. Nothing else needs to change.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

PLANNING_API = "https://www.planning.data.gov.uk/entity.geojson"
# The same search without geometry: used to ask "does this dataset hold any
# record at all?" without downloading a whole National Landscape to find out.
PLANNING_ENTITIES = "https://www.planning.data.gov.uk/entity.json"
NE = "https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services"
DEFRA = "https://services1.arcgis.com/JZM7qJpmv7vJ0Hzx/arcgis/rest/services"
# Forestry Commission open data. planning.data's forest-inventory dataset is an
# empty placeholder (0 records nationally), so woodland comes from here.
FC = "https://services2.arcgis.com/mHXjwgl3OARRqqD4/arcgis/rest/services"
# Field names below were read off the live services with
# scripts/inspect_layers.py (24 Oct 2026). Re-run it before changing them.

OGL = "Open Government Licence v3.0"


@dataclass(frozen=True)
class Style:
    fill: str            # hex, or "none"
    edge: str            # hex
    hatch: Optional[str] = None   # matplotlib hatch pattern, e.g. "///"
    alpha: float = 0.35  # fill opacity
    width: float = 0.8   # line width (pt)
    marker: str = "o"    # for points


@dataclass(frozen=True)
class Layer:
    id: str
    name: str            # as it appears in the key
    group: str
    source: str          # "planning" | "arcgis"
    search_m: int        # search radius from the red line
    publisher: str
    style: Style
    dataset: Optional[str] = None        # planning.data dataset slug
    url: Optional[str] = None            # arcgis layer url (…/FeatureServer/N)
    label_fields: List[str] = field(default_factory=lambda: ["name"])
    label_template: str = "{}"           # e.g. "Flood Zone {}"
    label_map: Dict[str, str] = field(default_factory=dict)   # code → words, e.g. ASNW
    default_label: str = ""              # when the publisher sends no name at all
    grade_field: str = ""                # appended as "(Grade II)" when present
    # "list": named features with distance and direction ("Box Hill SSSI, 450 m NE").
    # "area": hectares by type and the share of the red line covered — for
    # layers made of thousands of small parcels, where a list says nothing.
    # "grades": counts by grade, naming only the highest grades (listed buildings).
    # "zones": how many zones the red line falls in, with their criteria links.
    summary: str = "list"
    where: str = "1=1"                   # ArcGIS only: server-side filter
    # False where the publisher splits one thing into map tiles, so "(92 parcels)"
    # counts tiles, not places (flood zones, main rivers).
    count_parcels: bool = True
    on_map: bool = True                  # False = reported in findings only
    geom: str = "polygon"                # polygon | line | point
    licence: str = OGL
    note: str = ""


G_INT = "International designations"
G_NAT = "National designations"
G_HAB = "Habitats and nature recovery"
G_LAND = "Landscape and open land"
G_WATER = "Water and flooding"
G_HERITAGE = "Heritage and trees"

LAYERS: List[Layer] = [
    # --- International sites — searched to 10 km ---------------------------
    Layer("sac", "Special Area of Conservation", G_INT, "planning", 10_000,
          "Natural England", Style("#7b3294", "#7b3294", "\\\\\\", 0.18),
          dataset="special-area-of-conservation"),
    Layer("spa", "Special Protection Area", G_INT, "planning", 10_000,
          "Natural England", Style("#c2a5cf", "#5e3c99", "///", 0.18),
          dataset="special-protection-area"),
    Layer("ramsar", "Ramsar site", G_INT, "planning", 10_000,
          "Natural England", Style("#1f78b4", "#1f78b4", "xx", 0.15),
          dataset="ramsar"),

    # --- National ------------------------------------------------------------
    Layer("sssi", "Site of Special Scientific Interest", G_NAT, "planning", 2_000,
          "Natural England", Style("#33a02c", "#1b5e20", "///", 0.25),
          dataset="site-of-special-scientific-interest"),
    Layer("nnr", "National Nature Reserve", G_NAT, "planning", 2_000,
          "Natural England", Style("#006d2c", "#006d2c", "..", 0.25),
          dataset="national-nature-reserve"),
    Layer("sssi_irz", "SSSI Impact Risk Zone", G_NAT, "arcgis", 0,
          "Natural England", Style("none", "#999999"),
          url=f"{NE}/SSSI_Impact_Risk_Zones_England/FeatureServer/0",
          # The live service carries no SSSI name, only an IRZ link and code.
          label_fields=["IRZURL"], summary="zones",
          on_map=False,
          note="Reported only where the red line falls inside a zone. "
               "Check the zone's consultation criteria for the proposal type."),

    # --- Habitats and nature recovery — 2 km --------------------------------
    Layer("lnr", "Local Nature Reserve", G_HAB, "planning", 2_000,
          "Natural England", Style("#66c2a4", "#238b45", None, 0.35),
          dataset="local-nature-reserve"),
    Layer("ancient_woodland", "Ancient woodland", G_HAB, "planning", 2_000,
          "Natural England", Style("#4d7c0f", "#365314", None, 0.55),
          dataset="ancient-woodland",
          # planning.data leaves most names blank; the status is always there.
          label_fields=["name", "ancient-woodland-status"],
          label_map={"ASNW": "Ancient semi-natural woodland",
                     "PAWS": "Plantation on ancient woodland site",
                     "ARW": "Ancient replanted woodland",
                     "AWPP": "Ancient wood pasture"}),
    Layer("priority_habitat", "Priority habitat inventory", G_HAB, "arcgis", 2_000,
          "Natural England", Style("#b8e186", "#7fbc41", None, 0.45, 0.4),
          url=f"{NE}/Priority_Habitats_Inventory_England/FeatureServer/0",
          label_fields=["MainHabs", "Main_Habit", "mainhabs", "MAIN_HABIT", "habitat"],
          label_map={"No main habitat but additional habitats present":
                     "Additional habitats only (no main habitat)"},
          summary="area"),
    Layer("gcn_soa", "GCN strategic opportunity area", G_HAB, "arcgis", 2_000,
          "Natural England", Style("none", "#e6550d", "--", 0.0, 0.6),
          url=f"{NE}/GCN_Strategic_Opportunity_Areas_England/FeatureServer/0",
          label_fields=["SOA"], label_template="{} zone"),
    Layer("nia", "Nature improvement area", G_HAB, "planning", 2_000,
          "Natural England", Style("none", "#2ca25f", "\\\\", 0.0, 0.6),
          dataset="nature-improvement-area"),
    Layer("lnrs", "Local nature recovery strategy area", G_HAB, "planning", 2_000,
          "Responsible authority", Style("none", "#41ab5d", "..", 0.0, 0.6),
          dataset="local-nature-recovery-strategy",
          note="Only where the strategy has been published to planning.data."),
    Layer("nutrient", "Nutrient neutrality catchment", G_HAB, "planning", 0,
          "Natural England", Style("none", "#8c6d31"), dataset="nutrient-neutrality-catchment",
          on_map=False, note="Reported only where the red line falls inside one."),
    Layer("woodland", "Woodland (National Forest Inventory)", G_HAB, "arcgis", 1_000,
          "Forestry Commission", Style("#a1d99b", "#74c476", None, 0.35, 0.3),
          # Republished yearly under a new name; inspect_layers.py lists the newest.
          url=f"{FC}/National_Forest_Inventory_England_2025/FeatureServer/0",
          # The inventory maps open ground inside forests too (CATEGORY "Non woodland":
          # grassland, urban, bare area). Only woodland belongs in this finding.
          label_fields=["IFT_IOA"], where="CATEGORY='Woodland'", summary="area"),
    Layer("common_land", "Common land and village green", G_HAB, "planning", 1_000,
          "Defra", Style("#fee391", "#cc9a06", None, 0.4),
          dataset="common-land-and-village-green"),

    # --- Landscape and open land ----------------------------------------------
    Layer("national_landscape", "National Landscape (AONB)", G_LAND, "planning", 2_000,
          "Natural England", Style("none", "#b35806", None, 0.0, 1.4),
          dataset="area-of-outstanding-natural-beauty"),
    Layer("national_park", "National Park", G_LAND, "planning", 2_000,
          "Natural England", Style("none", "#7f3b08", None, 0.0, 1.4),
          dataset="national-park"),
    Layer("green_belt", "Green Belt", G_LAND, "planning", 1_000,
          "Local planning authority", Style("none", "#5aae61", None, 0.0, 1.4),
          dataset="green-belt"),
    Layer("local_green_space", "Local green space", G_LAND, "planning", 1_000,
          "Local planning authority", Style("#c7e9c0", "#31a354", "++", 0.35),
          dataset="local-green-space"),
    Layer("alc", "Agricultural land classification", G_LAND, "planning", 0,
          "Natural England", Style("none", "#a6611a"), dataset="agricultural-land-classification",
          label_fields=["agricultural-land-classification-grade", "name"], on_map=False,
          note="Provisional 1:250,000 grades — not field survey. Reported for the red line only."),

    # --- Water and flooding — 1 km ---------------------------------------------
    Layer("flood_zone", "Flood Zone 2 / 3", G_WATER, "planning", 1_000,
          "Environment Agency", Style("#9ecae1", "#3182bd", None, 0.4, 0.3),
          dataset="flood-risk-zone", label_fields=["flood-risk-level"], count_parcels=False,
          label_template="Flood Zone {}"),
    Layer("main_river", "Statutory main river", G_WATER, "arcgis", 1_000,
          "Environment Agency", Style("none", "#08519c", None, 0.0, 1.6),
          url=f"{DEFRA}/Statutory_Main_River_Map/FeatureServer/0",
          # The EA service carries no river names (only STATUS and LENGTH_KM).
          label_fields=[], default_label="Main river", geom="line", count_parcels=False),
    Layer("surface_water", "Surface water flooding (1% AEP)", G_WATER, "arcgis", 250,
          "Environment Agency", Style("#c6dbef", "#6baed6", None, 0.5, 0.2),
          url=f"{DEFRA}/Risk_of_Flooding_from_Surface_Water_Extents/FeatureServer/1",
          label_fields=[], summary="area"),
    Layer("flood_storage", "Flood storage area", G_WATER, "planning", 1_000,
          "Environment Agency", Style("none", "#2171b5", "..", 0.0, 0.6),
          dataset="flood-storage-area", default_label="Flood storage area"),

    # --- Heritage and trees ---------------------------------------------------
    Layer("conservation_area", "Conservation area", G_HERITAGE, "planning", 1_000,
          "Local planning authority", Style("none", "#ff7f00", "\\\\", 0.0, 1.0),
          dataset="conservation-area"),
    Layer("listed_building", "Listed building", G_HERITAGE, "planning", 500,
          "Historic England", Style("#fc8d59", "#b30000", None, 0.9, 0.4, "^"),
          dataset="listed-building", geom="point",
          label_fields=["name"], grade_field="listed-building-grade", summary="grades"),
    Layer("scheduled_monument", "Scheduled monument", G_HERITAGE, "planning", 1_000,
          "Historic England", Style("#fdae61", "#a50026", "xx", 0.35),
          dataset="scheduled-monument"),
    Layer("park_garden", "Registered park and garden", G_HERITAGE, "planning", 1_000,
          "Historic England", Style("none", "#a50026", "..", 0.0, 0.8),
          dataset="park-and-garden", grade_field="park-and-garden-grade"),
    Layer("tpo_area", "Tree preservation order (area)", G_HERITAGE, "planning", 250,
          "Local planning authority", Style("#addd8e", "#31a354", "oo", 0.3),
          dataset="tree-preservation-zone",
          label_fields=["tree-preservation-order"], label_template="TPO {}"),
    Layer("tpo_tree", "Tree preservation order (tree)", G_HERITAGE, "planning", 250,
          "Local planning authority", Style("#31a354", "#005a32", None, 0.9, 0.4, "o"),
          dataset="tree", geom="point",
          # "name" holds council boilerplate; the order reference is what people cite.
          label_fields=["tree-preservation-order"], label_template="TPO {}"),
]

assert len(LAYERS) == 30, len(LAYERS)
LAYER_BY_ID = {l.id: l for l in LAYERS}
assert len(LAYER_BY_ID) == 30, "duplicate layer id"

# Groups in the order they appear in the key and findings.
GROUPS = [G_INT, G_NAT, G_HAB, G_LAND, G_WATER, G_HERITAGE]
