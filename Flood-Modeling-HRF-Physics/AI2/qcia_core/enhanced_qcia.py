"""
Enhanced QCIA Meta-Optimizer
Combines causal reasoning with meta-optimization strategies for high-stakes generative AI.

This module extends the base QCIA with:
- Experience replay and continuous learning
- Causal pruning of failure zones
- Epsilon-greedy exploration with causal guidance
- Meta-optimization loop for iterative design refinement

Perfect for: Urban resilience, infrastructure design, high-stakes decision making
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
import warnings

from .causal_discovery import CausalDiscoveryEngine
from .causal_reasoning import CausalReasoningEngine
from .quantum_optimizer import QuantumInspiredOptimizer


@dataclass
class DesignExperience:
    """
    Records a single design experiment with its outcome.
    
    Attributes:
        parameters: Design parameters tested (e.g., {'drainage_density': 0.5, 'green_roof_area': 1000})
        outcome: Measured outcome (e.g., flood reduction, cost, risk)
        metrics: Additional performance metrics
        timestamp: When this experiment was conducted
        context: Additional context (budget, constraints, etc.)
    """
    parameters: Dict[str, float]
    outcome: float
    metrics: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for dataframe conversion"""
        return {**self.parameters, **self.metrics, 'outcome': self.outcome}


@dataclass
class CausalPruningZone:
    """
    Represents a causally-identified failure region in design space.
    
    Unlike proximity-based pruning, this understands WHY designs fail.
    """
    parameter: str
    causal_mechanism: str  # e.g., "high_cfl → instability"
    threshold: float
    failure_probability: float
    evidence_strength: float  # How confident we are about this causal relationship


class ExperienceBuffer:
    """
    Maintains history of all design experiments for causal learning.
    
    Features:
    - Stores all tested designs and outcomes
    - Converts to DataFrame for causal discovery
    - Identifies successful vs failed designs
    - Tracks statistics and patterns
    """
    
    def __init__(self, max_size: int = 10000):
        self.experiences: List[DesignExperience] = []
        self.max_size = max_size
        self.best_experience: Optional[DesignExperience] = None
        self.worst_experience: Optional[DesignExperience] = None
    
    def add(self, experience: DesignExperience):
        """Add a new experience to the buffer"""
        self.experiences.append(experience)
        
        # Update best/worst tracking
        if self.best_experience is None or experience.outcome > self.best_experience.outcome:
            self.best_experience = experience
        if self.worst_experience is None or experience.outcome < self.worst_experience.outcome:
            self.worst_experience = experience
        
        # Maintain max size (remove oldest)
        if len(self.experiences) > self.max_size:
            self.experiences.pop(0)
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert all experiences to DataFrame for causal discovery"""
        if not self.experiences:
            return pd.DataFrame()
        
        data = [exp.to_dict() for exp in self.experiences]
        return pd.DataFrame(data)
    
    def get_failures(self, threshold: Optional[float] = None) -> pd.DataFrame:
        """
        Get experiences that failed to meet threshold.
        
        Args:
            threshold: Outcome value below which designs are considered failures.
                      If None, uses median outcome.
        """
        df = self.to_dataframe()
        if df.empty:
            return df
        
        if threshold is None:
            threshold = df['outcome'].median()
        
        return df[df['outcome'] < threshold]
    
    def get_successes(self, threshold: Optional[float] = None) -> pd.DataFrame:
        """Get experiences that succeeded"""
        df = self.to_dataframe()
        if df.empty:
            return df
        
        if threshold is None:
            threshold = df['outcome'].median()
        
        return df[df['outcome'] >= threshold]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get buffer statistics"""
        if not self.experiences:
            return {'count': 0}
        
        df = self.to_dataframe()
        return {
            'count': len(self.experiences),
            'best_outcome': self.best_experience.outcome if self.best_experience else None,
            'worst_outcome': self.worst_experience.outcome if self.worst_experience else None,
            'mean_outcome': df['outcome'].mean(),
            'std_outcome': df['outcome'].std(),
            'success_rate': (df['outcome'] > df['outcome'].median()).mean()
        }
    
    def __len__(self) -> int:
        return len(self.experiences)


