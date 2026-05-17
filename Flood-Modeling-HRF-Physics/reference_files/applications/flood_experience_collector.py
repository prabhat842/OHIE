#!/usr/bin/env python3
"""
Flood Experience Collector: Extracts structured features from flood simulations for causal learning.

This module transforms raw simulation data (DEMs, flood depths, interventions) into
structured "experiences" that can be used by QCIA for causal discovery and reinforcement learning.

Each experience contains:
- Spatial features (terrain, land use)
- Intervention features (what was built, where)
- Outcomes (flood reduction, effectiveness)

Author: QCIA Learning Layer
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np
from dataclasses import dataclass, field, asdict


@dataclass
class SpatialFeatures:
    """Features describing a spatial location."""
    location_id: int
    grid_i: int
    grid_j: int
    lat: float
    lon: float
    
    # Terrain features
    elevation_m: float
    slope: float
    upstream_area_cells: int
    flow_accumulation: float
    distance_to_drain_m: float
    distance_to_river_m: float
    
    # Land use features
    lulc_class: int
    imperviousness: float
    infiltration_rate_mps: float
    manning_n: float
    
    # Baseline flood features
    baseline_flood_depth_m: float
    baseline_peak_velocity_mps: float
    baseline_inundation_duration_s: float
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class InterventionFeatures:
    """Features describing an intervention."""
    intervention_id: str
    type: str  # 'detention_basin', 'bioswale', 'green_roof', etc.
    location_id: int
    grid_i: int
    grid_j: int
    lat: float
    lon: float
    
    # Intervention-specific parameters
    volume_m3: Optional[float] = None
    diameter_m: Optional[float] = None
    depth_m: Optional[float] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    area_m2: Optional[float] = None
    infiltration_rate_mps: Optional[float] = None
    
    # Placement rationale
    placed_upstream: bool = False
    placed_at_hotspot: bool = False
    upstream_drainage_area_cells: int = 0
    
    # Cost (if available)
    cost_inr: Optional[float] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class OutcomeFeatures:
    """Features describing intervention outcomes."""
    intervention_id: str
    location_id: int
    
    # Local outcomes (at intervention location)
    local_depth_reduction_m: float
    local_depth_reduction_pct: float
    local_velocity_reduction_mps: float
    
    # Downstream outcomes (area affected)
    downstream_depth_reduction_m: float
    downstream_affected_area_m2: float
    downstream_volume_stored_m3: float
    
    # Global outcomes (entire domain)
    global_max_depth_reduction_m: float
    global_flooded_area_reduction_m2: float
    global_volume_reduction_m3: float
    
    # Effectiveness metrics
    storage_efficiency: float  # volume_stored / volume_capacity
    cost_effectiveness: Optional[float] = None  # depth_reduction / cost
    
    # Whether intervention was beneficial
    is_effective: bool = True
    effectiveness_score: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class FloodExperience:
    """Complete experience from one simulation iteration."""
    experience_id: int
    timestamp: str
    
    # Scenario metadata
    design_storm_mm_hr: float
    duration_hr: float
    total_interventions: int
    total_cost_inr: float
    
    # Spatial features for all locations
    spatial_features: List[SpatialFeatures] = field(default_factory=list)
    
    # Intervention features
    intervention_features: List[InterventionFeatures] = field(default_factory=list)
    
    # Outcomes for each intervention
    outcome_features: List[OutcomeFeatures] = field(default_factory=list)
    
    # Global metrics
    baseline_max_depth_m: float = 0.0
    mitigated_max_depth_m: float = 0.0
    baseline_flooded_area_m2: float = 0.0
    mitigated_flooded_area_m2: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'experience_id': self.experience_id,
            'timestamp': self.timestamp,
            'design_storm_mm_hr': self.design_storm_mm_hr,
            'duration_hr': self.duration_hr,
            'total_interventions': self.total_interventions,
            'total_cost_inr': self.total_cost_inr,
            'spatial_features': [s.to_dict() for s in self.spatial_features],
            'intervention_features': [i.to_dict() for i in self.intervention_features],
            'outcome_features': [o.to_dict() for o in self.outcome_features],
            'baseline_max_depth_m': self.baseline_max_depth_m,
            'mitigated_max_depth_m': self.mitigated_max_depth_m,
            'baseline_flooded_area_m2': self.baseline_flooded_area_m2,
            'mitigated_flooded_area_m2': self.mitigated_flooded_area_m2
        }


class FloodExperienceCollector:
    """Collects and structures experiences from flood simulations."""
    
    def __init__(self, verbose: bool = True):
        """Initialize collector."""
        self.verbose = verbose
        self.experiences: List[FloodExperience] = []
        self.next_experience_id = 1
    
    def collect_experience(self,
                          grid,
                          baseline_results: Dict,
                          mitigated_results: Dict,
                          interventions: List[Dict],
                          design_storm_mm_hr: float = 50.0,
                          duration_hr: float = 2.0) -> FloodExperience:
        """
        Collect experience from baseline vs mitigated simulation pair.
        
        Args:
            grid: Grid object with spatial information
            baseline_results: Results from baseline simulation
            mitigated_results: Results from mitigated simulation
            interventions: List of applied interventions
            design_storm_mm_hr: Rainfall intensity
            duration_hr: Storm duration
            
        Returns:
            FloodExperience object
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"COLLECTING EXPERIENCE {self.next_experience_id}")
            print(f"{'='*70}")
        
        from datetime import datetime
        
        experience = FloodExperience(
            experience_id=self.next_experience_id,
            timestamp=datetime.now().isoformat(),
            design_storm_mm_hr=design_storm_mm_hr,
            duration_hr=duration_hr,
            total_interventions=len(interventions),
            total_cost_inr=sum(i.get('cost_inr', 0.0) for i in interventions),
            baseline_max_depth_m=baseline_results.get('max_depth', 0.0),
            mitigated_max_depth_m=mitigated_results.get('max_depth', 0.0),
            baseline_flooded_area_m2=baseline_results.get('flooded_area_m2', 0.0),
            mitigated_flooded_area_m2=mitigated_results.get('flooded_area_m2', 0.0)
        )
        
        # Extract spatial features (sample key locations)
        spatial_features = self._extract_spatial_features(
            grid,
            baseline_results,
            interventions
        )
        experience.spatial_features = spatial_features
        
        # Extract intervention features
        intervention_features = self._extract_intervention_features(
            interventions,
            baseline_results
        )
        experience.intervention_features = intervention_features
        
        # Extract outcome features
        outcome_features = self._extract_outcome_features(
            grid,
            baseline_results,
            mitigated_results,
            interventions
        )
        experience.outcome_features = outcome_features
        
        self.experiences.append(experience)
        self.next_experience_id += 1
        
        if self.verbose:
            print(f"✅ Collected experience with:")
            print(f"   - {len(spatial_features)} spatial locations")
            print(f"   - {len(intervention_features)} interventions")
            print(f"   - {len(outcome_features)} outcomes")
        
        return experience
    
    def _extract_spatial_features(self,
                                  grid,
                                  baseline_results: Dict,
                                  interventions: List[Dict]) -> List[SpatialFeatures]:
        """
        Extract spatial features for intervention locations and hotspots.
        """
        spatial_features = []
        bed = baseline_results.get('bed')
        baseline_h = baseline_results.get('final_h')
        
        if bed is None or baseline_h is None:
            return []
        
        # Calculate terrain derivatives
        slope = self._calculate_slope(bed, grid.dx, grid.dy)
        flow_accum = self._calculate_flow_accumulation_simple(bed)
        
        location_id = 1
        
        # Extract features for intervention locations
        for intervention in interventions:
            loc = intervention.get('location', {})
            lat = loc.get('lat')
            lon = loc.get('lon')
            
            if lat is None or lon is None:
                continue
            
            # Convert to grid indices (simplified)
            i, j = self._latlon_to_grid_indices(lat, lon, grid)
            
            if i is None or j is None or i >= bed.shape[0] or j >= bed.shape[1]:
                continue
            
            spatial = SpatialFeatures(
                location_id=location_id,
                grid_i=i,
                grid_j=j,
                lat=lat,
                lon=lon,
                elevation_m=float(bed[i, j]),
                slope=float(slope[i, j]),
                upstream_area_cells=0,  # Placeholder
                flow_accumulation=float(flow_accum[i, j]),
                distance_to_drain_m=0.0,  # Placeholder
                distance_to_river_m=0.0,  # Placeholder
                lulc_class=1,  # Placeholder (urban)
                imperviousness=0.9,  # Placeholder
                infiltration_rate_mps=1e-8,  # Placeholder
                manning_n=0.06,  # Placeholder
                baseline_flood_depth_m=float(baseline_h[i, j]),
                baseline_peak_velocity_mps=0.0,  # Placeholder
                baseline_inundation_duration_s=0.0  # Placeholder
            )
            
            spatial_features.append(spatial)
            location_id += 1
        
        return spatial_features
    
    def _extract_intervention_features(self,
                                      interventions: List[Dict],
                                      baseline_results: Dict) -> List[InterventionFeatures]:
        """Extract features describing each intervention."""
        intervention_features = []
        
        for idx, intervention in enumerate(interventions):
            loc = intervention.get('location', {})
            
            interv_feat = InterventionFeatures(
                intervention_id=intervention.get('id', f"intervention_{idx+1}"),
                type=intervention.get('type', 'unknown'),
                location_id=idx + 1,
                grid_i=intervention.get('grid_indices', {}).get('i', 0),
                grid_j=intervention.get('grid_indices', {}).get('j', 0),
                lat=loc.get('lat', 0.0),
                lon=loc.get('lon', 0.0),
                volume_m3=intervention.get('storage_volume_m3'),
                diameter_m=intervention.get('diameter_m'),
                depth_m=intervention.get('depth_m'),
                length_m=intervention.get('length_m'),
                width_m=intervention.get('width_m'),
                area_m2=intervention.get('area_m2'),
                infiltration_rate_mps=intervention.get('infiltration_rate_mps'),
                placed_upstream=False,  # Placeholder
                placed_at_hotspot=True,  # Placeholder
                upstream_drainage_area_cells=0,  # Placeholder
                cost_inr=intervention.get('cost_inr')
            )
            
            intervention_features.append(interv_feat)
        
        return intervention_features
    
    def _extract_outcome_features(self,
                                  grid,
                                  baseline_results: Dict,
                                  mitigated_results: Dict,
                                  interventions: List[Dict]) -> List[OutcomeFeatures]:
        """Extract outcome features showing intervention effectiveness."""
        outcome_features = []
        
        baseline_h = baseline_results.get('final_h')
        mitigated_h = mitigated_results.get('final_h')
        
        if baseline_h is None or mitigated_h is None:
            return []
        
        # Calculate depth reduction map
        depth_reduction = baseline_h - mitigated_h
        
        for idx, intervention in enumerate(interventions):
            # Get intervention location
            i = intervention.get('grid_indices', {}).get('i', 0)
            j = intervention.get('grid_indices', {}).get('j', 0)
            
            if i >= baseline_h.shape[0] or j >= baseline_h.shape[1]:
                continue
            
            # Local outcomes (at intervention)
            local_baseline = float(baseline_h[i, j])
            local_mitigated = float(mitigated_h[i, j])
            local_reduction = local_baseline - local_mitigated
            local_reduction_pct = (local_reduction / max(local_baseline, 0.01)) * 100
            
            # Downstream outcomes (within radius)
            radius_cells = 10
            downstream_mask = self._get_circular_mask(baseline_h.shape, i, j, radius_cells)
            downstream_reduction = float(np.mean(depth_reduction[downstream_mask]))
            downstream_area = float(np.sum(downstream_mask)) * (grid.dx * grid.dy)
            downstream_volume = float(np.sum(np.maximum(depth_reduction[downstream_mask], 0))) * (grid.dx * grid.dy)
            
            # Global outcomes
            global_max_reduction = baseline_results['max_depth'] - mitigated_results['max_depth']
            global_area_reduction = baseline_results['flooded_area_m2'] - mitigated_results['flooded_area_m2']
            global_volume_reduction = baseline_results['total_volume_m3'] - mitigated_results['total_volume_m3']
            
            # Effectiveness metrics
            volume_capacity = intervention.get('storage_volume_m3', 1.0)
            storage_efficiency = min(1.0, downstream_volume / max(volume_capacity, 1.0))
            
            # Overall effectiveness
            is_effective = (local_reduction > 0) and (downstream_reduction > 0)
            effectiveness_score = local_reduction * 0.3 + downstream_reduction * 0.5 + (global_max_reduction * 0.2)
            
            outcome = OutcomeFeatures(
                intervention_id=intervention.get('id', f"intervention_{idx+1}"),
                location_id=idx + 1,
                local_depth_reduction_m=local_reduction,
                local_depth_reduction_pct=local_reduction_pct,
                local_velocity_reduction_mps=0.0,  # Placeholder
                downstream_depth_reduction_m=downstream_reduction,
                downstream_affected_area_m2=downstream_area,
                downstream_volume_stored_m3=downstream_volume,
                global_max_depth_reduction_m=global_max_reduction,
                global_flooded_area_reduction_m2=global_area_reduction,
                global_volume_reduction_m3=global_volume_reduction,
                storage_efficiency=storage_efficiency,
                is_effective=is_effective,
                effectiveness_score=effectiveness_score
            )
            
            outcome_features.append(outcome)
        
        return outcome_features
    
    def save_experiences(self, output_path: Path):
        """Save all collected experiences to JSON."""
        data = {
            'num_experiences': len(self.experiences),
            'experiences': [exp.to_dict() for exp in self.experiences]
        }
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        if self.verbose:
            print(f"\n✅ Saved {len(self.experiences)} experiences to: {output_path}")
    
    def load_experiences(self, input_path: Path):
        """Load experiences from JSON (placeholder for now)."""
        with open(input_path, 'r') as f:
            data = json.load(f)
        
        # Would need to reconstruct FloodExperience objects
        # For now, just store the raw data
        self.experiences = data.get('experiences', [])
        
        if self.verbose:
            print(f"✅ Loaded {len(self.experiences)} experiences from: {input_path}")
    
    def get_feature_matrix_for_causal_discovery(self) -> Tuple[np.ndarray, List[str]]:
        """
        Convert experiences to feature matrix for causal discovery.
        
        Returns:
            (features_matrix, feature_names) where:
            - features_matrix: N x M array (N=samples, M=features)
            - feature_names: List of feature names
        """
        if not self.experiences:
            return np.array([]), []
        
        # Flatten all experiences into rows
        rows = []
        
        for exp in self.experiences:
            # For each intervention in this experience
            for i, interv in enumerate(exp.intervention_features):
                if i < len(exp.spatial_features) and i < len(exp.outcome_features):
                    spatial = exp.spatial_features[i]
                    outcome = exp.outcome_features[i]
                    
                    row = [
                        # Spatial features
                        spatial.elevation_m,
                        spatial.slope,
                        spatial.flow_accumulation,
                        spatial.baseline_flood_depth_m,
                        
                        # Intervention features
                        interv.volume_m3 if interv.volume_m3 else 0.0,
                        interv.diameter_m if interv.diameter_m else 0.0,
                        interv.depth_m if interv.depth_m else 0.0,
                        
                        # Outcomes
                        outcome.local_depth_reduction_m,
                        outcome.downstream_depth_reduction_m,
                        outcome.storage_efficiency,
                        outcome.effectiveness_score
                    ]
                    
                    rows.append(row)
        
        if not rows:
            return np.array([]), []
        
        feature_names = [
            'elevation_m',
            'slope',
            'flow_accumulation',
            'baseline_flood_depth_m',
            'intervention_volume_m3',
            'intervention_diameter_m',
            'intervention_depth_m',
            'local_depth_reduction_m',
            'downstream_depth_reduction_m',
            'storage_efficiency',
            'effectiveness_score'
        ]
        
        features_matrix = np.array(rows)
        
        return features_matrix, feature_names
    
    def _calculate_slope(self, bed: np.ndarray, dx: float, dy: float) -> np.ndarray:
        """Calculate terrain slope."""
        # Simple gradient magnitude
        gy, gx = np.gradient(bed)
        slope = np.sqrt((gx/dx)**2 + (gy/dy)**2)
        return slope
    
    def _calculate_flow_accumulation_simple(self, bed: np.ndarray) -> np.ndarray:
        """Simple flow accumulation (counts upstream cells)."""
        # Placeholder: return elevation-based proxy
        # Real implementation would trace flow directions
        return np.max(bed) - bed
    
    def _latlon_to_grid_indices(self, lat: float, lon: float, grid) -> Tuple[Optional[int], Optional[int]]:
        """Convert lat/lon to grid indices."""
        # Simplified conversion (same as in intervention_applier)
        ref_lat = 23.1815
        ref_lon = 79.9864
        
        m_per_deg_lat = 111000.0
        m_per_deg_lon = 111000.0 * np.cos(np.radians(ref_lat))
        
        offset_x = (lon - ref_lon) * m_per_deg_lon
        offset_y = (lat - ref_lat) * m_per_deg_lat
        
        i = int((offset_x + grid.Lx / 2.0) / grid.dx)
        j = int((offset_y + grid.Ly / 2.0) / grid.dy)
        
        if 0 <= i < grid.nx and 0 <= j < grid.ny:
            return i, j
        else:
            return None, None
    
    def _get_circular_mask(self, shape: Tuple[int, int], center_i: int, center_j: int, radius: int) -> np.ndarray:
        """Get circular mask around a point."""
        mask = np.zeros(shape, dtype=bool)
        
        for i in range(max(0, center_i - radius), min(shape[0], center_i + radius + 1)):
            for j in range(max(0, center_j - radius), min(shape[1], center_j + radius + 1)):
                dist = np.sqrt((i - center_i)**2 + (j - center_j)**2)
                if dist <= radius:
                    mask[i, j] = True
        
        return mask


if __name__ == "__main__":
    print("Flood Experience Collector - Extracts features for causal learning")
    print("Import this module and use FloodExperienceCollector class")

