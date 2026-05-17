#!/usr/bin/env python3
"""
Gradient-Based Optimizer: Uses finite differences to optimize intervention parameters.

Instead of grid search, compute gradients of flood depth with respect to intervention
parameters (volume, location, depth) and use gradient descent to find optimal designs.

This is a stepping stone to full differentiable HRF (LEVEL 3 HARD).

Author: QCIA Optimization Layer
"""
from __future__ import annotations

import numpy as np
from typing import Dict, List, Tuple, Callable, Optional
from dataclasses import dataclass


@dataclass
class OptimizationResult:
    """Result from gradient-based optimization."""
    optimal_params: Dict[str, float]
    optimal_objective: float
    iterations: int
    convergence_history: List[float]
    gradient_norms: List[float]


class GradientBasedOptimizer:
    """
    Optimizes intervention parameters using gradient descent with finite differences.
    
    This approximates gradients by running physics simulations with perturbed parameters
    and computing ∂(flood_metric) / ∂(intervention_param).
    """
    
    def __init__(self,
                 objective_function: Callable,
                 learning_rate: float = 0.1,
                 max_iterations: int = 50,
                 convergence_tol: float = 1e-4,
                 finite_diff_epsilon: float = 1.0,
                 verbose: bool = True):
        """
        Initialize optimizer.
        
        Args:
            objective_function: Takes intervention params dict, returns scalar objective to MINIMIZE
            learning_rate: Step size for gradient descent
            max_iterations: Maximum optimization iterations
            convergence_tol: Stop if gradient norm < this
            finite_diff_epsilon: Step size for finite difference gradient approximation
            verbose: Print progress
        """
        self.objective_fn = objective_function
        self.learning_rate = learning_rate
        self.max_iterations = max_iterations
        self.convergence_tol = convergence_tol
        self.epsilon = finite_diff_epsilon
        self.verbose = verbose
    
    def optimize(self,
                initial_params: Dict[str, float],
                param_bounds: Dict[str, Tuple[float, float]]) -> OptimizationResult:
        """
        Optimize intervention parameters using gradient descent.
        
        Args:
            initial_params: Starting parameter values (e.g., {'volume_m3': 5000, 'diameter_m': 50})
            param_bounds: Min/max bounds for each parameter
            
        Returns:
            OptimizationResult with optimal parameters and history
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"GRADIENT-BASED OPTIMIZATION")
            print(f"{'='*70}")
            print(f"Initial params: {initial_params}")
            print(f"Bounds: {param_bounds}")
        
        # Current parameters
        params = initial_params.copy()
        param_names = list(params.keys())
        
        # History
        objective_history = []
        gradient_norms = []
        
        # Evaluate initial objective
        current_objective = self.objective_fn(params)
        objective_history.append(current_objective)
        
        if self.verbose:
            print(f"\nInitial objective: {current_objective:.4f}")
            print(f"\n{'Iter':<6} {'Objective':<12} {'Grad Norm':<12} {' | '.join(param_names)}")
            print(f"{'-'*70}")
        
        # Gradient descent loop
        for iteration in range(self.max_iterations):
            # Compute gradient via finite differences
            gradient = {}
            
            for param_name in param_names:
                # Perturb parameter up
                params_plus = params.copy()
                params_plus[param_name] += self.epsilon
                # Clip to bounds
                if param_name in param_bounds:
                    params_plus[param_name] = np.clip(
                        params_plus[param_name],
                        param_bounds[param_name][0],
                        param_bounds[param_name][1]
                    )
                
                objective_plus = self.objective_fn(params_plus)
                
                # Compute gradient (forward difference)
                gradient[param_name] = (objective_plus - current_objective) / self.epsilon
            
            # Compute gradient norm
            grad_norm = np.sqrt(sum(g**2 for g in gradient.values()))
            gradient_norms.append(grad_norm)
            
            # Print progress
            if self.verbose:
                param_str = ' | '.join(f"{params[k]:.2f}" for k in param_names)
                print(f"{iteration+1:<6} {current_objective:<12.4f} {grad_norm:<12.6f} | {param_str}")
            
            # Check convergence
            if grad_norm < self.convergence_tol:
                if self.verbose:
                    print(f"\n✅ Converged! Gradient norm {grad_norm:.6f} < {self.convergence_tol}")
                break
            
            # Gradient descent step
            for param_name in param_names:
                params[param_name] -= self.learning_rate * gradient[param_name]
                
                # Enforce bounds
                if param_name in param_bounds:
                    params[param_name] = np.clip(
                        params[param_name],
                        param_bounds[param_name][0],
                        param_bounds[param_name][1]
                    )
            
            # Evaluate new objective
            current_objective = self.objective_fn(params)
            objective_history.append(current_objective)
        
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"OPTIMIZATION COMPLETE")
            print(f"{'='*70}")
            print(f"Final objective: {current_objective:.4f}")
            print(f"Final params: {params}")
            print(f"Improvement: {objective_history[0] - current_objective:.4f}")
            print(f"Iterations: {len(objective_history)-1}")
        
        return OptimizationResult(
            optimal_params=params,
            optimal_objective=current_objective,
            iterations=len(objective_history) - 1,
            convergence_history=objective_history,
            gradient_norms=gradient_norms
        )
    
    def optimize_multiple_interventions(self,
                                       initial_designs: List[Dict[str, float]],
                                       param_bounds: Dict[str, Tuple[float, float]],
                                       objective_function: Callable) -> List[Dict[str, float]]:
        """
        Optimize multiple interventions jointly.
        
        Args:
            initial_designs: List of initial parameter dicts for each intervention
            param_bounds: Bounds for parameters
            objective_function: Takes list of param dicts, returns scalar objective
            
        Returns:
            List of optimized parameter dicts
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"JOINT OPTIMIZATION OF {len(initial_designs)} INTERVENTIONS")
            print(f"{'='*70}")
        
        # Flatten all parameters into a single vector
        all_param_names = []
        initial_vector = []
        
        for i, design in enumerate(initial_designs):
            for param_name, value in design.items():
                all_param_names.append(f"intervention_{i}_{param_name}")
                initial_vector.append(value)
        
        initial_vector = np.array(initial_vector)
        current_vector = initial_vector.copy()
        
        # Evaluate initial objective
        def vector_to_designs(vec):
            """Convert flat vector back to list of design dicts."""
            designs = []
            idx = 0
            for design in initial_designs:
                d = {}
                for param_name in design.keys():
                    d[param_name] = vec[idx]
                    idx += 1
                designs.append(d)
            return designs
        
        current_objective = objective_function(vector_to_designs(current_vector))
        
        if self.verbose:
            print(f"Initial objective: {current_objective:.4f}")
        
        # Gradient descent
        objective_history = [current_objective]
        
        for iteration in range(self.max_iterations):
            # Compute gradient
            gradient = np.zeros_like(current_vector)
            
            for i in range(len(current_vector)):
                # Perturb parameter
                perturbed = current_vector.copy()
                perturbed[i] += self.epsilon
                
                # Evaluate
                objective_plus = objective_function(vector_to_designs(perturbed))
                
                # Gradient
                gradient[i] = (objective_plus - current_objective) / self.epsilon
            
            grad_norm = np.linalg.norm(gradient)
            
            if self.verbose and iteration % 5 == 0:
                print(f"  Iter {iteration+1:3d}: objective={current_objective:.4f}, grad_norm={grad_norm:.6f}")
            
            if grad_norm < self.convergence_tol:
                if self.verbose:
                    print(f"✅ Converged at iteration {iteration+1}")
                break
            
            # Update
            current_vector -= self.learning_rate * gradient
            
            # Clip to bounds (TODO: implement per-parameter bounds)
            
            # Evaluate
            current_objective = objective_function(vector_to_designs(current_vector))
            objective_history.append(current_objective)
        
        # Return optimized designs
        optimized_designs = vector_to_designs(current_vector)
        
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"JOINT OPTIMIZATION COMPLETE")
            print(f"Initial objective: {objective_history[0]:.4f}")
            print(f"Final objective: {objective_history[-1]:.4f}")
            print(f"Improvement: {objective_history[0] - objective_history[-1]:.4f}")
        
        return optimized_designs


