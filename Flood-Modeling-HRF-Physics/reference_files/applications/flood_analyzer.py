#!/usr/bin/env python3
"""
Flood Analyzer: Identifies hotspots and optimal intervention locations from HRF simulation results.

This module analyzes flood simulation outputs to:
- Identify flood hotspots (areas with excessive water depth)
- Assess building exposure and risk
- Identify flow paths and accumulation zones
- Suggest optimal locations for interventions

Author: QCIA Flood Analysis Layer
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np

try:
    import rasterio as rio
    from rasterio import features as rio_features
    import fiona
    from shapely.geometry import shape as shp_shape, Point
    from shapely.ops import transform as shp_transform
    from pyproj import Transformer
    _HAS_GEOSPATIAL = True
except ImportError:
    _HAS_GEOSPATIAL = False


class FloodAnalyzer:
    """Analyzes HRF simulation results to identify flood patterns and intervention opportunities."""
    
    def __init__(self, grid, flood_depth: np.ndarray, bed: np.ndarray, verbose: bool = True):
        """
        Initialize analyzer with simulation results.
        
        Args:
            grid: Grid instance with spatial information
            flood_depth: 2D array of final flood depths (m)
            bed: 2D array of bed elevations (m)
            verbose: Print diagnostic messages
        """
        self.grid = grid
        self.flood_depth = flood_depth
        self.bed = bed
        self.verbose = verbose
        
        # Reference coordinates (Jabalpur center)
        self.ref_lat = 23.1815
        self.ref_lon = 79.9864
    
    def identify_hotspots(self, 
                         threshold_m: float = 0.3,
                         min_area_m2: float = 100.0,
                         top_n: int = 10) -> List[Dict]:
        """
        Identify flood hotspots where depth exceeds threshold.
        
        Args:
            threshold_m: Minimum flood depth to consider (meters)
            min_area_m2: Minimum contiguous flooded area (square meters)
            top_n: Return top N hotspots by severity
            
        Returns:
            List of hotspot dictionaries with location, severity, and area
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"IDENTIFYING FLOOD HOTSPOTS")
            print(f"{'='*70}")
            print(f"Threshold: {threshold_m:.2f}m")
            print(f"Min area: {min_area_m2:.0f}m²")
        
        # Create binary mask of flooded areas
        flooded = self.flood_depth > threshold_m
        
        # Label connected components
        labeled, num_features = self._label_connected_components(flooded)
        
        hotspots = []
        cell_area = self.grid.dx * self.grid.dy
        
        for label in range(1, num_features + 1):
            mask = (labeled == label)
            area_m2 = np.sum(mask) * cell_area
            
            if area_m2 < min_area_m2:
                continue
            
            # Calculate hotspot statistics
            depths = self.flood_depth[mask]
            mean_depth = float(np.mean(depths))
            max_depth = float(np.max(depths))
            
            # Find centroid
            indices = np.where(mask)
            center_i = int(np.mean(indices[0]))
            center_j = int(np.mean(indices[1]))
            
            # Convert to lat/lon
            lat, lon = self._grid_to_latlon(center_i, center_j)
            
            # Calculate severity score (combines depth and area)
            severity = mean_depth * np.sqrt(area_m2 / 1000.0)  # Scaled severity
            
            hotspot = {
                'id': len(hotspots) + 1,
                'location': {'lat': lat, 'lon': lon},
                'grid_indices': {'i': center_i, 'j': center_j},
                'area_m2': area_m2,
                'mean_depth_m': mean_depth,
                'max_depth_m': max_depth,
                'severity_score': severity,
                'num_cells': int(np.sum(mask))
            }
            
            hotspots.append(hotspot)
        
        # Sort by severity and return top N
        hotspots.sort(key=lambda x: x['severity_score'], reverse=True)
        hotspots = hotspots[:top_n]
        
        if self.verbose:
            print(f"\nFound {len(hotspots)} hotspots:")
            for h in hotspots:
                print(f"  Hotspot {h['id']}: {h['area_m2']:.0f}m², "
                      f"depth {h['mean_depth_m']:.2f}m (max {h['max_depth_m']:.2f}m), "
                      f"severity {h['severity_score']:.2f}")
                print(f"    Location: ({h['location']['lat']:.4f}°, {h['location']['lon']:.4f}°)")
        
        return hotspots
    
    def assess_building_exposure(self, 
                                buildings_path: Optional[Path] = None,
                                risk_threshold_m: float = 0.2) -> Dict:
        """
        Assess which buildings are exposed to flooding.
        
        Args:
            buildings_path: Path to buildings GeoJSON file
            risk_threshold_m: Minimum depth for building to be at risk
            
        Returns:
            Dictionary with exposure statistics
        """
        if not _HAS_GEOSPATIAL or buildings_path is None or not buildings_path.exists():
            if self.verbose:
                print("⚠️  Cannot assess building exposure (missing geospatial libs or building data)")
            return {}
        
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"ASSESSING BUILDING EXPOSURE")
            print(f"{'='*70}")
        
        try:
            with fiona.open(buildings_path, 'r') as src:
                total_buildings = 0
                exposed_buildings = 0
                high_risk_buildings = 0
                total_exposed_area = 0.0
                
                for feat in src:
                    total_buildings += 1
                    geom = shp_shape(feat['geometry'])
                    centroid = geom.centroid
                    
                    # Convert to grid indices
                    i, j = self._latlon_to_grid_indices(centroid.y, centroid.x)
                    
                    if i is not None and j is not None:
                        depth = self.flood_depth[i, j]
                        
                        if depth > risk_threshold_m:
                            exposed_buildings += 1
                            total_exposed_area += geom.area
                            
                            if depth > 0.5:
                                high_risk_buildings += 1
            
            exposure = {
                'total_buildings': total_buildings,
                'exposed_buildings': exposed_buildings,
                'high_risk_buildings': high_risk_buildings,
                'exposure_rate': exposed_buildings / max(1, total_buildings),
                'high_risk_rate': high_risk_buildings / max(1, total_buildings)
            }
            
            if self.verbose:
                print(f"Total buildings: {total_buildings}")
                print(f"Exposed (>{risk_threshold_m}m): {exposed_buildings} ({exposure['exposure_rate']*100:.1f}%)")
                print(f"High risk (>0.5m): {high_risk_buildings} ({exposure['high_risk_rate']*100:.1f}%)")
            
            return exposure
            
        except Exception as e:
            if self.verbose:
                print(f"❌ Failed to assess building exposure: {e}")
            return {}
    
    def identify_flow_paths(self) -> np.ndarray:
        """
        Identify major flow paths using terrain and flood depth.
        
        Returns:
            2D array with flow accumulation values
        """
        # Calculate flow direction using D8 algorithm
        flow_dir = self._calculate_flow_direction()
        
        # Calculate flow accumulation
        flow_accum = self._calculate_flow_accumulation(flow_dir)
        
        return flow_accum
    
    def suggest_intervention_locations(self, 
                                      hotspots: List[Dict],
                                      strategy: str = 'upstream') -> List[Dict]:
        """
        Suggest optimal locations for interventions based on hotspots and flow analysis.
        
        Args:
            hotspots: List of identified hotspots
            strategy: 'upstream' (intercept flow) or 'local' (treat at hotspot)
            
        Returns:
            List of suggested intervention locations with reasoning
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"SUGGESTING INTERVENTION LOCATIONS")
            print(f"{'='*70}")
            print(f"Strategy: {strategy}")
        
        suggestions = []
        
        for hotspot in hotspots:
            center_i = hotspot['grid_indices']['i']
            center_j = hotspot['grid_indices']['j']
            
            if strategy == 'upstream':
                # Find upstream location with high flow accumulation
                search_radius = 20  # cells
                best_i, best_j = self._find_upstream_location(center_i, center_j, search_radius)
            else:
                # Use hotspot center
                best_i, best_j = center_i, center_j
            
            lat, lon = self._grid_to_latlon(best_i, best_j)
            elevation = float(self.bed[best_i, best_j])
            
            # Estimate required basin volume (simple heuristic)
            flooded_volume = hotspot['area_m2'] * hotspot['mean_depth_m']
            required_volume = flooded_volume * 0.8  # Target 80% reduction
            
            # Suggest basin dimensions
            depth = 2.0  # Standard 2m depth
            diameter = np.sqrt(required_volume / (np.pi * depth / 4)) * 2.0
            
            suggestion = {
                'hotspot_id': hotspot['id'],
                'type': 'detention_basin',
                'location': {'lat': lat, 'lon': lon},
                'grid_indices': {'i': best_i, 'j': best_j},
                'elevation_m': elevation,
                'suggested_volume_m3': required_volume,
                'suggested_diameter_m': diameter,
                'suggested_depth_m': depth,
                'strategy': strategy,
                'reasoning': f"{'Upstream interception' if strategy == 'upstream' else 'Local storage'} "
                            f"for hotspot {hotspot['id']} (area {hotspot['area_m2']:.0f}m², "
                            f"depth {hotspot['mean_depth_m']:.2f}m)"
            }
            
            suggestions.append(suggestion)
            
            if self.verbose:
                print(f"\n  Suggestion {len(suggestions)}:")
                print(f"    Type: {suggestion['type']}")
                print(f"    Location: ({lat:.4f}°, {lon:.4f}°)")
                print(f"    Volume: {required_volume:.0f}m³ (D={diameter:.1f}m, depth={depth:.1f}m)")
                print(f"    Reasoning: {suggestion['reasoning']}")
        
        return suggestions
    
    def export_analysis(self, output_dir: Path, prefix: str = "analysis"):
        """
        Export analysis results to files.
        
        Args:
            output_dir: Directory to save analysis outputs
            prefix: Prefix for output filenames
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Identify hotspots
        hotspots = self.identify_hotspots()
        
        # Save hotspots as JSON
        hotspots_file = output_dir / f"{prefix}_hotspots.json"
        with open(hotspots_file, 'w') as f:
            json.dump({'hotspots': hotspots}, f, indent=2)
        
        if self.verbose:
            print(f"\n✅ Saved hotspots to: {hotspots_file}")
        
        # Save hotspots as GeoJSON for visualization
        if _HAS_GEOSPATIAL:
            features = []
            for h in hotspots:
                features.append({
                    'type': 'Feature',
                    'geometry': {
                        'type': 'Point',
                        'coordinates': [h['location']['lon'], h['location']['lat']]
                    },
                    'properties': {
                        'id': h['id'],
                        'area_m2': h['area_m2'],
                        'mean_depth_m': h['mean_depth_m'],
                        'max_depth_m': h['max_depth_m'],
                        'severity_score': h['severity_score']
                    }
                })
            
            geojson = {'type': 'FeatureCollection', 'features': features}
            geojson_file = output_dir / f"{prefix}_hotspots.geojson"
            with open(geojson_file, 'w') as f:
                json.dump(geojson, f, indent=2)
            
            if self.verbose:
                print(f"✅ Saved hotspots GeoJSON to: {geojson_file}")
        
        # Suggest interventions
        suggestions = self.suggest_intervention_locations(hotspots)
        suggestions_file = output_dir / f"{prefix}_intervention_suggestions.json"
        with open(suggestions_file, 'w') as f:
            json.dump({'suggestions': suggestions}, f, indent=2)
        
        if self.verbose:
            print(f"✅ Saved intervention suggestions to: {suggestions_file}")
    
    def _label_connected_components(self, binary_mask: np.ndarray) -> Tuple[np.ndarray, int]:
        """Simple connected component labeling (4-connectivity)."""
        labeled = np.zeros_like(binary_mask, dtype=int)
        current_label = 0
        
        for i in range(binary_mask.shape[0]):
            for j in range(binary_mask.shape[1]):
                if binary_mask[i, j] and labeled[i, j] == 0:
                    current_label += 1
                    self._flood_fill(binary_mask, labeled, i, j, current_label)
        
        return labeled, current_label
    
    def _flood_fill(self, binary_mask: np.ndarray, labeled: np.ndarray, 
                   i: int, j: int, label: int):
        """Recursive flood fill for connected component labeling."""
        if i < 0 or i >= binary_mask.shape[0] or j < 0 or j >= binary_mask.shape[1]:
            return
        if not binary_mask[i, j] or labeled[i, j] != 0:
            return
        
        labeled[i, j] = label
        
        # 4-connectivity
        self._flood_fill(binary_mask, labeled, i-1, j, label)
        self._flood_fill(binary_mask, labeled, i+1, j, label)
        self._flood_fill(binary_mask, labeled, i, j-1, label)
        self._flood_fill(binary_mask, labeled, i, j+1, label)
    
    def _calculate_flow_direction(self) -> np.ndarray:
        """Calculate D8 flow direction from terrain."""
        flow_dir = np.zeros_like(self.bed, dtype=int)
        
        for i in range(1, self.bed.shape[0] - 1):
            for j in range(1, self.bed.shape[1] - 1):
                # Find steepest descent neighbor
                max_slope = 0
                best_dir = 0
                
                for di, dj, direction in [(-1,-1,1), (-1,0,2), (-1,1,3),
                                         (0,-1,4), (0,1,5),
                                         (1,-1,6), (1,0,7), (1,1,8)]:
                    ni, nj = i + di, j + dj
                    if 0 <= ni < self.bed.shape[0] and 0 <= nj < self.bed.shape[1]:
                        slope = (self.bed[i, j] - self.bed[ni, nj]) / np.sqrt(di**2 + dj**2)
                        if slope > max_slope:
                            max_slope = slope
                            best_dir = direction
                
                flow_dir[i, j] = best_dir
        
        return flow_dir
    
    def _calculate_flow_accumulation(self, flow_dir: np.ndarray) -> np.ndarray:
        """Calculate flow accumulation from flow direction."""
        accum = np.ones_like(flow_dir, dtype=float)
        
        # Process cells in reverse topological order (simplified)
        # For production code, would use proper topological sort
        for _ in range(10):  # Multiple passes to propagate accumulation
            new_accum = accum.copy()
            for i in range(1, flow_dir.shape[0] - 1):
                for j in range(1, flow_dir.shape[1] - 1):
                    direction = flow_dir[i, j]
                    if direction > 0:
                        # Map direction to delta i, j
                        di_map = {1:-1, 2:-1, 3:-1, 4:0, 5:0, 6:1, 7:1, 8:1}
                        dj_map = {1:-1, 2:0, 3:1, 4:-1, 5:1, 6:-1, 7:0, 8:1}
                        ni = i + di_map[direction]
                        nj = j + dj_map[direction]
                        if 0 <= ni < accum.shape[0] and 0 <= nj < accum.shape[1]:
                            new_accum[ni, nj] += accum[i, j]
            accum = new_accum
        
        return accum
    
    def _find_upstream_location(self, center_i: int, center_j: int, 
                               radius: int) -> Tuple[int, int]:
        """Find upstream location with high elevation suitable for intervention."""
        flow_accum = self.identify_flow_paths()
        
        best_i, best_j = center_i, center_j
        best_score = 0
        
        for di in range(-radius, radius + 1):
            for dj in range(-radius, radius + 1):
                i = center_i + di
                j = center_j + dj
                
                if 0 <= i < self.bed.shape[0] and 0 <= j < self.bed.shape[1]:
                    # Score based on: higher elevation + high flow accumulation
                    elev_score = self.bed[i, j] - self.bed[center_i, center_j]
                    flow_score = flow_accum[i, j]
                    
                    if elev_score > 0:  # Must be upstream
                        score = elev_score * 0.5 + flow_score * 0.5
                        if score > best_score:
                            best_score = score
                            best_i, best_j = i, j
        
        return best_i, best_j
    
    def _grid_to_latlon(self, i: int, j: int) -> Tuple[float, float]:
        """Convert grid indices to lat/lon."""
        # Convert grid indices to meters offset
        offset_x = (i * self.grid.dx) - (self.grid.Lx / 2.0)
        offset_y = (j * self.grid.dy) - (self.grid.Ly / 2.0)
        
        # Convert to lat/lon offset
        m_per_deg_lat = 111000.0
        m_per_deg_lon = 111000.0 * np.cos(np.radians(self.ref_lat))
        
        lat = self.ref_lat + (offset_y / m_per_deg_lat)
        lon = self.ref_lon + (offset_x / m_per_deg_lon)
        
        return lat, lon
    
    def _latlon_to_grid_indices(self, lat: float, lon: float) -> Tuple[Optional[int], Optional[int]]:
        """Convert lat/lon to grid indices."""
        m_per_deg_lat = 111000.0
        m_per_deg_lon = 111000.0 * np.cos(np.radians(self.ref_lat))
        
        offset_x = (lon - self.ref_lon) * m_per_deg_lon
        offset_y = (lat - self.ref_lat) * m_per_deg_lat
        
        i = int((offset_x + self.grid.Lx / 2.0) / self.grid.dx)
        j = int((offset_y + self.grid.Ly / 2.0) / self.grid.dy)
        
        if 0 <= i < self.grid.nx and 0 <= j < self.grid.ny:
            return i, j
        else:
            return None, None


if __name__ == "__main__":
    print("Flood Analyzer - Identifies hotspots and optimal intervention locations")
    print("Import this module and use FloodAnalyzer class")

