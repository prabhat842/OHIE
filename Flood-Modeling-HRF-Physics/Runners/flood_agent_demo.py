#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from typing import Dict


def _ensure_paths():
    here = os.path.dirname(__file__)
    root = os.path.abspath(os.path.join(here, ".."))
    ai_dir = os.path.join(root, "AI")
    physics_dir = os.path.join(root, "Physics")
    for p in [root, ai_dir, physics_dir]:
        if p not in sys.path:
            sys.path.append(p)


_ensure_paths()

from AI.hrf_world_adapter import HRFWorldAdapter, HRFWorldConfig  # type: ignore
from AI.flood_agent import FloodAgent  # type: ignore


def run_demo(steps: int = 10, sim_chunk_s: float = 60.0) -> None:
    cfg = HRFWorldConfig(nx=64, ny=64, Lx_m=1000.0, Ly_m=1000.0, h_init_m=0.0, sim_chunk_s=sim_chunk_s)
    world = HRFWorldAdapter(cfg)
    agent = FloodAgent()

    # Start with a bit of rain to create a flood scenario
    world.step({"action": "rain", "rate_mps": 1.0e-5}, sim_seconds=sim_chunk_s)

    for k in range(steps):
        before = world.get_perception()
        act: Dict = agent.decide(before)
        reward, outcome = world.step(act, sim_seconds=sim_chunk_s)
        after = world.get_perception()
        agent.remember(before, act, after, reward)
        print(f"step={k:02d} action={act} reward={reward:.6f} mean_h={after['mean_h']:.4f} max_h={after['max_h']:.4f}")


if __name__ == "__main__":
    run_demo(steps=8, sim_chunk_s=60.0)




