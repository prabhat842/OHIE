"""
Test Causal Reasoning Engine

This tests Structural Causal Models, interventions, and counterfactuals.

We use synthetic data where we KNOW the true causal equations, then check:
1. Can the SCM learn the correct equations?
2. Do interventions produce the correct distributions?
3. Do counterfactuals give sensible answers?
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
from qcia_core import (
    CausalGraph,
    CausalDiscoveryEngine,
    StructuralCausalModel,
    CausalReasoningEngine
)


def generate_simple_causal_data(n=1000, seed=42):
    """
    Generate data from known causal model:
    
    Z → X → Y
    
    True equations:
        Z ~ N(0, 1)
        X = 2*Z + ε_X, ε_X ~ N(0, 0.5)
        Y = 3*X + ε_Y, ε_Y ~ N(0, 0.5)
    
    Returns:
        DataFrame and the true causal graph
    """
    np.random.seed(seed)
    
    Z = np.random.normal(0, 1, n)
    X = 2*Z + np.random.normal(0, 0.5, n)
    Y = 3*X + np.random.normal(0, 0.5, n)
    
    data = pd.DataFrame({'Z': Z, 'X': X, 'Y': Y})
    
    # Create true causal graph
    true_graph = CausalGraph()
    true_graph.add_edge('Z', 'X', strength=2.0, confidence=1.0)
    true_graph.add_edge('X', 'Y', strength=3.0, confidence=1.0)
    
    return data, true_graph


def test_scm_fitting():
    """
    Test 1: Can the SCM learn the correct equations?
    """
    print("\n" + "="*70)
    print("TEST 1: SCM Fitting - Learning Structural Equations")
    print("="*70)
    
    # Generate data
    data, true_graph = generate_simple_causal_data(n=2000)
    
    print("\n📊 True Causal Model:")
    print("   Z ~ N(0, 1)")
    print("   X = 2*Z + ε_X")
    print("   Y = 3*X + ε_Y")
    
    # Fit SCM
    scm = StructuralCausalModel(true_graph)
    scm.fit(data)
    
    # Check learned equations
    print("\n✅ Verification:")
    
    # Check Z equation (root node)
    z_eq = scm.equations['Z']
    print(f"\n   Z: Learned μ={z_eq.intercept:.3f} (true=0)")
    print(f"      Learned σ={z_eq.noise_std:.3f} (true=1)")
    assert abs(z_eq.intercept) < 0.1, "Z mean should be ~0"
    assert abs(z_eq.noise_std - 1.0) < 0.1, "Z std should be ~1"
    
    # Check X equation
    x_eq = scm.equations['X']
    learned_coef_z_to_x = x_eq.coefficients.get('Z', 0)
    print(f"\n   X = {learned_coef_z_to_x:.3f}*Z + ε (true=2.0)")
    assert abs(learned_coef_z_to_x - 2.0) < 0.1, "Coefficient Z→X should be ~2"
    
    # Check Y equation
    y_eq = scm.equations['Y']
    learned_coef_x_to_y = y_eq.coefficients.get('X', 0)
    print(f"   Y = {learned_coef_x_to_y:.3f}*X + ε (true=3.0)")
    assert abs(learned_coef_x_to_y - 3.0) < 0.1, "Coefficient X→Y should be ~3"
    
    print("\n🎉 SUCCESS: SCM learned the correct equations!")
    return scm


def test_interventions():
    """
    Test 2: Do interventions produce correct distributions?
    
    Key test: do(X=5) should give different results than observing X=5
    """
    print("\n" + "="*70)
    print("TEST 2: Interventions - Testing do(X) vs P(Y|X)")
    print("="*70)
    
    # Generate data and fit SCM
    data, true_graph = generate_simple_causal_data(n=2000)
    scm = StructuralCausalModel(true_graph)
    scm.fit(data)
    
    print("\n📊 Testing intervention do(X=5):")
    print("   True model: Y = 3*X + noise")
    print("   Expected: E[Y | do(X=5)] = 3*5 = 15")
    
    # Perform intervention
    intervened_samples = scm.intervene({'X': 5}, n_samples=5000)
    
    observed_y_mean = intervened_samples['Y'].mean()
    observed_y_std = intervened_samples['Y'].std()
    
    print(f"\n   Observed: E[Y | do(X=5)] = {observed_y_mean:.3f}")
    print(f"             σ[Y | do(X=5)] = {observed_y_std:.3f}")
    
    # Check if close to expected
    expected_y_mean = 3 * 5  # Y = 3*X, so 3*5 = 15
    assert abs(observed_y_mean - expected_y_mean) < 0.5, \
        f"Intervention mean should be ~{expected_y_mean}, got {observed_y_mean}"
    
    print("\n✅ Verification: Intervention mean is correct!")
    
    # Now test the KEY difference: intervention vs conditioning
    print("\n📊 Comparing do(X=5) vs conditioning on X≈5:")
    
    # Conditional distribution (observational)
    conditional_samples = data[(data['X'] >= 4.5) & (data['X'] <= 5.5)]
    
    if len(conditional_samples) > 0:
        cond_y_mean = conditional_samples['Y'].mean()
        print(f"   P(Y | X≈5) [observational]: {cond_y_mean:.3f}")
        print(f"   P(Y | do(X=5)) [interventional]: {observed_y_mean:.3f}")
        print(f"   Difference: {abs(cond_y_mean - observed_y_mean):.3f}")
        
        # In this simple chain, they should be similar but not identical
        # (because of noise and sampling)
    
    print("\n🎉 SUCCESS: Interventions work correctly!")
    return scm


def test_counterfactuals():
    """
    Test 3: Do counterfactuals give sensible answers?
    
    Counterfactual question: "What would Y have been if X=10,
    given that we observed X=5, Y=16?"
    """
    print("\n" + "="*70)
    print("TEST 3: Counterfactuals - What-If Reasoning")
    print("="*70)
    
    # Generate data and fit SCM
    data, true_graph = generate_simple_causal_data(n=2000)
    scm = StructuralCausalModel(true_graph)
    scm.fit(data)
    
    print("\n📊 Counterfactual Scenario:")
    print("   Model: Z → X → Y where X = 2*Z + ε_X, Y = 3*X + ε_Y")
    print("   Observed: Z=2, X=5, Y=16")
    print("   Question: What if X had been 10 instead of 5?")
    
    # Observed values
    observed = {'Z': 2.0, 'X': 5.0, 'Y': 16.0}
    
    # Counterfactual: What if X had been 10?
    intervention = {'X': 10.0}
    
    cf_values = scm.counterfactual(observed, intervention)
    
    print(f"\n   Counterfactual Y: {cf_values['Y']:.3f}")
    
    # Logic check: 
    # Original Y = 3*5 + noise = 15 + noise
    # So noise = 16 - 15 = 1
    # Counterfactual Y = 3*10 + noise = 30 + 1 = 31
    expected_cf_y = 31.0
    
    print(f"   Expected (by hand calculation): {expected_cf_y:.3f}")
    print(f"   Difference: {abs(cf_values['Y'] - expected_cf_y):.3f}")
    
    assert abs(cf_values['Y'] - expected_cf_y) < 0.5, \
        f"Counterfactual Y should be ~{expected_cf_y}, got {cf_values['Y']}"
    
    print("\n✅ Verification: Counterfactual is correct!")
    print("   The same noise is preserved in the alternate world!")
    
    print("\n🎉 SUCCESS: Counterfactuals work correctly!")
    return scm


def test_confounded_model():
    """
    Test 4: More complex model with confounding.
    
    Structure:
        Z → X → Y
        Z → Y  (confounding!)
    """
    print("\n" + "="*70)
    print("TEST 4: Confounded Model - Testing with Common Cause")
    print("="*70)
    
    np.random.seed(42)
    n = 2000
    
    # Confounder affects both X and Y
    Z = np.random.normal(0, 1, n)
    X = 2*Z + np.random.normal(0, 0.5, n)
    Y = 3*X + 1.5*Z + np.random.normal(0, 0.5, n)  # Both X and Z affect Y!
    
    data = pd.DataFrame({'Z': Z, 'X': X, 'Y': Y})
    
    print("\n📊 True Model:")
    print("   Z → X: X = 2*Z + ε")
    print("   Z → Y: Direct effect")
    print("   X → Y: Direct effect")
    print("   Total: Y = 3*X + 1.5*Z + ε")
    
    # Create graph
    graph = CausalGraph()
    graph.add_edge('Z', 'X')
    graph.add_edge('X', 'Y')
    graph.add_edge('Z', 'Y')  # Confounding!
    
    # Fit SCM
    scm = StructuralCausalModel(graph)
    scm.fit(data)
    
    # Check learned equation for Y
    y_eq = scm.equations['Y']
    coef_x = y_eq.coefficients.get('X', 0)
    coef_z = y_eq.coefficients.get('Z', 0)
    
    print(f"\n✅ Learned Y equation:")
    print(f"   Y = {coef_x:.3f}*X + {coef_z:.3f}*Z + ε")
    print(f"   True: Y = 3.0*X + 1.5*Z + ε")
    
    assert abs(coef_x - 3.0) < 0.2, "Coefficient X→Y should be ~3"
    assert abs(coef_z - 1.5) < 0.2, "Coefficient Z→Y should be ~1.5"
    
    print("\n🎉 SUCCESS: Handles confounding correctly!")
    
    # Test intervention: What if we set X=5, ignoring Z?
    print("\n📊 Testing intervention with confounder:")
    intervened = scm.intervene({'X': 5}, n_samples=5000)
    
    # When we intervene on X, we break Z→X but keep Z→Y
    # So Y will vary based on natural variation in Z
    y_mean = intervened['Y'].mean()
    y_std = intervened['Y'].std()
    
    print(f"   E[Y | do(X=5)] = {y_mean:.3f}")
    print(f"   σ[Y | do(X=5)] = {y_std:.3f}")
    
    # Expected: E[Y | do(X=5)] = 3*5 + 1.5*E[Z] = 15 + 0 = 15
    expected_mean = 15.0
    assert abs(y_mean - expected_mean) < 0.5, \
        f"Mean should be ~{expected_mean}, got {y_mean}"
    
    print(f"   Expected: {expected_mean:.3f} ✓")
    print("\n🎉 Intervention with confounding works!")


def test_reasoning_engine_api():
    """
    Test 5: High-level API for causal queries.
    """
    print("\n" + "="*70)
    print("TEST 5: CausalReasoningEngine - High-Level API")
    print("="*70)
    
    # Generate data and discover structure
    data, true_graph = generate_simple_causal_data(n=2000)
    
    # Use the reasoning engine
    engine = CausalReasoningEngine(true_graph)
    engine.fit(data)
    
    print("\n📊 Computing Average Causal Effect...")
    print("   Treatment: X, Outcome: Y")
    print("   Question: How much does X=1 vs X=0 change Y?")
    
    ace = engine.compute_causal_effect('X', 'Y', treatment_values=(0.0, 1.0))
    
    print(f"\n   ACE = E[Y|do(X=1)] - E[Y|do(X=0)] = {ace:.3f}")
    print(f"   Expected (Y = 3*X): 3*1 - 3*0 = 3.0")
    
    assert abs(ace - 3.0) < 0.2, f"ACE should be ~3, got {ace}"
    
    print("\n✅ Average Causal Effect is correct!")
    
    # Test counterfactual API
    print("\n📊 Testing counterfactual API...")
    cf_y = engine.answer_counterfactual(
        query_var='Y',
        observed={'Z': 2.0, 'X': 5.0, 'Y': 16.0},
        intervention={'X': 10.0}
    )
    
    print(f"   Counterfactual Y (if X=10 instead of 5): {cf_y:.3f}")
    print(f"   Expected: ~31.0")
    
    assert abs(cf_y - 31.0) < 1.0, f"Counterfactual should be ~31, got {cf_y}"
    
    print("\n✅ Counterfactual API works!")
    print("\n🎉 SUCCESS: High-level API is working!")


if __name__ == '__main__':
    print("\n" + "🔬 "*35)
    print("QCIA CAUSAL REASONING TESTS")
    print("🔬 "*35)
    
    # Run all tests
    test_scm_fitting()
    test_interventions()
    test_counterfactuals()
    test_confounded_model()
    test_reasoning_engine_api()
    
    print("\n" + "="*70)
    print("✨ ALL CAUSAL REASONING TESTS PASSED! ✨")
    print("="*70)
    print("\nWhat we validated:")
    print("✓ Structural equations are learned correctly")
    print("✓ Interventions (do-calculus) work")
    print("✓ Counterfactuals preserve noise correctly")
    print("✓ Confounding is handled properly")
    print("✓ High-level API is intuitive")
    print("\nPhase 2 COMPLETE! Ready for integration testing.")
    print("="*70 + "\n")

