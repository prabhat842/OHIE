"""
Causal Graph Data Structures

This module defines the core data structures for representing causal relationships:
- Edge: A causal edge with metadata (strength, confidence)
- CausalGraph: A Directed Acyclic Graph (DAG) representing causal structure
"""

from dataclasses import dataclass
from typing import Set, Dict, List, Tuple, Optional
import networkx as nx
import numpy as np


@dataclass
class Edge:
    """
    Represents a causal edge X → Y with metadata.
    
    Attributes:
        source: The cause variable
        target: The effect variable
        strength: The causal effect size (coefficient)
        confidence: Confidence in this edge [0, 1]
        edge_type: 'directed', 'bidirected', or 'undirected'
    """
    source: str
    target: str
    strength: float
    confidence: float
    edge_type: str = 'directed'
    
    def __repr__(self):
        arrow = '→' if self.edge_type == 'directed' else '↔'
        return f"{self.source} {arrow} {self.target} (strength={self.strength:.3f}, conf={self.confidence:.3f})"


class CausalGraph:
    """
    Represents a causal DAG (Directed Acyclic Graph) with uncertainty.
    
    This is the core data structure for storing learned causal relationships.
    It uses NetworkX under the hood for graph operations.
    
    Example:
        >>> graph = CausalGraph()
        >>> graph.add_edge('X', 'Y', strength=0.5, confidence=0.9)
        >>> graph.is_ancestor('X', 'Y')
        True
    """
    
    def __init__(self):
        self.graph = nx.DiGraph()  # Directed graph
        self.edges: Dict[Tuple[str, str], Edge] = {}
        self.latent_variables: Set[str] = set()  # Hidden confounders
        
    def add_edge(self, source: str, target: str, 
                 strength: float = 1.0, confidence: float = 1.0):
        """
        Add a causal edge X → Y.
        
        Args:
            source: The cause variable
            target: The effect variable
            strength: Causal effect size (default 1.0)
            confidence: Confidence in this edge (default 1.0)
        """
        self.graph.add_edge(source, target)
        self.edges[(source, target)] = Edge(
            source, target, strength, confidence, 'directed'
        )
    
    def remove_edge(self, source: str, target: str):
        """Remove a causal edge."""
        if self.graph.has_edge(source, target):
            self.graph.remove_edge(source, target)
        if (source, target) in self.edges:
            del self.edges[(source, target)]
    
    def add_node(self, node: str):
        """Add a node (variable) to the graph."""
        self.graph.add_node(node)
    
    def is_ancestor(self, X: str, Y: str) -> bool:
        """
        Check if X is an ancestor of Y (i.e., there's a directed path X → ... → Y).
        """
        return nx.has_path(self.graph, X, Y)
    
    def get_parents(self, node: str) -> Set[str]:
        """Get direct parents (immediate causes) of a node."""
        return set(self.graph.predecessors(node))
    
    def get_children(self, node: str) -> Set[str]:
        """Get direct children (immediate effects) of a node."""
        return set(self.graph.successors(node))
    
    def get_ancestors(self, node: str) -> Set[str]:
        """Get all ancestors (transitive causes) of a node."""
        return nx.ancestors(self.graph, node)
    
    def get_descendants(self, node: str) -> Set[str]:
        """Get all descendants (transitive effects) of a node."""
        return nx.descendants(self.graph, node)
    
    def is_d_separated(self, X: Set[str], Y: Set[str], Z: Set[str]) -> bool:
        """
        Test if X is d-separated from Y given Z.
        
        D-separation is the fundamental test for conditional independence
        in a causal graph. If X ⊥ Y | Z in the graph, then they should
        be independent in the data.
        
        Args:
            X: First set of variables
            Y: Second set of variables
            Z: Conditioning set
        
        Returns:
            True if X and Y are d-separated given Z
        """
        return nx.d_separated(self.graph, X, Y, Z)
    
    def get_adjustment_set(self, treatment: str, outcome: str) -> Optional[Set[str]]:
        """
        Find a valid adjustment set for estimating the causal effect of
        treatment on outcome using the backdoor criterion.
        
        An adjustment set blocks all backdoor paths (confounding) between
        treatment and outcome.
        
        Args:
            treatment: Treatment variable
            outcome: Outcome variable
        
        Returns:
            Set of variables to control for, or None if no valid set exists
        """
        # This is a simplified implementation
        # A full implementation would check the backdoor criterion
        # For now, return parents of treatment that are not descendants of treatment
        
        parents_of_treatment = self.get_parents(treatment)
        descendants_of_treatment = self.get_descendants(treatment)
        
        # Remove any parents that are descendants of treatment
        adjustment_set = parents_of_treatment - descendants_of_treatment - {outcome}
        
        return adjustment_set if adjustment_set else None
    
    def to_dot(self) -> str:
        """
        Export graph to GraphViz DOT format for visualization.
        
        Returns:
            DOT format string
        """
        dot_lines = ["digraph CausalGraph {"]
        dot_lines.append("    rankdir=LR;")  # Left to right layout
        dot_lines.append("    node [shape=box, style=rounded];")
        
        # Add edges with labels
        for (source, target), edge in self.edges.items():
            label = f"{edge.strength:.2f}"
            color = "green" if edge.confidence > 0.8 else "orange" if edge.confidence > 0.5 else "red"
            dot_lines.append(f'    "{source}" -> "{target}" [label="{label}", color={color}];')
        
        dot_lines.append("}")
        return "\n".join(dot_lines)
    
    def summary(self) -> str:
        """
        Get a human-readable summary of the causal graph.
        
        Returns:
            Summary string
        """
        n_nodes = self.graph.number_of_nodes()
        n_edges = self.graph.number_of_edges()
        
        lines = [
            f"Causal Graph Summary:",
            f"  Nodes (variables): {n_nodes}",
            f"  Edges (causal relationships): {n_edges}",
            f"  Latent variables: {len(self.latent_variables)}",
            "",
            "Causal Relationships:"
        ]
        
        for edge in self.edges.values():
            lines.append(f"  {edge}")
        
        return "\n".join(lines)
    
    def __repr__(self):
        return f"CausalGraph(nodes={self.graph.number_of_nodes()}, edges={self.graph.number_of_edges()})"

