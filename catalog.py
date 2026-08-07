"""
Site Scanner — factor catalogue
-------------------------------
The single source of truth for what this application can measure.

The important idea here is the split between a **base dataset** and a
**factor**. A base dataset is something we ingest and store; a factor is
something we can show the user. They are not the same thing, and conflating
them is what makes a 100-factor catalogue sound impossible.

Slope, aspect, ruggedness, curvature and height-above-drainage are five
factors computed from one stored elevation raster. NDVI, NDWI, EVI and SAVI
are four factors computed from the same two Sentinel-2 bands. A factor marked
`derived=True` costs nothing extra to store — it is arithmetic applied at read
time to a base we already hold.

That is how this file describes ~120 factors while committing to only 20
stored bases, of which just 8 need monthly resolution.

Every number the UI displays must be traceable to a row here. Nothing renders
without provenance attached to it.
"""

from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Base datasets — the things we actually ingest and pay to store.
#
# `stored` distinguishes rasters we hold ourselves from sources we query live
# (HM Land Registry, for instance, is an API lookup, not a raster we own).
# `cadence` here is the *storage* cadence, which may be coarser than the
# source's native revisit — Sentinel-2 passes every 5 days, but we store a
# monthly cloud-masked composite because that is what the timeline shows.
# ---------------------------------------------------------------------------
BASES: List[Dict[str, Any]] = [
    dict(id="sentinel2_sr", name="Sentinel-2 Surface Reflectance",
         source="Copernicus / ESA", licence="CC BY-SA 3.0 IGO",
         url="https://dataspace.copernicus.eu/",
         native_cadence="5 days", cadence="monthly", resolution_m=10, stored=True),
    dict(id="sentinel1_sar", name="Sentinel-1 SAR (C-band)",
         source="Copernicus / ESA", licence="CC BY-SA 3.0 IGO",
         url="https://dataspace.copernicus.eu/",
         native_cadence="6 days", cadence="monthly", resolution_m=10, stored=True),
    dict(id="esa_worldcover", name="ESA WorldCover Land Cover",
         source="ESA", licence="CC BY 4.0",
         url="https://esa-worldcover.org/",
         native_cadence="annual", cadence="annual", resolution_m=10, stored=True),
    dict(id="lidar_dtm", name="Environment Agency LIDAR Composite DTM",
         source="Environment Agency", licence="OGL v3",
         url="https://environment.data.gov.uk/",
         native_cadence="static", cadence="static", resolution_m=2, stored=True),
    dict(id="modis_lst", name="MODIS Land Surface Temperature",
         source="NASA LP DAAC", licence="Public domain",
         url="https://lpdaac.usgs.gov/products/mod11a2v061/",
         native_cadence="8 days", cadence="monthly", resolution_m=1000, stored=True),
    dict(id="era5_land", name="ERA5-Land Reanalysis",
         source="ECMWF / Copernicus C3S", licence="Copernicus licence",
         url="https://cds.climate.copernicus.eu/",
         native_cadence="hourly", cadence="monthly", resolution_m=9000, stored=True),
    dict(id="haduk_precip", name="HadUK-Grid Precipitation",
         source="Met Office", licence="OGL v3",
         url="https://www.metoffice.gov.uk/research/climate/maps-and-data/data/haduk-grid/",
         native_cadence="daily", cadence="monthly", resolution_m=1000, stored=True),
    # Gauge measurements, not a grid. Deliberately separate from haduk_precip:
    # a rain gauge is a point and HadUK-Grid is a 1 km areal average, so they
    # answer different questions about the same weather and must not share
    # provenance. `stored=False` — this is queried live per request.
    dict(id="ea_hydrology", name="EA Hydrology (rain gauges)",
         source="Environment Agency", licence="OGL v3",
         url="https://environment.data.gov.uk/hydrology/",
         native_cadence="daily", cadence="monthly", resolution_m=0, stored=False),
    dict(id="jrc_surface_water", name="JRC Global Surface Water",
         source="EC Joint Research Centre", licence="Open",
         url="https://global-surface-water.appspot.com/",
         native_cadence="annual", cadence="annual", resolution_m=30, stored=True),
    dict(id="ea_flood_zones", name="EA Flood Map for Planning",
         source="Environment Agency", licence="OGL v3",
         url="https://environment.data.gov.uk/",
         native_cadence="quarterly", cadence="static", resolution_m=5, stored=True),
    dict(id="ghsl_built", name="GHSL Built-Up Surface",
         source="EC Joint Research Centre", licence="CC BY 4.0",
         url="https://ghsl.jrc.ec.europa.eu/",
         native_cadence="5 years", cadence="5 years", resolution_m=100, stored=True),
    dict(id="os_open", name="OS OpenData (Roads, Rivers, Buildings)",
         source="Ordnance Survey", licence="OGL v3",
         url="https://osdatahub.os.uk/downloads/open",
         native_cadence="biannual", cadence="static", resolution_m=10, stored=True),
    dict(id="worldpop", name="WorldPop Population Density",
         source="WorldPop / Univ. Southampton", licence="CC BY 4.0",
         url="https://www.worldpop.org/",
         native_cadence="annual", cadence="annual", resolution_m=100, stored=True),
    dict(id="ons_imd", name="Indices of Multiple Deprivation",
         source="ONS / MHCLG", licence="OGL v3",
         url="https://www.gov.uk/government/statistics/english-indices-of-deprivation-2019",
         native_cadence="~4 years", cadence="periodic", resolution_m=None, stored=True),
    dict(id="land_registry_ppd", name="HM Land Registry Price Paid Data",
         source="HM Land Registry", licence="OGL v3",
         url="https://landregistry.data.gov.uk/",
         native_cadence="monthly", cadence="monthly", resolution_m=None, stored=False),
    dict(id="soilgrids", name="SoilGrids 250m",
         source="ISRIC World Soil Information", licence="CC BY 4.0",
         url="https://soilgrids.org/",
         native_cadence="static", cadence="static", resolution_m=250, stored=True),
    dict(id="bgs_geology", name="BGS Geology & Radon",
         source="British Geological Survey", licence="BGS Open Licence",
         url="https://www.bgs.ac.uk/",
         native_cadence="static", cadence="static", resolution_m=50, stored=True),
    dict(id="copernicus_air", name="CAMS European Air Quality",
         source="Copernicus Atmosphere Monitoring Service", licence="Copernicus licence",
         url="https://ads.atmosphere.copernicus.eu/",
         native_cadence="hourly", cadence="monthly", resolution_m=10000, stored=True),
    dict(id="natural_england", name="Natural England Designated Sites",
         source="Natural England", licence="OGL v3",
         url="https://naturalengland-defra.opendata.arcgis.com/",
         native_cadence="monthly", cadence="static", resolution_m=None, stored=True),
    dict(id="viirs_nightlights", name="VIIRS Nighttime Lights",
         source="NOAA / Colorado School of Mines", licence="Public domain",
         url="https://eogdata.mines.edu/products/vnl/",
         native_cadence="monthly", cadence="monthly", resolution_m=500, stored=True),
    dict(id="pvgis", name="PVGIS Solar Irradiation",
         source="EC Joint Research Centre", licence="Open",
         url="https://re.jrc.ec.europa.eu/pvg_tools/",
         native_cadence="static", cadence="static", resolution_m=5000, stored=False),

    # ------------------------------------------------------------------
    # Property, planning and market. These are tabular or vector sources
    # queried live rather than rasters we hold, which is why almost all of
    # them are `stored=False` — the storage argument in TECHNICAL_PLAN.md 8.2
    # is about imagery, and a planning register is not imagery.
    # ------------------------------------------------------------------
    dict(id="planning_data", name="Planning Data Platform",
         source="MHCLG", licence="OGL v3",
         url="https://www.planning.data.gov.uk/",
         native_cadence="weekly", cadence="monthly", resolution_m=None, stored=False),
    dict(id="historic_england", name="Historic England Heritage Register",
         source="Historic England", licence="OGL v3",
         url="https://historicengland.org.uk/listing/the-list/data-downloads/",
         native_cadence="monthly", cadence="static", resolution_m=None, stored=False),
    dict(id="epc_register", name="Energy Performance Certificate Register",
         source="MHCLG Open Data Communities", licence="OGL v3",
         url="https://epc.opendatacommunities.org/",
         native_cadence="daily", cadence="monthly", resolution_m=None, stored=False),
    dict(id="voa_rating", name="VOA Rating & Council Tax Lists",
         source="Valuation Office Agency", licence="OGL v3",
         url="https://www.gov.uk/government/organisations/valuation-office-agency",
         native_cadence="quarterly", cadence="periodic", resolution_m=None, stored=False),
    dict(id="ons_housing", name="ONS Housing, Rents & Earnings",
         source="Office for National Statistics", licence="OGL v3",
         url="https://www.ons.gov.uk/peoplepopulationandcommunity/housing",
         native_cadence="monthly", cadence="monthly", resolution_m=None, stored=False),
    dict(id="os_ngd_buildings", name="OS NGD Buildings & Heights",
         source="Ordnance Survey", licence="OS Data Hub licence",
         url="https://osdatahub.os.uk/",
         native_cadence="quarterly", cadence="static", resolution_m=1, stored=True),

    # ------------------------------------------------------------------
    # Infrastructure and utilities
    # ------------------------------------------------------------------
    dict(id="neso_grid", name="NESO / DNO Network Capacity",
         source="National Energy System Operator and DNOs", licence="Varies by DNO",
         url="https://www.neso.energy/data-portal",
         native_cadence="quarterly", cadence="periodic", resolution_m=None, stored=False),
    dict(id="ofcom_connected", name="Ofcom Connected Nations",
         source="Ofcom", licence="OGL v3",
         url="https://www.ofcom.org.uk/research-and-data/multi-sector-research/infrastructure-research",
         native_cadence="6 months", cadence="periodic", resolution_m=None, stored=False),
    dict(id="ncr_chargepoints", name="National Chargepoint Registry",
         source="Department for Transport", licence="OGL v3",
         url="https://www.gov.uk/guidance/find-and-use-data-on-electric-vehicle-chargepoints",
         native_cadence="daily", cadence="monthly", resolution_m=None, stored=False),
    dict(id="ea_water", name="EA Water Resources & Abstraction",
         source="Environment Agency", licence="OGL v3",
         url="https://environment.data.gov.uk/",
         native_cadence="annual", cadence="annual", resolution_m=None, stored=False),

    # ------------------------------------------------------------------
    # Transport and access
    # ------------------------------------------------------------------
    dict(id="naptan_transit", name="NaPTAN Public Transport Access Nodes",
         source="Department for Transport", licence="OGL v3",
         url="https://beta-naptan.dft.gov.uk/",
         native_cadence="daily", cadence="static", resolution_m=None, stored=False),
    dict(id="dft_traffic", name="DfT Road Traffic Statistics",
         source="Department for Transport", licence="OGL v3",
         url="https://roadtraffic.dft.gov.uk/",
         native_cadence="annual", cadence="annual", resolution_m=None, stored=False),
    dict(id="rail_usage", name="ORR Station Usage & Service Data",
         source="Office of Rail and Road", licence="OGL v3",
         url="https://dataportal.orr.gov.uk/",
         native_cadence="annual", cadence="annual", resolution_m=None, stored=False),

    # ------------------------------------------------------------------
    # People, services and safety
    # ------------------------------------------------------------------
    dict(id="ons_census", name="ONS Census 2021",
         source="Office for National Statistics", licence="OGL v3",
         url="https://www.ons.gov.uk/census",
         native_cadence="10 years", cadence="periodic", resolution_m=None, stored=False),
    dict(id="police_crime", name="Police.uk Street-Level Crime",
         source="Home Office / police forces", licence="OGL v3",
         url="https://data.police.uk/",
         native_cadence="monthly", cadence="monthly", resolution_m=None, stored=False),
    dict(id="dfe_schools", name="DfE School Performance & Capacity",
         source="Department for Education", licence="OGL v3",
         url="https://www.compare-school-performance.service.gov.uk/",
         native_cadence="annual", cadence="annual", resolution_m=None, stored=False),
    dict(id="nhs_estates", name="NHS Service Locations",
         source="NHS England", licence="OGL v3",
         url="https://www.nhs.uk/about-us/nhs-website-datasets/",
         native_cadence="quarterly", cadence="periodic", resolution_m=None, stored=False),

    # ------------------------------------------------------------------
    # Ground risk and liability
    # ------------------------------------------------------------------
    dict(id="bgs_geosure", name="BGS GeoSure Ground Stability",
         source="British Geological Survey", licence="BGS Open Licence",
         url="https://www.bgs.ac.uk/datasets/geosure/",
         native_cadence="static", cadence="static", resolution_m=50, stored=True),
    dict(id="coal_authority", name="Coal Authority Mining Data",
         source="The Coal Authority", licence="OGL v3",
         url="https://www.gov.uk/government/organisations/the-coal-authority",
         native_cadence="static", cadence="static", resolution_m=None, stored=False),
    dict(id="ea_landfill", name="EA Historic Landfill & Permits",
         source="Environment Agency", licence="OGL v3",
         url="https://environment.data.gov.uk/",
         native_cadence="quarterly", cadence="periodic", resolution_m=None, stored=False),

    # ------------------------------------------------------------------
    # Energy, land and growing
    # ------------------------------------------------------------------
    dict(id="wind_atlas", name="Global Wind Atlas 3",
         source="DTU Wind Energy / World Bank", licence="CC BY 4.0",
         url="https://globalwindatlas.info/",
         native_cadence="static", cadence="static", resolution_m=250, stored=True),
    dict(id="canopy_height", name="ETH Global Canopy Height",
         source="ETH Zurich", licence="CC BY 4.0",
         url="https://langnico.github.io/globalcanopyheight/",
         native_cadence="5 years", cadence="5 years", resolution_m=10, stored=True),
    dict(id="forestry_nfi", name="National Forest Inventory",
         source="Forestry Commission", licence="OGL v3",
         url="https://www.forestresearch.gov.uk/tools-and-resources/national-forest-inventory/",
         native_cadence="annual", cadence="annual", resolution_m=None, stored=False),
    dict(id="defra_agland", name="Defra Agricultural Land Classification",
         source="Defra / Natural England", licence="OGL v3",
         url="https://www.data.gov.uk/dataset/provisional-agricultural-land-classification-alc",
         native_cadence="static", cadence="static", resolution_m=None, stored=False),
]

