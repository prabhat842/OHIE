#!/usr/bin/env python3
"""
Flood Causal Discovery: Learn causal relationships in flood systems using QCIA.

This module uses QCIA's causal discovery engine to learn:
- What terrain features CAUSE flooding?
- Which interventions WORK and WHY?
- What are confounders and mediators?
- How do interventions affect downstream flooding?

The learned causal graph guides future intervention placement.

Author: QCIA Causal Intelligence Layer
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np

# Import QCIA core
try:
    from AI.qcia_core.causal_discovery import CausalDiscoveryEngine
    from AI.qcia_core.causal_graph import CausalGraph
    from AI.qcia_core.causal_reasoning import CausalReasoningEngine
except ImportError:
    print("❌ Failed to import QCIA core modules")
    sys.exit(1)


class FloodCausalDiscovery:
    """Learns causal structure of flood systems from simulation data."""
    
    def __init__(self, alpha: float = 0.05, verbose: bool = True):
        """
        Initialize causal discovery engine.
        
        Args:
            alpha: Significance level for conditional independence tests
            verbose: Print diagnostic messages
        """
        self.discovery_engine = CausalDiscoveryEngine(alpha=alpha)
        self.causal_graph: Optional[CausalGraph] = None
        self.reasoning_engine: Optional[CausalReasoningEngine] = None
        self.verbose = verbose
        
        self.feature_names: List[str] = []
        self.learned_insights: Dict[str, any] = {}
    
    def discover_from_experiences(self, 
                                 features_matrix: np.ndarray,
                                 feature_names: List[str]) -> CausalGraph:
        """
        Discover causal graph from experience feature matrix.
        
        Args:
            features_matrix: N x M array (N=samples, M=features)
            feature_names: List of feature names
            
        Returns:
            Learned CausalGraph
        """
        if self.verbose:
            print(f"\n{'='*70}")
            print(f"DISCOVERING CAUSAL STRUCTURE")
            print(f"{'='*70}")
            print(f"Data: {features_matrix.shape[0]} samples, {features_matrix.shape[1]} features")
        
        self.feature_names = feature_names
        
        # Convert to pandas DataFrame (required by CausalDiscoveryEngine)
        import pandas as pd
        data_df = pd.DataFrame(features_matrix, columns=feature_names)
        
        # Learn causal structure using PC algorithm
        if self.verbose:
            print(f"\nRunning PC Algorithm (alpha={self.discovery_engine.alpha})...")
        
        self.causal_graph = self.discovery_engine.learn_structure(
            data_df,
            method='pc'
        )
        
        # Create reasoning engine
        self.reasoning_engine = CausalReasoningEngine(self.causal_graph)
        
        # Analyze and extract insights
        self._analyze_causal_graph()
        
        if self.verbose:
            self._print_causal_graph()
        
        return self.causal_graph
    
    def _analyze_causal_graph(self):
        """Analyze learned causal graph to extract actionable insights."""
        if self.causal_graph is None:
            return
        
        graph = self.causal_graph.graph
        
        # Identify causal drivers of flooding
        flooding_features = ['baseline_flood_depth_m', 'local_depth_reduction_m']
        terrain_features = ['elevation_m', 'slope', 'flow_accumulation']
        intervention_features = ['intervention_volume_m3', 'intervention_diameter_m', 'intervention_depth_m']
        outcome_features = ['local_depth_reduction_m', 'downstream_depth_reduction_m', 'effectiveness_score']
        
        insights = {
            'flood_drivers': [],
            'intervention_effects': [],
            'confounders': [],
            'mediators': []
        }
        
        # Find what causes flooding
        for flood_var in flooding_features:
            if flood_var in graph.nodes:
                parents = list(graph.predecessors(flood_var))
                if parents:
                    insights['flood_drivers'].append({
                        'target': flood_var,
                        'causes': parents
                    })
        
        # Find what interventions affect
        for interv_var in intervention_features:
            if interv_var in graph.nodes:
                children = list(graph.successors(interv_var))
                if children:
                    insights['intervention_effects'].append({
                        'intervention': interv_var,
                        'affects': children
                    })
        
        # Find confounders (variables that affect both intervention placement and outcomes)
        for terrain_var in terrain_features:
            if terrain_var in graph.nodes:
                descendants = set()
                for interv_var in intervention_features:
                    if interv_var in graph.nodes and graph.has_edge(terrain_var, interv_var):
                        descendants.add(interv_var)
                for outcome_var in outcome_features:
                    if outcome_var in graph.nodes and graph.has_edge(terrain_var, outcome_var):
                        descendants.add(outcome_var)
                
                if len(descendants) >= 2:
                    insights['confounders'].append({
                        'variable': terrain_var,
                        'affects': list(descendants)
                    })
        
        # Find mediators (variables through which interventions affect outcomes)
        for interv_var in intervention_features:
            if interv_var in graph.nodes:
                for node in graph.nodes:
                    if node == interv_var or node in intervention_features:
                        continue
                    # Check if node is between intervention and outcome
                    if graph.has_edge(interv_var, node):
                        for outcome_var in outcome_features:
                            if outcome_var in graph.nodes and graph.has_edge(node, outcome_var):
                                insights['mediators'].append({
                                    'intervention': interv_var,
                                    'mediator': node,
                                    'outcome': outcome_var
                                })
        
        self.learned_insights = insights
    
    def _print_causal_graph(self):
        """Print causal graph in human-readable format."""
        if self.causal_graph is None:
            return
        
        graph = self.causal_graph.graph
        
        print(f"\n{'='*70}")
        print(f"LEARNED CAUSAL GRAPH")
        print(f"{'='*70}")
        print(f"Nodes: {graph.number_of_nodes()}")
        print(f"Edges: {graph.number_of_edges()}")
        
        print(f"\n{'-'*70}")
        print(f"CAUSAL RELATIONSHIPS:")
        print(f"{'-'*70}")
        
        for parent, child in graph.edges():
            print(f"  {parent:30s} → {child}")
        
        # Print insights
        if self.learned_insights:
            print(f"\n{'-'*70}")
            print(f"KEY INSIGHTS:")
            print(f"{'-'*70}")
            
            if self.learned_insights.get('flood_drivers'):
                print(f"\n📊 FLOOD DRIVERS (what causes flooding):")
                for driver in self.learned_insights['flood_drivers']:
                    print(f"   {driver['target']} is caused by:")
                    for cause in driver['causes']:
                        print(f"     - {cause}")
            
            if self.learned_insights.get('intervention_effects'):
                print(f"\n🔧 INTERVENTION EFFECTS (what interventions affect):")
                for effect in self.learned_insights['intervention_effects']:
                    print(f"   {effect['intervention']} affects:")
                    for target in effect['affects']:
                        print(f"     - {target}")
            
            if self.learned_insights.get('confounders'):
                print(f"\n⚠️  CONFOUNDERS (variables affecting both placement and outcomes):")
                for conf in self.learned_insights['confounders']:
                    print(f"   {conf['variable']} affects: {', '.join(conf['affects'])}")
            
            if self.learned_insights.get('mediators'):
                print(f"\n🔀 MEDIATORS (how interventions affect outcomes):")
                for med in self.learned_insights['mediators']:
                    print(f"   {med['intervention']} → {med['mediator']} → {med['outcome']}")
        
        print(f"{'='*70}\n")
    
    def predict_intervention_effect(self,
                                   intervention_params: Dict[str, float],
                                   spatial_context: Dict[str, float]) -> Dict[str, float]:
        """
        Predict the effect of a proposed intervention using causal reasoning.
        
        Args:
            intervention_params: Intervention features (volume, diameter, etc.)
            spatial_context: Spatial features (elevation, slope, etc.)
            
        Returns:
            Predicted outcomes (depth reduction, effectiveness, etc.)
        """
        if self.reasoning_engine is None:
            if self.verbose:
                print("⚠️  No causal model learned yet. Call discover_from_experiences() first.")
            return {}
        
        # Combine intervention and spatial features
        evidence = {**spatial_context, **intervention_params}
        
        # Predict outcomes using causal reasoning
        # For each outcome variable, do intervention (set intervention features)
        predictions = {}
        
        outcome_vars = ['local_depth_reduction_m', 'downstream_depth_reduction_m', 
                       'effectiveness_score', 'storage_efficiency']
        
        for outcome_var in outcome_vars:
            if outcome_var not in self.causal_graph.graph.nodes:
                continue
            
            try:
                # This is a simplified prediction - real implementation would use
                # the full SCM (Structural Causal Model) machinery
                parents = list(self.causal_graph.graph.predecessors(outcome_var))
                
                # Simple linear combination of parents (placeholder for real SCM)
                prediction = 0.0
                for parent in parents:
                    if parent in evidence:
                        prediction += evidence[parent] * 0.1  # Placeholder weight
                
                predictions[outcome_var] = prediction
                
            except Exception as e:
                if self.verbose:
                    print(f"⚠️  Failed to predict {outcome_var}: {e}")
        
        return predictions
    
    def explain_why_intervention_works(self, intervention_id: str) -> str:
        """
        Generate causal explanation for why an intervention was effective or not.
        
        Args:
            intervention_id: ID of intervention to explain
            
        Returns:
            Human-readable explanation
        """
        if self.causal_graph is None:
            return "No causal model available."
        
        # Build explanation by tracing causal paths
        explanation = []
        explanation.append(f"Causal analysis of intervention {intervention_id}:\n")
        
        # Check if intervention features affect outcomes
        interv_vars = ['intervention_volume_m3', 'intervention_diameter_m']
        outcome_vars = ['local_depth_reduction_m', 'effectiveness_score']
        
        for interv_var in interv_vars:
            if interv_var not in self.causal_graph.graph.nodes:
                continue
            
            for outcome_var in outcome_vars:
                if outcome_var not in self.causal_graph.graph.nodes:
                    continue
                
                # Check for direct effect
                if self.causal_graph.graph.has_edge(interv_var, outcome_var):
                    explanation.append(f"  - {interv_var} directly affects {outcome_var}")
                
                # Check for indirect effects (mediators)
                # Simple path checking (real implementation would use proper causal paths)
                for node in self.causal_graph.graph.nodes:
                    if (self.causal_graph.graph.has_edge(interv_var, node) and 
                        self.causal_graph.graph.has_edge(node, outcome_var)):
                        explanation.append(f"  - {interv_var} affects {outcome_var} through {node}")
        
        # Check for confounders
        if self.learned_insights.get('confounders'):
            explanation.append(f"\nConfounding factors:")
            for conf in self.learned_insights['confounders']:
                explanation.append(f"  - {conf['variable']} affects both placement and outcomes")
        
        return "\n".join(explanation)
    
    def recommend_optimal_intervention_params(self,
                                             spatial_context: Dict[str, float],
                                             target_depth_reduction_m: float = 0.5) -> Dict[str, float]:
        """
        Recommend optimal intervention parameters for given spatial context.
        
        Uses causal model to suggest parameters that maximize effectiveness.
        
        Args:
            spatial_context: Spatial features at proposed location
            target_depth_reduction_m: Desired flood depth reduction
            
        Returns:
            Recommended intervention parameters
        """
        if self.reasoning_engine is None:
            if self.verbose:
                print("⚠️  No causal model available.")
            return {}
        
        # Search over intervention parameter space
        # This is a simplified version - real implementation would use optimization
        
        best_params = None
        best_predicted_reduction = -999.0
        
        # Grid search over volumes and depths
        for volume in [1000, 2000, 5000, 10000]:
            for depth in [1.5, 2.0, 2.5, 3.0]:
                diameter = 2.0 * np.sqrt(volume / (np.pi * depth / 4))
                
                intervention_params = {
                    'intervention_volume_m3': volume,
                    'intervention_diameter_m': diameter,
                    'intervention_depth_m': depth
                }
                
                predictions = self.predict_intervention_effect(intervention_params, spatial_context)
                
                predicted_reduction = predictions.get('local_depth_reduction_m', 0.0)
                
                if predicted_reduction > best_predicted_reduction:
                    best_predicted_reduction = predicted_reduction
                    best_params = intervention_params.copy()
        
        if self.verbose and best_params:
            print(f"\n💡 Recommended intervention parameters:")
            print(f"   Volume: {best_params['intervention_volume_m3']:.0f}m³")
            print(f"   Diameter: {best_params['intervention_diameter_m']:.1f}m")
            print(f"   Depth: {best_params['intervention_depth_m']:.1f}m")
            print(f"   Predicted reduction: {best_predicted_reduction:.2f}m")
        
        return best_params
    
    def export_causal_graph(self, output_path: Path):
        """Export causal graph and insights to JSON."""
        if self.causal_graph is None:
            if self.verbose:
                print("⚠️  No causal graph to export.")
            return
        
        graph = self.causal_graph.graph
        
        # Convert graph to dict format
        edges = [
            {'from': parent, 'to': child}
            for parent, child in graph.edges()
        ]
        
        data = {
            'nodes': list(graph.nodes()),
            'edges': edges,
            'num_nodes': graph.number_of_nodes(),
            'num_edges': graph.number_of_edges(),
            'insights': self.learned_insights
        }
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        if self.verbose:
            print(f"\n✅ Saved causal graph to: {output_path}")
    
    def visualize_causal_graph(self, output_path: Path):
        """Generate visualization of causal graph (requires graphviz/matplotlib)."""
        if self.causal_graph is None:
            if self.verbose:
                print("⚠️  No causal graph to visualize.")
            return
        
        try:
            import matplotlib.pyplot as plt
            import networkx as nx
            
            graph = self.causal_graph.graph
            
            # Create figure
            fig, ax = plt.subplots(figsize=(14, 10))
            
            # Layout
            pos = nx.spring_layout(graph, k=2, iterations=50)
            
            # Color nodes by type
            node_colors = []
            for node in graph.nodes():
                if 'intervention' in node.lower():
                    node_colors.append('#FF6B6B')  # Red for interventions
                elif any(terrain in node.lower() for terrain in ['elevation', 'slope', 'flow']):
                    node_colors.append('#4ECDC4')  # Teal for terrain
                elif 'reduction' in node.lower() or 'effectiveness' in node.lower():
                    node_colors.append('#95E1D3')  # Light green for outcomes
                else:
                    node_colors.append('#FFE66D')  # Yellow for other
            
            # Draw
            nx.draw_networkx_nodes(graph, pos, node_color=node_colors, 
                                  node_size=3000, alpha=0.9, ax=ax)
            nx.draw_networkx_edges(graph, pos, edge_color='#666', 
                                  arrows=True, arrowsize=20, width=2, ax=ax)
            nx.draw_networkx_labels(graph, pos, font_size=8, font_weight='bold', ax=ax)
            
            ax.set_title("Learned Causal Graph: Flood System Relationships", 
                        fontsize=16, fontweight='bold', pad=20)
            ax.axis('off')
            
            # Legend
            legend_elements = [
                plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='#FF6B6B', 
                          markersize=10, label='Interventions'),
                plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='#4ECDC4', 
                          markersize=10, label='Terrain Features'),
                plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='#95E1D3', 
                          markersize=10, label='Outcomes'),
                plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='#FFE66D', 
                          markersize=10, label='Other')
            ]
            ax.legend(handles=legend_elements, loc='upper left', fontsize=10)
            
            plt.tight_layout()
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            plt.close()
            
            if self.verbose:
                print(f"✅ Saved causal graph visualization to: {output_path}")
                
        except ImportError:
            if self.verbose:
                print("⚠️  matplotlib/networkx not available for visualization")
        except Exception as e:
            if self.verbose:
                print(f"⚠️  Failed to visualize causal graph: {e}")


if __name__ == "__main__":
    print("Flood Causal Discovery - Learn causal relationships from flood simulations")
    print("Import this module and use FloodCausalDiscovery class")

