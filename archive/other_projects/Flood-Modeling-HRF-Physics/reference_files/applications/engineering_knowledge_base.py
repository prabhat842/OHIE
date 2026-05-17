"""
Engineering Knowledge Base

Contains real-world engineering standards, materials, costs, and design rules
for urban infrastructure. This knowledge base is used by the spec generator
to create construction-ready engineering designs.

Based on:
- Indian Standards (IS codes)
- IRC (Indian Roads Congress) standards
- CPHEEO manual
- NBC (National Building Code)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import math


class SoilType(Enum):
    """Soil classification for foundation design"""
    ROCK = "rock"
    HARD_SOIL = "hard_soil"
    MEDIUM_SOIL = "medium_soil"
    SOFT_SOIL = "soft_soil"
    VERY_SOFT = "very_soft"


class ConcreteGrade(Enum):
    """Concrete grades per IS 456"""
    M15 = "M15"
    M20 = "M20"
    M25 = "M25"
    M30 = "M30"
    M35 = "M35"
    M40 = "M40"


class PipeMaterial(Enum):
    """Pipe materials for drainage"""
    RCC_NP2 = "RCC NP2"
    RCC_NP3 = "RCC NP3"
    RCC_NP4 = "RCC NP4"
    HDPE = "HDPE"
    DI_K7 = "DI K7"
    DI_K9 = "DI K9"
    PVC = "PVC"


@dataclass
class MaterialProperties:
    """Material properties and costs"""
    name: str
    unit: str
    unit_cost: float  # INR
    density: Optional[float] = None  # kg/m³
    strength: Optional[float] = None
    durability_years: int = 50
    
    
@dataclass
class ConstructionActivity:
    """Construction activity with duration and crew requirements"""
    name: str
    description: str
    duration_days: float
    crew_size: int
    equipment: List[str]
    dependencies: List[str]  # Must complete before this
    unit_rate: float  # INR per unit


class EngineeringKnowledgeBase:
    """
    Comprehensive engineering knowledge for infrastructure design.
    
    Contains:
    - Material specifications and costs
    - Design standards and codes
    - Construction methods and rates
    - Hydraulic design parameters
    - Structural design rules
    """
    
    def __init__(self):
        self.materials = self._initialize_materials()
        self.concrete_grades = self._initialize_concrete_grades()
        self.pipe_materials = self._initialize_pipe_materials()
        self.construction_rates = self._initialize_construction_rates()
        self.design_standards = self._initialize_design_standards()
        
    def _initialize_materials(self) -> Dict[str, MaterialProperties]:
        """Initialize material properties database"""
        return {
            # Concrete materials
            'cement_opc43': MaterialProperties(
                name="OPC 43 Grade Cement",
                unit="tonne",
                unit_cost=6000,
                density=1440
            ),
            'cement_opc53': MaterialProperties(
                name="OPC 53 Grade Cement",
                unit="tonne",
                unit_cost=6500,
                density=1440
            ),
            'sand': MaterialProperties(
                name="Fine Aggregate (Sand)",
                unit="cum",
                unit_cost=800,
                density=1600
            ),
            'coarse_aggregate_20mm': MaterialProperties(
                name="Coarse Aggregate 20mm",
                unit="cum",
                unit_cost=1200,
                density=1450
            ),
            'coarse_aggregate_40mm': MaterialProperties(
                name="Coarse Aggregate 40mm",
                unit="cum",
                unit_cost=1100,
                density=1450
            ),
            
            # Steel reinforcement
            'steel_tor8mm': MaterialProperties(
                name="TMT Steel Bar 8mm",
                unit="tonne",
                unit_cost=55000,
                density=7850,
                strength=500  # Fe500
            ),
            'steel_tor10mm': MaterialProperties(
                name="TMT Steel Bar 10mm",
                unit="tonne",
                unit_cost=54000,
                density=7850,
                strength=500
            ),
            'steel_tor12mm': MaterialProperties(
                name="TMT Steel Bar 12mm",
                unit="tonne",
                unit_cost=53000,
                density=7850,
                strength=500
            ),
            'steel_tor16mm': MaterialProperties(
                name="TMT Steel Bar 16mm",
                unit="tonne",
                unit_cost=52000,
                density=7850,
                strength=500
            ),
            
            # Pipes
            'rcc_pipe_np3_300mm': MaterialProperties(
                name="RCC NP3 Pipe 300mm",
                unit="m",
                unit_cost=450,
                durability_years=50
            ),
            'rcc_pipe_np3_450mm': MaterialProperties(
                name="RCC NP3 Pipe 450mm",
                unit="m",
                unit_cost=850,
                durability_years=50
            ),
            'rcc_pipe_np3_600mm': MaterialProperties(
                name="RCC NP3 Pipe 600mm",
                unit="m",
                unit_cost=1500,
                durability_years=50
            ),
            'hdpe_pipe_300mm': MaterialProperties(
                name="HDPE Pipe 300mm",
                unit="m",
                unit_cost=380,
                durability_years=50
            ),
            'hdpe_pipe_450mm': MaterialProperties(
                name="HDPE Pipe 450mm",
                unit="m",
                unit_cost=720,
                durability_years=50
            ),
            
            # Excavation
            'excavation_ordinary_soil': MaterialProperties(
                name="Excavation in ordinary soil",
                unit="cum",
                unit_cost=120
            ),
            'excavation_hard_soil': MaterialProperties(
                name="Excavation in hard soil",
                unit="cum",
                unit_cost=180
            ),
            'excavation_rock': MaterialProperties(
                name="Excavation in rock",
                unit="cum",
                unit_cost=450
            ),
            
            # Plants
            'native_tree_sapling': MaterialProperties(
                name="Native tree sapling",
                unit="each",
                unit_cost=150,
                durability_years=50
            ),
            'grass_turf': MaterialProperties(
                name="Grass turf",
                unit="sqm",
                unit_cost=80,
                durability_years=5
            ),
            'bioswale_soil_mix': MaterialProperties(
                name="Bioswale engineered soil mix",
                unit="cum",
                unit_cost=2500,
                durability_years=25
            ),
            'geotextile': MaterialProperties(
                name="Geotextile fabric",
                unit="sqm",
                unit_cost=45,
                durability_years=25
            ),
            
            # Waterproofing
            'waterproofing_compound': MaterialProperties(
                name="Integral waterproofing compound",
                unit="litre",
                unit_cost=350,
                durability_years=30
            ),
            'epoxy_coating': MaterialProperties(
                name="Epoxy coating",
                unit="sqm",
                unit_cost=280,
                durability_years=15
            )
        }
    
    def _initialize_concrete_grades(self) -> Dict[str, Dict]:
        """Concrete mix designs per IS 456"""
        return {
            'M15': {
                'cement': 0.210,      # tonnes per cum
                'sand': 0.440,        # cum per cum
                'coarse_agg': 0.880,  # cum per cum
                'water': 0.190,       # cum per cum
                'strength_mpa': 15,
                'applications': ['lean concrete', 'leveling'],
                'cost_per_cum': 3800
            },
            'M20': {
                'cement': 0.280,
                'sand': 0.420,
                'coarse_agg': 0.840,
                'water': 0.180,
                'strength_mpa': 20,
                'applications': ['foundations', 'slabs', 'columns'],
                'cost_per_cum': 4500
            },
            'M25': {
                'cement': 0.320,
                'sand': 0.410,
                'coarse_agg': 0.820,
                'water': 0.170,
                'strength_mpa': 25,
                'applications': ['beams', 'columns', 'structural elements'],
                'cost_per_cum': 5200
            },
            'M30': {
                'cement': 0.360,
                'sand': 0.400,
                'coarse_agg': 0.800,
                'water': 0.165,
                'strength_mpa': 30,
                'applications': ['detention basins', 'retaining walls', 'heavy structures'],
                'cost_per_cum': 5800
            },
            'M35': {
                'cement': 0.400,
                'sand': 0.390,
                'coarse_agg': 0.780,
                'water': 0.160,
                'strength_mpa': 35,
                'applications': ['high-strength requirements', 'pump stations'],
                'cost_per_cum': 6500
            }
        }
    
    def _initialize_pipe_materials(self) -> Dict[str, Dict]:
        """Pipe specifications per IS standards"""
        return {
            'RCC_NP3_300': {
                'diameter_mm': 300,
                'class': 'NP3',
                'working_pressure_bar': 3,
                'test_pressure_bar': 4.5,
                'thickness_mm': 45,
                'weight_kg_per_m': 85,
                'cost_per_m': 450,
                'standard': 'IS 458'
            },
            'RCC_NP3_450': {
                'diameter_mm': 450,
                'class': 'NP3',
                'working_pressure_bar': 3,
                'test_pressure_bar': 4.5,
                'thickness_mm': 55,
                'weight_kg_per_m': 140,
                'cost_per_m': 850,
                'standard': 'IS 458'
            },
            'RCC_NP3_600': {
                'diameter_mm': 600,
                'class': 'NP3',
                'working_pressure_bar': 3,
                'test_pressure_bar': 4.5,
                'thickness_mm': 65,
                'weight_kg_per_m': 210,
                'cost_per_m': 1500,
                'standard': 'IS 458'
            },
            'HDPE_300': {
                'diameter_mm': 300,
                'class': 'PE100',
                'working_pressure_bar': 6,
                'sdr': 17,
                'thickness_mm': 17.9,
                'weight_kg_per_m': 12.5,
                'cost_per_m': 380,
                'standard': 'IS 4984'
            }
        }
    
    def _initialize_construction_rates(self) -> Dict[str, ConstructionActivity]:
        """Construction activities with rates per CPWD/DSR"""
        return {
            'excavation_ordinary': ConstructionActivity(
                name="Excavation in ordinary soil",
                description="Excavation by mechanical means including dewatering",
                duration_days=0.05,  # per cum
                crew_size=4,
                equipment=['excavator_20t', 'tipper_10t'],
                dependencies=[],
                unit_rate=120
            ),
            'excavation_rock': ConstructionActivity(
                name="Excavation in rock",
                description="Rock excavation with breaker/blasting",
                duration_days=0.12,
                crew_size=6,
                equipment=['excavator_breaker', 'tipper_10t'],
                dependencies=[],
                unit_rate=450
            ),
            'concrete_m30': ConstructionActivity(
                name="M30 Concrete",
                description="Supply, mix, pour, vibrate, cure M30 grade concrete",
                duration_days=0.08,  # per cum
                crew_size=8,
                equipment=['concrete_mixer', 'vibrator', 'pumps'],
                dependencies=['formwork', 'reinforcement'],
                unit_rate=5800
            ),
            'reinforcement': ConstructionActivity(
                name="Reinforcement fixing",
                description="Cutting, bending, placing TMT bars",
                duration_days=0.15,  # per tonne
                crew_size=4,
                equipment=['bar_bender', 'cutting_machine'],
                dependencies=['formwork'],
                unit_rate=52000
            ),
            'formwork': ConstructionActivity(
                name="Formwork",
                description="Plywood formwork with supports",
                duration_days=0.12,  # per sqm
                crew_size=6,
                equipment=['scaffolding'],
                dependencies=['excavation'],
                unit_rate=350
            ),
            'pipe_laying_rcc': ConstructionActivity(
                name="RCC Pipe laying",
                description="Laying, jointing, testing RCC pipes",
                duration_days=0.25,  # per m
                crew_size=5,
                equipment=['crane_mobile'],
                dependencies=['trench_excavation', 'bedding'],
                unit_rate=180
            ),
            'tree_planting': ConstructionActivity(
                name="Tree planting",
                description="Pit excavation, soil preparation, planting, watering",
                duration_days=0.5,  # per tree
                crew_size=2,
                equipment=[],
                dependencies=[],
                unit_rate=450
            ),
            'bioswale_construction': ConstructionActivity(
                name="Bioswale construction",
                description="Excavation, soil placement, vegetation, mulching",
                duration_days=0.8,  # per 10m length
                crew_size=4,
                equipment=['bobcat'],
                dependencies=[],
                unit_rate=15000
            )
        }
    
    def _initialize_design_standards(self) -> Dict[str, Dict]:
        """Design standards and guidelines"""
        return {
            'detention_basin': {
                'min_freeboard_m': 0.5,
                'side_slope_ratio': 2.0,  # H:V (2 horizontal : 1 vertical)
                'min_depth_m': 2.0,
                'max_depth_m': 5.0,
                'concrete_grade': 'M30',
                'min_thickness_mm': 200,
                'safety_factor': 1.5,
                'overflow_factor': 1.2,
                'standards': ['IS 3370', 'IS 456']
            },
            'drainage_pipe': {
                'min_grade_percent': 0.1,
                'max_velocity_mps': 3.0,
                'min_velocity_mps': 0.6,
                'mannings_n': 0.013,  # for concrete pipes
                'min_cover_m': 0.6,
                'bedding_thickness_mm': 150,
                'standards': ['IS 1742', 'IRC SP 50']
            },
            'bioswale': {
                'bottom_width_m': 1.5,
                'side_slope_ratio': 3.0,  # 3:1 for vegetation
                'min_depth_m': 0.3,
                'max_depth_m': 0.6,
                'longitudinal_slope_percent': 2.0,
                'soil_permeability_mm_hr': 50,
                'vegetation_type': 'native_grasses',
                'standards': ['CPHEEO Manual']
            },
            'pump_station': {
                'design_flow_factor': 1.5,  # peak factor
                'wet_well_detention_min': 20,  # minutes at peak flow
                'pump_count': 2,  # minimum for redundancy
                'pump_type': 'submersible',
                'concrete_grade': 'M35',
                'waterproofing': 'integral + coating',
                'standards': ['IS 9283', 'IS 2186']
            },
            'green_roof': {
                'min_depth_mm': 100,
                'max_depth_mm': 400,
                'drainage_layer_mm': 50,
                'filter_fabric': 'geotextile_200gsm',
                'growing_medium_depth_mm': 150,
                'waterproof_membrane': 'EPDM',
                'standards': ['NBC', 'IGBC Guidelines']
            }
        }
    
    def get_concrete_volume_requirements(self, grade: str, volume_cum: float) -> Dict[str, float]:
        """
        Calculate material requirements for concrete.
        
        Args:
            grade: Concrete grade (e.g., 'M30')
            volume_cum: Volume in cubic meters
        
        Returns:
            Dict with quantities of cement, sand, aggregate, water
        """
        if grade not in self.concrete_grades:
            raise ValueError(f"Unknown concrete grade: {grade}")
        
        mix = self.concrete_grades[grade]
        
        return {
            'cement_tonnes': mix['cement'] * volume_cum,
            'sand_cum': mix['sand'] * volume_cum,
            'coarse_aggregate_cum': mix['coarse_agg'] * volume_cum,
            'water_cum': mix['water'] * volume_cum,
            'total_cost': mix['cost_per_cum'] * volume_cum
        }
    
    def calculate_reinforcement(
        self, 
        concrete_volume_cum: float,
        reinforcement_percent: float = 1.0
    ) -> Dict[str, float]:
        """
        Calculate reinforcement requirements.
        
        Args:
            concrete_volume_cum: Volume of concrete
            reinforcement_percent: Percentage of steel (0.5-2.0 typical)
        
        Returns:
            Dict with steel quantity and cost
        """
        # Concrete density ~ 2500 kg/m³
        concrete_weight_kg = concrete_volume_cum * 2500
        steel_weight_kg = concrete_weight_kg * (reinforcement_percent / 100)
        steel_weight_tonnes = steel_weight_kg / 1000
        
        # Average cost of mixed bar sizes
        avg_steel_rate = 53000  # INR per tonne
        
        return {
            'steel_tonnes': steel_weight_tonnes,
            'steel_cost': steel_weight_tonnes * avg_steel_rate
        }
    
    def select_pipe_size(self, flow_lps: float, slope_percent: float) -> Dict[str, any]:
        """
        Select appropriate pipe size based on hydraulic requirements.
        
        Uses Manning's equation: Q = (1/n) * A * R^(2/3) * S^(1/2)
        
        Args:
            flow_lps: Design flow in liters per second
            slope_percent: Pipe slope in percentage
        
        Returns:
            Dict with pipe specification
        """
        flow_cms = flow_lps / 1000  # Convert to cubic meters per second
        slope = slope_percent / 100
        
        # Try standard pipe sizes
        pipe_sizes = [300, 450, 600, 750, 900]  # mm
        
        for diameter_mm in pipe_sizes:
            diameter_m = diameter_mm / 1000
            area = math.pi * (diameter_m ** 2) / 4
            perimeter = math.pi * diameter_m
            hydraulic_radius = area / perimeter
            
            # Manning's equation (n = 0.013 for concrete)
            capacity_cms = (1/0.013) * area * (hydraulic_radius ** (2/3)) * (slope ** 0.5)
            
            # Apply safety factor (use 80% of capacity)
            usable_capacity = capacity_cms * 0.8
            
            if usable_capacity >= flow_cms:
                pipe_key = f"RCC_NP3_{diameter_mm}"
                if pipe_key in self.pipe_materials:
                    return {
                        'diameter_mm': diameter_mm,
                        'capacity_lps': usable_capacity * 1000,
                        'velocity_mps': flow_cms / area,
                        'specification': self.pipe_materials[pipe_key],
                        'recommended': True
                    }
        
        # If no standard size works, return largest
        return {
            'diameter_mm': 900,
            'capacity_lps': 0,
            'recommended': False,
            'note': 'Flow exceeds standard pipe capacity - consider multiple pipes'
        }
    
    def estimate_excavation_cost(
        self,
        volume_cum: float,
        soil_type: SoilType,
        depth_m: float
    ) -> Dict[str, float]:
        """
        Estimate excavation cost based on soil type and depth.
        
        Args:
            volume_cum: Volume to excavate
            soil_type: Type of soil
            depth_m: Depth of excavation
        
        Returns:
            Dict with cost breakdown
        """
        # Base rates
        rates = {
            SoilType.ROCK: 450,
            SoilType.HARD_SOIL: 180,
            SoilType.MEDIUM_SOIL: 120,
            SoilType.SOFT_SOIL: 100,
            SoilType.VERY_SOFT: 90
        }
        
        base_rate = rates.get(soil_type, 120)
        
        # Depth factor (deeper = more expensive due to dewatering, supports)
        depth_factor = 1.0
        if depth_m > 3:
            depth_factor = 1.2
        if depth_m > 5:
            depth_factor = 1.5
        
        # Dewatering cost if needed
        dewatering_cost = 0
        if depth_m > 2:
            dewatering_cost = volume_cum * 25  # INR per cum for dewatering
        
        total_cost = (base_rate * depth_factor * volume_cum) + dewatering_cost
        
        return {
            'excavation_volume_cum': volume_cum,
            'base_rate': base_rate,
            'depth_factor': depth_factor,
            'excavation_cost': base_rate * depth_factor * volume_cum,
            'dewatering_cost': dewatering_cost,
            'total_cost': total_cost
        }


# Singleton instance
knowledge_base = EngineeringKnowledgeBase()

