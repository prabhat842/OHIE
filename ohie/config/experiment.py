from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

import numpy as np

from ohie import DiffusiveWaveFV, DiffusiveWaveParams, Grid
from ohie.hydro.boundaries import FixedHeadBoundary, FluxBoundary, HydrographBoundary, RainfallBoundary, RiverStageBoundary
from ohie.interventions import ChannelCarve, DetentionBasin, Pump
from ohie.terrain.routing import D8Routing, DInfinityRouting, MultiFlowRouting, RoutingStrategy


@dataclass
class ExperimentConfig:
    """Shareable OHIE experiment configuration."""

    raw: dict[str, Any]
    path: Path | None = None

    def build_grid(self) -> Grid:
        cfg = self.raw.get("grid", {})
        return Grid(
            nx=int(cfg.get("nx", 50)),
            ny=int(cfg.get("ny", 50)),
            dx=float(cfg.get("dx", cfg.get("resolution", 30.0))),
            dy=float(cfg.get("dy", cfg.get("resolution", 30.0))),
        )

    def build_bed(self, grid: Grid) -> np.ndarray:
        terrain = self.raw.get("terrain", {})
        kind = terrain.get("synthetic", "flat_bowl")
        x = np.linspace(0.0, 1.0, grid.nx)[:, None]
        y = np.linspace(0.0, 1.0, grid.ny)[None, :]
        if kind == "slope":
            return float(terrain.get("slope_x", 0.05)) * x + float(terrain.get("slope_y", 0.0)) * y
        if kind == "flat_bowl":
            bed = float(terrain.get("slope_x", 0.02)) * x + float(terrain.get("slope_y", 0.02)) * y
            bed -= float(terrain.get("bowl_depth_m", 0.25)) * np.exp(-(((x - 0.5) ** 2 + (y - 0.5) ** 2) / 0.02))
            return bed
        raise ValueError(f"unsupported synthetic terrain: {kind}")

    def build_solver(self) -> DiffusiveWaveFV:
        grid = self.build_grid()
        solver_cfg = self.raw.get("solver", {})
        params = DiffusiveWaveParams(
            manning_n=float(solver_cfg.get("manning_n", 0.06)),
            dt_max=float(solver_cfg.get("dt_max", 1.0)),
            h_min=float(solver_cfg.get("h_min", 1.0e-4)),
        )
        solver = DiffusiveWaveFV(grid, params)
        solver.initialize(self.build_bed(grid), h0=float(self.raw.get("initial_depth_m", 0.0)))
        for boundary in self.build_boundaries(solver):
            solver.add_boundary(boundary)
        return solver

    def build_routing(self) -> RoutingStrategy:
        method = str(self.raw.get("routing", {}).get("method", "d8")).lower()
        if method in ("d8", "d-8"):
            return D8Routing()
        if method in ("dinfinity", "dinf", "d-infinity"):
            return DInfinityRouting()
        if method in ("multiflow", "mfd"):
            return MultiFlowRouting()
        raise ValueError(f"unsupported routing method: {method}")

    def build_boundaries(self, solver: DiffusiveWaveFV) -> list:
        boundaries = []
        for item in self.raw.get("boundaries", []):
            btype = item.get("type")
            if btype == "rainfall":
                boundaries.append(RainfallBoundary(float(item["rate_mm_per_hr"]) / 1000.0 / 3600.0))
            elif btype == "fixed_head":
                boundaries.append(FixedHeadBoundary(edge=item.get("edge", "west"), stage_m=float(item["stage_m"])))
            elif btype == "flux":
                boundaries.append(FluxBoundary(edge=item.get("edge", "west"), discharge_m3s=float(item["discharge_m3s"])))
            elif btype == "river_stage":
                mask = np.zeros(solver.grid.shape, dtype=bool)
                col = int(item.get("column", 0))
                mask[:, col] = True
                boundaries.append(RiverStageBoundary(mask=mask, stage_m=float(item["stage_m"])))
            elif btype == "hydrograph":
                mask = np.zeros(solver.grid.shape, dtype=bool)
                row = int(item.get("row", 0))
                mask[row, :] = True
                q = float(item["discharge_m3s"])
                boundaries.append(HydrographBoundary(mask=mask, discharge_m3s=lambda _t, q=q: q))
            else:
                raise ValueError(f"unsupported boundary type: {btype}")
        return boundaries

    def build_interventions(self) -> list:
        interventions = []
        for item in self.raw.get("interventions", []):
            itype = item.get("type")
            row = int(item.get("row", item.get("location", [0, 0])[0]))
            col = int(item.get("col", item.get("location", [0, 0])[1]))
            if itype == "detention_basin":
                interventions.append(DetentionBasin(row, col, depth_m=float(item.get("depth_m", 1.5)), radius_cells=int(item.get("radius_cells", 3))))
            elif itype == "channel_carve":
                interventions.append(ChannelCarve(row, col, max_steps=int(item.get("max_steps", 100)), carve_depth_m=float(item.get("carve_depth_m", 0.4))))
            elif itype == "pump":
                interventions.append(Pump(row, col, rate_m3s=float(item.get("rate_m3s", 1.5))))
            else:
                raise ValueError(f"unsupported intervention type: {itype}")
        return interventions


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    p = Path(path)
    text = p.read_text()
    if p.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except Exception as exc:
            raise RuntimeError("YAML configs require optional dependency: pip install ohie[config]") from exc
        raw = yaml.safe_load(text)
    else:
        raw = json.loads(text)
    return ExperimentConfig(raw=raw or {}, path=p)

