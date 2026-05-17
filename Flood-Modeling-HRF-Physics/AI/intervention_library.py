#!/usr/bin/env python3
"""
Intervention Library - Real Civil Engineering Infrastructure
Cost estimates based on typical Indian urban infrastructure (to be validated with CEEW)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np

@dataclass
class InterventionSpec:
    """Specification for a single intervention type"""
    type: str  # 'culvert', 'drain', 'pond', 'pump', 'permeable'
    name: str
    description: str
    
    # Technical specs
    capacity_m3_s: Optional[float] = None
    dimensions: str = ""
    
    # Costs (in Rupees)
    cost_base: float = 0  # Fixed cost
    cost_per_unit: float = 0  # Per meter, per m2, etc.
    maintenance_annual: float = 0  # Annual maintenance
    lifespan_years: int = 50
    
    # Constraints
    min_slope: float = 0.001
    max_depth: float = 6.0
    min_spacing: float = 50  # meters between similar interventions
    requires_land_acquisition: bool = False
    requires_power: bool = False
    must_follow_roads: bool = False
    
    def total_cost(self, length_or_area: float = 1.0) -> float:
        """Calculate total cost given length/area"""
        return self.cost_base + (self.cost_per_unit * length_or_area)
    
    def annual_cost(self, length_or_area: float = 1.0) -> float:
        """Calculate annualized cost (including maintenance)"""
        capital = self.total_cost(length_or_area)
        annualized_capital = capital / self.lifespan_years
        return annualized_capital + self.maintenance_annual


# =============================================================================
# INTERVENTION CATALOG
# Based on typical Indian urban infrastructure costs (2024)
# TO BE UPDATED WITH CEEW/CPWD RATES
# =============================================================================

INTERVENTION_CATALOG = {
    # CULVERTS
    'culvert_box_2x2': InterventionSpec(
        type='culvert',
        name='Box Culvert (2m × 2m)',
        description='Standard RCC box culvert for urban drainage',
        capacity_m3_s=5.0,
        dimensions='2m × 2m × typical 10m length',
        cost_base=2000000,  # ₹20 lakh (₹15-25L typical range)
        cost_per_unit=0,  # Base cost includes typical installation
        maintenance_annual=30000,  # ₹30k/year
        lifespan_years=50,
        min_slope=0.001,
        max_depth=6.0,
        min_spacing=50,
    ),
    
    'culvert_box_3x3': InterventionSpec(
        type='culvert',
        name='Box Culvert (3m × 3m)',
        description='Large RCC box culvert for main drains',
        capacity_m3_s=12.0,
        dimensions='3m × 3m × typical 10m length',
        cost_base=3500000,  # ₹35 lakh
        maintenance_annual=50000,
        lifespan_years=50,
        min_slope=0.001,
        max_depth=8.0,
        min_spacing=100,
    ),
    
    # DRAINS
    'drain_rcc_1m': InterventionSpec(
        type='drain',
        name='RCC Drain (1m wide)',
        description='Covered rectangular drain along roads',
        capacity_m3_s=2.0,
        dimensions='1m wide × 0.8m deep',
        cost_base=0,
        cost_per_unit=8000,  # ₹8k per meter (₹6-10k typical)
        maintenance_annual=50000,  # ₹50k/km/year
        lifespan_years=40,
        min_slope=0.002,
        must_follow_roads=True,
        max_depth=3.0,
    ),
    
    'drain_rcc_1.5m': InterventionSpec(
        type='drain',
        name='RCC Drain (1.5m wide)',
        description='Large covered drain for heavy flows',
        capacity_m3_s=4.0,
        dimensions='1.5m wide × 1.2m deep',
        cost_base=0,
        cost_per_unit=12000,  # ₹12k per meter
        maintenance_annual=80000,  # ₹80k/km/year
        lifespan_years=40,
        min_slope=0.002,
        must_follow_roads=True,
        max_depth=4.0,
    ),
    
    # DETENTION PONDS (SCALED UP 5X FOR REAL IMPACT)
    'pond_medium': InterventionSpec(
        type='storage',
        name='Detention Pond (25000 m³)',  # Was 5000, now 5x bigger
        description='Large surface storage basin with controlled outlet',
        capacity_m3_s=0,  # Storage, not continuous flow
        dimensions='25000 m³ capacity, ~5000 m² area',
        cost_base=80000000,  # ₹8 Cr (scales with volume, but economies of scale)
        cost_per_unit=3200,  # ₹3.2k per m³ (better than before due to scale)
        maintenance_annual=1500000,  # ₹15 lakh/year
        lifespan_years=60,
        requires_land_acquisition=True,
        min_spacing=800,  # Bigger spacing needed
    ),
    
    'pond_large': InterventionSpec(
        type='storage',
        name='Detention Pond (50000 m³)',  # Was 10000, now 5x bigger
        description='Major surface storage for regional drainage',
        capacity_m3_s=0,
        dimensions='50000 m³ capacity, ~8000 m² area',
        cost_base=140000000,  # ₹14 Cr (₹2800/m³ - good economies of scale)
        cost_per_unit=2800,  # Even better rate at this scale
        maintenance_annual=2500000,  # ₹25 lakh/year
        lifespan_years=60,
        requires_land_acquisition=True,
        min_spacing=1500,  # Needs more space
    ),
    
    # NEW: MEGA POND (100,000 m³)
    'pond_xlarge': InterventionSpec(
        type='storage',
        name='Mega Detention Pond (100000 m³)',
        description='Regional-scale storage for critical areas',
        capacity_m3_s=0,
        dimensions='100000 m³ capacity, ~12000 m² area',
        cost_base=250000000,  # ₹25 Cr (₹2500/m³ - best economies of scale)
        cost_per_unit=2500,
        maintenance_annual=4000000,  # ₹40 lakh/year
        lifespan_years=60,
        requires_land_acquisition=True,
        min_spacing=2000,  # Large footprint
    ),
    
    # PUMP STATIONS
    'pump_small': InterventionSpec(
        type='active',
        name='Pump Station (1.5 m³/s)',
        description='Submersible pump with wet well',
        capacity_m3_s=1.5,
        dimensions='Single 1.5 m³/s pump with controls',
        cost_base=15000000,  # ₹1.5 Cr (₹1.2-1.8 Cr typical)
        maintenance_annual=300000,  # ₹3 lakh/year
        lifespan_years=25,  # Shorter due to mechanical components
        requires_power=True,
        min_spacing=200,
    ),
    
    'pump_medium': InterventionSpec(
        type='active',
        name='Pump Station (3.0 m³/s)',
        description='Dual pump system with backup',
        capacity_m3_s=3.0,
        dimensions='Two 1.5 m³/s pumps with controls',
        cost_base=25000000,  # ₹2.5 Cr
        maintenance_annual=500000,
        lifespan_years=25,
        requires_power=True,
        min_spacing=500,
    ),
    
    # PERMEABLE SURFACES
    'permeable_pavement': InterventionSpec(
        type='surface',
        name='Permeable Pavement',
        description='Porous pavement for infiltration',
        capacity_m3_s=0,  # Infiltration, not flow
        dimensions='Per m² of road surface',
        cost_base=0,
        cost_per_unit=1200,  # ₹1200 per m² (₹800-1500 typical)
        maintenance_annual=200000,  # ₹2 lakh per km² per year
        lifespan_years=20,
        must_follow_roads=True,
    ),
    
    # =========================================================================
    # ADVANCED INTERVENTIONS (New - Phase 2)
    # =========================================================================
    
    # FLOOD BARRIERS
    'flood_wall_concrete': InterventionSpec(
        type='barrier',
        name='Concrete Flood Wall',
        description='Permanent concrete barrier to block flood paths',
        capacity_m3_s=0,  # Barrier, not flow
        dimensions='H=2-6m, per meter length',
        cost_base=1000000,  # ₹10 lakh base
        cost_per_unit=50000,  # ₹50k per meter
        maintenance_annual=50000,
        lifespan_years=100,
        requires_land_acquisition=False,  # Usually on public land
        min_spacing=100,
    ),
    
    'levee_earthen': InterventionSpec(
        type='barrier',
        name='Earthen Levee',
        description='Compacted earth embankment along flood-prone areas',
        capacity_m3_s=0,
        dimensions='H=3-8m, base=5×height, per meter',
        cost_base=500000,  # ₹5 lakh base
        cost_per_unit=15000,  # ₹15k per meter
        maintenance_annual=100000,
        lifespan_years=50,
        requires_land_acquisition=True,
        min_spacing=200,
    ),
    
    'floodgate_automated': InterventionSpec(
        type='active_barrier',
        name='Automated Floodgate',
        description='Motorized gate for controlled drainage blockage',
        capacity_m3_s=20.0,  # Can pass flow when open
        dimensions='W=5-15m, motorized',
        cost_base=80000000,  # ₹8 Cr
        maintenance_annual=500000,
        lifespan_years=50,
        requires_power=True,
        requires_land_acquisition=False,
        min_spacing=1000,
    ),
    
    # STORAGE (Expanded)
    'detention_basin_dry': InterventionSpec(
        type='storage',
        name='Dry Detention Basin',
        description='Large temporary storage (empty except during floods)',
        capacity_m3_s=0,
        dimensions='Vol=20000-100000 m³',
        cost_base=50000000,  # ₹5 Cr
        cost_per_unit=2000,  # ₹2k per m³
        maintenance_annual=1000000,
        lifespan_years=75,
        requires_land_acquisition=True,
        min_spacing=2000,
    ),
    
    'retention_pond_wet': InterventionSpec(
        type='storage',
        name='Wet Retention Pond',
        description='Permanent water body for peak shaving + amenity',
        capacity_m3_s=0,
        dimensions='Vol=10000-50000 m³, permanent water',
        cost_base=40000000,  # ₹4 Cr
        cost_per_unit=3000,  # ₹3k per m³ (includes landscaping)
        maintenance_annual=800000,
        lifespan_years=50,
        requires_land_acquisition=True,
        min_spacing=1500,
    ),
    
    'underground_tank': InterventionSpec(
        type='storage',
        name='Underground Storage Tank',
        description='Buried RCC tank under roads/parks',
        capacity_m3_s=0,
        dimensions='Vol=2000-10000 m³, buried',
        cost_base=60000000,  # ₹6 Cr
        cost_per_unit=8000,  # ₹8k per m³ (expensive but no land acquisition)
        maintenance_annual=300000,
        lifespan_years=100,
        requires_land_acquisition=False,  # Under existing infrastructure
        min_spacing=500,
    ),
    
    # CONVEYANCE (Expanded)
    'channel_upgrade_concrete': InterventionSpec(
        type='drain',
        name='Channel Lining & Widening',
        description='Upgrade existing natural channel with concrete',
        capacity_m3_s=15.0,
        dimensions='W=5-10m, D=2-4m',
        cost_base=5000000,  # ₹50 lakh
        cost_per_unit=40000,  # ₹40k per meter
        maintenance_annual=200000,
        lifespan_years=75,
        min_slope=0.0005,
        min_spacing=1000,
    ),
    
    'box_culvert_large': InterventionSpec(
        type='culvert',
        name='Large Box Culvert (4m × 4m)',
        description='Heavy-duty box culvert for main drains',
        capacity_m3_s=20.0,
        dimensions='4m × 4m RCC',
        cost_base=50000000,  # ₹5 Cr
        maintenance_annual=100000,
        lifespan_years=100,
        min_spacing=500,
    ),
    
    'pipe_culvert_hdpe': InterventionSpec(
        type='culvert',
        name='HDPE Pipe Culvert (2m dia)',
        description='High-density polyethylene pipe for quick installation',
        capacity_m3_s=6.0,
        dimensions='D=2m HDPE',
        cost_base=8000000,  # ₹80 lakh
        maintenance_annual=50000,
        lifespan_years=50,
        min_spacing=100,
    ),
    
    # GREEN INFRASTRUCTURE
    'bioswale': InterventionSpec(
        type='green',
        name='Bioswale',
        description='Vegetated channel for conveyance + infiltration',
        capacity_m3_s=0.5,
        dimensions='W=2-5m, vegetated',
        cost_base=100000,  # ₹1 lakh
        cost_per_unit=5000,  # ₹5k per meter
        maintenance_annual=50000,
        lifespan_years=25,
        must_follow_roads=True,
        min_spacing=50,
    ),
    
    'rain_garden': InterventionSpec(
        type='green',
        name='Rain Garden',
        description='Depressed planted area for infiltration',
        capacity_m3_s=0,
        dimensions='Area=50-500 m², depth=0.3-0.6m',
        cost_base=200000,  # ₹2 lakh
        cost_per_unit=2000,  # ₹2k per m²
        maintenance_annual=30000,
        lifespan_years=20,
        requires_land_acquisition=False,
        min_spacing=100,
    ),
    
    'green_roof': InterventionSpec(
        type='green',
        name='Green Roof',
        description='Vegetated roof for runoff reduction',
        capacity_m3_s=0,
        dimensions='Per building roof area',
        cost_base=0,
        cost_per_unit=3000,  # ₹3k per m²
        maintenance_annual=50000,
        lifespan_years=30,
        requires_land_acquisition=False,
        min_spacing=0,  # Can be on multiple buildings
    ),
    
    # ACTIVE SYSTEMS (Expanded)
    'pump_station_large': InterventionSpec(
        type='active',
        name='Large Pump Station (5.0 m³/s)',
        description='Major pump station with diesel backup',
        capacity_m3_s=5.0,
        dimensions='3× 1.7 m³/s pumps + backup diesel',
        cost_base=120000000,  # ₹12 Cr
        maintenance_annual=1000000,
        lifespan_years=25,
        requires_power=True,
        min_spacing=2000,
    ),
    
    'smart_valve_network': InterventionSpec(
        type='active',
        name='IoT Smart Valve Network',
        description='Automated valves for adaptive drainage control',
        capacity_m3_s=0,  # Controls existing drainage
        dimensions='Network of 5-10 IoT-controlled valves',
        cost_base=25000000,  # ₹2.5 Cr
        cost_per_unit=2500000,  # ₹25 lakh per additional valve
        maintenance_annual=500000,
        lifespan_years=15,  # Electronics have shorter life
        requires_power=True,
        min_spacing=500,
    ),
    
    # DISTRIBUTED SOLUTIONS
    'infiltration_trench': InterventionSpec(
        type='infiltration',
        name='Infiltration Trench',
        description='Gravel-filled trench for groundwater recharge',
        capacity_m3_s=0,
        dimensions='W=1-2m, D=1-3m, gravel-filled',
        cost_base=100000,  # ₹1 lakh
        cost_per_unit=8000,  # ₹8k per meter
        maintenance_annual=20000,
        lifespan_years=25,
        min_spacing=50,
    ),
    
    'permeable_interlocking_pavers': InterventionSpec(
        type='surface',
        name='Permeable Interlocking Pavers',
        description='Modular permeable blocks for parking/plazas',
        capacity_m3_s=0,
        dimensions='Per m² of surface',
        cost_base=0,
        cost_per_unit=1500,  # ₹1500 per m²
        maintenance_annual=100000,  # ₹1 lakh per km² per year
        lifespan_years=30,
        must_follow_roads=False,  # Can be used in open spaces
        min_spacing=0,
    ),
}


def get_intervention(key: str) -> InterventionSpec:
    """Get intervention spec by key"""
    if key not in INTERVENTION_CATALOG:
        raise ValueError(f"Unknown intervention: {key}. Available: {list(INTERVENTION_CATALOG.keys())}")
    return INTERVENTION_CATALOG[key]


def list_interventions_by_type(intervention_type: str) -> List[str]:
    """List all interventions of a given type"""
    return [k for k, v in INTERVENTION_CATALOG.items() if v.type == intervention_type]


def estimate_cost_scenario(interventions: List[tuple]) -> Dict:
    """
    Estimate total cost for a scenario
    
    Args:
        interventions: List of (intervention_key, length_or_area) tuples
        
    Returns:
        Dict with cost breakdown
    """
    total_capital = 0
    total_annual = 0
    breakdown = []
    
    for key, size in interventions:
        spec = get_intervention(key)
        capital = spec.total_cost(size)
        annual = spec.annual_cost(size)
        
        total_capital += capital
        total_annual += annual
        
        breakdown.append({
            'intervention': spec.name,
            'size': size,
            'capital_cost': capital,
            'annual_cost': annual
        })
    
    return {
        'total_capital_cost': total_capital,
        'total_annual_cost': total_annual,
        'breakdown': breakdown,
        'total_capital_cr': total_capital / 1e7,  # Convert to crores
        'total_annual_lakh': total_annual / 1e5,  # Convert to lakhs
    }


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    print("="*70)
    print("INTERVENTION LIBRARY - COST ESTIMATION")
    print("="*70)
    
    print("\n📋 Available Interventions:")
    for key, spec in INTERVENTION_CATALOG.items():
        print(f"\n  {key}:")
        print(f"    {spec.name} - {spec.description}")
        print(f"    Base cost: ₹{spec.cost_base/1e5:.1f} lakh")
        if spec.cost_per_unit > 0:
            print(f"    Per unit: ₹{spec.cost_per_unit:,.0f}")
        print(f"    Capacity: {spec.capacity_m3_s} m³/s" if spec.capacity_m3_s else "    Storage/infiltration")
    
    # Example scenario
    print("\n\n" + "="*70)
    print("EXAMPLE SCENARIO: ₹12 CR BUDGET")
    print("="*70)
    
    example_interventions = [
        ('culvert_box_2x2', 1),     # 1 culvert
        ('culvert_box_2x2', 1),     # Another culvert
        ('culvert_box_2x2', 1),     # Third culvert
        ('drain_rcc_1m', 1500),     # 1.5 km of drain
        ('drain_rcc_1m', 800),      # 0.8 km more drain
        ('pond_medium', 1),         # 1 detention pond
        ('pump_small', 1),          # 1 pump station
    ]
    
    cost_estimate = estimate_cost_scenario(example_interventions)
    
    print(f"\n💰 Cost Breakdown:")
    for item in cost_estimate['breakdown']:
        print(f"  • {item['intervention']}")
        if item['size'] > 1:
            print(f"    Size: {item['size']} units")
        print(f"    Capital: ₹{item['capital_cost']/1e5:.1f} lakh")
        print(f"    Annual: ₹{item['annual_cost']/1e5:.1f} lakh/year")
    
    print(f"\n📊 Total:")
    print(f"  Capital Cost: ₹{cost_estimate['total_capital_cr']:.2f} Crores")
    print(f"  Annual Maintenance: ₹{cost_estimate['total_annual_lakh']:.1f} lakh/year")
    
    print("\n✅ Ready for spatial optimization!")
    print("="*70)