class AdamOptimizer(GradientBasedOptimizer):
    """
    Adam optimizer (adaptive moment estimation) for better convergence.
    
    More sophisticated than vanilla gradient descent - uses momentum and adaptive
    learning rates per parameter.
    """
    
    def __init__(self,
                 objective_function: Callable,
                 learning_rate: float = 0.01,
                 beta1: float = 0.9,
                 beta2: float = 0.999,
                 epsilon_adam: float = 1e-8,
                 **kwargs):
        """
        Initialize Adam optimizer.
        
        Args:
            beta1: Exponential decay rate for first moment
            beta2: Exponential decay rate for second moment
            epsilon_adam: Small constant for numerical stability
        """
        super().__init__(objective_function, learning_rate, **kwargs)
        self.beta1 = beta1
        self.beta2 = beta2
        self.epsilon_adam = epsilon_adam
    
    def optimize(self,
                initial_params: Dict[str, float],
                param_bounds: Dict[str, Tuple[float, float]]) -> OptimizationResult:
        """Optimize using Adam."""
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"ADAM OPTIMIZATION")
            print(f"{'='*70}")
        
        params = initial_params.copy()
        param_names = list(params.keys())
        
        # Adam state
        m = {name: 0.0 for name in param_names}  # First moment
        v = {name: 0.0 for name in param_names}  # Second moment
        
        objective_history = []
        gradient_norms = []
        
        current_objective = self.objective_fn(params)
        objective_history.append(current_objective)
        
        if self.verbose:
            print(f"Initial objective: {current_objective:.4f}")
        
        for t in range(1, self.max_iterations + 1):
            # Compute gradient
            gradient = {}
            for param_name in param_names:
                params_plus = params.copy()
                params_plus[param_name] += self.epsilon
                if param_name in param_bounds:
                    params_plus[param_name] = np.clip(
                        params_plus[param_name],
                        param_bounds[param_name][0],
                        param_bounds[param_name][1]
                    )
                
                objective_plus = self.objective_fn(params_plus)
                gradient[param_name] = (objective_plus - current_objective) / self.epsilon
            
            grad_norm = np.sqrt(sum(g**2 for g in gradient.values()))
            gradient_norms.append(grad_norm)
            
            if self.verbose and t % 5 == 0:
                print(f"  Iter {t:3d}: obj={current_objective:.4f}, grad={grad_norm:.6f}")
            
            if grad_norm < self.convergence_tol:
                if self.verbose:
                    print(f"✅ Converged at iteration {t}")
                break
            
            # Adam update
            for param_name in param_names:
                g = gradient[param_name]
                
                # Update biased first moment
                m[param_name] = self.beta1 * m[param_name] + (1 - self.beta1) * g
                
                # Update biased second moment
                v[param_name] = self.beta2 * v[param_name] + (1 - self.beta2) * (g ** 2)
                
                # Bias correction
                m_hat = m[param_name] / (1 - self.beta1 ** t)
                v_hat = v[param_name] / (1 - self.beta2 ** t)
                
                # Update parameter
                params[param_name] -= self.learning_rate * m_hat / (np.sqrt(v_hat) + self.epsilon_adam)
                
                # Enforce bounds
                if param_name in param_bounds:
                    params[param_name] = np.clip(
                        params[param_name],
                        param_bounds[param_name][0],
                        param_bounds[param_name][1]
                    )
            
            current_objective = self.objective_fn(params)
            objective_history.append(current_objective)
        
        if self.verbose:
            print(f"\nFinal objective: {current_objective:.4f}")
            print(f"Improvement: {objective_history[0] - current_objective:.4f}")
        
        return OptimizationResult(
            optimal_params=params,
            optimal_objective=current_objective,
            iterations=len(objective_history) - 1,
            convergence_history=objective_history,
            gradient_norms=gradient_norms
        )


if __name__ == "__main__":
    print("Gradient-Based Optimizer - Faster optimization via gradients")
    print("Import and use GradientBasedOptimizer or AdamOptimizer")
