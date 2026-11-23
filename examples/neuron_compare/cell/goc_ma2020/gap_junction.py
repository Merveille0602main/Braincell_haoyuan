# Copyright 2026 BrainX Ecosystem Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""Compare somatically driven Golgi gap-junction transfer in BrainCell and NEURON."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import brainunit as u
import numpy as np

import braincell as bc
from braincell.filter import at
from examples.neuron_compare.cell._nrnmech import nrnmech_path

from .goc_braincell import GoC as BrainCellGoC
from .parameters import DEFAULT_MORPH_PATH, load_goc20_params


RECORDINGS = {"dendrite": "Receiver gap-junction dendrite", "soma": "Receiver soma"}
SPIKE_THRESHOLD_MV = -20.0


@dataclass(frozen=True)
class Protocol:
    dt_ms: float = 0.025
    stop_ms: float = 35.0
    delay_ms: float = 5.0
    pulse_ms: float = 20.0
    amplitude_pa: float = 20.0
    conductance_ns: float = 1.0
    temperature_c: float = 30.0
    initial_mv: float = -65.0
    dendrite_index: int = 0
    position: float = 0.5


def _compile_neuron(build_dir: Path) -> Path:
    executable = Path(sys.executable).with_name("nrnivmodl")
    if not executable.is_file():
        located = shutil.which("nrnivmodl")
        if located is None:
            raise RuntimeError("Install NEURON with nrnivmodl to run this comparison.")
        executable = Path(located)
    mod_root = DEFAULT_MORPH_PATH.parent.parent
    sources = [
        *sorted((mod_root / "channel").glob("*.mod")),
        mod_root / "ion" / "CdpStC_MA20_GoC.mod",
        Path(__file__).with_name("goc_gap_half.mod"),
    ]
    result = subprocess.run(
        [str(executable), *(str(source.resolve()) for source in sources)],
        cwd=build_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    library = nrnmech_path(build_dir / "x86_64")
    if result.returncode or not library.is_file():
        raise RuntimeError(f"NEURON mechanism compilation failed:\n{result.stdout}")
    return library


def _check_geometry(braincell_goc, neuron_goc) -> dict:
    max_length_error = 0.0
    for kind, sections in (
        ("soma", neuron_goc.soma_sections),
        ("dendrite", neuron_goc.dend_sections),
        ("axon", neuron_goc.axon_sections),
    ):
        branches = [
            (branch_id, branch)
            for branch_id, branch in enumerate(braincell_goc.morph.branches)
            if branch.type == kind
        ]
        for (branch_id, branch), section in zip(branches, sections, strict=True):
            difference = abs(float(branch.length.to_decimal(u.um)) - section.L)
            max_length_error = max(max_length_error, difference)
            if difference > 1e-3:
                raise ValueError(f"Mismatched morphology at {branch.name} and {section.name()}.")
            if len(braincell_goc.cell.cv_tree.branch_to_cv_ids[branch_id]) != section.nseg:
                raise ValueError(f"Mismatched compartment count at {branch.name} and {section.name()}.")
    return {
        "sections_per_cell": len(neuron_goc.sections),
        "compartments_per_cell": braincell_goc.cell.n_cv,
        "max_section_length_difference_um": max_length_error,
    }


def _run_braincell(goc_pair, protocol: Protocol):
    donor, receiver = goc_pair
    soma_location = at("soma", protocol.position)
    dendrites = [branch for branch in receiver.morph.branches if branch.type == "dendrite"]
    junction_branch = dendrites[protocol.dendrite_index].name
    junction_location = at(junction_branch, protocol.position)
    donor.cell.place(
        soma_location,
        bc.mech.CurrentClamp(
            delay=protocol.delay_ms * u.ms,
            durations=protocol.pulse_ms * u.ms,
            amplitudes=protocol.amplitude_pa * u.pA,
        ),
    )
    receiver.cell.loc(junction_location).record("dendrite", bc.observe.state("v"))
    receiver.cell.loc(soma_location).record("soma", bc.observe.state("v"))
    network = bc.Network("golgi_gap_junction")
    network.add_population("donor", donor.cell)
    network.add_population("receiver", receiver.cell)
    network.connect_junction(
        "basal_dendrites",
        endpoint=bc.mech.JunctionEndpoint(donor.cell, junction_location),
        junction=bc.mech.Junction(
            partner=bc.mech.JunctionEndpoint(receiver.cell, junction_location),
            params={"g": protocol.conductance_ns * u.nS},
        ),
    )
    result = network.run(dt=protocol.dt_ms * u.ms, duration=protocol.stop_ms * u.ms)
    blocks = result.samples["receiver"]
    time = np.asarray(blocks["soma"].time.to_decimal(u.ms))
    traces = {
        name: np.asarray(blocks[name].values.to_decimal(u.mV)).reshape(len(time))
        for name in RECORDINGS
    }
    return time, traces, junction_branch


def _run_neuron(goc_pair, protocol: Protocol):
    from neuron import h

    donor, receiver = goc_pair
    donor_dend = donor.dend_sections[protocol.dendrite_index](protocol.position)
    receiver_dend = receiver.dend_sections[protocol.dendrite_index](protocol.position)
    donor_gap, receiver_gap = h.GoCGapHalf(donor_dend), h.GoCGapHalf(receiver_dend)
    for gap, peer in ((donor_gap, receiver_dend), (receiver_gap, donor_dend)):
        gap.g = protocol.conductance_ns / 1000.0
        h.setpointer(peer._ref_v, "vpeer", gap)

    clamp = h.IClamp(donor.root_soma(protocol.position))
    clamp.delay = protocol.delay_ms
    clamp.dur = protocol.pulse_ms
    clamp.amp = protocol.amplitude_pa / 1000.0
    time = h.Vector().record(h._ref_t)
    recorded = {
        "dendrite": h.Vector().record(receiver_dend._ref_v),
        "soma": h.Vector().record(receiver.root_soma(protocol.position)._ref_v),
    }
    h.celsius = protocol.temperature_c
    h.CVode().active(0)
    h.secondorder = 0
    h.dt = protocol.dt_ms
    h.finitialize(protocol.initial_mv)
    h.continuerun(protocol.stop_ms)
    return np.array(time), {name: np.array(values) for name, values in recorded.items()}


def _save_comparison(output: Path, protocol: Protocol, time, braincell, neuron, metadata) -> dict:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    columns = [time]
    column_names = ["time_ms"]
    metrics = {}
    figure, axes = plt.subplots(2, 2, figsize=(11, 5.6), sharex=True, layout="constrained")
    stimulus_end = protocol.delay_ms + protocol.pulse_ms
    for row, (name, label) in enumerate(RECORDINGS.items()):
        voltage_bc, voltage_nrn = braincell[name], neuron[name]
        error = voltage_bc - voltage_nrn
        if not np.isfinite(error).all():
            raise ValueError(f"Non-finite comparison at {label}.")
        columns.extend((voltage_bc, voltage_nrn, error))
        column_names.extend((f"{name}_braincell_mV", f"{name}_neuron_mV", f"{name}_difference_mV"))
        crossings = {}
        for model, voltage in (("braincell", voltage_bc), ("neuron", voltage_nrn)):
            upward = (voltage[:-1] < SPIKE_THRESHOLD_MV) & (voltage[1:] >= SPIKE_THRESHOLD_MV)
            indices = np.flatnonzero(upward)
            previous, following = voltage[indices], voltage[indices + 1]
            fraction = (SPIKE_THRESHOLD_MV - previous) / (following - previous)
            crossings[f"{model}_upcrossings_ms"] = time[indices + 1].tolist()
            crossings[f"{model}_interpolated_upcrossings_ms"] = (
                time[indices] + fraction * (time[indices + 1] - time[indices])
            ).tolist()
        braincell_crossings = crossings["braincell_interpolated_upcrossings_ms"]
        neuron_crossings = crossings["neuron_interpolated_upcrossings_ms"]
        first_upcrossing_lag = (
            braincell_crossings[0] - neuron_crossings[0]
            if braincell_crossings and neuron_crossings
            else None
        )
        before_clamp = time < protocol.delay_ms
        max_error_index = int(np.argmax(np.abs(error)))
        metrics[name] = {
            "rmse_mV": float(np.sqrt(np.mean(error**2))),
            "pre_clamp_rmse_mV": float(np.sqrt(np.mean(error[before_clamp] ** 2))),
            "max_abs_difference_mV": float(abs(error[max_error_index])),
            "max_error_time_ms": float(time[max_error_index]),
            "first_upcrossing_lag_ms": first_upcrossing_lag,
            **crossings,
        }
        for axis in axes[row]:
            axis.axvspan(protocol.delay_ms, stimulus_end, color="#f3dfab", alpha=0.48)
            axis.grid(alpha=0.22)
        axes[row, 0].plot(time, voltage_nrn, color="#163e5d", label="NEURON", linewidth=1.8)
        axes[row, 0].plot(time, voltage_bc, "--", color="#b54b35", label="BrainCell", linewidth=1.5)
        axes[row, 0].set_title(label, loc="left")
        axes[row, 0].set_ylabel("Membrane voltage (mV)")
        axes[row, 1].plot(time, error, color="#62518c", linewidth=1.5)
        axes[row, 1].axhline(0.0, color="0.5", linewidth=0.6)
        axes[row, 1].set_title("BrainCell minus NEURON", loc="left")
        axes[row, 1].set_ylabel("Difference (mV)")
    axes[0, 0].legend(loc="best")
    for axis in axes[-1]:
        axis.set_xlabel("Time (ms)")
    figure.suptitle(f"Two Golgi cells coupled by a {protocol.conductance_ns:g} nS gap junction")

    summary = {
        "protocol": asdict(protocol),
        **metadata,
        "samples": len(time),
        "upcrossing_threshold_mV": SPIKE_THRESHOLD_MV,
        "voltage_comparison": metrics,
    }
    output.mkdir(parents=True, exist_ok=True)
    np.savetxt(output / "voltages.csv", np.column_stack(columns), delimiter=",",
               header=",".join(column_names), comments="", fmt="%.9g")
    figure.savefig(output / "voltage-comparison.png", dpi=170)
    plt.close(figure)
    (output / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Directory for traces, metrics, and the PNG.")
    parser.add_argument("--dt-ms", type=float, default=Protocol.dt_ms, help="Shared fixed integration step.")
    args = parser.parse_args()
    protocol = Protocol(dt_ms=args.dt_ms)
    boundaries = np.array([protocol.stop_ms, protocol.delay_ms, protocol.pulse_ms])
    if not np.isfinite(protocol.dt_ms) or protocol.dt_ms <= 0:
        parser.error("--dt-ms must be finite and positive.")
    step_indices = boundaries / protocol.dt_ms
    if not np.allclose(step_indices, np.rint(step_indices), rtol=0.0, atol=1e-8):
        parser.error("--dt-ms must divide the run duration, clamp onset, and clamp duration.")

    from neuron import __version__ as neuron_version
    from .goc_neuron import GoC as NeuronGoC

    parameters = load_goc20_params()
    braincell_pair = [
        BrainCellGoC(
            params=parameters, pop_size=(1,), temperature_celsius=protocol.temperature_c,
            v_init_mV=protocol.initial_mv,
        ).build()
        for _ in range(2)
    ]
    with TemporaryDirectory(prefix="goc-gap-neuron-") as temporary:
        library = _compile_neuron(Path(temporary))
        neuron_pair = [NeuronGoC(params=parameters, nrnmech_path=library).build() for _ in range(2)]
        geometry = _check_geometry(braincell_pair[0], neuron_pair[0])
        if neuron_pair[0].root_soma == neuron_pair[1].root_soma:
            raise RuntimeError("NEURON morphology import did not preserve two independent cells.")
        neuron_time, neuron_traces = _run_neuron(neuron_pair, protocol)
    time, braincell_traces, branch = _run_braincell(braincell_pair, protocol)

    # BrainCell samples the beginning of each step. NEURON also saves the final boundary.
    np.testing.assert_allclose(neuron_time[:len(time)], time, rtol=0.0, atol=1e-5)
    aligned = {name: values[:len(time)] for name, values in neuron_traces.items()}
    metadata = {
        "braincell_version": bc.__version__,
        "braincell_voltage_method": "coupled_backward_euler",
        "neuron_version": neuron_version,
        "junction_branch": branch,
        "geometry": geometry,
    }
    summary = _save_comparison(args.output, protocol, time, braincell_traces, aligned, metadata)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