BASE_BY_ID = {b["id"]: b for b in BASES}


# ---------------------------------------------------------------------------
# Attribution and commercial terms
# ---------------------------------------------------------------------------
# Almost every licence here is free for commercial use *conditional on
# attribution in a specified form*. Naming the source is not enough: OGL wants
# the Crown copyright line, Copernicus wants "modified Copernicus … data",
# Ordnance Survey wants its own wording. Displaying the licence name while
# omitting the required notice is the most common way an otherwise permissive
# licence gets breached, and it is the state this app was in.
#
# These strings travel with the numbers — into the UI, and into every export,
# because a CSV that leaves the building carries the obligation with it.
#
# `commercial` is a triage flag for COMMERCIAL_READINESS.md, not legal advice:
#   "yes"    — the licence text plainly permits commercial use with attribution
#   "verify" — something needs confirming before money changes hands
# ---------------------------------------------------------------------------
from datetime import date as _date  # noqa: E402

_YEAR = _date.today().year

ATTRIBUTION: Dict[str, str] = {
    "sentinel2_sr": "Contains modified Copernicus Sentinel data {year}",
    "sentinel1_sar": "Contains modified Copernicus Sentinel data {year}",
    "esa_worldcover": "© ESA WorldCover project, licensed under CC BY 4.0",
    "lidar_dtm": "© Environment Agency copyright and/or database right {year}. "
                 "All rights reserved. Licensed under the Open Government "
                 "Licence v3.0.",
    "modis_lst": "MODIS data courtesy of NASA LP DAAC, USGS/EROS Center",
    "era5_land": "Contains modified Copernicus Climate Change Service "
                 "information {year}",
    "haduk_precip": "© Crown copyright, Met Office. Contains public sector "
                    "information licensed under the Open Government Licence v3.0",
    "ea_hydrology": "© Environment Agency copyright and/or database right "
                    "{year}. All rights reserved. Licensed under the Open "
                    "Government Licence v3.0.",
    "jrc_surface_water": "© European Union, Joint Research Centre — "
                         "Global Surface Water",
    "ea_flood_zones": "© Environment Agency copyright and/or database right "
                      "{year}. All rights reserved. Licensed under the Open "
                      "Government Licence v3.0.",
    "ghsl_built": "© European Union, 1995–{year} — Global Human Settlement "
                  "Layer, Joint Research Centre",
    "os_open": "Contains OS data © Crown copyright and database right {year}",
    "worldpop": "© WorldPop, University of Southampton, licensed under CC BY 4.0",
    "ons_imd": "Source: Office for National Statistics and MHCLG, licensed "
               "under the Open Government Licence v3.0",
    "land_registry_ppd": "Contains HM Land Registry data © Crown copyright and "
                         "database right {year}. This data is licensed under "
                         "the Open Government Licence v3.0.",
    "soilgrids": "© ISRIC — World Soil Information (SoilGrids), licensed "
                 "under CC BY 4.0",
    "bgs_geology": "Contains British Geological Survey materials © UKRI {year}",
    "copernicus_air": "Contains modified Copernicus Atmosphere Monitoring "
                      "Service information {year}",
    "natural_england": "© Natural England copyright. Contains Ordnance Survey "
                       "data © Crown copyright and database right {year}",
    "viirs_nightlights": "VIIRS nighttime lights — NOAA/NCEI and Colorado "
                         "School of Mines",
    "pvgis": "© European Union, 2001–{year}. PVGIS, Joint Research Centre",
    "planning_data": "Contains public sector information licensed under the "
                     "Open Government Licence v3.0 (planning.data.gov.uk, MHCLG)",
    "historic_england": "© Historic England {year}. Contains Ordnance Survey data "
                        "© Crown copyright and database right {year}",
    "epc_register": "Contains Energy Performance of Buildings data © Crown "
                    "copyright, licensed under the Open Government Licence v3.0",
    "voa_rating": "Contains Valuation Office Agency data © Crown copyright and "
                  "database right {year}, licensed under the Open Government "
                  "Licence v3.0",
    "ons_housing": "Source: Office for National Statistics, licensed under the "
                   "Open Government Licence v3.0",
    "os_ngd_buildings": "Contains OS data © Crown copyright and database right "
                        "{year}",
    "neso_grid": "Contains network capacity data published by NESO and the "
                 "electricity distribution network operators",
    "ofcom_connected": "Contains Ofcom Connected Nations data, licensed under "
                       "the Open Government Licence v3.0",
    "ncr_chargepoints": "Contains National Chargepoint Registry data © Crown "
                        "copyright, licensed under the Open Government Licence v3.0",
    "ea_water": "© Environment Agency copyright and/or database right {year}. "
                "All rights reserved. Licensed under the Open Government "
                "Licence v3.0.",
    "naptan_transit": "Contains NaPTAN data © Crown copyright, licensed under "
                      "the Open Government Licence v3.0",
    "dft_traffic": "Contains Department for Transport road traffic statistics, "
                   "licensed under the Open Government Licence v3.0",
    "rail_usage": "Contains Office of Rail and Road data, licensed under the "
                  "Open Government Licence v3.0",
    "ons_census": "Source: Office for National Statistics, Census 2021, "
                  "licensed under the Open Government Licence v3.0",
    "police_crime": "Contains public sector information licensed under the Open "
                    "Government Licence v3.0 (data.police.uk)",
    "dfe_schools": "Contains Department for Education data, licensed under the "
                   "Open Government Licence v3.0",
    "nhs_estates": "Contains NHS England data, licensed under the Open "
                   "Government Licence v3.0",
    "bgs_geosure": "Contains British Geological Survey materials © UKRI {year}",
    "coal_authority": "Contains Coal Authority data © Crown copyright and "
                      "database right {year}, licensed under the Open "
                      "Government Licence v3.0",
    "ea_landfill": "© Environment Agency copyright and/or database right {year}. "
                   "All rights reserved. Licensed under the Open Government "
                   "Licence v3.0.",
    "wind_atlas": "Global Wind Atlas 3.0, DTU Wind Energy and the World Bank "
                  "Group, licensed under CC BY 4.0",
    "canopy_height": "Global canopy height map © ETH Zurich, licensed under "
                     "CC BY 4.0",
    "forestry_nfi": "Contains Forestry Commission information licensed under "
                    "the Open Government Licence v3.0",
    "defra_agland": "Contains Defra and Natural England data © Crown copyright "
                    "and database right {year}, licensed under the Open "
                    "Government Licence v3.0",
}

