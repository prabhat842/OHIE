"""
Generative Urban Resilience using Enhanced QCIA

This module applies Enhanced QCIA to high-stakes urban resilience design:
- Generate optimal flood mitigation infrastructure
- Design green infrastructure for climate resilience
- Optimize budget allocation across interventions
- Ensure equity and effectiveness

Key Features:
- Causal understanding: Knows WHY interventions work
- Quantum optimization: Finds globally optimal designs
- Experience learning: Gets smarter over time
- Failure avoidance: Learns what NOT to do
- Explainable: Shows causal reasoning for decisions

Example Use Cases:
1. Flood mitigation design (drainage, green infrastructure, elevation)
2. Heat island mitigation (trees, cool roofs, water features)
3. Disaster preparedness (shelters, evacuation routes, stockpiles)
4. Climate adaptation (sea walls, nature-based solutions)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Callable
from dataclasses import dataclass
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from qcia_core.enhanced_qcia import EnhancedQCIA, DesignExperience


@dataclass
class UrbanIntervention:
    """
    Represents a single urban resilience intervention.
    
    Examples:
    - Drainage system (pipes, pumps, storage)
    - Green infrastructure (bioswales, rain gardens, green roofs)
    - Gray infrastructure (levees, sea walls, elevation)
    - Nature-based solutions (wetlands, forests, parks)
    """
    name: str
    category: str  # 'drainage', 'green', 'gray', 'nature'
    cost_per_unit: float
    effectiveness: float  # Base effectiveness (0-1)
    maintenance_cost: float  # Annual maintenance as fraction of capital
    lifespan_years: int
    scalable: bool = True  # Can we build more?
    
    def total_cost(self, scale: float) -> float:
        """Calculate total cost including maintenance (NPV)"""
        capital_cost = self.cost_per_unit * scale
        discount_rate = 0.03
        maintenance_npv = sum(
            (capital_cost * self.maintenance_cost) / (1 + discount_rate)**t
            for t in range(1, self.lifespan_years + 1)
        )
        return capital_cost + maintenance_npv


class UrbanResilienceGenerator:
    """
    Generative AI for Urban Resilience Design using Enhanced QCIA.
    
    This system:
    1. Generates candidate urban designs
    2. Simulates their performance (flood reduction, etc.)
    3. Learns causal relationships (what interventions CAUSE improvements)
    4. Optimizes using quantum-inspired methods
    5. Explains decisions causally
    
    Example:
        >>> generator = UrbanResilienceGenerator(city_name="Jabalpur")
        >>> generator.define_interventions([...])
        >>> generator.set_constraints(budget=10_000_000, flood_target=0.7)
        >>> optimal_design = generator.generate_optimal_design()
        >>> generator.explain_design(optimal_design)
    """
    
    def __init__(
        self,
        city_name: str = "City",
        population: int = 1000000,
        area_km2: float = 100.0,
        flood_simulator: Optional[Callable] = None,
        verbose: bool = True
    ):
        """
        Initialize the urban resilience generator.
        
        Args:
            city_name: Name of the city
            population: City population
            area_km2: City area in square kilometers
            flood_simulator: Optional function to simulate floods. If None, uses simplified model.
            verbose: Whether to print progress
        """
        self.city_name = city_name
        self.population = population
        self.area_km2 = area_km2
        self.flood_simulator = flood_simulator or self._default_flood_simulator
        self.verbose = verbose
        
        # Initialize Enhanced QCIA
        self.qcia = EnhancedQCIA(
            alpha=0.05,
            initial_exploration_rate=1.0,
            min_experiences_for_causal=20,
            verbose=verbose
        )
        
        # Design space
        self.interventions: List[UrbanIntervention] = []
        self.constraints = {}
        self.objectives = {}
        
    def define_interventions(self, interventions: List[UrbanIntervention]):
        """
        Define available interventions for the city.
        
        Example:
            >>> generator.define_interventions([
            ...     UrbanIntervention(
            ...         name="bioswale",
            ...         category="green",
            ...         cost_per_unit=50000,  # per 100m
            ...         effectiveness=0.15,
            ...         maintenance_cost=0.05,
            ...         lifespan_years=25
            ...     ),
            ...     UrbanIntervention(
            ...         name="detention_basin",
            ...         category="gray",
            ...         cost_per_unit=2000000,  # per basin
            ...         effectiveness=0.40,
            ...         maintenance_cost=0.03,
            ...         lifespan_years=50
            ...     ),
            ... ])
        """
        self.interventions = interventions
        if self.verbose:
            print(f"\n📋 Defined {len(interventions)} interventions for {self.city_name}")
            for interv in interventions:
                print(f"   - {interv.name} ({interv.category}): "
                      f"₹{interv.cost_per_unit:,.0f}/unit, "
                      f"effectiveness={interv.effectiveness:.2f}")
    
    def set_constraints(
        self,
        budget: float,
        flood_reduction_target: float = 0.5,
        equity_min: float = 0.3,
        max_construction_time_years: float = 5
    ):
        """
        Set constraints for the optimization.
        
        Args:
            budget: Total budget in currency units
            flood_reduction_target: Target flood reduction (0-1, where 1=complete elimination)
            equity_min: Minimum fraction of benefits that must go to vulnerable populations
            max_construction_time_years: Maximum time to complete construction
        """
        self.constraints = {
            'budget': budget,
            'flood_reduction_target': flood_reduction_target,
            'equity_min': equity_min,
            'max_construction_time_years': max_construction_time_years
        }
        
        if self.verbose:
            print(f"\n🎯 Constraints set:")
            print(f"   Budget: ₹{budget:,.0f}")
            print(f"   Flood reduction target: {flood_reduction_target:.1%}")
            print(f"   Equity minimum: {equity_min:.1%}")
            print(f"   Construction time: ≤{max_construction_time_years} years")
    
    def generate_optimal_design(
        self,
        n_iterations: int = 100,
        multi_objective_weights: Optional[Dict[str, float]] = None
    ) -> Dict:
        """
        Generate optimal urban resilience design using Enhanced QCIA.
        
        Args:
            n_iterations: Number of design iterations to explore
            multi_objective_weights: Weights for multiple objectives.
                                    Default: {'flood_reduction': 0.5, 'cost_efficiency': 0.3, 'equity': 0.2}
        
        Returns:
            Dict with optimal design and explanations
        """
        if not self.interventions:
            raise ValueError("Must define interventions first using define_interventions()")
        
        if not self.constraints:
            raise ValueError("Must set constraints first using set_constraints()")
        
        # Default multi-objective weights
        if multi_objective_weights is None:
            multi_objective_weights = {
                'flood_reduction': 0.5,
                'cost_efficiency': 0.3,
                'equity': 0.2,
                'sustainability': 0.0  # Optional
            }
        
        if self.verbose:
            print(f"\n{'='*80}")
            print(f"🏙️  GENERATIVE URBAN RESILIENCE - {self.city_name.upper()}")
            print(f"{'='*80}")
            print(f"\nOptimization objectives:")
            for obj, weight in multi_objective_weights.items():
                if weight > 0:
                    print(f"   {obj}: {weight:.1%}")
        
        # Define parameter bounds (scale for each intervention)
        parameter_bounds = {}
        for interv in self.interventions:
            # Scale from 0 (none) to reasonable maximum
            max_scale = self.constraints['budget'] / interv.cost_per_unit
            parameter_bounds[interv.name] = (0.0, min(max_scale, 100.0))
        
        # Define objective function
        def objective_function(params: Dict[str, float]) -> float:
            """
            Evaluate a design configuration.
            
            Returns higher score for better designs.
            """
            return self._evaluate_design(params, multi_objective_weights)
        
        # Run Enhanced QCIA meta-optimization
        results = self.qcia.meta_optimize(
            objective_function=objective_function,
            parameter_bounds=parameter_bounds,
            n_iterations=n_iterations,
            goal='maximize'
        )
        
        # Compile comprehensive results
        optimal_design = self._compile_design_report(results, multi_objective_weights)
        
        return optimal_design
    
    def _evaluate_design(
        self,
        intervention_scales: Dict[str, float],
        weights: Dict[str, float]
    ) -> float:
        """
        Evaluate a design configuration across multiple objectives.
        
        This is where the simulation happens. In production, this would
        call actual flood simulation, equity analysis, etc.
        """
        # 1. Calculate total cost
        total_cost = 0
        for interv in self.interventions:
            scale = intervention_scales.get(interv.name, 0)
            total_cost += interv.total_cost(scale)
        
        # Check budget constraint
        if total_cost > self.constraints['budget']:
            # Penalty for exceeding budget
            penalty = (total_cost - self.constraints['budget']) / self.constraints['budget']
            return -penalty * 10  # Large negative score
        
        # 2. Simulate flood reduction
        flood_reduction = self._simulate_flood_reduction(intervention_scales)
        
        # 3. Calculate cost efficiency
        if total_cost > 0:
            cost_efficiency = flood_reduction / (total_cost / self.constraints['budget'])
        else:
            cost_efficiency = 0
        
        # 4. Calculate equity (how benefits are distributed)
        equity = self._calculate_equity(intervention_scales)
        
        # 5. Calculate sustainability (green vs gray infrastructure)
        sustainability = self._calculate_sustainability(intervention_scales)
        
        # 6. Multi-objective score
        score = (
            weights.get('flood_reduction', 0) * flood_reduction +
            weights.get('cost_efficiency', 0) * cost_efficiency +
            weights.get('equity', 0) * equity +
            weights.get('sustainability', 0) * sustainability
        )
        
        return score
    
    def _simulate_flood_reduction(self, intervention_scales: Dict[str, float]) -> float:
        """
        Simulate flood reduction from interventions.
        
        In production, this would call actual flood simulator (HRF, FVM, etc.)
        Here we use a simplified but realistic model.
        """
        if self.flood_simulator != self._default_flood_simulator:
            # Use custom simulator
            return self.flood_simulator(intervention_scales)
        
        # Default model: Combined effectiveness with diminishing returns
        total_reduction = 0
        
        for interv in self.interventions:
            scale = intervention_scales.get(interv.name, 0)
            
            # Effectiveness with diminishing returns
            contribution = interv.effectiveness * (1 - np.exp(-scale / 10))
            total_reduction += contribution
        
        # Cap at 95% (can't eliminate all floods)
        total_reduction = min(total_reduction, 0.95)
        
        # Add some interactions (green + gray is better than either alone)
        green_total = sum(
            intervention_scales.get(i.name, 0) 
            for i in self.interventions if i.category == 'green'
        )
        gray_total = sum(
            intervention_scales.get(i.name, 0) 
            for i in self.interventions if i.category == 'gray'
        )
        
        if green_total > 0 and gray_total > 0:
            synergy_bonus = 0.1 * min(green_total / 10, 1.0) * min(gray_total / 10, 1.0)
            total_reduction += synergy_bonus
        
        return min(total_reduction, 0.95)
    
    def _calculate_equity(self, intervention_scales: Dict[str, float]) -> float:
        """
        Calculate how equitably benefits are distributed.
        
        Green infrastructure typically benefits everyone.
        Gray infrastructure may be more localized.
        """
        if not intervention_scales:
            return 0
        
        # Simple model: green infrastructure is more equitable
        green_proportion = sum(
            intervention_scales.get(i.name, 0) 
            for i in self.interventions if i.category in ['green', 'nature']
        )
        
        total = sum(intervention_scales.values())
        
        if total == 0:
            return 0
        
        equity_score = green_proportion / total
        return equity_score
    
    def _calculate_sustainability(self, intervention_scales: Dict[str, float]) -> float:
        """
        Calculate sustainability (preference for nature-based solutions).
        """
        if not intervention_scales:
            return 0
        
        green_nature_total = sum(
            intervention_scales.get(i.name, 0) 
            for i in self.interventions if i.category in ['green', 'nature']
        )
        
        total = sum(intervention_scales.values())
        
        if total == 0:
            return 0
        
        return green_nature_total / total
    
    def _compile_design_report(
        self,
        qcia_results: Dict,
        weights: Dict[str, float]
    ) -> Dict:
        """Compile comprehensive design report"""
        best_params = qcia_results['best_parameters']
        
        # Calculate metrics for optimal design
        flood_reduction = self._simulate_flood_reduction(best_params)
        equity = self._calculate_equity(best_params)
        sustainability = self._calculate_sustainability(best_params)
        
        # Calculate costs
        interventions_used = []
        total_cost = 0
        
        for interv in self.interventions:
            scale = best_params.get(interv.name, 0)
            if scale > 0.01:  # Threshold for inclusion
                cost = interv.total_cost(scale)
                total_cost += cost
                interventions_used.append({
                    'name': interv.name,
                    'category': interv.category,
                    'scale': scale,
                    'cost': cost,
                    'effectiveness': interv.effectiveness
                })
        
        # Generate causal explanation
        explanation = self.qcia.explain_design(best_params)
        
        report = {
            'city': self.city_name,
            'optimal_parameters': best_params,
            'interventions_used': interventions_used,
            'performance': {
                'flood_reduction': flood_reduction,
                'equity_score': equity,
                'sustainability_score': sustainability,
                'total_cost': total_cost,
                'budget_used': total_cost / self.constraints['budget'],
                'cost_per_percent_reduction': total_cost / (flood_reduction * 100) if flood_reduction > 0 else np.inf
            },
            'causal_insights': explanation,
            'qcia_results': qcia_results,
            'meets_constraints': {
                'budget': total_cost <= self.constraints['budget'],
                'flood_target': flood_reduction >= self.constraints['flood_reduction_target'],
                'equity': equity >= self.constraints['equity_min']
            }
        }
        
        if self.verbose:
            self._print_design_report(report)
        
        return report
    
    def _print_design_report(self, report: Dict):
        """Print human-readable design report"""
        print(f"\n{'='*80}")
        print(f"🏆 OPTIMAL DESIGN FOR {report['city'].upper()}")
        print(f"{'='*80}")
        
        perf = report['performance']
        print(f"\n📊 Performance:")
        print(f"   Flood Reduction: {perf['flood_reduction']:.1%}")
        print(f"   Equity Score: {perf['equity_score']:.1%}")
        print(f"   Sustainability: {perf['sustainability_score']:.1%}")
        print(f"   Total Cost: ₹{perf['total_cost']:,.0f} ({perf['budget_used']:.1%} of budget)")
        print(f"   Cost Efficiency: ₹{perf['cost_per_percent_reduction']:,.0f} per 1% flood reduction")
        
        print(f"\n🏗️  Interventions ({len(report['interventions_used'])}):")
        for interv in sorted(report['interventions_used'], key=lambda x: -x['cost']):
            print(f"   • {interv['name']} ({interv['category']})")
            print(f"      Scale: {interv['scale']:.2f} units")
            print(f"      Cost: ₹{interv['cost']:,.0f}")
        
        print(f"\n✅ Constraints:")
        for constraint, met in report['meets_constraints'].items():
            status = "✓" if met else "✗"
            print(f"   {status} {constraint}")
        
        if report['causal_insights'].get('recommendations'):
            print(f"\n🧠 Causal Insights:")
            for rec in report['causal_insights']['recommendations'][:3]:
                print(f"   • {rec}")
    
    def _default_flood_simulator(self, intervention_scales: Dict[str, float]) -> float:
        """Default simplified flood simulation"""
        return self._simulate_flood_reduction(intervention_scales)


def create_example_interventions() -> List[UrbanIntervention]:
    """
    Create example interventions for demonstration.
    
    Based on real-world costs and effectiveness.
    """
    return [
        # Green infrastructure
        UrbanIntervention(
            name="bioswales",
            category="green",
            cost_per_unit=50000,  # per 100m
            effectiveness=0.12,
            maintenance_cost=0.05,
            lifespan_years=25
        ),
        UrbanIntervention(
            name="rain_gardens",
            category="green",
            cost_per_unit=30000,  # per garden
            effectiveness=0.08,
            maintenance_cost=0.04,
            lifespan_years=20
        ),
        UrbanIntervention(
            name="green_roofs",
            category="green",
            cost_per_unit=200000,  # per 1000 m²
            effectiveness=0.10,
            maintenance_cost=0.06,
            lifespan_years=30
        ),
        UrbanIntervention(
            name="urban_forest",
            category="nature",
            cost_per_unit=100000,  # per hectare
            effectiveness=0.15,
            maintenance_cost=0.03,
            lifespan_years=50
        ),
        # Gray infrastructure
        UrbanIntervention(
            name="detention_basins",
            category="gray",
            cost_per_unit=2000000,  # per basin
            effectiveness=0.35,
            maintenance_cost=0.03,
            lifespan_years=50
        ),
        UrbanIntervention(
            name="drainage_pipes",
            category="drainage",
            cost_per_unit=150000,  # per 100m
            effectiveness=0.25,
            maintenance_cost=0.02,
            lifespan_years=40
        ),
        UrbanIntervention(
            name="pump_stations",
            category="drainage",
            cost_per_unit=5000000,  # per station
            effectiveness=0.40,
            maintenance_cost=0.08,
            lifespan_years=30
        ),
        # Nature-based solutions
        UrbanIntervention(
            name="wetland_restoration",
            category="nature",
            cost_per_unit=500000,  # per hectare
            effectiveness=0.30,
            maintenance_cost=0.02,
            lifespan_years=50
        ),
        UrbanIntervention(
            name="permeable_pavements",
            category="green",
            cost_per_unit=80000,  # per 100m²
            effectiveness=0.15,
            maintenance_cost=0.04,
            lifespan_years=25
        )
    ]


if __name__ == "__main__":
    # Example: Generate optimal flood mitigation design for a city
    
    print("="*80)
    print("ENHANCED QCIA - GENERATIVE URBAN RESILIENCE DEMO")
    print("="*80)
    
    # Create generator
    generator = UrbanResilienceGenerator(
        city_name="Jabalpur",
        population=1200000,
        area_km2=65,
        verbose=True
    )
    
    # Define available interventions
    interventions = create_example_interventions()
    generator.define_interventions(interventions)
    
    # Set constraints
    generator.set_constraints(
        budget=12_00_00_000,  # ₹12 Crores
        flood_reduction_target=0.60,
        equity_min=0.30,
        max_construction_time_years=5
    )
    
    # Generate optimal design
    optimal_design = generator.generate_optimal_design(
        n_iterations=50,
        multi_objective_weights={
            'flood_reduction': 0.50,
            'cost_efficiency': 0.30,
            'equity': 0.15,
            'sustainability': 0.05
        }
    )
    
    print("\n" + "="*80)
    print("✅ GENERATION COMPLETE!")
    print("="*80)
    
    # Export results
    print("\n💾 Exporting results...")
    pd.DataFrame(optimal_design['interventions_used']).to_csv(
        'optimal_urban_design.csv', index=False
    )
    print("   Saved to: optimal_urban_design.csv")

