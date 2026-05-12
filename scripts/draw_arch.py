import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(14, 9))
ax.set_xlim(0, 14)
ax.set_ylim(0, 9)
ax.axis("off")
fig.patch.set_facecolor("#0F1117")
ax.set_facecolor("#0F1117")

# ── palette ──────────────────────────────────────────────
C_BG     = "#0F1117"
C_BLOCK  = "#1E2130"
C_BORDER = "#2E3352"
C_BLUE   = "#2684FF"
C_LIME   = "#B6FF00"
C_PEACH  = "#FFC58D"
C_WHITE  = "#E8ECF4"
C_MUTED  = "#8B92A0"

def box(ax, x, y, w, h, label, sublabel="", color=C_BLOCK, border=C_BORDER, lc=C_WHITE):
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle="round,pad=0.08",
                          facecolor=color, edgecolor=border, linewidth=1.4, zorder=3)
    ax.add_patch(rect)
    if sublabel:
        ax.text(x + w/2, y + h*0.62, label,
                ha="center", va="center", fontsize=9, fontweight="bold",
                color=lc, zorder=4)
        ax.text(x + w/2, y + h*0.28, sublabel,
                ha="center", va="center", fontsize=7,
                color=C_MUTED, zorder=4)
    else:
        ax.text(x + w/2, y + h/2, label,
                ha="center", va="center", fontsize=9, fontweight="bold",
                color=lc, zorder=4)

def arrow(ax, x1, y1, x2, y2, color=C_BLUE):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=1.6, mutation_scale=14),
                zorder=5)

def hline(ax, x, y, w, color=C_BORDER):
    ax.plot([x, x+w], [y, y], color=color, lw=1, ls="--", zorder=2)

# ── 1. Web UI ─────────────────────────────────────────────
box(ax, 4.5, 7.7, 5, 0.9,
    "Web UI  ·  app/web/server.py",
    "браузер → HTTP → SSE stream",
    border=C_BLUE)

# ── 2. LangGraph Workflow ────────────────────────────────
box(ax, 1.0, 5.5, 12, 1.9,
    "", color="#161B2E", border=C_BLUE)
ax.text(7.0, 7.25, "LangGraph Workflow  ·  app/workflow/graph.py",
        ha="center", va="center", fontsize=9.5, fontweight="bold",
        color=C_BLUE, zorder=4)

# workflow steps inside
steps = [
    ("Supervisor", 1.25), ("Intent\nAnalyst", 2.7), ("Research\nDesigner", 4.15),
    ("Source\nScouts", 5.6), ("Coverage", 7.05), ("Extraction\nPlanner", 8.5),
    ("Det.\nTools", 9.95), ("Critic /\nNarrator", 11.4),
]
for label, xpos in steps:
    box(ax, xpos, 5.65, 1.25, 1.5, label,
        color="#252B45", border=C_BORDER, lc=C_WHITE)

# arrows between steps
for i in range(len(steps) - 1):
    arrow(ax, steps[i][1] + 1.25, 6.4, steps[i+1][1], 6.4)

# ── 3. Three bottom pillars ──────────────────────────────
# Retrieval
box(ax, 0.3, 2.8, 3.8, 2.3,
    "Retrieval", color="#151C2E", border=C_BORDER)
for i, (lbl, sub) in enumerate([
    ("BM25 Lexical", "hybrid_retrieval.py"),
    ("Qdrant Dense", "embedding_index.py"),
    ("Graph Store",  "graph_store.py"),
]):
    box(ax, 0.5, 2.95 + i*0.65, 3.4, 0.55, lbl, sub,
        color="#1A2235", border=C_BORDER, lc=C_WHITE)

# Data Layer
box(ax, 5.1, 2.8, 3.8, 2.3,
    "Data Layer", color="#151C2E", border=C_BORDER)
for i, (lbl, sub) in enumerate([
    ("FedStat",    "fedstat_adapter.py"),
    ("World Bank", "world_bank_adapter.py"),
    ("CKAN",       "ckan_adapter.py"),
]):
    box(ax, 5.3, 2.95 + i*0.65, 3.4, 0.55, lbl, sub,
        color="#1A2235", border=C_BORDER, lc=C_WHITE)

# LLM
box(ax, 9.9, 2.8, 3.8, 2.3,
    "LLM  ·  Qwen", color="#1A1F30", border=C_PEACH)
for i, (lbl, sub) in enumerate([
    ("Intent Analysis", "analyze_intent()"),
    ("Critic",          "run_methodology_critic()"),
    ("Narrator",        "build_workflow_response()"),
]):
    box(ax, 10.1, 2.95 + i*0.65, 3.4, 0.55, lbl, sub,
        color="#22293D", border=C_BORDER, lc=C_WHITE)

# pillar labels
for x, lbl, col in [(2.2, "Retrieval", C_BLUE), (7.0, "Data Layer", C_LIME), (11.8, "LLM / Qwen", C_PEACH)]:
    ax.text(x, 4.98, lbl, ha="center", va="center",
            fontsize=8.5, fontweight="bold", color=col, zorder=6)

# ── 4. Data Sources ──────────────────────────────────────
box(ax, 0.3, 0.5, 13.4, 1.9,
    "", color="#12171F", border=C_BORDER)
ax.text(7.0, 2.25, "Data Sources", ha="center", fontsize=9, fontweight="bold",
        color=C_MUTED, zorder=4)
for i, lbl in enumerate([
    "embedding-corpus.jsonl\n(36k source cards)",
    "Qdrant\ncollection",
    "WB parquet\nFP.CPI / NY.GDP …",
    "FedStat\nparquet files",
    "SQLite\nsource-catalog",
]):
    box(ax, 0.6 + i*2.65, 0.65, 2.4, 1.4, lbl,
        color="#181E28", border=C_BORDER, lc=C_MUTED)

# ── Arrows between layers ────────────────────────────────
# UI → Workflow
arrow(ax, 7.0, 7.7, 7.0, 7.4)
# Workflow → pillars
arrow(ax, 2.2, 5.5, 2.2, 5.1)
arrow(ax, 7.0, 5.5, 7.0, 5.1)
arrow(ax, 11.8, 5.5, 11.8, 5.1)
# Pillars → Data Sources
arrow(ax, 2.2, 2.8, 2.2, 2.4)
arrow(ax, 7.0, 2.8, 7.0, 2.4)

# ── Title ────────────────────────────────────────────────
ax.text(7.0, 8.75, "DataAgent — Architecture",
        ha="center", va="center", fontsize=14, fontweight="bold",
        color=C_WHITE, zorder=6)

plt.tight_layout(pad=0.3)
plt.savefig("architecture.png", dpi=180, bbox_inches="tight",
            facecolor=C_BG)
print("saved architecture.png")
