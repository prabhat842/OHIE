"""
Test the CausalGraph data structure.

This test verifies basic graph operations work correctly.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from qcia_core.causal_graph import CausalGraph, Edge


def test_basic_graph_operations():
    """Test that we can create and query a causal graph."""
    print("\n" + "="*60)
    print("TEST: Basic Graph Operations")
    print("="*60)
    
    # Create a simple causal structure: Z → X → Y
    graph = CausalGraph()
    graph.add_node('Z')
    graph.add_node('X')
    graph.add_node('Y')
    
    graph.add_edge('Z', 'X', strength=2.0, confidence=0.95)
    graph.add_edge('X', 'Y', strength=3.0, confidence=0.90)
    
    print("\n✅ Created graph: Z → X → Y")
    print(graph.summary())
    
    # Test ancestry
    assert graph.is_ancestor('Z', 'X'), "Z should be ancestor of X"
    assert graph.is_ancestor('X', 'Y'), "X should be ancestor of Y"
    assert graph.is_ancestor('Z', 'Y'), "Z should be ancestor of Y (transitive)"
    assert not graph.is_ancestor('Y', 'X'), "Y should NOT be ancestor of X"
    
    print("\n✅ Ancestry tests passed")
    
    # Test parents/children
    assert graph.get_parents('X') == {'Z'}, "Z should be parent of X"
    assert graph.get_children('X') == {'Y'}, "Y should be child of X"
    assert graph.get_parents('Z') == set(), "Z should have no parents (root node)"
    
    print("✅ Parent/child queries work correctly")
    
    # Test edge metadata
    edge_zx = graph.edges[('Z', 'X')]
    assert edge_zx.strength == 2.0
    assert edge_zx.confidence == 0.95
    
    print("✅ Edge metadata stored correctly")
    
    print("\n" + "="*60)
    print("ALL TESTS PASSED! ✨")
    print("="*60)


def test_collider_structure():
    """Test a more complex structure with a collider (V-structure)."""
    print("\n" + "="*60)
    print("TEST: Collider Structure (X → Z ← Y)")
    print("="*60)
    
    # Create: X → Z ← Y (Z is a collider)
    graph = CausalGraph()
    graph.add_edge('X', 'Z', strength=1.0, confidence=0.9)
    graph.add_edge('Y', 'Z', strength=1.0, confidence=0.9)
    
    print(graph.summary())
    
    # Test that X and Y are NOT ancestors of each other
    assert not graph.is_ancestor('X', 'Y')
    assert not graph.is_ancestor('Y', 'X')
    
    # But both are ancestors of Z
    assert graph.is_ancestor('X', 'Z')
    assert graph.is_ancestor('Y', 'Z')
    
    # Z is a child of both
    assert graph.get_parents('Z') == {'X', 'Y'}
    
    print("\n✅ Collider structure correct")
    print("="*60)


if __name__ == '__main__':
    test_basic_graph_operations()
    test_collider_structure()
    print("\n🎉 All CausalGraph tests passed!\n")

