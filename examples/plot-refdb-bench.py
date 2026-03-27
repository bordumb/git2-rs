"""
Plot refdb compress benchmark results.

Usage:
    cargo run --release --example bench-refdb-compress -- --csv results.csv
    python examples/plot-refdb-bench.py results.csv
"""

import sys
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "#fafafa",
    "axes.facecolor": "#fafafa",
})

# Deuteranopia-safe palette
LOOSE = "#e69f00"    # orange
COMPRESS = "#0072b2" # blue
GC = "#cc79a7"       # muted pink


def fmt_x(x, _):
    if x >= 1000:
        return f"{int(x / 1000)}k"
    return f"{int(x)}"


def main():
    if len(sys.argv) < 2:
        print("Usage: python plot-refdb-bench.py <results.csv> [output.png]")
        sys.exit(1)

    csv_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "refdb-bench.png"

    df = pd.read_csv(csv_path)

    # Detect CSV format: 3-way (loose/compress/gc) or 2-way (before/after)
    three_way = "lookup_loose_us" in df.columns

    if three_way:
        plot_three_way(df, out_path)
    else:
        plot_two_way(df, out_path)


def plot_three_way(df, out_path):
    fig, axes = plt.subplots(2, 2, figsize=(15, 11), gridspec_kw={"hspace": 0.35, "wspace": 0.3})
    fig.suptitle(
        "Ref operation performance: Loose vs refdb_compress() vs git gc",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )

    # --- Panel 1: refname_to_id latency ---
    ax = axes[0, 0]
    ax.plot(df["refs"], df["lookup_loose_us"], "o-", color=LOOSE, label="Loose refs", linewidth=2.2, markersize=6, zorder=3)
    ax.plot(df["refs"], df["lookup_compress_us"], "s-", color=COMPRESS, label="refdb_compress()", linewidth=2.2, markersize=6, zorder=3)
    ax.plot(df["refs"], df["lookup_gc_us"], "^-", color=GC, label="git gc", linewidth=2.2, markersize=6, zorder=3)
    ax.fill_between(df["refs"], df["lookup_compress_us"], df["lookup_loose_us"], color=LOOSE, alpha=0.08)
    ax.set_xlabel("Number of refs")
    ax.set_ylabel("Avg latency (µs)")
    ax.set_title("refname_to_id()", fontsize=13, pad=10)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:.0f}" if y >= 1 else f"{y:.1f}"))
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(fmt_x))
    ax.legend(frameon=True, facecolor="white", edgecolor="#ddd", fontsize=10)

    # --- Panel 2: references_glob latency ---
    ax = axes[0, 1]
    ax.plot(df["refs"], df["glob_loose_us"] / 1000, "o-", color=LOOSE, label="Loose refs", linewidth=2.2, markersize=6, zorder=3)
    ax.plot(df["refs"], df["glob_compress_us"] / 1000, "s-", color=COMPRESS, label="refdb_compress()", linewidth=2.2, markersize=6, zorder=3)
    ax.plot(df["refs"], df["glob_gc_us"] / 1000, "^-", color=GC, label="git gc", linewidth=2.2, markersize=6, zorder=3)
    ax.fill_between(df["refs"], df["glob_compress_us"] / 1000, df["glob_loose_us"] / 1000, color=LOOSE, alpha=0.08)
    ax.set_xlabel("Number of refs")
    ax.set_ylabel("Avg latency (ms)")
    ax.set_title("references_glob()", fontsize=13, pad=10)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(fmt_x))
    ax.legend(frameon=True, facecolor="white", edgecolor="#ddd", fontsize=10)

    # --- Panel 3: Speedup bars (compress vs gc, relative to loose) ---
    ax = axes[1, 0]
    x = np.arange(len(df))
    width = 0.2

    lookup_compress_speedup = df["lookup_loose_us"] / df["lookup_compress_us"]
    lookup_gc_speedup = df["lookup_loose_us"] / df["lookup_gc_us"]
    glob_compress_speedup = df["glob_loose_us"] / df["glob_compress_us"]
    glob_gc_speedup = df["glob_loose_us"] / df["glob_gc_us"]

    bars1 = ax.bar(x - width * 1.5, lookup_compress_speedup, width, color=COMPRESS, alpha=0.75, label="lookup · compress", zorder=3)
    bars2 = ax.bar(x - width * 0.5, lookup_gc_speedup, width, color=GC, alpha=0.75, label="lookup · gc", zorder=3)
    bars3 = ax.bar(x + width * 0.5, glob_compress_speedup, width, color=COMPRESS, alpha=0.45, label="glob · compress", zorder=3, hatch="//")
    bars4 = ax.bar(x + width * 1.5, glob_gc_speedup, width, color=GC, alpha=0.45, label="glob · gc", zorder=3, hatch="//")

    for bar in bars3:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h * 1.05, f"{h:.0f}x", ha="center", va="bottom", fontsize=7, color=COMPRESS, fontweight="bold")
    for bar in bars4:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h * 1.05, f"{h:.0f}x", ha="center", va="bottom", fontsize=7, color=GC, fontweight="bold")

    ax.set_xlabel("Number of refs")
    ax.set_ylabel("Speedup vs loose (×, log scale)")
    ax.set_title("Speedup over loose refs", fontsize=13, pad=10)
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([fmt_x(r, None) for r in df["refs"]])
    ax.axhline(y=1, color="#999", linestyle="--", linewidth=0.8, zorder=1)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:.0f}x"))
    ax.legend(frameon=True, facecolor="white", edgecolor="#ddd", fontsize=9, ncol=2)

    # --- Panel 4: Operation time (compress vs gc) ---
    ax = axes[1, 1]
    x = np.arange(len(df))
    width = 0.35

    ax.bar(x - width / 2, df["compress_ms"], width, color=COMPRESS, alpha=0.75, label="refdb_compress()", zorder=3)
    ax.bar(x + width / 2, df["gc_ms"], width, color=GC, alpha=0.75, label="git gc", zorder=3)

    ax.set_xlabel("Number of refs")
    ax.set_ylabel("Time (ms)")
    ax.set_title("Cost of packing operation", fontsize=13, pad=10)
    ax.set_xticks(x)
    ax.set_xticklabels([fmt_x(r, None) for r in df["refs"]])
    ax.legend(frameon=True, facecolor="white", edgecolor="#ddd", fontsize=10)

    fig.savefig(out_path, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved to {out_path}")


def plot_two_way(df, out_path):
    """Fallback for old 2-column CSV format."""
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.5), gridspec_kw={"wspace": 0.35})
    fig.suptitle(
        "Impact of refdb_compress() on ref operations",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )

    ax = axes[0]
    ax.plot(df["refs"], df["lookup_before_us"], "o-", color=LOOSE, label="Loose refs", linewidth=2.2, markersize=6, zorder=3)
    ax.plot(df["refs"], df["lookup_after_us"], "s-", color=COMPRESS, label="Packed refs", linewidth=2.2, markersize=6, zorder=3)
    ax.fill_between(df["refs"], df["lookup_after_us"], df["lookup_before_us"], color=LOOSE, alpha=0.08)
    ax.set_xlabel("Number of refs")
    ax.set_ylabel("Avg latency (µs)")
    ax.set_title("refname_to_id()", fontsize=13, pad=10)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:.0f}" if y >= 1 else f"{y:.1f}"))
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(fmt_x))
    ax.legend(frameon=True, facecolor="white", edgecolor="#ddd", fontsize=10)

    ax = axes[1]
    ax.plot(df["refs"], df["glob_before_us"] / 1000, "o-", color=LOOSE, label="Loose refs", linewidth=2.2, markersize=6, zorder=3)
    ax.plot(df["refs"], df["glob_after_us"] / 1000, "s-", color=COMPRESS, label="Packed refs", linewidth=2.2, markersize=6, zorder=3)
    ax.fill_between(df["refs"], df["glob_before_us"] / 1000, df["glob_after_us"] / 1000, color=LOOSE, alpha=0.08)
    ax.set_xlabel("Number of refs")
    ax.set_ylabel("Avg latency (ms)")
    ax.set_title("references_glob()", fontsize=13, pad=10)
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(fmt_x))
    ax.legend(frameon=True, facecolor="white", edgecolor="#ddd", fontsize=10)

    ax = axes[2]
    x = np.arange(len(df))
    width = 0.35
    lookup_speedup = df["lookup_before_us"] / df["lookup_after_us"]
    glob_speedup = df["glob_before_us"] / df["glob_after_us"]
    bars1 = ax.bar(x - width / 2, lookup_speedup, width, color=GC, alpha=0.75, label="refname_to_id", zorder=3)
    bars2 = ax.bar(x + width / 2, glob_speedup, width, color=COMPRESS, alpha=0.75, label="references_glob", zorder=3)
    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.3, f"{h:.1f}x", ha="center", va="bottom", fontsize=8, color=GC, fontweight="bold")
    for bar in bars2:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + 0.3, f"{h:.0f}x", ha="center", va="bottom", fontsize=8, color=COMPRESS, fontweight="bold")
    ax.set_xlabel("Number of refs")
    ax.set_ylabel("Speedup (×, log scale)")
    ax.set_title("Speedup after compress", fontsize=13, pad=10)
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([fmt_x(r, None) for r in df["refs"]])
    ax.axhline(y=1, color="#999", linestyle="--", linewidth=0.8, zorder=1)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: f"{y:.0f}x"))
    ax.legend(frameon=True, facecolor="white", edgecolor="#ddd", fontsize=10)

    fig.savefig(out_path, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved to {out_path}")


if __name__ == "__main__":
    main()
