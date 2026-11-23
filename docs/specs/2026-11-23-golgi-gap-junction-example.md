# Golgi gap junction comparison example

Use two instances of the repository's full-compartment Masoli 2020 Golgi
model with the same morphology, regional channel parameters, initial voltage,
temperature, and fixed timestep in BrainCell and NEURON. Connect equivalent
basal dendritic midpoints at 1 nS. Inject a rectangular current pulse at the
first soma and record the voltage at the second soma and its junction site.

Use BrainCell's Network.connect_junction in the example. NEURON places one
ohmic half-junction at each endpoint and points it at the other voltage. Load
each NEURON morphology under its own Python owner so the two trees coexist.
Compile the existing Golgi NMODL files and the half-junction in a temporary
directory. Leave generated traces and figures in a caller-selected directory.

Check section and compartment correspondence, align both sample grids without
interpolation, write the time series and per-site residual metrics, and
generate the waveform comparison. Document the invocation and any solver or
discretization differences observed during validation.
