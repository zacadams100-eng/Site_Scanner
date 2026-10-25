#!/usr/bin/env bash
# Download OS Open Rivers (GeoPackage, Open Government Licence) for river names.
# Then: export CONTOUR_OPEN_RIVERS=data/oprvrs_gb.gpkg
set -euo pipefail
mkdir -p data
curl -fsSL -o data/open-rivers.zip \
  "https://api.os.uk/downloads/v1/products/OpenRivers/downloads?area=GB&format=GeoPackage&redirect"
unzip -o -q data/open-rivers.zip -d data/open-rivers
f=$(find data/open-rivers -name "*.gpkg" | head -1)
mv "$f" data/oprvrs_gb.gpkg
rm -rf data/open-rivers data/open-rivers.zip
echo "export CONTOUR_OPEN_RIVERS=$(pwd)/data/oprvrs_gb.gpkg"