class EnhancedQCIA:
    """
    Enhanced Quantum-Inspired Causal Intelligence Architecture with Meta-Optimization.
    
    Combines the power of causal reasoning with intelligent exploration strategies
    for high-stakes generative design problems.
    
    Features:
    - Causal discovery: Learn true cause-effect relationships
    - Causal reasoning: Predict intervention outcomes
    - Quantum optimization: Find optimal designs
    - Experience replay: Learn from all experiments
    - Causal pruning: Avoid failures for causal reasons
    - Epsilon-greedy: Balance exploration vs exploitation
    - Continuous learning: Improve over time
    
    Example Usage:
        >>> qcia = EnhancedQCIA()
        >>> optimal_design = qcia.meta_optimize(
        ...     objective_function=evaluate_flood_design,
        ...     parameter_bounds={
        ...         'drainage_density': (0.1, 0.9),
        ...         'green_area': (0, 10000),
        ...         'elevation': (0, 5)
        ...     },
        ...     n_iterations=100
        ... )
    """
    
    def __init__(
        self,
        alpha: float = 0.05,
        initial_exploration_rate: float = 1.0,
        min_experiences_for_causal: int = 20,
        prune_interval: int = 25,
        verbose: bool = True
    ):
        """
        Initialize Enhanced QCIA.
        
        Args:
            alpha: Significance level for causal discovery (lower = more conservative)
            initial_exploration_rate: Starting epsilon for epsilon-greedy (1.0 = full exploration)
            min_experiences_for_causal: Minimum samples before causal learning
            prune_interval: How often to update pruning zones
            verbose: Whether to print progress
        """
        # Core QCIA components
        self.discovery_engine = CausalDiscoveryEngine(alpha=alpha)
        self.reasoning_engine = None  # Will be created after learning causal graph
        self.optimizer = QuantumInspiredOptimizer()
        
        # Meta-optimization enhancements
        self.experience_buffer = ExperienceBuffer()
        self.causal_pruning_zones: List[CausalPruningZone] = []
        
        # Hyperparameters
        self.initial_exploration_rate = initial_exploration_rate
        self.min_experiences_for_causal = min_experiences_for_causal
        self.prune_interval = prune_interval
        self.verbose = verbose
        
        # State tracking
        self.current_iteration = 0
        self.causal_graph = None
        self.last_causal_update = 0
        
    def meta_optimize(
        self,
        objective_function: Callable[[Dict[str, float]], float],
        parameter_bounds: Dict[str, Tuple[float, float]],
        n_iterations: int = 100,
        goal: str = 'maximize',
        early_stopping_patience: int = 20,
        early_stopping_threshold: float = 0.01
    ) -> Dict[str, Any]:
        """
        Main meta-optimization loop with causal learning and intelligent exploration.
        
        Args:
            objective_function: Function to evaluate designs. Takes parameters dict, returns score.
                               Higher scores = better (will be minimized if goal='minimize')
            parameter_bounds: Dict mapping parameter names to (min, max) tuples
            n_iterations: Number of design iterations to test
            goal: 'maximize' or 'minimize' the objective
            early_stopping_patience: Stop if no improvement for this many iterations
            early_stopping_threshold: Minimum improvement to reset patience counter
        
        Returns:
            Dict containing:
                - 'best_parameters': Optimal design parameters
                - 'best_outcome': Best objective value achieved
                - 'causal_graph': Learned causal structure
                - 'pruning_zones': Identified failure regions
                - 'statistics': Optimization statistics
                - 'experiences': All tested designs
        """
        if self.verbose:
            print("\n" + "="*80)
            print(f"🚀 ENHANCED QCIA META-OPTIMIZER")
            print(f"   Objective: {goal.upper()}")
            print(f"   Iterations: {n_iterations}")
            print(f"   Parameters: {list(parameter_bounds.keys())}")
            print("="*80 + "\n")
        
        # Setup
        sign = 1 if goal == 'maximize' else -1
        best_outcome = -np.inf
        best_parameters = None
        no_improvement_count = 0
        
        for iteration in range(n_iterations):
            self.current_iteration = iteration
            
            # 1. Calculate exploration rate (epsilon-greedy decay)
            epsilon = self._calculate_epsilon(iteration, n_iterations)
            
            # 2. Learn causal structure from experiences (if enough data)
            if self._should_update_causal_model():
                self._learn_causal_structure()
            
            # 3. Update pruning zones periodically
            if iteration > 0 and iteration % self.prune_interval == 0:
                self._update_causal_pruning_zones()
            
            # 4. Decide next design to test (epsilon-greedy with causal guidance)
            if np.random.rand() < epsilon or self.causal_graph is None:
                # EXPLORE: Sample from parameter space (avoiding pruned zones)
                candidate = self._explore_parameter_space(parameter_bounds)
                mode = "EXPLORE"
            else:
                # EXPLOIT: Use causal reasoning + quantum optimization
                candidate = self._exploit_causal_knowledge(
                    objective_function, 
                    parameter_bounds,
                    sign
                )
                mode = "EXPLOIT"
            
            # 5. Evaluate candidate design
            try:
                outcome = objective_function(candidate)
                signed_outcome = sign * outcome
            except Exception as e:
                if self.verbose:
                    print(f"⚠️  Iteration {iteration+1}: Evaluation failed - {str(e)}")
                outcome = -np.inf if goal == 'maximize' else np.inf
                signed_outcome = sign * outcome
            
            # 6. Record experience
            experience = DesignExperience(
                parameters=candidate,
                outcome=signed_outcome,
                metrics={'raw_outcome': outcome, 'iteration': iteration}
            )
            self.experience_buffer.add(experience)
            
            # 7. Track best design
            if signed_outcome > best_outcome:
                improvement = signed_outcome - best_outcome
                best_outcome = signed_outcome
                best_parameters = candidate.copy()
                # Only reset patience if improvement exceeds threshold
                if improvement >= early_stopping_threshold:
                    no_improvement_count = 0
                else:
                    no_improvement_count += 1
                
                if self.verbose:
                    print(f"✨ Iteration {iteration+1}/{n_iterations} [{mode}] | "
                          f"New Best: {outcome:.6f} (improvement: {improvement:.6f})")
            else:
                no_improvement_count += 1
                
                if self.verbose and iteration % 10 == 0:
                    print(f"   Iteration {iteration+1}/{n_iterations} [{mode}] | "
                          f"Current: {outcome:.6f} | Best: {sign * best_outcome:.6f}")
            
            # 8. Early stopping
            if no_improvement_count >= early_stopping_patience:
                if self.verbose:
                    print(f"\n⏹️  Early stopping: No improvement for {early_stopping_patience} iterations")
                break
        
        # Final causal learning with all data
        if len(self.experience_buffer) >= self.min_experiences_for_causal:
            self._learn_causal_structure()
        
        # Compile results
        results = {
            'best_parameters': best_parameters,
            'best_outcome': sign * best_outcome,
            'causal_graph': self.causal_graph,
            'pruning_zones': self.causal_pruning_zones,
            'statistics': self.experience_buffer.get_statistics(),
            'experiences': self.experience_buffer.to_dataframe(),
            'iterations_run': iteration + 1
        }
        
        if self.verbose:
            self._print_final_report(results, goal)
        
        return results
    
    def _calculate_epsilon(self, iteration: int, total_iterations: int) -> float:
        """Calculate exploration rate using quadratic decay"""
        return self.initial_exploration_rate * (1.0 - (iteration / total_iterations)**2)
    
    def _should_update_causal_model(self) -> bool:
        """Decide if we should update the causal model"""
        enough_data = len(self.experience_buffer) >= self.min_experiences_for_causal
        enough_new_data = self.current_iteration - self.last_causal_update >= 10
        return enough_data and enough_new_data
    
    def _learn_causal_structure(self):
        """Learn causal graph from experiences"""
        if self.verbose:
            print(f"\n🧠 Learning causal structure from {len(self.experience_buffer)} experiences...")
        
        try:
            data = self.experience_buffer.to_dataframe()
            
            # Discover causal graph
            self.causal_graph = self.discovery_engine.learn_structure(data, method='pc')
            
            # Create reasoning engine if first time, or update graph
            if self.reasoning_engine is None:
                self.reasoning_engine = CausalReasoningEngine(self.causal_graph)
            else:
                self.reasoning_engine.graph = self.causal_graph
            
            # Fit SCM for interventions
            # Use nonlinear SCM by default for richer domains
            self.reasoning_engine.fit(data, model_type='random_forest')
            
            self.last_causal_update = self.current_iteration
            
            if self.verbose:
                print(f"   ✓ Causal graph learned: {len(self.causal_graph.graph.nodes)} variables, "
                      f"{len(self.causal_graph.edges)} causal relationships")
                
                # Show key causal relationships
                if self.causal_graph.edges:
                    print(f"   Key relationships:")
                    for parent, child in list(self.causal_graph.edges)[:5]:
                        print(f"      {parent} → {child}")
        
        except Exception as e:
            if self.verbose:
                print(f"   ⚠️  Causal learning failed: {str(e)}")
    
    def _update_causal_pruning_zones(self):
        """
        Identify failure patterns CAUSALLY, not just by proximity.
        
        This is the key innovation: we understand WHY designs fail,
        not just that they're close to failed designs.
        """
        if self.causal_graph is None or self.reasoning_engine.scm is None:
            return
        
        if self.verbose:
            print(f"\n🔍 Analyzing failures causally...")
        
        try:
            failures = self.experience_buffer.get_failures()
            
            if len(failures) < 5:
                return
            
            # Analyze each parameter's causal effect on outcome
            for param in self.causal_graph.graph.nodes:
                if param == 'outcome':
                    continue
                
                try:
                    # Compute causal effect on outcome
                    effect = self.reasoning_engine.compute_causal_effect(
                        treatment=param,
                        outcome='outcome',
                        treatment_values=(0.0, 1.0)
                    )
                    
                    # If strong negative causal effect, identify failure threshold
                    if effect < -0.3:  # Strong negative effect
                        # Find threshold where failures concentrate
                        failure_values = failures[param].values
                        threshold = np.percentile(failure_values, 75)
                        
                        zone = CausalPruningZone(
                            parameter=param,
                            causal_mechanism=f"{param} → poor_outcome",
                            threshold=threshold,
                            failure_probability=0.8,
                            evidence_strength=abs(effect)
                        )
                        
                        # Update or add pruning zone
                        existing = [z for z in self.causal_pruning_zones if z.parameter == param]
                        if existing:
                            self.causal_pruning_zones.remove(existing[0])
                        self.causal_pruning_zones.append(zone)
                        
                        if self.verbose:
                            print(f"   🚫 Pruning zone: {param} > {threshold:.4f} "
                                  f"(causal effect: {effect:.4f})")
                
                except Exception:
                    continue
        
        except Exception as e:
            if self.verbose:
                print(f"   ⚠️  Pruning analysis failed: {str(e)}")
    
    def _explore_parameter_space(
        self, 
        parameter_bounds: Dict[str, Tuple[float, float]]
    ) -> Dict[str, float]:
        """
        Sample parameter space randomly, avoiding pruned zones.
        """
        max_attempts = 100
        
        for attempt in range(max_attempts):
            # Random sample
            candidate = {}
            for param, (low, high) in parameter_bounds.items():
                candidate[param] = np.random.uniform(low, high)
            
            # Check if in pruned zone
            in_pruned_zone = False
            for zone in self.causal_pruning_zones:
                if zone.parameter in candidate:
                    if candidate[zone.parameter] > zone.threshold:
                        in_pruned_zone = True
                        break
            
            if not in_pruned_zone:
                return candidate
        
        # If all attempts failed, return random sample anyway
        return candidate
    
    def _exploit_causal_knowledge(
        self,
        objective_function: Callable,
        parameter_bounds: Dict[str, Tuple[float, float]],
        sign: int
    ) -> Dict[str, float]:
        """
        Use causal reasoning + quantum optimization to find promising design.
        """
        if self.reasoning_engine.scm is None:
            # Fallback to exploration if no causal model
            return self._explore_parameter_space(parameter_bounds)
        
        try:
            # Create bounds array for optimizer
            params_list = sorted(parameter_bounds.keys())
            bounds_array = np.array([parameter_bounds[p] for p in params_list])
            
            # Define causal-guided objective
            def causal_objective(x):
                params = {params_list[i]: x[i] for i in range(len(x))}
                
                # Use causal model to predict outcome
                try:
                    samples = self.reasoning_engine.scm.intervene(params, n_samples=10)
                    predicted_outcome = samples['outcome'].mean()
                    return -sign * predicted_outcome  # Minimize negative for maximization
                except:
                    # Fallback to actual evaluation if prediction fails
                    return -sign * objective_function(params)
            
            # Use quantum annealing (returns ndarray best_x)
            x_best = self.optimizer.quantum_anneal(
                cost_function=causal_objective,
                bounds=bounds_array
            )
            
            # Convert back to dict
            optimal_params = {params_list[i]: float(x_best[i]) for i in range(len(params_list))}
            
            return optimal_params
        
        except Exception as e:
            if self.verbose:
                print(f"   ⚠️  Causal exploitation failed: {str(e)}, falling back to exploration")
            return self._explore_parameter_space(parameter_bounds)
    
    def _print_final_report(self, results: Dict, goal: str):
        """Print final optimization report"""
        print("\n" + "="*80)
        print("🎯 OPTIMIZATION COMPLETE")
        print("="*80)
        
        print(f"\n📊 Statistics:")
        stats = results['statistics']
        print(f"   Total designs tested: {stats['count']}")
        print(f"   Success rate: {stats['success_rate']:.1%}")
        print(f"   Mean outcome: {stats['mean_outcome']:.6f}")
        print(f"   Std deviation: {stats['std_outcome']:.6f}")
        
        print(f"\n🏆 Best Design Found:")
        print(f"   Outcome: {results['best_outcome']:.6f}")
        print(f"   Parameters:")
        for param, value in results['best_parameters'].items():
            print(f"      {param}: {value:.6f}")
        
        if results['causal_graph'] and results['causal_graph'].edges:
            print(f"\n🧠 Causal Understanding:")
            print(f"   Discovered {len(results['causal_graph'].edges)} causal relationships")
            for parent, child in list(results['causal_graph'].edges)[:5]:
                print(f"      {parent} → {child}")
        
        if results['pruning_zones']:
            print(f"\n🚫 Learned {len(results['pruning_zones'])} Failure Patterns:")
            for zone in results['pruning_zones'][:3]:
                print(f"      {zone.causal_mechanism} (confidence: {zone.evidence_strength:.2f})")
        
        print("\n" + "="*80)
    
    def explain_design(self, parameters: Dict[str, float]) -> Dict[str, Any]:
        """
        Explain why a design works or doesn't work using causal reasoning.
        
        Args:
            parameters: Design parameters to explain
        
        Returns:
            Dict with causal explanation
        """
        if self.reasoning_engine.scm is None:
            return {'error': 'No causal model learned yet'}
        
        explanation = {
            'parameters': parameters,
            'causal_effects': {},
            'counterfactuals': {},
            'recommendations': []
        }
        
        # Analyze causal effect of each parameter
        for param, value in parameters.items():
            if param in self.causal_graph.graph.nodes:
                try:
                    effect = self.reasoning_engine.compute_causal_effect(
                        treatment=param,
                        outcome='outcome',
                        treatment_values=(value * 0.5, value)
                    )
                    explanation['causal_effects'][param] = effect
                    
                    # Generate recommendation
                    if effect > 0:
                        explanation['recommendations'].append(
                            f"Increasing {param} will improve outcome (effect: +{effect:.4f})"
                        )
                    elif effect < -0.1:
                        explanation['recommendations'].append(
                            f"Reducing {param} will improve outcome (effect: {effect:.4f})"
                        )
                except:
                    pass
        
        return explanation

