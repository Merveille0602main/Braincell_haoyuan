#!/usr/bin/env python3
"""Run all channel_no_conc configs and export large-error reports.

This is a script version of the batch workflow notebook. It recursively scans
``configs/**/*.json``, runs each config over all of its templates, then writes:

- ``template_observable_summary.csv``: one row per config/template/observable.
- ``case_observable_metrics.csv``: one row per config/template/case/observable.
- ``large_errors_template_summary.csv``: template-level rows with errors >= threshold.
- ``large_errors_case_rows.csv``: case-level rows with errors >= threshold.
- ``large_error_targets.csv``: unique config/template pairs worth drilling into.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any

import pandas as pd


os.environ.setdefault("JAX_PLATFORMS", "cpu")


def _find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / "braincell" / "__init__.py").exists() and (
            candidate / "examples" / "neuron_compare" / "channel_no_conc"
        ).exists():
            return candidate
    raise RuntimeError("Could not find the braincell repository root.")


REPO_ROOT = _find_repo_root(Path(__file__))
CHANNEL_NO_CONC_ROOT = REPO_ROOT / "examples" / "neuron_compare" / "channel_no_conc"
WORKFLOWS_ROOT = CHANNEL_NO_CONC_ROOT / "workflows"

for candidate in (REPO_ROOT, WORKFLOWS_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import brainstate  # noqa: E402
import workflow_api  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-root",
        type=Path,
        default=CHANNEL_NO_CONC_ROOT / "configs",
        help="Directory to scan recursively for config JSON files.",
    )
    parser.add_argument(
        "--summary-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to results/batch_runs/YYMMDD_HHMMSS.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=1e-3,
        help="Absolute-error threshold. Default: 1e-3.",
    )
    parser.set_defaults(plot=False)
    parser.add_argument("--plot", dest="plot", action="store_true", help="Generate per-case plots.")
    parser.add_argument("--no-plot", dest="plot", action="store_false", help="Disable plots.")
    parser.add_argument(
        "--no-progress",
        dest="progress",
        action="store_false",
        default=True,
        help="Disable tqdm/simple case progress output.",
    )
    return parser


def _config_records(config_root: Path) -> list[dict[str, Any]]:
    config_paths = sorted(config_root.expanduser().resolve().rglob("*.json"))
    if not config_paths:
        raise FileNotFoundError(f"No config JSON files found under {config_root!s}.")

    records: list[dict[str, Any]] = []
    for config_path in config_paths:
        info = workflow_api.load_config_workflow_inputs(config_path)
        records.append(
            {
                "config_path": info["config_path"],
                "config_name": info["config_name"],
                "run_id": info["config_name"],
                "mod_dir": info["mod_dir"],
                "template_paths": list(info["template_paths"]),
                "template_names": list(info["template_names"]),
                "n_templates": info["n_templates"],
                "default_out_dir": info["default_out_dir"],
            }
        )
    return records


def _read_template_summaries(config_run_infos: list[dict[str, Any]]) -> pd.DataFrame:
    frames = []
    for run_info in config_run_infos:
        path = Path(run_info["observable_summary_path"])
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df["config_out_dir"] = str(Path(run_info["out_dir"]).resolve())
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _read_case_metrics(config_run_infos: list[dict[str, Any]]) -> pd.DataFrame:
    frames = []
    for run_info in config_run_infos:
        for template_run in run_info.get("template_runs", []):
            template_out_dir = Path(str(template_run["out_dir"])).expanduser().resolve()
            metrics_path = template_out_dir / "case_metrics.csv"
            if not metrics_path.exists():
                continue
            df = pd.read_csv(metrics_path)
            df.insert(0, "config_name", str(template_run["config_name"]))
            df.insert(1, "template_name", str(template_run["template_name"]))
            df["run_id"] = str(template_run["run_id"])
            df["config_path"] = str(Path(str(template_run["config_path"])).expanduser().resolve())
            df["template_path"] = str(Path(str(template_run["template_path"])).expanduser().resolve())
            df["mod_dir"] = str(Path(str(template_run["mod_dir"])).expanduser().resolve())
            df["template_out_dir"] = str(template_out_dir)
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _filter_large(df: pd.DataFrame, metric_cols: list[str], threshold: float) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    result = df.copy()
    for col in metric_cols:
        result[col] = pd.to_numeric(result[col], errors="coerce")
    mask = result[metric_cols].ge(threshold).any(axis=1)
    result = result.loc[mask].copy()
    result["trigger_metrics"] = result.apply(
        lambda row: ";".join(col for col in metric_cols if pd.notna(row[col]) and row[col] >= threshold),
        axis=1,
    )
    return result


def _target_rows(large_template_df: pd.DataFrame, large_case_df: pd.DataFrame) -> pd.DataFrame:
    pieces = []
    for source, df in (("template", large_template_df), ("case", large_case_df)):
        if df.empty:
            continue
        cols = ["config_name", "template_name", "template_path"]
        present = [col for col in cols if col in df.columns]
        piece = df[present].drop_duplicates().copy()
        piece["source"] = source
        pieces.append(piece)
    if not pieces:
        return pd.DataFrame(columns=["config_name", "template_name", "template_path", "source"])
    return (
        pd.concat(pieces, ignore_index=True)
        .drop_duplicates(["config_name", "template_name", "source"])
        .sort_values(["config_name", "template_name", "source"])
        .reset_index(drop=True)
    )


def main() -> int:
    args = build_parser().parse_args()
    brainstate.environ.set(precision=64)

    config_root = args.config_root.expanduser().resolve()
    batch_run_id = workflow_api.make_batch_run_id()
    summary_dir = workflow_api.default_batch_run_output_dir(
        batch_run_id=batch_run_id,
        summary_dir=args.summary_dir,
    )
    configs_out_dir = summary_dir / "configs"
    configs_out_dir.mkdir(parents=True, exist_ok=True)

    records = _config_records(config_root)
    print(f"batch_run_id: {batch_run_id}", flush=True)
    print(f"summary_dir: {summary_dir}", flush=True)
    print(f"n_configs: {len(records)}", flush=True)

    config_run_infos = []
    for index, record in enumerate(records, start=1):
        config_name = str(record["config_name"])
        print(f"\n[{index}/{len(records)}] config: {config_name}", flush=True)
        run_info = workflow_api.run_notebook_config_workflow(
            config_path=record["config_path"],
            out_dir=configs_out_dir / config_name,
            plot=args.plot,
            expand_only=False,
            raise_on_failure=False,
            progress=args.progress,
        )
        config_run_infos.append(run_info)
        print(
            f"[{index}/{len(records)}] done: status={run_info['status']} "
            f"success={run_info['n_success_cases']} failed={run_info['n_failed_cases']}",
            flush=True,
        )

    batch_summary = workflow_api.write_batch_summary_artifacts(
        config_dir=config_root,
        summary_dir=summary_dir,
        batch_run_id=batch_run_id,
        config_records=records,
        config_run_infos=config_run_infos,
        plot_cases=args.plot,
    )

    template_df = _read_template_summaries(config_run_infos)
    case_df = _read_case_metrics(config_run_infos)

    template_summary_path = summary_dir / "template_observable_summary.csv"
    case_metrics_path = summary_dir / "case_observable_metrics.csv"
    template_df.to_csv(template_summary_path, index=False)
    case_df.to_csv(case_metrics_path, index=False)

    large_template_df = _filter_large(
        template_df,
        ["mae_mean", "rmse_mean", "max_abs_max"],
        args.threshold,
    ).sort_values(["max_abs_max", "rmse_mean", "mae_mean"], ascending=False, na_position="last")
    large_case_df = _filter_large(
        case_df,
        ["mae", "rmse", "max_abs"],
        args.threshold,
    ).sort_values(["max_abs", "rmse", "mae"], ascending=False, na_position="last")
    targets_df = _target_rows(large_template_df, large_case_df)

    large_template_path = summary_dir / "large_errors_template_summary.csv"
    large_case_path = summary_dir / "large_errors_case_rows.csv"
    targets_path = summary_dir / "large_error_targets.csv"
    large_template_df.to_csv(large_template_path, index=False)
    large_case_df.to_csv(large_case_path, index=False)
    targets_df.to_csv(targets_path, index=False)

    print("\nWrote:")
    print(f"  batch_manifest: {batch_summary['manifest_path']}")
    print(f"  batch_failures: {batch_summary['batch_failures_path']}")
    print(f"  template_summary: {template_summary_path}")
    print(f"  case_metrics: {case_metrics_path}")
    print(f"  large_template_errors: {large_template_path} ({len(large_template_df)} rows)")
    print(f"  large_case_errors: {large_case_path} ({len(large_case_df)} rows)")
    print(f"  large_error_targets: {targets_path} ({len(targets_df)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
