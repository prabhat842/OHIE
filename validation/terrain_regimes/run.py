from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ohie.validation.terrain_regimes import run_terrain_regime_study


def main() -> int:
    results = run_terrain_regime_study()
    lines = [
        "# Terrain Regime Transfer Results",
        "",
        "| Terrain | Mean slope | Slope var | Relief range (m) | Floodplain width proxy (m) | Roughness | Elevation var | Storage proxy (m3) | Boundary volume (m3) | Mass error | Edge response (m) | Persistence (s) | Flooded delta | Classification |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for result in results:
        d = result.descriptors
        lines.append(
            f"| {result.terrain.label} | {d.mean_slope:.5f} | {d.slope_variance:.5f} | {d.relief_range_m:.2f} | "
            f"{d.floodplain_width_proxy_m:.1f} | {d.terrain_roughness:.5f} | {d.elevation_variance:.5f} | "
            f"{d.storage_proxy_m3:.1f} | {result.boundary_volume_m3:.1f} | {result.mass_error:.6f} | "
            f"{result.near_edge_response_m:.3f} | {result.persistence_s:.1f} | {result.flooded_area_delta_cells} | {result.classification} |"
        )
    out = Path(__file__).with_name("observed_output.md")
    out.write_text("\n".join(lines) + "\n")
    print(out.read_text())

    csv_lines = [
        "key,label,mean_slope,slope_variance,relief_range_m,floodplain_width_proxy_m,terrain_roughness,elevation_variance,storage_proxy_m3,boundary_volume_m3,mass_error,near_edge_response_m,persistence_s,flooded_area_delta_cells,classification"
    ]
    for result in results:
        d = result.descriptors
        csv_lines.append(
            f"{result.terrain.key},{result.terrain.label},{d.mean_slope:.8f},{d.slope_variance:.8f},{d.relief_range_m:.3f},{d.floodplain_width_proxy_m:.3f},"
            f"{d.terrain_roughness:.8f},{d.elevation_variance:.8f},{d.storage_proxy_m3:.3f},{result.boundary_volume_m3:.3f},{result.mass_error:.6f},"
            f"{result.near_edge_response_m:.6f},{result.persistence_s:.3f},{result.flooded_area_delta_cells},{result.classification}"
        )
    Path(__file__).with_name("descriptors.csv").write_text("\n".join(csv_lines) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
