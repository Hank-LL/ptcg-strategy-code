#!/usr/bin/env python3
"""Strategy 部門レポート用の図を作る。

★ポケモンのカード画像・イラストは一切使わない(ライセンス違反は失格事由)。
  すべて自前で測った数値のグラフだけ。
出力: ~/ptcg/figures/fig1..fig5.png
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "figures")
os.makedirs(OUT, exist_ok=True)

INK = "#1f2430"
MUTE = "#8b93a7"
BLUE = "#3f6fb5"
SAND = "#d98b4a"
GRID = "#e3e6ec"

plt.rcParams.update({
    "figure.dpi": 160,
    "savefig.dpi": 160,
    "font.size": 11,
    "axes.edgecolor": MUTE,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def finish(fig, ax, title, sub, path, ylab=None):
    ax.set_title(title, loc="left", fontsize=13, fontweight="bold", pad=30)
    ax.text(0, 1.015, sub, transform=ax.transAxes, fontsize=9.5, color=MUTE, va="bottom")
    if ylab:
        ax.set_ylabel(ylab)
    ax.yaxis.grid(True, color=GRID, lw=1)
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, path), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", path)


# --- Fig 0: 主題。汎用的なうまさは3点、デッキ固有プランは+15〜40pp ----
# ★レポートの中心主張そのもの。左=一般的なアプローチのラダーレート、
#   右=同一デッキ・同一相手でデッキ専用レイヤーだけを足したときの差。
#   「general competence は3点、plan は数十pp」を1枚で見せる。
fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.9),
                         gridspec_kw={"width_ratios": [1, 1.25]})
a0, a1 = axes

lab0 = ["Random\nsample agent", "Generic heuristic\n(plays any 60 cards)", "MaskablePPO\n10M steps"]
val0 = [599.4, 602.4, 510.0]
a0.bar(lab0, val0, color=[MUTE, SAND, BLUE], width=0.55)
# RLはラダーで470〜550を往復したので幅で示す(点ではない)
a0.errorbar([2], [510], yerr=[[40], [40]], fmt="none", ecolor=INK, lw=1.6, capsize=7)
for i, v in enumerate(val0):
    a0.text(i, v + 6, "%.1f" % v if i < 2 else "470-550", ha="center",
            fontweight="bold", fontsize=10)
a0.set_ylim(450, 650)
a0.set_ylabel("Ladder rating")
a0.set_title("General play skill", loc="left", fontsize=11.5, fontweight="bold")
# 599.4 の高さに水平線を引いて「汎用はランダムとほぼ同じ高さ」を見せる
a0.plot([-0.4, 1.4], [599.4, 599.4], color=INK, lw=1.2, ls=":", zorder=4)
a0.annotate("only +3.0\nover random", xy=(1.0, 612), xytext=(1.45, 640),
            fontsize=10, fontweight="bold", ha="center", linespacing=1.3,
            arrowprops=dict(arrowstyle="->", color=INK, lw=1.2))
a0.tick_params(axis="x", labelsize=8.5)

lab1 = ["Alakazam", "Grimmsnarl ex", "Ogerpon ex", "Wanaider", "Crustle"]
val1 = [40.0, 30.0, 29.7, 21.0, 15.0]
a1.barh(lab1[::-1], val1[::-1], color=SAND, height=0.58)
for i, v in enumerate(val1[::-1]):
    a1.text(v + 0.8, i, "+%.1fpp" % v, va="center", fontweight="bold", fontsize=10)
a1.set_xlim(0, 54)
a1.set_xlabel("Win rate gained by the deck-specific layer (pp)")
a1.set_title("A plan for one deck", loc="left", fontsize=11.5, fontweight="bold")
a1.xaxis.grid(True, color=GRID, lw=1)
a1.yaxis.grid(False)

for a in axes:
    a.set_axisbelow(True)
    a.spines["top"].set_visible(False)
    a.spines["right"].set_visible(False)
a0.yaxis.grid(True, color=GRID, lw=1)
fig.suptitle("General competence is worth three points. The plan is worth tens.",
             x=0.02, ha="left", fontsize=13, fontweight="bold")
fig.text(0.02, 0.895, "Left: ladder rating. Right: same 60 cards and same opponents, "
         "adding only a layer that knows the deck's plan.", fontsize=9.5, color=MUTE)
fig.tight_layout(rect=[0, 0, 1, 0.87])
fig.savefig(os.path.join(OUT, "fig0_value_of_a_plan.png"), bbox_inches="tight",
            facecolor="white")
plt.close(fig)
print("wrote fig0_value_of_a_plan.png")

# --- Fig 1: 相手の操縦者を変えるだけで勝率が49pp動く ------------------
fig, ax = plt.subplots(figsize=(7.2, 3.9))
lab = ["Our agent\nvs generic pilot", "Our agent\nvs real agent", "Generic heuristic\nvs real agent"]
val = [87, 38, 20]
col = [SAND, BLUE, BLUE]
b = ax.bar(lab, val, color=col, width=0.55)
for r, v in zip(b, val):
    ax.text(r.get_x() + r.get_width() / 2, v + 2, "%d%%" % v, ha="center",
            fontweight="bold", fontsize=12)
# 1本目と2本目の天面を結ぶ補助線 + 縦の両矢印(棒やラベルに重ねない)
for y in (87, 38):
    ax.plot([-0.35, 0.62], [y, y], color=MUTE, lw=0.9, ls=":", zorder=1)
ax.annotate("", xy=(0.58, 87), xytext=(0.58, 38),
            arrowprops=dict(arrowstyle="<->", color=INK, lw=1.5))
ax.text(0.66, 62.5, "49pp\nfrom the pilot\nalone", fontsize=10.5,
        fontweight="bold", va="center", linespacing=1.4)
ax.set_ylim(0, 100)
finish(fig, ax, "Opponent skill, not opponent deck, decides your score",
       "Same Alakazam deck in all three. 100 games each.", "fig1_pilot_strength.png",
       "Win rate (%)")

# --- Fig 2: 同一設定でも10.3pp振れる --------------------------------
fig, ax = plt.subplots(figsize=(7.2, 3.6))
runs = [48.3, 42.7, 50.0, 42.3, 45.7, 39.7]
x = range(1, 7)
mean = sum(runs) / len(runs)
ax.axhspan(mean - 2.9, mean + 2.9, color=BLUE, alpha=0.12,
           label="binomial expectation (±1 SE)")
ax.axhline(mean, color=MUTE, lw=1.2, ls="--")
ax.plot(x, runs, "o", color=SAND, ms=11, zorder=3)
for i, v in zip(x, runs):
    ax.text(i, v + 1.2, "%.1f" % v, ha="center", fontsize=9.5)
ax.annotate("", xy=(0.62, 39.7), xytext=(0.62, 50.0),
            arrowprops=dict(arrowstyle="<->", color=INK, lw=1.4))
ax.text(0.72, 44.8, "10.3pp\nspread", fontsize=10, fontweight="bold",
        va="center", linespacing=1.4)
ax.set_xlim(0.3, 6.6)
ax.set_ylim(38, 53)
ax.set_xticks(list(x))
ax.set_xlabel("repetition (identical configuration, 300 games each)")
ax.legend(frameon=False, fontsize=9, loc="lower left")
finish(fig, ax, "A single 300-game result carries no information",
       "Six runs of the same configuration. SD is 1.4x the binomial expectation.",
       "fig2_variance.png", "Win rate (%)")

# --- Fig 3: ローカルは苦手マッチほど逆に出る ------------------------
fig, ax = plt.subplots(figsize=(7.6, 4.0))
m = ["Mega Lucario ex", "Dragapult ex", "Archaludon ex", "Mirror"]
ladder = [35, 17, 50, 50]
local = [94, 100, 100, 25]
xs = range(len(m))
w = 0.38
ax.bar([i - w / 2 for i in xs], ladder, w, color=BLUE, label="Real ladder (90 games)")
ax.bar([i + w / 2 for i in xs], local, w, color=SAND, label="Local arena")
for i, (a, c) in enumerate(zip(ladder, local)):
    ax.text(i - w / 2, a + 2, "%d%%" % a, ha="center", fontsize=9.5)
    ax.text(i + w / 2, c + 2, "%d%%" % c, ha="center", fontsize=9.5)
ax.set_xticks(list(xs))
ax.set_xticklabels(m)
ax.set_ylim(0, 110)
ax.legend(frameon=False, fontsize=9.5, ncol=2, loc="upper center",
          bbox_to_anchor=(0.5, -0.12))
finish(fig, ax, "The matchups you 'win' locally are the ones you actually lose",
       "Only decks with a dedicated pilot are played competently offline.",
       "fig3_ladder_vs_local.png", "Win rate (%)")

# --- Fig 4: 帯でメタが別物 ------------------------------------------
fig, ax = plt.subplots(figsize=(7.6, 4.0))
arch = ["Grimmsnarl ex", "Mega Kangaskhan", "Wanaider", "Alakazam",
        "Mega Lucario ex", "Archaludon ex"]
# 正規化して「その帯での出現率」にする
low_raw = [9, 0, 6, 10, 17, 14]
top_raw = [71, 25, 13, 12, 1, 0]
low = [100.0 * v / sum(low_raw) for v in low_raw]
top = [100.0 * v / sum(top_raw) for v in top_raw]
xs = range(len(arch))
w = 0.38
ax.bar([i - w / 2 for i in xs], low, w, color=BLUE, label="~660 rating (our games)")
ax.bar([i + w / 2 for i in xs], top, w, color=SAND, label="1100-1180 rating (top teams)")
ax.set_xticks(list(xs))
ax.set_xticklabels(arch, rotation=18, ha="right", fontsize=9.5)
ax.set_ylim(0, 76)
ax.legend(frameon=False, fontsize=9.5, loc="upper right")
ax.annotate("absent at the top —\nour two worst matchups", xy=(4.9, 33),
            xytext=(4.4, 50), fontsize=9.5, color=INK, ha="center",
            arrowprops=dict(arrowstyle="->", color=MUTE, lw=1.1))
finish(fig, ax, "The metagame is stratified: you cannot learn it from top replays",
       "Share of games by archetype, within each rating band.",
       "fig4_stratification.png", "Share of games (%)")

# --- Fig 5: 勝率では見えない、機序では見える ------------------------
fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.8))
a0, a1 = axes
a0.bar(["off", "on"], [92.5, 93.5], yerr=[1.1, 0.8], capsize=6,
       color=[MUTE, BLUE], width=0.5)
a0.set_ylim(85, 100)
a0.set_title("Win rate", loc="left", fontsize=11, fontweight="bold")
a0.text(0.5, 97.5, "+1.0 ± 1.0 pp\nnot detected", ha="center", fontsize=10, color=MUTE)
a1.bar(["off", "on"], [51.3, 40.0], color=[MUTE, SAND], width=0.5)
for i, v in enumerate([51.3, 40.0]):
    a1.text(i, v + 1.2, "%.1f%%" % v, ha="center", fontweight="bold")
a1.set_ylim(0, 62)
a1.set_title("Promoted attacker unable to attack", loc="left", fontsize=11,
             fontweight="bold")
for a in axes:
    a.yaxis.grid(True, color=GRID, lw=1)
    a.set_axisbelow(True)
    a.spines["top"].set_visible(False)
    a.spines["right"].set_visible(False)
fig.suptitle("Measure the mechanism, not the outcome", x=0.02, ha="left",
             fontsize=13, fontweight="bold")
fig.text(0.02, 0.90, "Same change, same 600 paired games. Only one panel can resolve it.",
         fontsize=9.5, color=MUTE)
fig.tight_layout(rect=[0, 0, 1, 0.88])
fig.savefig(os.path.join(OUT, "fig5_mechanism.png"), bbox_inches="tight",
            facecolor="white")
plt.close(fig)
print("wrote fig5_mechanism.png")

# --- Fig 6: 全96提出の実測。傾向は上向きだが1点1点は当てにならない ----
# ★Kaggle API で取得した自分の全提出(meta/ladder/submissions.csv)。
#   当初は「節目だけを結んだ折れ線」を描いたが、**同一ファイルの再提出でも
#   80〜290点ずれる**ことが分かったので、生データ全点に描き直した。
import csv
import datetime as dt

SUB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "meta", "ladder", "submissions.csv")
rows = []
for r in csv.DictReader(open(SUB)):
    try:
        rows.append((dt.datetime.strptime(r["date"][:10], "%Y-%m-%d"),
                     float(r["publicScore"]), r["fileName"]))
    except (ValueError, KeyError):
        continue
rows.sort()

fig, ax = plt.subplots(figsize=(9.2, 4.4))
ax.plot([d for d, _, _ in rows], [v for _, v, _ in rows], "o", color=BLUE,
        ms=7, alpha=0.55, zorder=3)

# 7提出ごとの移動中央値で傾向を示す(平均だと外れ値に引っ張られる)
import statistics
k = 7
med_x, med_y = [], []
for i in range(len(rows) - k + 1):
    w = rows[i:i + k]
    med_x.append(w[k // 2][0])
    med_y.append(statistics.median([v for _, v, _ in w]))
ax.plot(med_x, med_y, "-", color=INK, lw=2.4, zorder=4,
        label="rolling median (7 submissions)")

# 同一ファイルを59秒差で再提出した2点 = 純粋なノイズの実例
pair_day = dt.datetime(2026, 8, 3)
ax.plot([pair_day, pair_day], [596.8, 517.3], "-", color=SAND, lw=2.6, zorder=5)
ax.plot([pair_day, pair_day], [596.8, 517.3], "o", color=SAND, ms=9, zorder=6)
ax.annotate("same file, resubmitted\n59 seconds apart: 79 points",
            xy=(pair_day, 557), xytext=(dt.datetime(2026, 7, 19), 338),
            fontsize=9.5, color=INK,
            arrowprops=dict(arrowstyle="->", color=SAND, lw=1.4))

ax.axhline(932.4, color=MUTE, lw=1.1, ls="--")
ax.text(dt.datetime(2026, 8, 13), 948, "final: 932.4  (300th / 6,807)",
        fontsize=9.5, ha="right", fontweight="bold")
ax.set_ylim(320, 1000)
import matplotlib.dates as mdates
ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=0))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax.legend(frameon=False, fontsize=9.5, loc="upper left")
fig.autofmt_xdate(rotation=0, ha="center")
finish(fig, ax, "The trend is real. No individual point is.",
       "All 96 of our ladder submissions (Kaggle API). Median spread on resubmitting "
       "an unchanged agent: 159 points.",
       "fig6_progression.png", "Ladder rating")
