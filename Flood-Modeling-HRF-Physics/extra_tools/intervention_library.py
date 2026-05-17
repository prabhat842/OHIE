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
    
    # DETENTION PONDS
    'pond_medium': InterventionSpec(
        type='storage',
        name='Detention Pond (5000 m³)',
        description='Surface storage basin with controlled outlet',
        capacity_m3_s=0,  # Storage, not continuous flow
        dimensions='5000 m³ capacity, ~2000 m² area',
        cost_base=20000000,  # ₹2 Cr (₹1.8-2.2 Cr typical)
        cost_per_unit=4000,  # ₹4k per additional m³
        maintenance_annual=500000,  # ₹5 lakh/year
        lifespan_years=60,
        requires_land_acquisition=True,
        min_spacing=500,
    ),
    
    'pond_large': InterventionSpec(
        type='storage',
        name='Detention Pond (10000 m³)',
        description='Large surface storage for major drainage',
        capacity_m3_s=0,
        dimensions='10000 m³ capacity, ~4000 m² area',
        cost_base=35000000,  # ₹3.5 Cr
        cost_per_unit=3500,  # Economies of scale
        maintenance_annual=800000,
        lifespan_years=60,
        requires_land_acquisition=True,
        min_spacing=1000,
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

