# Phase 6 Benchmark Summary

## Real Terrain

| Benchmark | Status | Confidence | Notes |
|-----------|--------|------------|-------|
| Flat terrain small | Runnable | Medium for reproducibility; Low for site hydrology | Uses local historical-project-derived terrain chip |
| River adjacent small | Runnable | Medium for boundary plumbing; Low for river hydraulics | Uses synthetic river-edge mask |

## Literature Behavior

| Benchmark | Confidence | Claim Type |
|-----------|------------|------------|
| Closed basin conservation | High | Controlled synthetic behavior |
| Bowl filling | High | Controlled synthetic behavior |
| Flat terrain routing | Medium | Qualitative behavior |
| River stage influence | Medium | Boundary-response behavior |
| Storage attenuation | Medium | Intervention-response behavior |

## Remote Sensing

Current comparison:

> **proxy comparison only**

Metrics implemented:

- IoU
- observed overlap percent
- flooded area agreement

The current observation mask is local historical-output-derived. It should be replaced or supplemented with raw Sentinel-1, NDWI, Copernicus EMS, or JRC-derived water masks before publication-grade claims.

