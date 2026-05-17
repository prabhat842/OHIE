"""
Tests that demonstrate improvements over the previous linear-only setup:

1) HSIC-based independence detects nonlinear dependence missed by partial correlation.
2) Nonlinear SCM (random forest) estimates causal effects better on a nonlinear model.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd

from qcia_core import CausalDiscoveryEngine, CausalGraph
from qcia_core import CausalReasoningEngine


def generate_nonlinear_data_paired(n_pairs=600, seed=7):
    """
    Construct a dataset where linear correlation is (near) exactly zero,
    but strong nonlinear dependence exists: Y = X^2.
    We create symmetric pairs (u, -u) so sample correlation cancels.
    """
    rng = np.random.default_rng(seed)
    u = rng.uniform(0.2, 1.5, n_pairs)
    X = np.concatenate([u, -u])
    Y = np.concatenate([u**2, u**2])  # same Y for ±u
    return pd.DataFrame({ 'X': X, 'Y': Y })


def test_hsic_detects_nonlinear_dependence():
    data = generate_nonlinear_data_paired(n_pairs=800)

    # Engine with partial correlation (baseline)
    engine_lin = CausalDiscoveryEngine(alpha=0.05, independence_test='partial_correlation')
    engine_lin.data = data
    indep_lin = engine_lin._is_independent('X', 'Y', [])  # pylint: disable=protected-access

    # Engine with HSIC (nonlinear)
    engine_hsic = CausalDiscoveryEngine(
        alpha=0.05,
        independence_test='hsic',
        hsic_num_permutations=200,
        residual_model='linear',
        random_state=42
    )
    engine_hsic.data = data
    indep_hsic = engine_hsic._is_independent('X', 'Y', [])  # pylint: disable=protected-access

    print(f"Partial correlation says independent? {indep_lin}")
    print(f"HSIC says independent? {indep_hsic}")

    # Expect: partial corr fails (thinks independent), HSIC succeeds (dependent)
    assert indep_lin, "Partial correlation should miss the nonlinear dependence (treat as independent)"
    assert not indep_hsic, "HSIC should detect nonlinear dependence (reject independence)"


def generate_nonlinear_causal_chain(n=3000, seed=11):
    """
    Nonlinear chain: Z -> X -> Y with nonlinear effect X->Y.
    Z ~ N(0,1), X = 2*Z + noise, Y = (X^2) + noise.
    True ACE of X on Y around X=1 vs X=0 is ~ (1^2 - 0^2) = 1 (local notion).
    We'll measure via interventions and compare model fits.
    """
    rng = np.random.default_rng(seed)
    Z = rng.normal(0, 1.0, n)
    X = 2*Z + rng.normal(0, 0.3, n)
    Y = (X**2) + rng.normal(0, 0.5, n)
    data = pd.DataFrame({ 'Z': Z, 'X': X, 'Y': Y })
    graph = CausalGraph()
    graph.add_edge('Z', 'X')
    graph.add_edge('X', 'Y')
    return data, graph


def test_nonlinear_scm_better_ace_estimate():
    data, graph = generate_nonlinear_causal_chain(n=2500)

    # Fit linear SCM
    eng_lin = CausalReasoningEngine(graph)
    eng_lin.fit(data, model_type='linear')
    ace_lin = eng_lin.compute_causal_effect('X', 'Y', treatment_values=(0.0, 1.0))

    # Fit nonlinear SCM (random forest)
    eng_rf = CausalReasoningEngine(graph)
    eng_rf.fit(data, model_type='random_forest')
    ace_rf = eng_rf.compute_causal_effect('X', 'Y', treatment_values=(0.0, 1.0))

    print(f"ACE linear ~ {ace_lin:.3f}")
    print(f"ACE RF     ~ {ace_rf:.3f}")

    # Ground truth (local): around 1
    true_local_ace = 1.0
    err_lin = abs(ace_lin - true_local_ace)
    err_rf = abs(ace_rf - true_local_ace)

    # Expect the nonlinear SCM to be closer
    assert err_rf <= err_lin, "Nonlinear SCM should estimate ACE closer to the nonlinear ground truth"