# The two Sentinel entries are flagged deliberately. They are recorded here as
# CC BY-SA 3.0 IGO, and share-alike on a commercial derived product would be a
# genuine constraint — but Copernicus Sentinel data is generally distributed
# under the Copernicus terms (Regulation 1159/2013), which permit commercial
# reuse with attribution and impose no share-alike. One of those two things is
# wrong, and which one matters, so it is marked for confirmation rather than
# quietly assumed either way.
# OS NGD is a paid Data Hub product whose licence depends on the plan taken,
# and DNO capacity data is published under a patchwork of per-operator terms
# rather than one licence — both are flagged rather than assumed.
_VERIFY = ("sentinel2_sr", "sentinel1_sar", "os_ngd_buildings", "neso_grid")

COMMERCIAL_USE: Dict[str, str] = {
    b["id"]: ("verify" if b["id"] in _VERIFY else "yes")
    for b in BASES
}

for _b in BASES:
    _b["attribution"] = ATTRIBUTION[_b["id"]].format(year=_YEAR)
    _b["commercial"] = COMMERCIAL_USE[_b["id"]]


def attributions_for(base_ids) -> List[str]:
    """Deduplicated attribution lines for a set of bases, ready to display."""
    seen, out = set(), []
    for bid in base_ids:
        text = BASE_BY_ID[bid]["attribution"]
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out

