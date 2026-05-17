#!/usr/bin/env python3
"""
Build side-by-side comparison panel from overlay PNGs and write simple KPI CSV.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--baseline', type=str, required=True)
    ap.add_argument('--selected', type=str, required=True)
    ap.add_argument('--agent', type=str, required=True)
    ap.add_argument('--compare', type=str, required=True)
    ap.add_argument('--out_dir', type=str, default='runs/gurdaspur_kmz_export')
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    img_b = plt.imread(args.baseline)
    img_s = plt.imread(args.selected)
    img_a = plt.imread(args.agent)
    img_c = plt.imread(args.compare)

    # 3-up panel
    fig, axes = plt.subplots(1, 3, figsize=(16, 6))
    for ax, im, title in zip(axes, [img_b, img_s, img_a], ['Baseline', 'Selected (Budgeted)', 'Agent Final']):
        ax.imshow(im)
        ax.set_title(title)
        ax.axis('off')
    fig.tight_layout()
    panel_path = out_dir / 'panel_baseline_selected_agent.png'
    fig.savefig(panel_path, dpi=150)
    plt.close(fig)

    # Compare image copy
    from shutil import copyfile
    copyfile(args.compare, out_dir / 'overlay_compare.png')

    # Optional KPI CSV if logits printed in text files present (skip for now)
    print('Saved', panel_path)


if __name__ == '__main__':
    main()




