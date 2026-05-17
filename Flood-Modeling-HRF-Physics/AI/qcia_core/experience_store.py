#!/usr/bin/env python3
"""
QCIA Experience Store - Persistent Intervention Learning
========================================================
Tracks intervention performance across runs to enable:
1. Type-based learning (culverts work better than pumps in this region)
2. Prune poor performers (avoid repeating failures)
3. Boost proven winners (exploit successful patterns)

Inspired by concept.py pruning mechanism, adapted for discrete interventions.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import numpy as np


@dataclass
class InterventionRecord:
    """Single intervention performance record."""
    type: str
    location: tuple  # (i, j)
    cost_inr: float
    damage_reduction_cr: float
    road_km_reduction: float
    roi: float
    success: bool  # True if ROI > 0
    aoi_name: str = "unknown"
    timestamp: str = ""
    
    def to_dict(self):
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        d['location'] = list(d['location'])  # tuple → list for JSON
        d['success'] = bool(d['success'])  # Ensure Python bool, not numpy.bool_
        d['roi'] = float(d['roi'])  # Ensure float, not numpy.float64
        d['cost_inr'] = float(d['cost_inr'])
        d['damage_reduction_cr'] = float(d['damage_reduction_cr'])
        d['road_km_reduction'] = float(d['road_km_reduction'])
        return d
    
    @classmethod
    def from_dict(cls, d):
        """Restore from dict."""
        d['location'] = tuple(d['location'])
        return cls(**d)


class ExperienceStore:
    """
    Persistent store for intervention performance.
    
    Maintains:
    - Per-type success rates
    - Per-type average ROI
    - Pruning zones (types with consistent failure)
    """
    
    def __init__(self, store_path: Optional[Path] = None):
        """
        Args:
            store_path: Path to JSON store file. If None, uses default workspace location.
        """
        if store_path is None:
            store_path = Path(__file__).parent.parent.parent / "experience_store.json"
        
        self.store_path = Path(store_path)
        self.records: List[InterventionRecord] = []
        
        # Load existing experiences
        if self.store_path.exists():
            self._load()
    
    def _load(self):
        """Load experiences from disk."""
        try:
            with open(self.store_path, 'r') as f:
                data = json.load(f)
            self.records = [InterventionRecord.from_dict(r) for r in data.get('records', [])]
            print(f"   📚 Loaded {len(self.records)} past intervention records from experience store")
        except Exception as e:
            print(f"   ⚠️  Could not load experience store: {e}")
            self.records = []
    
    def save(self):
        """Persist experiences to disk."""
        try:
            data = {
                'records': [r.to_dict() for r in self.records],
                'version': '1.0'
            }
            with open(self.store_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"   💾 Saved {len(self.records)} records to experience store")
        except Exception as e:
            print(f"   ⚠️  Could not save experience store: {e}")
    
    def add_record(self, record: InterventionRecord):
        """Add new intervention record."""
        self.records.append(record)
    
    def add_batch(self, records: List[InterventionRecord]):
        """Add multiple records at once."""
        self.records.extend(records)
    
    def get_type_statistics(self) -> Dict[str, Dict[str, float]]:
        """
        Compute performance statistics per intervention type.
        
        Returns:
            Dict mapping type → {
                'success_rate': fraction with ROI > 0,
                'avg_roi': mean ROI,
                'avg_damage_reduction_cr': mean damage reduction,
                'avg_road_km_reduction': mean road km saved,
                'count': number of records
            }
        """
        stats = {}
        
        # Group by type
        by_type = {}
        for rec in self.records:
            if rec.type not in by_type:
                by_type[rec.type] = []
            by_type[rec.type].append(rec)
        
        # Compute stats
        for typ, recs in by_type.items():
            successes = sum(1 for r in recs if r.success)
            stats[typ] = {
                'success_rate': successes / len(recs) if recs else 0.0,
                'avg_roi': np.mean([r.roi for r in recs]),
                'avg_damage_reduction_cr': np.mean([r.damage_reduction_cr for r in recs]),
                'avg_road_km_reduction': np.mean([r.road_km_reduction for r in recs]),
                'count': len(recs)
            }
        
        return stats
    
    def get_learning_multipliers(self, min_samples: int = 3) -> Dict[str, float]:
        """
        Compute learning-based multipliers for candidate scoring.
        
        Types with consistent success → multiplier > 1.0 (boost)
        Types with consistent failure → multiplier < 1.0 (penalize)
        Types with insufficient data → multiplier = 1.0 (neutral)
        
        Args:
            min_samples: Minimum records needed before applying learning
        
        Returns:
            Dict mapping type → multiplier (0.1 to 3.0)
        """
        stats = self.get_type_statistics()
        multipliers = {}
        
        for typ, stat in stats.items():
            if stat['count'] < min_samples:
                # Not enough data, stay neutral
                multipliers[typ] = 1.0
                continue
            
            # Blend success rate and average ROI
            success_rate = stat['success_rate']
            avg_roi = max(0.0, stat['avg_roi'])  # Clamp negative to 0
            
            # success_rate: 0→0.5x, 0.5→1x, 1→1.5x
            # avg_roi: 0→1x, 1→1.2x, 2→1.5x, 3+→2x
            success_mult = 0.5 + success_rate
            roi_mult = 1.0 + min(1.0, avg_roi / 3.0)
            
            # Combine (geometric mean)
            combined = (success_mult * roi_mult) ** 0.5
            
            # Clamp to reasonable range
            multipliers[typ] = np.clip(combined, 0.1, 3.0)
        
        return multipliers
    
    def should_prune_type(self, intervention_type: str, threshold: float = 0.2, min_samples: int = 5) -> bool:
        """
        Check if an intervention type should be pruned (avoided).
        
        Args:
            intervention_type: Type to check
            threshold: Success rate below which to prune
            min_samples: Minimum records before pruning
        
        Returns:
            True if type consistently fails and should be avoided
        """
        stats = self.get_type_statistics()
        
        if intervention_type not in stats:
            return False  # Unknown type, don't prune
        
        stat = stats[intervention_type]
        
        if stat['count'] < min_samples:
            return False  # Not enough evidence
        
        # Prune if success rate below threshold
        return stat['success_rate'] < threshold
    
    def get_summary(self) -> str:
        """Generate human-readable summary of experience store."""
        if not self.records:
            return "Experience store is empty (no prior runs)"
        
        stats = self.get_type_statistics()
        multipliers = self.get_learning_multipliers()
        
        lines = [
            f"📊 Experience Store Summary ({len(self.records)} interventions)",
            ""
        ]
        
        # Sort by success rate (descending)
        sorted_types = sorted(stats.items(), key=lambda x: x[1]['success_rate'], reverse=True)
        
        for typ, stat in sorted_types:
            mult = multipliers.get(typ, 1.0)
            emoji = "✅" if stat['success_rate'] > 0.5 else "⚠️" if stat['success_rate'] > 0.2 else "❌"
            
            lines.append(
                f"{emoji} {typ:30s} | "
                f"Success: {stat['success_rate']*100:5.1f}% | "
                f"ROI: {stat['avg_roi']:5.2f}x | "
                f"Multiplier: {mult:4.2f}x | "
                f"Count: {stat['count']:3d}"
            )
        
        return "\n".join(lines)


def apply_experience_learning(candidates: List[Dict], store: ExperienceStore, verbose: bool = True):
    """
    Apply experience-based learning to adjust candidate scores.
    
    Modifies candidates in-place:
    - Adds 'experience_multiplier' field
    - Multiplies 'causal_impact' by learned multiplier
    - Adds 'learned_expected_roi' field
    
    Args:
        candidates: List of candidate interventions
        store: Experience store with historical performance
        verbose: Print learning adjustments
    """
    multipliers = store.get_learning_multipliers()
    stats = store.get_type_statistics()
    
    if verbose and multipliers:
        print(f"\n📚 Applying experience-based learning to {len(candidates)} candidates:")
        print(f"   Learned from {len(store.records)} past interventions")
    
    adjusted_count = 0
    pruned_count = 0
    
    for cand in candidates:
        typ = cand['type']
        
        # Check if should prune
        if store.should_prune_type(typ):
            # Mark for filtering (don't hard-delete to preserve transparency)
            cand['experience_pruned'] = True
            cand['experience_multiplier'] = 0.05  # Near-zero to de-prioritize
            pruned_count += 1
            continue
        
        # Apply learned multiplier
        mult = multipliers.get(typ, 1.0)
        cand['experience_multiplier'] = mult
        
        # Adjust causal impact
        if mult != 1.0:
            original_impact = cand.get('causal_impact', 0.0)
            cand['causal_impact'] = original_impact * mult
            adjusted_count += 1
        
        # Add expected ROI from history
        if typ in stats:
            cand['learned_expected_roi'] = stats[typ]['avg_roi']
        else:
            cand['learned_expected_roi'] = 0.0
    
    if verbose and multipliers:
        print(f"   ✅ Adjusted {adjusted_count} candidates, pruned {pruned_count} poor performers")
        
        # Show top adjustments
        boosts = [(c['type'], c['experience_multiplier']) for c in candidates if c.get('experience_multiplier', 1.0) > 1.1]
        penalties = [(c['type'], c['experience_multiplier']) for c in candidates if c.get('experience_multiplier', 1.0) < 0.9]
        
        if boosts:
            boosts_summary = {typ: mult for typ, mult in boosts}
            unique_boosts = {k: v for k, v in sorted(set((t, m) for t, m in boosts), key=lambda x: -x[1])}
            print(f"   ⬆️  Boosted: {', '.join(f'{t} ({m:.2f}x)' for t, m in list(unique_boosts.items())[:3])}")
        
        if penalties:
            unique_penalties = {k: v for k, v in sorted(set((t, m) for t, m in penalties), key=lambda x: x[1])}
            print(f"   ⬇️  Penalized: {', '.join(f'{t} ({m:.2f}x)' for t, m in list(unique_penalties.items())[:3])}")

