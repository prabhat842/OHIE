#!/usr/bin/env python3
"""
Parameter sweep for channel settings on a given AOI run.
Varies: channel_n, channel_crest_h_m, drain_sink_mps, culvert_area_m2.

Requires: kpi_overlay_roads.py present to compute KPI.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
from pathlib import Path


def run_cmd(cmd: list[str]) -> None:
    subprocess.check_call(cmd)


def main() -> None:
    ap = argparse.ArgumentParser(description='Sweep channel parameters')
    ap.add_argument('--base_out', type=str, default='runs/gurdaspur_aoi12')
    ap.add_argument('--dem', type=str, default='Data/GDSP_DEM_utm43n_100m.tif')
    ap.add_argument('--nx', type=int, default=35)
    ap.add_argument('--ny', type=int, default=35)
    ap.add_argument('--upsample', type=int, default=2)
    ap.add_argument('--tile_col0', type=int, default=938)
    ap.add_argument('--tile_row0', type=int, default=1094)
    ap.add_argument('--lulc', type=str, default='Data/LULC2_utm43n_100m.tif')
    ap.add_argument('--rivers', type=str, default='Data/osm_rivers.geojson')
    ap.add_argument('--drains', type=str, default='Data/osm_drains_aoi.geojson')
    ap.add_argument('--canals', type=str, default='Data/osm_canals_aoi.geojson')
    ap.add_argument('--culverts', type=str, default='Data/osm_culverts_aoi.geojson')
    ap.add_argument('--roads', type=str, default='Data/roads_aoi.geojson')
    ap.add_argument('--structs', type=str, default='Data/osm_structures_aoi.geojson')
    ap.add_argument('--rain_mmph', type=float, default=20.0)
    ap.add_argument('--t_hours', type=float, default=1.5)
    ap.add_argument('--threshold_m', type=float, default=0.05)
    ap.add_argument('--n_list', type=str, default='')
    ap.add_argument('--crest_list', type=str, default='')
    ap.add_argument('--sink_list', type=str, default='')
    ap.add_argument('--carea_list', type=str, default='')
    args = ap.parse_args()

    def parse_floats(s: str):
        return [float(x.strip()) for x in s.split(',') if x.strip()]

    channel_n_vals = parse_floats(args.n_list) if args.n_list else [0.024, 0.028, 0.032, 0.036]
    crest_vals = parse_floats(args.crest_list) if args.crest_list else [0.06, 0.08, 0.12, 0.16]
    sink_vals = parse_floats(args.sink_list) if args.sink_list else [5e-7, 1e-6, 1.5e-6]
    culvert_area_vals = parse_floats(args.carea_list) if args.carea_list else [0.6, 0.8, 1.0]

    best = None
    results = []
    for n, crest, sink, carea in itertools.product(channel_n_vals, crest_vals, sink_vals, culvert_area_vals):
        tag = f"n{n:.3f}_crest{crest:.2f}_sink{sink:.1e}_cA{carea:.1f}"
        out_dir = f"{args.base_out}_sweep_{tag}"
        cmd = [
            'python', 'Runners/pb_cli.py',
            '--dem', args.dem,
            '--out', out_dir,
            '--nx', str(args.nx), '--ny', str(args.ny), '--upsample', str(args.upsample),
            '--tile_col0', str(args.tile_col0), '--tile_row0', str(args.tile_row0),
            '--lulc', args.lulc,
            '--rivers', args.rivers,
            '--drains', args.drains,
            '--canals', args.canals,
            '--culverts', args.culverts,
            '--channel_buffer_m', '30',
            '--channel_crest_h_m', str(crest),
            '--channel_n', str(n),
            '--drain_sink_mps', str(sink),
            '--culvert_area_m2', str(carea),
            '--rain_mm_per_hour', str(args.rain_mmph),
            '--t_hours', str(args.t_hours),
            '--h_init_m', '0.0'
        ]
        run_cmd(cmd)
        # KPI
        kcmd = [
            'python', 'Runners/kpi_overlay_roads.py',
            '--run_dir', out_dir,
            '--roads', args.roads,
            '--rivers', 'Data/osm_rivers_aoi.geojson',
            '--drains', 'Data/osm_drains_aoi.geojson',
            '--canals', 'Data/osm_canals_aoi.geojson',
            '--structures', args.structs,
            '--depth_threshold_m', str(args.threshold_m)
        ]
        out = subprocess.check_output(kcmd, text=True)
        # parse km from stdout
        km = None
        for line in out.splitlines():
            if 'Road flooded length' in line:
                try:
                    km = float(line.split(':')[1].split('km')[0].strip())
                except Exception:
                    pass
        results.append({'tag': tag, 'out_dir': out_dir, 'flooded_km': km})
        if km is not None and (best is None or km < best['flooded_km']):
            best = {'tag': tag, 'out_dir': out_dir, 'flooded_km': km}
        print('Done', tag, '=>', km, 'km')

    summary_path = Path(f"{args.base_out}_sweep_summary.json")
    summary_path.write_text(json.dumps({'best': best, 'results': results}, indent=2))
    print('Best:', best)
    print('Saved', summary_path)


if __name__ == '__main__':
    main()
