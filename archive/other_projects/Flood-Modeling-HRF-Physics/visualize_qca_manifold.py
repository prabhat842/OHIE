#!/usr/bin/env python3
"""
Visualize QCA Manifold - Show learned intervention synergies
"""
import sys
sys.path.insert(0, '/Users/tiger/Desktop/QCIA_HRF_Flood copy')

from AI.qcia_core.qca_manifold_optimizer import QCAOptimizer, visualize_manifold
from AI.qcia_core.flood_encoder import FloodStateEncoder
import json
import numpy as np
from pathlib import Path

print("="*70)
print("🎨 QCA MANIFOLD VISUALIZATION")
print("="*70)

# Load learned manifold
manifold_file = Path('outputs/qcia_full_demo/qcia_analysis/qca_manifold.json')

if not manifold_file.exists():
    print(f"❌ Manifold file not found: {manifold_file}")
    print(f"   Run run_qcia_flood_optimization.py first")
    sys.exit(1)

# Initialize QCA and encoder
qca = QCAOptimizer()
encoder = FloodStateEncoder()

# Load experiences
print(f"📂 Loading manifold from {manifold_file}...")
qca.load_from_file(str(manifold_file), hypotheses=encoder.hypotheses)

print(f"   ✅ Loaded {len(qca.engine.experiences)} experiences")
print(f"   Manifold dimension: {qca.engine.manifold_dim}D")

# Visualize manifold
output_path = 'outputs/qcia_full_demo/qcia_analysis/qca_manifold_3d.png'
print(f"\n🎨 Generating 3D visualization...")
visualize_manifold(qca, save_path=output_path)

# Analyze clusters (synergies)
print(f"\n🔍 Discovering intervention synergies (clusters)...")
clusters = qca.engine.get_experience_clusters(n_clusters=3)

for i, cluster in enumerate(clusters):
    print(f"\n   Cluster {i+1}: {len(cluster)} interventions")
    
    # Get intervention types in this cluster
    types = {}
    rewards = []
    for idx in cluster[:10]:  # Show first 10
        exp = qca.engine.experiences[idx]
        itype = exp.action['type']
        types[itype] = types.get(itype, 0) + 1
        rewards.append(exp.reward)
    
    print(f"      Types: {dict(types)}")
    print(f"      Avg reward: {np.mean(rewards):.3f} ± {np.std(rewards):.3f}")
    print(f"      Reward range: [{min(rewards):.3f}, {max(rewards):.3f}]")

# Find best synergies (experiences with highest reward)
print(f"\n🏆 Top 5 highest-reward interventions:")
sorted_exps = sorted(enumerate(qca.engine.experiences), 
                     key=lambda x: x[1].reward, reverse=True)

for rank, (idx, exp) in enumerate(sorted_exps[:5], 1):
    print(f"   {rank}. {exp.action['type']} @ {exp.action['location']}")
    print(f"      Reward: {exp.reward:.3f}, Cost: ₹{exp.metadata['cost']/1e7:.2f} Cr")
    print(f"      B/C ratio: {exp.metadata['benefit_cost_ratio']:.2f}")

print(f"\n{'='*70}")
print(f"✅ Visualization saved: {output_path}")
print(f"{'='*70}")