# ---------------------------------------------------------------------------
# Factors.
#
# Compact tuple form, expanded below. Fields:
#   id, name, base, group, unit, kind, cadence, lo, hi, derived, note
#
# `lo`/`hi` are the plausible England range — they drive colour ramps, axis
# defaults and the mock generator, so they are not decoration.
#
# `kind` is load-bearing: 'categorical' factors must never be averaged. The
# mean of two land-cover class codes is meaningless, and this flag is what
# stops the table, the charts and the reducers from doing it.
# ---------------------------------------------------------------------------
_F = [
    # --- Vegetation (Sentinel-2) ------------------------------------------
    ("ndvi", "NDVI (vegetation vigour)", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.2, 0.95, True, "Normalised difference of NIR and red. The workhorse greenness index."),
    ("evi", "EVI (enhanced vegetation)", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.1, 0.9, True, "Less prone to saturation than NDVI over dense canopy."),
    ("savi", "SAVI (soil-adjusted)", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.1, 0.85, True, "Corrects for soil brightness on sparse cover."),
    ("msavi", "MSAVI (modified soil-adjusted)", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.1, 0.9, True, "Self-adjusting soil correction; good on bare ground."),
    ("gndvi", "GNDVI (green NDVI)", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.1, 0.85, True, "Green-band variant, more sensitive to chlorophyll."),
    ("ndmi", "NDMI (moisture)", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.5, 0.6, True, "Canopy water content from NIR and SWIR."),
    ("nbr", "NBR (burn ratio)", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.6, 0.9, True, "Fire severity and post-burn recovery."),
    ("chlorophyll_index", "Chlorophyll index", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", 0.0, 8.0, True, "Red-edge chlorophyll proxy; early stress signal."),
    ("leaf_area_index", "Leaf area index", "sentinel2_sr", "Vegetation", "m²/m²", "continuous", "monthly", 0.0, 7.0, True, "Modelled canopy leaf area per unit ground."),
    ("greenness", "Tasselled-cap greenness", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.2, 0.6, True, "Canopy vigour component of the tasselled-cap transform."),
    ("wetness", "Tasselled-cap wetness", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.4, 0.3, True, "Surface moisture component."),
    ("brightness", "Tasselled-cap brightness", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", 0.0, 0.7, True, "Bare-soil and albedo component."),
    ("bare_soil_index", "Bare soil index", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.5, 0.5, True, "Exposed soil fraction proxy."),
    ("ndbi", "NDBI (built-up index)", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.5, 0.5, True, "Spectral built-up signal from SWIR and NIR."),
    ("ndwi", "NDWI (open water)", "sentinel2_sr", "Vegetation", "index", "continuous", "monthly", -0.8, 0.8, True, "Open-water delineation from green and NIR."),

    # --- Land cover (ESA WorldCover) --------------------------------------
    ("lc_tree_pct", "Tree cover", "esa_worldcover", "Land cover", "%", "continuous", "annual", 0.0, 100.0, True, "Share of the area classed as tree cover."),
    ("lc_shrub_pct", "Shrubland", "esa_worldcover", "Land cover", "%", "continuous", "annual", 0.0, 60.0, True, "Share classed as shrubland."),
    ("lc_grass_pct", "Grassland", "esa_worldcover", "Land cover", "%", "continuous", "annual", 0.0, 100.0, True, "Share classed as grassland."),
    ("lc_crop_pct", "Cropland", "esa_worldcover", "Land cover", "%", "continuous", "annual", 0.0, 100.0, True, "Share classed as cropland."),
    ("lc_built_pct", "Built-up", "esa_worldcover", "Land cover", "%", "continuous", "annual", 0.0, 100.0, True, "Share classed as built-up."),
    ("lc_bare_pct", "Bare / sparse", "esa_worldcover", "Land cover", "%", "continuous", "annual", 0.0, 40.0, True, "Share classed as bare or sparsely vegetated."),
    ("lc_water_pct", "Open water", "esa_worldcover", "Land cover", "%", "continuous", "annual", 0.0, 100.0, True, "Share classed as permanent water."),
    ("lc_wetland_pct", "Wetland", "esa_worldcover", "Land cover", "%", "continuous", "annual", 0.0, 50.0, True, "Share classed as herbaceous wetland."),
    ("lc_dominant", "Dominant land cover", "esa_worldcover", "Land cover", "class", "categorical", "annual", None, None, True, "Most common class by area. Never averaged."),
    ("lc_diversity", "Land cover diversity", "esa_worldcover", "Land cover", "Shannon H", "continuous", "annual", 0.0, 2.2, True, "Shannon entropy across classes — habitat mosaic proxy."),
    ("lc_fragmentation", "Habitat fragmentation", "esa_worldcover", "Land cover", "edge m/ha", "continuous", "annual", 0.0, 400.0, True, "Edge density between cover patches."),
    ("lc_change_rate", "Land cover change rate", "esa_worldcover", "Land cover", "%/yr", "continuous", "annual", 0.0, 12.0, True, "Share of area changing class year on year."),

    # --- Terrain (LIDAR DTM) ----------------------------------------------
    ("elevation_mean", "Elevation (mean)", "lidar_dtm", "Terrain", "m", "continuous", "static", -5.0, 950.0, False, "Mean height above ordnance datum."),
    ("elevation_min", "Elevation (min)", "lidar_dtm", "Terrain", "m", "continuous", "static", -5.0, 900.0, True, "Lowest point in the area."),
    ("elevation_max", "Elevation (max)", "lidar_dtm", "Terrain", "m", "continuous", "static", 0.0, 980.0, True, "Highest point in the area."),
    ("elevation_range", "Relief (max − min)", "lidar_dtm", "Terrain", "m", "continuous", "static", 0.0, 600.0, True, "Vertical range across the area."),
    ("slope_mean", "Slope (mean)", "lidar_dtm", "Terrain", "°", "continuous", "static", 0.0, 45.0, True, "Mean gradient — buildability and erosion risk."),
    ("slope_max", "Slope (max)", "lidar_dtm", "Terrain", "°", "continuous", "static", 0.0, 70.0, True, "Steepest gradient present."),
    ("aspect_dominant", "Dominant aspect", "lidar_dtm", "Terrain", "class", "categorical", "static", None, None, True, "Prevailing slope direction. Circular — never averaged."),
    ("ruggedness", "Terrain ruggedness (TRI)", "lidar_dtm", "Terrain", "index", "continuous", "static", 0.0, 60.0, True, "Mean elevation difference between neighbouring cells."),
    ("tpi", "Topographic position", "lidar_dtm", "Terrain", "index", "continuous", "static", -30.0, 30.0, True, "Ridge (positive) to valley (negative) position."),
    ("curvature", "Profile curvature", "lidar_dtm", "Terrain", "1/100 m", "continuous", "static", -5.0, 5.0, True, "Convex or concave surface form; drives runoff."),
    ("flow_accumulation", "Flow accumulation", "lidar_dtm", "Terrain", "cells", "continuous", "static", 0.0, 100000.0, True, "Upslope contributing area — where water collects."),
    ("hand", "Height above drainage", "lidar_dtm", "Terrain", "m", "continuous", "static", 0.0, 120.0, True, "Elevation above nearest watercourse. Strong flood predictor."),
    ("solar_aspect_score", "Solar aspect score", "lidar_dtm", "Terrain", "0–1", "continuous", "static", 0.0, 1.0, True, "South-facing, low-shade favourability for solar."),

    # --- Temperature (MODIS LST + ERA5-Land) ------------------------------
    ("lst_day", "Land surface temp (day)", "modis_lst", "Temperature", "°C", "continuous", "monthly", -5.0, 42.0, False, "Daytime skin temperature."),
    ("lst_night", "Land surface temp (night)", "modis_lst", "Temperature", "°C", "continuous", "monthly", -10.0, 22.0, False, "Night-time skin temperature."),
    ("lst_diurnal_range", "Diurnal temp range", "modis_lst", "Temperature", "°C", "continuous", "monthly", 0.0, 25.0, True, "Day minus night — thermal inertia proxy."),
    ("heat_anomaly", "Urban heat anomaly", "modis_lst", "Temperature", "°C", "continuous", "monthly", -4.0, 9.0, True, "Excess over the surrounding rural baseline."),
    ("air_temp_mean", "Air temperature (mean)", "era5_land", "Temperature", "°C", "continuous", "monthly", -4.0, 24.0, False, "2 m air temperature."),
    ("air_temp_max", "Air temperature (max)", "era5_land", "Temperature", "°C", "continuous", "monthly", 0.0, 38.0, True, "Monthly maximum 2 m air temperature."),
    ("air_temp_min", "Air temperature (min)", "era5_land", "Temperature", "°C", "continuous", "monthly", -12.0, 16.0, True, "Monthly minimum 2 m air temperature."),
    ("growing_degree_days", "Growing degree days", "era5_land", "Temperature", "°C·day", "continuous", "monthly", 0.0, 420.0, True, "Accumulated warmth above 5 °C — crop development."),
    ("frost_days", "Frost days", "era5_land", "Temperature", "days", "continuous", "monthly", 0.0, 28.0, True, "Days with minimum below 0 °C."),

    # --- Water & precipitation --------------------------------------------
    ("precip_total", "Precipitation total", "haduk_precip", "Water", "mm", "continuous", "monthly", 0.0, 320.0, False, "Monthly rainfall total."),
    ("precip_anomaly", "Rainfall anomaly", "haduk_precip", "Water", "%", "continuous", "monthly", -100.0, 200.0, True, "Departure from the 1991–2020 monthly normal."),
    ("dry_days", "Dry days", "haduk_precip", "Water", "days", "continuous", "monthly", 0.0, 31.0, True, "Days below 1 mm."),
    ("wet_days", "Wet days", "haduk_precip", "Water", "days", "continuous", "monthly", 0.0, 31.0, True, "Days at or above 1 mm."),
    ("max_daily_precip", "Heaviest daily rainfall", "haduk_precip", "Water", "mm", "continuous", "monthly", 0.0, 110.0, True, "Wettest single day — surface-water flood driver."),
    ("spi_3month", "Drought index (SPI-3)", "haduk_precip", "Water", "σ", "continuous", "monthly", -3.0, 3.0, True, "Standardised precipitation over three months."),

    # Measured at a gauge rather than modelled onto a grid. The note names the
    # trade in the factor itself, because "measured" reads as strictly better
    # than "gridded" and for an area it often is not.
    ("ea_rain_total", "Rainfall (gauge)", "ea_hydrology", "Water", "mm", "continuous", "monthly", 0.0, 260.0, False, "Monthly total at the nearest EA rain gauge. A point measurement, not an average over the site."),
    ("ea_rain_max_daily", "Heaviest day (gauge)", "ea_hydrology", "Water", "mm", "continuous", "monthly", 0.0, 90.0, True, "Wettest single day in the month at that gauge."),
    ("ea_rain_wet_days", "Wet days (gauge)", "ea_hydrology", "Water", "days", "continuous", "monthly", 0.0, 31.0, True, "Days of 1 mm or more — the WMO threshold, so this is comparable with published statistics."),
    ("ea_rain_dry_days", "Dry days (gauge)", "ea_hydrology", "Water", "days", "continuous", "monthly", 0.0, 31.0, True, "Days below 1 mm at that gauge."),
    ("soil_moisture", "Soil moisture", "era5_land", "Water", "m³/m³", "continuous", "monthly", 0.05, 0.5, False, "Volumetric water in the top soil layer."),
    ("evapotranspiration", "Evapotranspiration", "era5_land", "Water", "mm", "continuous", "monthly", 0.0, 140.0, False, "Water returned to atmosphere by soil and plants."),
    ("humidity", "Relative humidity", "era5_land", "Water", "%", "continuous", "monthly", 55.0, 98.0, True, "Mean monthly relative humidity."),

    # --- Surface water & flood --------------------------------------------
    ("water_occurrence", "Surface water occurrence", "jrc_surface_water", "Flood & water", "%", "continuous", "annual", 0.0, 100.0, False, "Share of observations showing water present."),
    ("water_seasonality", "Water seasonality", "jrc_surface_water", "Flood & water", "months", "continuous", "annual", 0.0, 12.0, False, "Months per year with water present."),
    ("water_change", "Surface water change", "jrc_surface_water", "Flood & water", "%", "continuous", "annual", -60.0, 60.0, True, "Gain or loss against the long-term baseline."),
    ("flood_zone2_pct", "Flood Zone 2 coverage", "ea_flood_zones", "Flood & water", "%", "continuous", "static", 0.0, 100.0, True, "Share in the 1-in-1000-year fluvial extent."),
    ("flood_zone3_pct", "Flood Zone 3 coverage", "ea_flood_zones", "Flood & water", "%", "continuous", "static", 0.0, 100.0, True, "Share in the 1-in-100-year fluvial extent."),
    ("surface_water_risk", "Surface water flood risk", "ea_flood_zones", "Flood & water", "0–1", "continuous", "static", 0.0, 1.0, True, "EA risk of flooding from surface water."),
    ("reservoir_risk", "Reservoir flood risk", "ea_flood_zones", "Flood & water", "0–1", "continuous", "static", 0.0, 1.0, True, "Extent of reservoir inundation scenarios."),
    ("distance_to_water", "Distance to watercourse", "os_open", "Flood & water", "m", "continuous", "static", 0.0, 6000.0, True, "Straight-line distance to the nearest river or stream."),

    # --- Built environment -------------------------------------------------
    ("built_pct", "Built-up surface", "ghsl_built", "Built environment", "%", "continuous", "5 years", 0.0, 100.0, False, "Impervious built surface share."),
    ("built_volume", "Built volume", "ghsl_built", "Built environment", "m³/ha", "continuous", "5 years", 0.0, 90000.0, False, "Total built volume per hectare."),
    ("built_change_rate", "Built-up change rate", "ghsl_built", "Built environment", "%/yr", "continuous", "5 years", -2.0, 12.0, True, "Rate of built surface growth."),
    ("impervious_pct", "Impervious surface", "ghsl_built", "Built environment", "%", "continuous", "5 years", 0.0, 100.0, True, "Sealed ground — runoff and heat driver."),
    ("building_density", "Building density", "os_open", "Built environment", "bldg/ha", "continuous", "static", 0.0, 60.0, True, "Building footprints per hectare."),
    ("road_density", "Road density", "os_open", "Built environment", "km/km²", "continuous", "static", 0.0, 22.0, True, "Total road length per unit area."),
    ("distance_a_road", "Distance to A road", "os_open", "Built environment", "m", "continuous", "static", 0.0, 15000.0, True, "Straight-line distance to the nearest A road."),
    ("distance_motorway", "Distance to motorway", "os_open", "Built environment", "m", "continuous", "static", 0.0, 60000.0, True, "Straight-line distance to the nearest motorway."),
    ("distance_railway", "Distance to railway", "os_open", "Built environment", "m", "continuous", "static", 0.0, 40000.0, True, "Straight-line distance to the nearest railway line."),

    # --- Population & socioeconomic ---------------------------------------
    ("population_density", "Population density", "worldpop", "People & economy", "people/km²", "continuous", "annual", 0.0, 16000.0, False, "Modelled residential population."),
    ("population_change", "Population change", "worldpop", "People & economy", "%/yr", "continuous", "annual", -5.0, 12.0, True, "Year-on-year population growth."),
    ("imd_score", "Deprivation score (IMD)", "ons_imd", "People & economy", "score", "continuous", "periodic", 0.5, 92.0, False, "Overall index of multiple deprivation."),
    ("imd_income_decile", "IMD income decile", "ons_imd", "People & economy", "decile", "continuous", "periodic", 1.0, 10.0, False, "1 = most deprived, 10 = least."),
    ("imd_employment_decile", "IMD employment decile", "ons_imd", "People & economy", "decile", "continuous", "periodic", 1.0, 10.0, False, "1 = most deprived, 10 = least."),
    ("imd_health_decile", "IMD health decile", "ons_imd", "People & economy", "decile", "continuous", "periodic", 1.0, 10.0, False, "1 = most deprived, 10 = least."),
    ("imd_education_decile", "IMD education decile", "ons_imd", "People & economy", "decile", "continuous", "periodic", 1.0, 10.0, False, "1 = most deprived, 10 = least."),
    ("avg_sale_price", "Average sale price", "land_registry_ppd", "People & economy", "£", "continuous", "monthly", 60000.0, 1400000.0, False, "Mean residential transaction price."),
    ("price_per_m2", "Price per m²", "land_registry_ppd", "People & economy", "£/m²", "continuous", "monthly", 900.0, 14000.0, True, "Sale price normalised by floor area."),
    ("transaction_count", "Transaction count", "land_registry_ppd", "People & economy", "sales", "continuous", "monthly", 0.0, 400.0, False, "Residential sales completed in the month."),
    ("price_change_yoy", "Price change (YoY)", "land_registry_ppd", "People & economy", "%", "continuous", "monthly", -25.0, 30.0, True, "Year-on-year change in average price."),

    # --- Soil & geology ----------------------------------------------------
    ("soil_ph", "Soil pH", "soilgrids", "Soil & geology", "pH", "continuous", "static", 3.8, 8.4, False, "Topsoil acidity or alkalinity."),
    ("soil_organic_carbon", "Soil organic carbon", "soilgrids", "Soil & geology", "g/kg", "continuous", "static", 5.0, 180.0, False, "Topsoil carbon content — fertility and sequestration."),
    ("soil_clay_pct", "Clay content", "soilgrids", "Soil & geology", "%", "continuous", "static", 3.0, 60.0, False, "Clay fraction of topsoil."),
    ("soil_sand_pct", "Sand content", "soilgrids", "Soil & geology", "%", "continuous", "static", 3.0, 90.0, False, "Sand fraction of topsoil."),
    ("soil_silt_pct", "Silt content", "soilgrids", "Soil & geology", "%", "continuous", "static", 3.0, 70.0, False, "Silt fraction of topsoil."),
    ("soil_bulk_density", "Soil bulk density", "soilgrids", "Soil & geology", "kg/m³", "continuous", "static", 800.0, 1700.0, False, "Compaction proxy; affects drainage and rooting."),
    ("soil_water_capacity", "Available water capacity", "soilgrids", "Soil & geology", "mm/m", "continuous", "static", 40.0, 220.0, True, "Water the soil can hold for plant use."),
    ("bedrock_class", "Bedrock geology", "bgs_geology", "Soil & geology", "class", "categorical", "static", None, None, False, "Dominant bedrock unit. Never averaged."),
    ("superficial_deposits", "Superficial deposits", "bgs_geology", "Soil & geology", "class", "categorical", "static", None, None, False, "Dominant drift geology. Never averaged."),
    ("radon_potential", "Radon potential", "bgs_geology", "Soil & geology", "%", "continuous", "static", 0.0, 30.0, False, "Share of homes estimated above the action level."),

    # --- Air quality -------------------------------------------------------
    ("no2", "Nitrogen dioxide", "copernicus_air", "Air quality", "µg/m³", "continuous", "monthly", 1.0, 70.0, False, "Traffic and combustion pollutant."),
    ("pm25", "PM2.5", "copernicus_air", "Air quality", "µg/m³", "continuous", "monthly", 2.0, 32.0, False, "Fine particulates; the main health-burden pollutant."),
    ("pm10", "PM10", "copernicus_air", "Air quality", "µg/m³", "continuous", "monthly", 4.0, 48.0, False, "Coarse particulates."),
    ("o3", "Ozone", "copernicus_air", "Air quality", "µg/m³", "continuous", "monthly", 20.0, 110.0, False, "Ground-level ozone; peaks in summer."),
    ("so2", "Sulphur dioxide", "copernicus_air", "Air quality", "µg/m³", "continuous", "monthly", 0.2, 14.0, False, "Industrial and shipping emissions."),

    # --- Radar (Sentinel-1) ------------------------------------------------
    ("sar_vv", "SAR backscatter (VV)", "sentinel1_sar", "Radar", "dB", "continuous", "monthly", -25.0, 2.0, False, "Co-polarised return; cloud-independent."),
    ("sar_vh", "SAR backscatter (VH)", "sentinel1_sar", "Radar", "dB", "continuous", "monthly", -32.0, -5.0, False, "Cross-polarised return; sensitive to canopy volume."),
    ("sar_ratio", "SAR VH/VV ratio", "sentinel1_sar", "Radar", "ratio", "continuous", "monthly", 0.1, 0.9, True, "Structure proxy that works through cloud."),
    ("sar_soil_moisture", "SAR soil moisture", "sentinel1_sar", "Radar", "%", "continuous", "monthly", 5.0, 55.0, True, "Radar-derived near-surface wetness."),
    ("sar_coherence", "SAR coherence", "sentinel1_sar", "Radar", "0–1", "continuous", "monthly", 0.05, 0.95, True, "Interferometric stability — detects ground disturbance."),

    # --- Designations ------------------------------------------------------
    ("sssi_pct", "SSSI coverage", "natural_england", "Designations", "%", "continuous", "static", 0.0, 100.0, True, "Share within Sites of Special Scientific Interest."),
    ("aonb_pct", "National Landscape (AONB)", "natural_england", "Designations", "%", "continuous", "static", 0.0, 100.0, True, "Share within a National Landscape."),
    ("national_park_pct", "National Park", "natural_england", "Designations", "%", "continuous", "static", 0.0, 100.0, True, "Share within a National Park."),
    ("sac_spa_pct", "SAC / SPA coverage", "natural_england", "Designations", "%", "continuous", "static", 0.0, 100.0, True, "Share within European-designated habitat sites."),
    ("ancient_woodland_pct", "Ancient woodland", "natural_england", "Designations", "%", "continuous", "static", 0.0, 60.0, True, "Share on the ancient woodland inventory."),
    ("green_belt_pct", "Green Belt", "natural_england", "Designations", "%", "continuous", "static", 0.0, 100.0, True, "Share within designated Green Belt."),
    ("priority_habitat_pct", "Priority habitat", "natural_england", "Designations", "%", "continuous", "static", 0.0, 90.0, True, "Share on the priority habitat inventory."),

    # --- Night lights ------------------------------------------------------
    ("nightlight_radiance", "Night-time radiance", "viirs_nightlights", "Night lights", "nW/cm²/sr", "continuous", "monthly", 0.0, 120.0, False, "Artificial light emission — activity and sprawl proxy."),
    ("nightlight_change", "Night-time light change", "viirs_nightlights", "Night lights", "%/yr", "continuous", "monthly", -30.0, 40.0, True, "Growth or decline in emitted light."),

    # --- Solar -------------------------------------------------------------
    ("solar_ghi", "Global horizontal irradiance", "pvgis", "Solar", "kWh/m²/yr", "continuous", "static", 750.0, 1250.0, False, "Total annual solar resource."),
    ("solar_pv_potential", "PV generation potential", "pvgis", "Solar", "kWh/kWp/yr", "continuous", "static", 700.0, 1150.0, True, "Expected yield from an optimally tilted array."),
    ("sunshine_hours", "Sunshine hours", "pvgis", "Solar", "hours", "continuous", "static", 1150.0, 1900.0, False, "Mean annual bright sunshine duration."),

    # =====================================================================
    # SECOND HALF OF THE CATALOGUE — the things a site is worth, not just
    # what grows on it.
    #
    # Everything above answers "what is this land like". Everything below
    # answers "what can be done with it, by whom, and at what risk" — which
    # is the question a developer, a lender, an insurer, a grid operator or
    # a farm agent actually arrives with. Same geometry, same timeline, same
    # provenance rules; a different profession reading it.
    # =====================================================================

    # --- Planning & consents ----------------------------------------------
    ("planning_apps", "Planning applications", "planning_data", "Planning & consents", "apps", "continuous", "monthly", 0.0, 60.0, False, "Applications validated in the month within the area."),
    ("planning_approval_rate", "Approval rate", "planning_data", "Planning & consents", "%", "continuous", "monthly", 25.0, 98.0, True, "Share of decided applications approved."),
    ("planning_major_apps", "Major applications", "planning_data", "Planning & consents", "apps", "continuous", "monthly", 0.0, 12.0, True, "Schemes of 10+ dwellings or 1,000+ m²."),
    ("planning_decision_days", "Time to decision", "planning_data", "Planning & consents", "days", "continuous", "monthly", 28.0, 400.0, True, "Mean days from validation to decision."),
    ("planning_appeal_rate", "Appeal rate", "planning_data", "Planning & consents", "%", "continuous", "monthly", 0.0, 30.0, True, "Refusals taken to appeal."),
    ("planning_appeal_success", "Appeal success rate", "planning_data", "Planning & consents", "%", "continuous", "monthly", 0.0, 65.0, True, "Appeals allowed, wholly or in part."),
    ("residential_permissions", "Homes permitted", "planning_data", "Planning & consents", "homes", "continuous", "monthly", 0.0, 800.0, True, "Dwellings with extant permission."),
    ("commercial_permissions", "Commercial floorspace permitted", "planning_data", "Planning & consents", "m²", "continuous", "monthly", 0.0, 40000.0, True, "Non-residential floorspace with extant permission."),
    ("local_plan_allocation", "Local plan allocation", "planning_data", "Planning & consents", "class", "categorical", "periodic", None, None, False, "What the adopted plan allocates this land for. Never averaged."),
    ("conservation_area_pct", "Conservation area", "planning_data", "Planning & consents", "%", "continuous", "static", 0.0, 100.0, True, "Share within a designated conservation area."),
    ("article4_pct", "Article 4 direction", "planning_data", "Planning & consents", "%", "continuous", "static", 0.0, 100.0, True, "Share where permitted development rights are withdrawn."),
    ("tpo_density", "Tree preservation orders", "planning_data", "Planning & consents", "per km²", "continuous", "static", 0.0, 45.0, True, "Density of protected trees and groups."),
    ("brownfield_register_pct", "On the brownfield register", "planning_data", "Planning & consents", "%", "continuous", "annual", 0.0, 100.0, True, "Share on the authority's brownfield land register."),
    ("permitted_dev_headroom", "Permitted development headroom", "planning_data", "Planning & consents", "0–1", "continuous", "static", 0.0, 1.0, True, "How much can be built without a full application."),
    ("listed_building_density", "Listed buildings", "historic_england", "Planning & consents", "per km²", "continuous", "static", 0.0, 70.0, False, "Density of listed structures."),
    ("listed_grade1_count", "Grade I / II* listings", "historic_england", "Planning & consents", "count", "continuous", "static", 0.0, 8.0, True, "Highest-grade listings present."),
    ("scheduled_monument_pct", "Scheduled monuments", "historic_england", "Planning & consents", "%", "continuous", "static", 0.0, 40.0, False, "Share within a scheduled ancient monument."),

    # --- Property market ---------------------------------------------------
    ("median_sale_price", "Median sale price", "land_registry_ppd", "Property market", "£", "continuous", "monthly", 55000.0, 1200000.0, True, "Median residential transaction price — less skewed than the mean."),
    ("price_growth_5yr", "Price growth (5 years)", "land_registry_ppd", "Property market", "%", "continuous", "monthly", -20.0, 90.0, True, "Change against the same month five years earlier."),
    ("sales_velocity", "Sales velocity", "land_registry_ppd", "Property market", "per 1,000 homes", "continuous", "monthly", 0.0, 45.0, True, "Transactions per thousand dwellings — market liquidity."),
    ("new_build_share", "New-build share", "land_registry_ppd", "Property market", "%", "continuous", "monthly", 0.0, 60.0, True, "Share of sales that are new build."),
    ("new_build_premium", "New-build premium", "land_registry_ppd", "Property market", "%", "continuous", "monthly", -5.0, 45.0, True, "New-build price against second-hand stock."),
    ("flat_share", "Flat share", "land_registry_ppd", "Property market", "%", "continuous", "monthly", 0.0, 95.0, True, "Share of sales that are flats or maisonettes."),
    ("rental_median", "Median rent", "ons_housing", "Property market", "£/month", "continuous", "monthly", 400.0, 3200.0, False, "Median private rent for the area."),
    ("rental_growth_yoy", "Rent growth (YoY)", "ons_housing", "Property market", "%", "continuous", "monthly", -6.0, 18.0, True, "Year-on-year change in median rent."),
    ("gross_yield", "Gross rental yield", "ons_housing", "Property market", "%", "continuous", "monthly", 2.0, 12.0, True, "Annual rent against sale price, before costs."),
    ("affordability_ratio", "Affordability ratio", "ons_housing", "Property market", "×earnings", "continuous", "annual", 3.0, 22.0, False, "House price to workplace earnings."),
    ("earnings_median", "Median earnings", "ons_housing", "Property market", "£/yr", "continuous", "annual", 22000.0, 60000.0, False, "Median gross annual pay, workplace-based."),
    ("land_value_residential", "Residential land value", "voa_rating", "Property market", "£/ha", "continuous", "annual", 250000.0, 12000000.0, True, "Indicative value of serviced residential land."),
    ("land_value_industrial", "Industrial land value", "voa_rating", "Property market", "£/ha", "continuous", "annual", 150000.0, 3500000.0, True, "Indicative value of serviced industrial land."),
    ("rateable_value_m2", "Rateable value", "voa_rating", "Property market", "£/m²", "continuous", "periodic", 20.0, 700.0, False, "Mean non-domestic rateable value per square metre."),
    ("business_rates_density", "Business rates base", "voa_rating", "Property market", "£/ha", "continuous", "periodic", 0.0, 900000.0, True, "Rateable value per hectare — commercial intensity."),
    ("commercial_vacancy", "Commercial vacancy", "voa_rating", "Property market", "%", "continuous", "periodic", 0.0, 35.0, True, "Share of rated units recorded as empty."),
    ("council_tax_band_mode", "Modal council tax band", "voa_rating", "Property market", "class", "categorical", "periodic", None, None, False, "Most common band. Never averaged."),

    # --- Buildings & fabric ------------------------------------------------
    ("epc_mean_sap", "Mean EPC score", "epc_register", "Buildings & fabric", "SAP", "continuous", "monthly", 30.0, 92.0, False, "Mean SAP rating of certificated dwellings."),
    ("epc_band_mode", "Modal EPC band", "epc_register", "Buildings & fabric", "class", "categorical", "monthly", None, None, True, "Most common energy band. Never averaged."),
    ("epc_below_c_share", "Below EPC C", "epc_register", "Buildings & fabric", "%", "continuous", "monthly", 5.0, 95.0, True, "Stock failing the proposed rental minimum."),
    ("epc_potential_uplift", "Retrofit headroom", "epc_register", "Buildings & fabric", "SAP points", "continuous", "monthly", 0.0, 35.0, True, "Mean gap between current and potential rating."),
    ("heat_demand_density", "Heat demand density", "epc_register", "Buildings & fabric", "kWh/m²/yr", "continuous", "annual", 60.0, 320.0, True, "Modelled space-heating demand — heat network viability."),
    ("retrofit_cost_index", "Retrofit cost", "epc_register", "Buildings & fabric", "£/dwelling", "continuous", "annual", 4000.0, 45000.0, True, "Indicative cost to reach band C."),
    ("dwelling_age_mode", "Modal dwelling age", "epc_register", "Buildings & fabric", "class", "categorical", "static", None, None, True, "Dominant construction period. Never averaged."),
    ("mean_floor_area", "Mean floor area", "epc_register", "Buildings & fabric", "m²", "continuous", "annual", 45.0, 220.0, False, "Mean certificated dwelling floor area."),
    ("heat_pump_share", "Heat pump share", "epc_register", "Buildings & fabric", "%", "continuous", "monthly", 0.0, 25.0, True, "Certificates recording a heat pump as main heating."),
    ("building_footprint_pct", "Building footprint", "os_ngd_buildings", "Buildings & fabric", "%", "continuous", "static", 0.0, 70.0, False, "Share of the area under a building."),
    ("mean_building_height", "Mean building height", "os_ngd_buildings", "Buildings & fabric", "m", "continuous", "static", 0.0, 40.0, False, "Mean eaves-to-ground height."),
    ("max_building_height", "Tallest building", "os_ngd_buildings", "Buildings & fabric", "m", "continuous", "static", 0.0, 180.0, True, "Height of the tallest structure present."),
    ("plot_ratio", "Plot ratio", "os_ngd_buildings", "Buildings & fabric", "ratio", "continuous", "static", 0.0, 4.0, True, "Floorspace against site area — development intensity."),
    ("roof_area_total", "Roof area", "os_ngd_buildings", "Buildings & fabric", "m²/ha", "continuous", "static", 0.0, 5500.0, True, "Total roof plane per hectare."),
    ("flat_roof_share", "Flat roof share", "os_ngd_buildings", "Buildings & fabric", "%", "continuous", "static", 0.0, 90.0, True, "Roof area that is flat — solar and plant siting."),
    ("rooftop_solar_potential", "Rooftop solar potential", "os_ngd_buildings", "Buildings & fabric", "MWh/yr", "continuous", "static", 0.0, 4000.0, True, "Generation available from suitable roof planes."),
    ("developable_area", "Undeveloped area", "os_ngd_buildings", "Buildings & fabric", "ha", "continuous", "static", 0.0, 250000.0, True, "Area with no building on it — before constraints."),

    # --- Infrastructure & utilities ----------------------------------------
    ("grid_headroom", "Grid connection headroom", "neso_grid", "Infrastructure", "MVA", "continuous", "periodic", 0.0, 120.0, False, "Firm capacity available at the local primary substation."),
    ("distance_substation", "Distance to substation", "neso_grid", "Infrastructure", "m", "continuous", "static", 50.0, 25000.0, True, "Straight-line distance to the nearest primary."),
    ("substation_class", "Nearest substation type", "neso_grid", "Infrastructure", "class", "categorical", "periodic", None, None, True, "What the nearest connection point is. Never averaged."),
    ("grid_connection_cost", "Indicative connection cost", "neso_grid", "Infrastructure", "£k/MVA", "continuous", "periodic", 20.0, 900.0, True, "Reinforcement cost per megavolt-ampere."),
    ("curtailment_risk", "Curtailment risk", "neso_grid", "Infrastructure", "0–1", "continuous", "periodic", 0.0, 1.0, True, "Likelihood generation is constrained off."),
    ("broadband_gigabit_pct", "Gigabit broadband", "ofcom_connected", "Infrastructure", "%", "continuous", "periodic", 0.0, 100.0, False, "Premises able to order a gigabit service."),
    ("broadband_median_speed", "Median download speed", "ofcom_connected", "Infrastructure", "Mbit/s", "continuous", "periodic", 5.0, 900.0, False, "Median measured residential speed."),
    ("broadband_notspot_pct", "Under 10 Mbit/s", "ofcom_connected", "Infrastructure", "%", "continuous", "periodic", 0.0, 40.0, True, "Premises below the universal service obligation."),
    ("mobile_4g_coverage", "4G coverage", "ofcom_connected", "Infrastructure", "%", "continuous", "periodic", 30.0, 100.0, False, "Outdoor coverage from all four operators."),
    ("mobile_5g_coverage", "5G coverage", "ofcom_connected", "Infrastructure", "%", "continuous", "periodic", 0.0, 100.0, False, "Outdoor 5G availability."),
    ("ev_chargepoint_density", "EV chargepoints", "ncr_chargepoints", "Infrastructure", "per 1,000 people", "continuous", "monthly", 0.0, 220.0, False, "Public charging devices per thousand residents."),
    ("water_stress_class", "Water stress", "ea_water", "Infrastructure", "class", "categorical", "annual", None, None, False, "Supply-demand balance of the resource zone. Never averaged."),
    ("abstraction_availability", "Abstraction availability", "ea_water", "Infrastructure", "class", "categorical", "annual", None, None, False, "Whether new abstraction is licensable here. Never averaged."),

    # --- Transport & access -------------------------------------------------
    ("bus_stops_400m", "Bus stops within 400 m", "naptan_transit", "Transport & access", "count", "continuous", "static", 0.0, 45.0, False, "Stops inside the standard walk-to-bus distance."),
    ("bus_frequency", "Bus frequency", "naptan_transit", "Transport & access", "services/hr", "continuous", "annual", 0.0, 40.0, True, "Weekday daytime departures from nearby stops."),
    ("transit_access_score", "Public transport access", "naptan_transit", "Transport & access", "0–100", "continuous", "annual", 0.0, 100.0, True, "Composite of stop density and service frequency."),
    ("distance_rail_station", "Distance to a station", "rail_usage", "Transport & access", "m", "continuous", "static", 100.0, 30000.0, False, "Straight-line distance to the nearest station."),
    ("rail_entries_annual", "Station usage", "rail_usage", "Transport & access", "entries/yr", "continuous", "annual", 0.0, 30000000.0, False, "Annual entries and exits at the nearest station."),
    ("rail_service_frequency", "Train frequency", "rail_usage", "Transport & access", "trains/hr", "continuous", "annual", 0.0, 24.0, True, "Weekday off-peak departures."),
    ("distance_motorway_junction", "Distance to a junction", "os_open", "Transport & access", "m", "continuous", "static", 200.0, 55000.0, True, "Straight-line distance to the nearest motorway junction."),
    ("hgv_access_class", "HGV access", "os_open", "Transport & access", "class", "categorical", "static", None, None, True, "How a lorry reaches the site. Never averaged."),
    ("aadt_nearest", "Traffic on the nearest road", "dft_traffic", "Transport & access", "vehicles/day", "continuous", "annual", 100.0, 140000.0, False, "Annual average daily flow — passing trade and noise."),
    ("cycle_network_density", "Cycle network", "os_open", "Transport & access", "km/km²", "continuous", "static", 0.0, 12.0, True, "Signed or segregated cycle route density."),
    ("walk_score", "Walkable amenities", "os_open", "Transport & access", "0–100", "continuous", "static", 0.0, 100.0, True, "Everyday destinations reachable on foot."),
    ("distance_airport", "Distance to an airport", "os_open", "Transport & access", "m", "continuous", "static", 2000.0, 180000.0, True, "Nearest passenger or freight airport."),
    ("distance_port", "Distance to a port", "os_open", "Transport & access", "m", "continuous", "static", 3000.0, 250000.0, True, "Nearest commercial port."),
    ("drive_time_pop_30", "Population within 30 min", "os_open", "Transport & access", "people", "continuous", "annual", 5000.0, 6000000.0, True, "Residents inside a 30-minute drive."),
    ("labour_pool_30", "Workforce within 30 min", "ons_census", "Transport & access", "people", "continuous", "periodic", 2000.0, 3000000.0, True, "Economically active residents inside a 30-minute drive."),

    # --- Community & services ----------------------------------------------
    ("households", "Households", "ons_census", "Community & services", "per km²", "continuous", "periodic", 0.0, 7000.0, False, "Household density."),
    ("tenure_owner_pct", "Owner-occupied", "ons_census", "Community & services", "%", "continuous", "periodic", 5.0, 95.0, False, "Households owning outright or with a mortgage."),
    ("tenure_social_pct", "Social rented", "ons_census", "Community & services", "%", "continuous", "periodic", 0.0, 70.0, False, "Households in social housing."),
    ("tenure_private_rent_pct", "Privately rented", "ons_census", "Community & services", "%", "continuous", "periodic", 2.0, 70.0, False, "Households renting privately."),
    ("age_median", "Median age", "ons_census", "Community & services", "years", "continuous", "periodic", 22.0, 58.0, False, "Median resident age."),
    ("age_under16_pct", "Under 16s", "ons_census", "Community & services", "%", "continuous", "periodic", 5.0, 32.0, False, "Residents aged under 16."),
    ("age_over65_pct", "Over 65s", "ons_census", "Community & services", "%", "continuous", "periodic", 4.0, 45.0, False, "Residents aged 65 and over."),
    ("economically_active_pct", "Economically active", "ons_census", "Community & services", "%", "continuous", "periodic", 40.0, 85.0, False, "Residents in or seeking work."),
    ("degree_qualified_pct", "Degree qualified", "ons_census", "Community & services", "%", "continuous", "periodic", 10.0, 75.0, False, "Residents with a level 4+ qualification."),
    ("crime_rate", "Crime rate", "police_crime", "Community & services", "per 1,000/yr", "continuous", "monthly", 20.0, 320.0, False, "Recorded street-level offences per thousand residents."),
    ("crime_density", "Crime density", "police_crime", "Community & services", "per km²/month", "continuous", "monthly", 0.0, 400.0, True, "Street-level offences inside the drawn shape, per square kilometre."),
    ("burglary_density", "Burglary density", "police_crime", "Community & services", "per km²/month", "continuous", "monthly", 0.0, 40.0, True, "Residential burglary inside the drawn shape, per square kilometre."),
    ("antisocial_share", "Antisocial share", "police_crime", "Community & services", "%", "continuous", "monthly", 0.0, 60.0, True, "Share of recorded offences that are antisocial behaviour."),
    ("violent_crime_share", "Violence share", "police_crime", "Community & services", "%", "continuous", "monthly", 5.0, 45.0, True, "Share of offences that are violent."),
    ("burglary_rate", "Burglary rate", "police_crime", "Community & services", "per 1,000/yr", "continuous", "monthly", 0.5, 30.0, True, "Residential burglary per thousand residents."),
    ("school_good_pct", "Good or outstanding schools", "dfe_schools", "Community & services", "%", "continuous", "annual", 30.0, 100.0, False, "Ofsted-rated schools within 2 km."),
    ("primary_distance", "Distance to a primary school", "dfe_schools", "Community & services", "m", "continuous", "annual", 80.0, 9000.0, True, "Nearest state primary."),
    ("school_places_pressure", "School places pressure", "dfe_schools", "Community & services", "0–1", "continuous", "annual", 0.0, 1.0, True, "Reception intake against capacity — a section 106 driver."),
    ("gp_within_2km", "GP practices within 2 km", "nhs_estates", "Community & services", "count", "continuous", "periodic", 0.0, 25.0, False, "Practices inside a two-kilometre radius."),
    ("hospital_distance", "Distance to a hospital", "nhs_estates", "Community & services", "m", "continuous", "periodic", 500.0, 60000.0, True, "Nearest hospital with an emergency department."),
    ("greenspace_access", "Greenspace within 300 m", "os_open", "Community & services", "%", "continuous", "static", 0.0, 100.0, True, "Share of the area near accessible open space."),

    # --- Ground risk & liability -------------------------------------------
    ("subsidence_risk", "Subsidence risk", "bgs_geosure", "Ground risk", "class", "categorical", "static", None, None, False, "GeoSure shrink-swell hazard band. Never averaged."),
    ("shrink_swell_score", "Shrink-swell hazard", "bgs_geosure", "Ground risk", "0–5", "continuous", "static", 0.0, 5.0, True, "Clay movement potential — the commonest subsidence claim."),
    ("landslide_score", "Landslide susceptibility", "bgs_geosure", "Ground risk", "0–5", "continuous", "static", 0.0, 5.0, False, "Slope instability potential."),
    ("compressible_ground", "Compressible ground", "bgs_geosure", "Ground risk", "0–5", "continuous", "static", 0.0, 5.0, False, "Settlement risk from soft deposits."),
    ("soluble_rocks", "Soluble rocks", "bgs_geosure", "Ground risk", "0–5", "continuous", "static", 0.0, 5.0, False, "Dissolution and sinkhole potential."),
    ("running_sand", "Running sand", "bgs_geosure", "Ground risk", "0–5", "continuous", "static", 0.0, 5.0, False, "Ground that flows when saturated — excavation risk."),
    ("coal_mining_pct", "Coal mining reporting area", "coal_authority", "Ground risk", "%", "continuous", "static", 0.0, 100.0, False, "Share where a mining report is required."),
    ("mine_entry_count", "Recorded mine entries", "coal_authority", "Ground risk", "count", "continuous", "static", 0.0, 40.0, False, "Shafts and adits on record."),
    ("historic_landfill_pct", "Historic landfill", "ea_landfill", "Ground risk", "%", "continuous", "periodic", 0.0, 60.0, False, "Share over a recorded historic landfill."),
    ("landfill_distance", "Distance to landfill", "ea_landfill", "Ground risk", "m", "continuous", "periodic", 0.0, 20000.0, True, "Nearest historic or operational landfill."),
    ("contamination_flag", "Contamination status", "ea_landfill", "Ground risk", "class", "categorical", "periodic", None, None, True, "Whether past use suggests investigation. Never averaged."),
    ("ground_risk_score", "Composite ground risk", "bgs_geosure", "Ground risk", "0–100", "continuous", "static", 0.0, 100.0, True, "The GeoSure bands combined into one screening number."),
    ("storm_gust_50yr", "50-year gust", "era5_land", "Ground risk", "m/s", "continuous", "static", 22.0, 45.0, True, "Wind speed with a 2% annual exceedance — design load."),
    ("insurance_peril_score", "Composite peril score", "ea_flood_zones", "Ground risk", "0–100", "continuous", "annual", 0.0, 100.0, True, "Flood, subsidence and wind combined for screening."),

    # --- Energy & renewables ------------------------------------------------
    ("wind_speed_50m", "Wind speed at 50 m", "wind_atlas", "Energy", "m/s", "continuous", "static", 3.5, 11.0, False, "Mean wind speed at small-turbine hub height."),
    ("wind_speed_100m", "Wind speed at 100 m", "wind_atlas", "Energy", "m/s", "continuous", "static", 4.0, 12.5, False, "Mean wind speed at utility hub height."),
    ("wind_power_density", "Wind power density", "wind_atlas", "Energy", "W/m²", "continuous", "static", 80.0, 1200.0, False, "Energy flux through the rotor plane."),
    ("wind_capacity_factor", "Wind capacity factor", "wind_atlas", "Energy", "%", "continuous", "static", 15.0, 52.0, True, "Expected output against nameplate."),
    ("solar_farm_suitability", "Solar farm suitability", "pvgis", "Energy", "0–1", "continuous", "static", 0.0, 1.0, True, "Irradiance, slope, aspect and grid distance combined."),
    ("shading_horizon_loss", "Horizon shading loss", "pvgis", "Energy", "%", "continuous", "static", 0.0, 20.0, True, "Generation lost to terrain shading."),
    ("battery_site_suitability", "Battery storage suitability", "neso_grid", "Energy", "0–1", "continuous", "periodic", 0.0, 1.0, True, "Flat ground, grid headroom and access combined."),

    # --- Agriculture --------------------------------------------------------
    ("alc_grade", "Agricultural land class", "defra_agland", "Agriculture", "class", "categorical", "static", None, None, False, "Provisional ALC grade. Never averaged."),
    ("bmv_land_pct", "Best and most versatile land", "defra_agland", "Agriculture", "%", "continuous", "static", 0.0, 100.0, True, "Grades 1–3a — the land planning policy protects."),
    ("nvz_pct", "Nitrate vulnerable zone", "defra_agland", "Agriculture", "%", "continuous", "static", 0.0, 100.0, False, "Share inside an NVZ — fertiliser and slurry rules."),
    ("field_size_mean", "Mean field size", "defra_agland", "Agriculture", "ha", "continuous", "annual", 1.0, 60.0, True, "Average parcel size — machinery efficiency."),
    ("hedgerow_density", "Hedgerow density", "os_open", "Agriculture", "m/ha", "continuous", "static", 0.0, 220.0, True, "Field boundary length per hectare."),
    ("workable_days", "Workable days", "era5_land", "Agriculture", "days", "continuous", "monthly", 0.0, 28.0, True, "Days dry enough to travel on the land."),
    ("irrigation_demand", "Irrigation demand", "era5_land", "Agriculture", "mm", "continuous", "monthly", 0.0, 120.0, True, "Water needed above rainfall for a reference crop."),
    ("grazing_days", "Grazing days", "era5_land", "Agriculture", "days", "continuous", "monthly", 0.0, 31.0, True, "Days grass growth supports stock outdoors."),
    ("late_frost_risk", "Late frost risk", "era5_land", "Agriculture", "0–1", "continuous", "monthly", 0.0, 1.0, True, "Frost after bud burst — orchard and vine loss."),
    ("yield_potential_wheat", "Wheat yield potential", "soilgrids", "Agriculture", "t/ha", "continuous", "annual", 4.0, 13.0, True, "Modelled attainable yield from soil and climate."),
    ("yield_potential_grass", "Grass yield potential", "soilgrids", "Agriculture", "t DM/ha", "continuous", "annual", 3.0, 16.0, True, "Dry matter production potential."),
    ("crop_stress_days", "Crop stress days", "era5_land", "Agriculture", "days", "continuous", "monthly", 0.0, 25.0, True, "Days of heat or moisture stress in the growing season."),
    ("sfi_eligible_pct", "SFI-eligible area", "defra_agland", "Agriculture", "%", "continuous", "annual", 0.0, 100.0, True, "Share eligible for Sustainable Farming Incentive actions."),

    # --- Forestry & carbon ---------------------------------------------------
    ("canopy_height_mean", "Canopy height (mean)", "canopy_height", "Forestry & carbon", "m", "continuous", "5 years", 0.0, 32.0, False, "Mean top-of-canopy height."),
    ("canopy_cover_pct", "Canopy cover", "canopy_height", "Forestry & carbon", "%", "continuous", "5 years", 0.0, 100.0, True, "Share under canopy above 5 m."),
    ("above_ground_biomass", "Above-ground biomass", "canopy_height", "Forestry & carbon", "t/ha", "continuous", "5 years", 0.0, 420.0, True, "Standing woody biomass."),
    ("carbon_stock", "Carbon stock", "canopy_height", "Forestry & carbon", "tCO₂e/ha", "continuous", "5 years", 0.0, 700.0, True, "Carbon held in biomass — the tradeable quantity."),
    ("sequestration_rate", "Sequestration rate", "forestry_nfi", "Forestry & carbon", "tCO₂e/ha/yr", "continuous", "annual", 0.0, 14.0, True, "Annual carbon uptake at current stocking."),
    ("woodland_type", "Woodland type", "forestry_nfi", "Forestry & carbon", "class", "categorical", "annual", None, None, False, "Dominant woodland composition. Never averaged."),
    ("woodland_creation_suitability", "Woodland creation suitability", "forestry_nfi", "Forestry & carbon", "0–1", "continuous", "annual", 0.0, 1.0, True, "Soil, slope and designation constraints combined."),
    ("timber_access_score", "Timber access", "forestry_nfi", "Forestry & carbon", "0–1", "continuous", "annual", 0.0, 1.0, True, "Whether a timber lorry can reach and turn."),
    ("windthrow_risk", "Windthrow risk", "wind_atlas", "Forestry & carbon", "0–5", "continuous", "static", 0.0, 5.0, True, "Exposure and rooting depth combined."),
    ("bng_units_available", "Biodiversity units", "esa_worldcover", "Forestry & carbon", "units/ha", "continuous", "annual", 0.0, 12.0, True, "Indicative statutory biodiversity units at current condition."),
    ("bng_uplift_potential", "Biodiversity uplift", "esa_worldcover", "Forestry & carbon", "units/ha", "continuous", "annual", 0.0, 9.0, True, "Units creatable by habitat change — the BNG market."),

    # --- Siting & logistics --------------------------------------------------
    ("warehouse_suitability", "Warehouse suitability", "lidar_dtm", "Siting & logistics", "0–1", "continuous", "static", 0.0, 1.0, True, "Flat, dry, accessible ground of usable shape."),
    ("data_centre_suitability", "Data centre suitability", "neso_grid", "Siting & logistics", "0–1", "continuous", "periodic", 0.0, 1.0, True, "Power, water, fibre and flood risk combined."),
    ("last_mile_score", "Last-mile score", "os_open", "Siting & logistics", "0–1", "continuous", "static", 0.0, 1.0, True, "Population reachable inside a 20-minute van round."),
    ("freight_access_score", "Freight access", "os_open", "Siting & logistics", "0–1", "continuous", "static", 0.0, 1.0, True, "Motorway, rail freight and port access combined."),
    ("retail_catchment_spend", "Retail catchment spend", "ons_housing", "Siting & logistics", "£m/yr", "continuous", "annual", 5.0, 900.0, True, "Household spend inside the drive-time catchment."),
    ("earthworks_volume", "Earthworks required", "lidar_dtm", "Siting & logistics", "m³/ha", "continuous", "static", 0.0, 9000.0, True, "Cut and fill to reach a level platform."),
]

FACTORS: List[Dict[str, Any]] = [
    dict(id=f[0], name=f[1], base=f[2], group=f[3], unit=f[4], kind=f[5],
         cadence=f[6], lo=f[7], hi=f[8], derived=f[9], note=f[10])
    for f in _F
]

FACTOR_BY_ID: Dict[str, Dict[str, Any]] = {f["id"]: f for f in FACTORS}

GROUPS: List[str] = list(dict.fromkeys(f["group"] for f in FACTORS))

# Categorical factors carry their class list here. The UI colours chips from
# this and the table refuses to average them.
CLASS_VALUES: Dict[str, List[str]] = {
    "lc_dominant": ["Tree cover", "Shrubland", "Grassland", "Cropland", "Built-up",
                    "Bare / sparse", "Open water", "Herbaceous wetland"],
    "aspect_dominant": ["North", "North-east", "East", "South-east",
                        "South", "South-west", "West", "North-west"],
    "bedrock_class": ["Chalk", "Clay", "Limestone", "Sandstone", "Mudstone",
                      "Granite", "Gravel", "Slate"],
    "superficial_deposits": ["Alluvium", "River terrace", "Glacial till",
                             "Head", "Sand and gravel", "Peat", "None recorded"],
    "local_plan_allocation": ["Housing", "Employment", "Mixed use",
                              "Green infrastructure", "Safeguarded", "Not allocated"],
    "council_tax_band_mode": ["A", "B", "C", "D", "E", "F", "G", "H"],
    "epc_band_mode": ["A", "B", "C", "D", "E", "F", "G"],
    "dwelling_age_mode": ["Pre-1900", "1900–1929", "1930–1949", "1950–1966",
                          "1967–1975", "1976–1990", "1991–2006", "Post-2007"],
    "substation_class": ["Grid supply point", "Bulk supply point", "Primary",
                         "Secondary only", "None within 5 km"],
    "water_stress_class": ["Low", "Moderate", "Serious"],
    "abstraction_availability": ["Water available", "Restricted",
                                 "Over-licensed", "Over-abstracted"],
    "hgv_access_class": ["Direct from primary route", "Within 2 km",
                         "Weight-restricted approach", "Unsuitable"],
    "subsidence_risk": ["Very low", "Low", "Moderate", "High", "Very high"],
    "contamination_flag": ["None recorded", "Historic use noted",
                           "Investigation advised", "Determined"],
    "alc_grade": ["Grade 1", "Grade 2", "Grade 3a", "Grade 3b", "Grade 4",
                  "Grade 5", "Urban / non-agricultural"],
    "woodland_type": ["Broadleaved", "Conifer", "Mixed", "Young trees",
                      "Felled", "Non-woodland"],
}

# The area we cover today. Stated once, used for validation everywhere —
# drawing outside it should fail with an honest message, not silent nonsense.
ENGLAND_BBOX = dict(west=-6.42, south=49.86, east=1.77, north=55.81)

# The catalogue's time span. 15+ years of monthly steps.
TIME_START = "2011-01"
TIME_END = "2025-12"


def catalogue_summary() -> Dict[str, Any]:
    """Counts used by the UI header and by the storage-cost argument in
    TECHNICAL_PLAN.md §8.2 — 100+ factors from a much smaller stored set."""
    stored = [b for b in BASES if b["stored"]]
    monthly_bases = [b for b in stored if b["cadence"] == "monthly"]
    return {
        "factor_count": len(FACTORS),
        "base_count": len(BASES),
        "stored_base_count": len(stored),
        "monthly_base_count": len(monthly_bases),
        "derived_factor_count": sum(1 for f in FACTORS if f["derived"]),
        "group_count": len(GROUPS),
    }


def factors_for_base(base_id: str) -> List[Dict[str, Any]]:
    return [f for f in FACTORS if f["base"] == base_id]


def resolve(factor_id: str) -> Optional[Dict[str, Any]]:
    """A factor plus its base's provenance, which is what the UI needs to show
    a source and licence next to every number."""
    f = FACTOR_BY_ID.get(factor_id)
    if f is None:
        return None
    return {**f, "base_meta": BASE_BY_ID[f["base"]]}
