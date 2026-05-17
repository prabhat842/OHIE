# External Transfer Results

## brahmaputra_dhakuakhana_open_dem_transfer

Site: Dhakuakhana floodplain, Brahmaputra north-bank sector, Assam
Study window: AWS Terrain Tiles z12 tile 3122/1726 (~9.8 km square at the chosen location)
Dataset: /home/prabhat/Desktop/Infraloom(urbanist)-All-Code-Files/Urbanist-Prototypes/ohie-data/external_transfer/brahmaputra_dhakuakhana_z12.tif

Assumptions: open DEM tile from AWS Terrain Tiles; river-adjacent edge chosen as the lowest-median border (west); uniform rainfall forcing; no calibration; no engineered drainage network
Limitations: open-DEM-only transfer test; river stage is a simplified edge forcing; no measured hydrograph; no SAR/NDWI/EMS validation; no embankment or channel morphology model
Confidence: Low for calibration; Medium for transfer-failure diagnosis
Classification: Local failure: the external case improves relative to the benchmark family, but the coefficient remains terrain dependent.

## Baseline
- boundary_volume_m3: 0.000
- mass_error: 0.000000
- near_edge_mean_depth_m: 0.028
- near_edge_persistence_s: 459.7
- flooded_area_cells: 34597

## Default coefficient (1e-6)
- boundary_volume_m3: 9858.094
- mass_error: 0.004086
- near_edge_mean_depth_m: 0.040
- near_edge_persistence_s: 568.2
- flooded_area_cells: 34669

