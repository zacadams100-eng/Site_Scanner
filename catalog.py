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
}

# The two Sentinel entries are flagged deliberately. They are recorded here as
# CC BY-SA 3.0 IGO, and share-alike on a commercial derived product would be a
# genuine constraint — but Copernicus Sentinel data is generally distributed
# under the Copernicus terms (Regulation 1159/2013), which permit commercial
# reuse with attribution and impose no share-alike. One of those two things is
# wrong, and which one matters, so it is marked for confirmation rather than
# quietly assumed either way.
COMMERCIAL_USE: Dict[str, str] = {
    b["id"]: ("verify" if b["id"] in ("sentinel2_sr", "sentinel1_sar") else "yes")
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
