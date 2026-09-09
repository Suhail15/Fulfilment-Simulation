"""Paired scenario comparisons with independent replication confidence intervals."""
import argparse
import csv
from dataclasses import replace
import json
from pathlib import Path
import platform
import statistics
from scipy.stats import t
from .model import Config, simulate


def interval(values):
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return {"mean": statistics.mean(values) if values else None, "low": None, "high": None, "n": len(values)}
    mean = statistics.mean(values)
    half = float(t.ppf(.975, len(values)-1))*statistics.stdev(values)/len(values)**.5
    return {"mean": mean, "low": mean-half, "high": mean+half, "n": len(values)}


def experiment(replications=20, first_seed=2025, base=Config()):
    if replications < 2:
        raise ValueError("At least two replications are required")
    scenarios = {"baseline": base, "extra_picker": replace(base, pickers=base.pickers+1),
        "extra_packer": replace(base, packers=base.packers+1),
        "faster_courier": replace(base, courier_interval=base.courier_interval/2),
        "fifo_picking": replace(base, express_priority=False)}
    runs = {name: [simulate(cfg, seed) for seed in range(first_seed, first_seed+replications)]
            for name, cfg in scenarios.items()}
    metrics = list(runs["baseline"][0]["metrics"])
    summary = {name: {metric: interval([r["metrics"][metric] for r in group]) for metric in metrics}
               for name, group in runs.items()}
    differences = {name: {metric: interval([a["metrics"][metric]-b["metrics"][metric]
        for a,b in zip(group,runs["baseline"]) if a["metrics"][metric] is not None and b["metrics"][metric] is not None])
        for metric in metrics} for name,group in runs.items() if name != "baseline"}
    return {"metadata": {"replications": replications, "first_seed": first_seed, "python": platform.python_version(),
            "design": "Same per-order random inputs across scenarios; independent seeds across replications.",
            "units": "Abstract time units; synthetic arrivals and service times."},
            "configs": {name: group[0]["config"] for name,group in runs.items()},
            "summary": summary, "paired_differences_from_baseline": differences,
            "runs": [{"scenario": name, "seed": r["seed"], **r["metrics"]} for name,group in runs.items() for r in group]}


def save_report(report, destination):
    destination.mkdir(parents=True, exist_ok=True)
    (destination/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    with (destination/"replications.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(report["runs"][0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(report["runs"])
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "svg.fonttype": "none", "svg.hashsalt": "fulfilment"})
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    labels = list(report["summary"])
    for ax, metric, title in zip(axes, ["mean_total_time", "express_wait_over_6"],
            ["Arrival to courier collection", "Express orders waiting > 6 units"]):
        rows = [report["summary"][n][metric] for n in labels]
        means = [r["mean"] for r in rows]
        ax.barh([n.replace("_", " ").title() for n in labels], means,
            xerr=[r["high"]-r["mean"] for r in rows], capsize=4,
            color=["#284c49", "#538578", "#77a38e", "#c39245", "#82939e"])
        ax.set_title(title, loc="left", fontweight="bold", pad=18)
        ax.invert_yaxis()
        ax.set_xlabel("Time units" if metric=="mean_total_time" else "Fraction of express orders")
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(f"Fulfilment scenarios · {report['metadata']['replications']} independent replications\n95% t intervals for scenario means · synthetic model", fontsize=12)
    fig.savefig(destination/"comparison.svg", metadata={"Date": None})
    svg = destination/"comparison.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines())+"\n")
    plt.close(fig)
    lines = ["# Experiment results", "", "Synthetic model; abstract time units. Error bars are 95% t intervals across independent replication means.", "",
             "| Scenario | Mean arrival-to-collection | 95% interval | Paired change vs baseline |", "|---|---:|---|---|"]
    for name, metrics in report["summary"].items():
        v = metrics["mean_total_time"]
        d = report["paired_differences_from_baseline"].get(name, {}).get("mean_total_time")
        change = f"{d['mean']:+.2f} [{d['low']:+.2f}, {d['high']:+.2f}]" if d else "—"
        lines.append(f"| {name} | {v['mean']:.2f} | [{v['low']:.2f}, {v['high']:.2f}] | {change} |")
    lines += ["", "Intervals are per comparison, without multiple-comparison correction. They quantify simulation sampling uncertainty, not uncertainty about real operations.", "",
        "See report.json for all metrics and configuration, and replications.csv for every measured run."]
    (destination/"README.md").write_text("\n".join(lines)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replications", type=int, default=20)
    parser.add_argument("--seed", type=int, default=2025)
    parser.add_argument("--output", type=Path, default=Path("results"))
    args = parser.parse_args()
    report = experiment(args.replications, args.seed)
    save_report(report, args.output)
    print((args.output/"README.md").read_text())


if __name__ == "__main__":
    main()
