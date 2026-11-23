# Golgi cell gap-junction comparison

Run two full-compartment Masoli 2020 Golgi cells in BrainCell and NEURON.
Both simulations use the repository's GoC ASC morphology, regional channel
parameters, initial voltage and temperature. Both couple the midpoint of
basal dendrite 0 on the first cell to the equivalent position on the second
cell. The example checks the lengths and discretization counts of all sections
before comparing the two voltage traces.

The first soma receives a 20 pA current pulse from 5 to 25 ms. The gap
conductance is 1 nS, the temperature is 30 °C, the initial voltage is −65 mV,
and the default step is 0.025 ms. The second cell records the voltage at the
coupled dendrite and soma. BrainCell uses Network.connect_junction. NEURON
places two ohmic point mechanisms, each reading the peer segment's voltage.

## Run the comparison

From the BrainCell repository root, use a Python environment with BrainCell
dependencies, NEURON, and Matplotlib. The NEURON distribution must provide
nrnivmodl and a working C++ toolchain. The example builds the Golgi mechanisms
and the half-junction in a temporary directory.

```bash
JAX_PLATFORMS=cpu python -m examples.neuron_compare.cell.goc_ma2020.gap_junction --output /tmp/goc-gap-comparison
```

The output directory contains voltages.csv, comparison.json, and
voltage-comparison.png. The CSV contains aligned samples from both simulators
and their difference at each site. The plot overlays both voltages and shows
the residual, with shading during the current pulse. The JSON records the
settings, geometry checks, voltage error, and upward crossings of −20 mV.

## Voltage integration

BrainCell automatically solves the cable equations and electrical contacts
together using the staggered cell solver. The current from B into A uses
both end-of-step voltages.

$$
I_{\mathrm{gap}\to A}^{n+1} =
g\left(V_B^{n+1}-V_A^{n+1}\right).
$$

The solver applies the cross-cell correction through the existing tree
solves and a matrix-free junction system. It solves all coupled voltages
before updating the staggered ion-channel states.

## Reference runs

The two simulators each use 227 sections and 317 compartments per cell.
The comparison uses NEURON 9.0.1. Positive lag means BrainCell crosses
the threshold later. The JSON includes both sampled crossing times and
linearly interpolated crossing times.

| Step (ms) | Dendrite RMSE (mV) | Soma RMSE (mV) | Dendrite lag (ms) | Soma lag (ms) |
| ---: | ---: | ---: | ---: | ---: |
| 0.025 | 0.8441 | 1.2083 | +0.0351 | +0.0364 |
| 0.0125 | 0.0638 | 0.0934 | -0.0025 | -0.0028 |

At 0.0125 ms both platforms reach the threshold on the same sampled step
at both recording sites. To reproduce that run, add
`--dt-ms 0.0125` to the command and use a separate output directory.
