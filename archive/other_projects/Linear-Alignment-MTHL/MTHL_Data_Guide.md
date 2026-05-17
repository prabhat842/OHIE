# MTHL Bridge Data Collection Guide

## Priority Datasets to Download:

### 1. HIGH-RESOLUTION BATHYMETRY (Critical for Bridge)
- GEBCO Global Bathymetry: https://www.gebco.net/data_and_products/gridded_bathymetry_data/
- Search for: 'Thane Creek' or coordinates 18.9-19.0°N, 72.8-73.1°E

### 2. SHIPPING CHANNELS & NAVIGATION
- NOAA Nautical Charts: https://charts.noaa.gov/
- Search for: 'Mumbai Harbour' or 'Jawaharlal Nehru Port'

### 3. SEISMIC HAZARD DATA
- USGS Seismic Hazard Maps: https://earthquake.usgs.gov/hazards/interactive/
- Search for: 'Mumbai, India'

### 4. WIND LOAD DATA
- Global Wind Atlas: https://globalwindatlas.info/
- Location: 18.97°N, 72.84°E (Mumbai)

### 5. MANGROVE & PROTECTED AREAS
- Global Mangrove Watch: https://www.globalmangrovewatch.org/
- Search: 'Thane Creek, India'

### 6. BIRD MIGRATION DATA
- BirdLife International: https://www.birdlife.org/
- Search: 'Flamingo, Thane Creek'

## Download Commands (run in terminal):

# GEBCO Bathymetry
wget https://www.gebco.net/data_and_products/gridded_bathymetry_data/gebco_2023/zip/gebco_2023.zip

# Or use curl for smaller regions
curl -O https://www.gebco.net/data_and_products/gridded_bathymetry_data/gebco_2023/netcdf/GEBCO_2023.nc


