# Minor1 pseudocode

1. Load STL, config, layer-path policy, and paired global-placement policy.
2. Select one XY translation for the full mesh and apply it before slicing.
3. For each layer, choose path parameters and robot partition.
4. Generate candidate routes; check concurrent and staggered starts against collision and reach constraints.
5. Compute per-layer reward; placement reward is the mean over layers of that same STL.
6. Export the full trajectory and run the official WAAM Validator.

Reward gate: when IoU > 0.9, `10 × mean deposition utilization × reference time / layer duration`; otherwise use terminal Validator status.
