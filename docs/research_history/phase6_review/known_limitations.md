# Phase 6 Known Limitations

## Scientific Limitations

OHIE currently cannot claim:

- calibrated municipal flood forecasting
- real-time operational readiness
- full shallow-water-equation fidelity
- groundwater coupling
- calibrated pipe-network hydraulics
- detailed sewer/backwater interaction
- calibrated Yamuna/Najafgarh-style compound flooding
- raw SAR/NDWI water classification
- remote-sensing-validated inundation accuracy

## Data Limitations

- Real-terrain benchmarks use small local historical-project-derived terrain chips.
- The river-adjacent benchmark uses a synthetic river-edge mask.
- The remote-sensing comparison uses a proxy historical-output mask.
- External open datasets are not downloaded or redistributed in this phase.

## Numerical Limitations

- Diffusive-wave assumptions dominate current solver behavior.
- Stability is documented but not exhaustively characterized for all terrain classes.
- D-Infinity is a practical implementation, not a complete reproduction of every published triangular facet edge case.

## Interpretation Limits

The Phase 6 outputs support:

- reproducibility review
- qualitative scientific behavior inspection
- researcher experimentation

They do not support:

- DPR-grade design sizing
- flood warning operations
- legal/regulatory floodplain determination
- claims of superiority over HEC-RAS, MIKE, LISFLOOD-FP, or Bentley tools

