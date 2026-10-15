
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import os
import json
import re
import re
import shutil
import subprocess
from pathlib  import Path
from dataclasses import dataclass

# third-party modules

import numpy             as np
import pandas            as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from jinja2 import Template

# local modules
from epsimple import GreenRetrofitModel, Zone
from .auxiliary  import find_weatherdata
from .postprocess import (
    현장조사체크리스트,
    어린이집체크리스트,
    보건소체크리스트,
)
from .core import rebexcel_to_idf_and_grm

# settings
PLOTFONTSIZE = 11
PLOTFONTFAMILY = 'Malgun Gothic'
plt.rc('font', family=PLOTFONTFAMILY, size=PLOTFONTSIZE)
plt.rc('mathtext', fontset='custom', rm=PLOTFONTFAMILY,
       it=f'{PLOTFONTFAMILY}:italic', bf=f'{PLOTFONTFAMILY}:bold')
plt.rc('axes.formatter', useoffset=False)
plt.rc('axes', titlesize=PLOTFONTSIZE, labelsize=PLOTFONTSIZE, unicode_minus=False)
plt.rc('xtick', labelsize=PLOTFONTSIZE)
plt.rc('ytick', labelsize=PLOTFONTSIZE)
plt.rc('legend', fontsize=PLOTFONTSIZE)


# ---------------------------------------------------------------------------- #
#                                   VARIABLES                                  #
# ---------------------------------------------------------------------------- #

TEMPLATEPATH = Path(__file__).parent / "report_template.tex"
BUILD_DIR    = Path(__file__).parents[2] / "dist" / "reb-report"
FIG_DIR      = BUILD_DIR / "figures"

os.makedirs(BUILD_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

# ---------------------------------------------------------------------------- #
#                                   METADATA                                   #
# ---------------------------------------------------------------------------- #

@dataclass
class MetaData:
    name: str
    area: str
    addr: str
    date: str

# ---------------------------------------------------------------------------- #
#                                 SUBFUNCTIONS                                 #
# ---------------------------------------------------------------------------- #

MONTH_LBLS = ([f"{m}월" for m in range(1, 13)])
DEFAULT_COLORS = ("tab:blue", "tab:orange")  # epw1, epw2 색상
# PALETTE = ['#FF0305', '#363AFF', '#FF8820', '#FFFE03', '#98C1EF', '#A4C761']
PALETTE = ['#e15759', '#4e79a7', '#F28e3b', '#b07aa1', '#FFC61E', '#00CD6C', '#A1B1BA', '#A6761D']

# ---------------------------------------------------------------------------- #
#                               FIGURE FUNCTIONS                               #
# ---------------------------------------------------------------------------- #

def _scenario_bar_style(et_key: str, scenario_idx: int) -> dict:
    """
    monthly stacked bars와 동일한 scenario 표현:
    0: GR 이전       -> 원색
    1: GR 이후       -> 연한색 + hatch
    2: 운영특성 반영 -> 연한색
    """
    color = DEFAULT_COLORS_BEFORE[et_key]

    return {
        "ec": None,
        "fc": [color, color + "40", color + "40"][scenario_idx],
        "hatch": [None, "//////", None][scenario_idx],
        "lw": 0.8,
    }


def draw_3step_bargraph(
    title: str,
    values: list[list[int | float]],
    index: list[str],
    *,
    ylabel: str = "Value",
    ax: plt.Axes,
    scenario_style: bool = False,
    show_legend: bool = True,
) -> np.ndarray:

    values_arr = np.asarray(values, dtype=float)

    num_bars = values_arr.shape[0]
    x_positions = np.arange(num_bars)

    width = 0.7
    num_subbars = values_arr.shape[1]
    energy_types = ENERGY_TYPES[:num_subbars]
    subbar_width = width / num_subbars

    for n, pos in enumerate(x_positions):
        for et_idx, (et_key, et_label) in enumerate(energy_types):
            color = DEFAULT_COLORS_BEFORE[et_key]
            subbar_pos = pos - subbar_width * (num_subbars / 2 - et_idx - 0.5)

            if scenario_style:
                style = _scenario_bar_style(et_key, n)
                ax.bar(
                    subbar_pos,
                    values_arr[n, et_idx],
                    width=subbar_width,
                    ec=style["ec"],
                    fc=style["fc"],
                    hatch=style["hatch"],
                    lw=style["lw"],
                    zorder=3,
                )
            else:
                # 기존 draw_mainfigures fig2 유지
                ax.bar(
                    subbar_pos,
                    values_arr[n, et_idx],
                    width=subbar_width,
                    ec=None,
                    fc=color + "90",
                    lw=1,
                    zorder=3,
                )

    ax.set_xticks(x_positions)
    ax.set_xticklabels(index, fontsize=10)

    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=11, y=1.08, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    ax.set_xlim(-0.5, num_bars - 0.5)

    max_value = np.nanmax(values_arr) if values_arr.size > 0 else 0
    ax.set_ylim(0, max(1, max_value * 1.12))

    if show_legend:
        ax.legend(
            fontsize=8,
            handles=[
                Patch(ec=None, fc=DEFAULT_COLORS_BEFORE[et_key] + "90")
                for et_key, _ in energy_types
            ],
            labels=[et_label for _, et_label in energy_types],
            loc="upper center",
            ncol=4,
            bbox_to_anchor=(0.5, -0.15),
        )

    return values_arr

GRAPH_ORDER = [
    ("heating", "난방"),
    ("cooling", "냉방"),
    ("lighting", "조명"),
    ("circulation", "팬,펌프,전열"),
    ("hotwater", "급탕"),
    ("generators", "발전량"),
]
ENERGY_TYPES = [
    ("ELECTRICITY", "전기"),
    ("NATURALGAS", "가스"),
    ("OIL", "유류"),
    ("DISTRICTHEATING", "지역난방"),
]
SCENARIO_PREFIXES = ("GR이전", "GR이후", "N년차")

DEFAULT_COLORS_BEFORE = {
    "NATURALGAS": PALETTE[0],
    "ELECTRICITY": PALETTE[1],
    "OIL": PALETTE[2],
    "DISTRICTHEATING": PALETTE[3],
}

def _energy_values(category_data: dict, et_key: str) -> np.ndarray:
    return np.asarray(category_data.get(et_key, [0] * 12), dtype=float)

def _sum_grr_monthly_totals(
    result: dict,
    datatype: str,
) -> np.ndarray:
    totals = np.zeros(12)

    for cat_key, _ in GRAPH_ORDER:
        sign = -1 if cat_key == "generators" else 1
        category_data = result[datatype].get(cat_key, {})
        for et_key, _ in ENERGY_TYPES:
            totals += sign * _energy_values(category_data, et_key)

    return totals

def _sum_grr_annual_total(
    result: dict,
    datatype: str,
) -> float:
    return float(_sum_grr_monthly_totals(result, datatype).sum())

def _sum_grr_energy_total(
    result: dict,
    datatype: str,
    et_key: str,
) -> float:
    total = 0.0

    for cat_key, _ in GRAPH_ORDER:
        sign = -1 if cat_key == "generators" else 1
        total += sign * _energy_values(
            result[datatype].get(cat_key, {}),
            et_key,
        ).sum()

    return float(total)

def _is_empty_value(value) -> bool:
    if value is None:
        return True

    isna = pd.isna(value)
    if isinstance(isna, (bool, np.bool_)):
        return bool(isna)

    return False

def _value_is_lpg(value) -> bool:
    if _is_empty_value(value):
        return False

    normalized = str(value).upper().replace(" ", "")
    return any(token in normalized for token in ("LPG", "액화석유가스"))

def _find_heating_energy_source(masterdict: dict, prefix: str):
    exact_suffixes = (
        "_난방1_열원",
        "_난방1_에너지원",
        "_난방1_ET",
        "_보일러_열원",
        "_보일러_에너지원",
        "_보일러_ET",
        "_난방_열원",
        "_난방_에너지원",
        "_난방_ET",
        "_열원",
        "_에너지원",
        "_연료종류",
        "_ET",
    )

    for suffix in exact_suffixes:
        key = f"{prefix}{suffix}"
        if key in masterdict and not _is_empty_value(masterdict[key]):
            return masterdict[key]

    candidates = []
    for key, value in masterdict.items():
        if not isinstance(key, str) or not key.startswith(f"{prefix}_"):
            continue
        if _is_empty_value(value):
            continue
        if not any(token in key for token in ("열원", "에너지원", "연료종류", "_ET")):
            continue
        if key == f"{prefix}_ET" or any(token in key for token in ("난방", "보일러")):
            score = 0
            if "난방1" in key:
                score -= 4
            if "보일러" in key:
                score -= 2
            if key.endswith("_ET"):
                score -= 1
            score += len(key)
            candidates.append((score, key, value))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]

def parse_lpg_usage(masterdict: dict) -> dict[str, bool]:
    return {
        prefix: _value_is_lpg(_find_heating_energy_source(masterdict, prefix))
        for prefix in SCENARIO_PREFIXES
    }

def _scenario_bar_style(et_key: str, scenario_idx: int) -> dict:
    """
    monthly stacked bars와 동일한 scenario 표현:
    0: GR 이전          -> 원색
    1: GR 이후          -> 연한색 + hatch
    2: 운영특성 반영    -> 연한색
    """
    color = DEFAULT_COLORS_BEFORE[et_key]

    fcs = [color, color + "40", color + "40"]
    hatches = [None, "//////", None]

    return {
        "ec": None,
        "fc": fcs[scenario_idx],
        "hatch": hatches[scenario_idx],
        "lw": 0.8,
    }


def _make_energy_scenario_legend_handles() -> tuple[list[Patch], list[str]]:
    """
    monthly stacked bars의 legend와 동일한 handles/labels 생성
    """
    handles = []
    labels = []

    for et_key, et_label in ENERGY_TYPES:
        for l_idx, label in enumerate(["GR 이전", "GR 이후", "운영특성 반영"]):
            style = _scenario_bar_style(et_key, l_idx)

            handles.append(
                Patch(
                    ec=style["ec"],
                    lw=style["lw"],
                    fc=style["fc"],
                    hatch=style["hatch"],
                )
            )
            labels.append(f"{et_label} {label}")

    return handles, labels


def _draw_value_table(
    ax: plt.Axes,
    values: np.ndarray,
    *,
    row_labels: list[str],
    col_labels: list[str],
    digits: int = 1,
    fontsize: float = 8.2,
    row_label_width: float = 0.15,
) -> None:
    """
    summary figure용 범용 표.
    monthly_stacked_bars의 표 스타일과 맞추되, 열/행 개수가 달라도 사용 가능.
    """
    ax.axis("off")

    values = np.asarray(values, dtype=float)

    cell_text = [
        [f"{v:.{digits}f}" for v in row]
        for row in values
    ]

    ncols = values.shape[1]
    col_width = 1.0 / max(ncols, 1)

    table = ax.table(
        cellText=cell_text,
        rowLabels=row_labels,
        colLabels=col_labels,
        cellLoc="center",
        rowLoc="center",
        colLoc="center",
        loc="center",
        bbox=[0.00, 0.00, 1.00, 1.00],  # summary table에서는 높이 전체 사용
        colWidths=[col_width] * ncols,
    )

    table.auto_set_font_size(False)
    table.set_fontsize(fontsize)
    table.scale(1.0, 1.45)  # monthly stacked table보다 작아 보이는 문제 완화

    for (r, c), cell in table.get_celld().items():
        cell.set_linewidth(0.35)
        cell.PAD = 0.035
        cell.get_text().set_clip_on(False)

        if r == 0:
            cell.set_facecolor("#F2F2F2")
            cell.set_text_props(weight="bold")

        if c == -1:
            cell.set_width(row_label_width)
            cell.set_facecolor("#F7F7F7")
            cell.set_text_props(weight="bold")

        if c >= 0:
            cell.set_width(col_width)

def _draw_monthly_value_table(
    ax: plt.Axes,
    values_3x12: np.ndarray,
    digits: int = 1,
    fontsize: float = 8.2,
) -> None:
    """
    values_3x12[0, :] = GR 이전
    values_3x12[1, :] = GR 이후
    values_3x12[2, :] = 운영특성 반영
    """
    ax.axis("off")

    row_labels = ["이전", "이후", "운영"]
    month_labels = [f"{m}월" for m in range(1, 13)]

    cell_text = [
        [f"{v:.{digits}f}" for v in row]
        for row in values_3x12
    ]

    # month 열 폭은 약간 줄이고, row label(인덱스) 쪽은 별도 폭 확보
    table = ax.table(
        cellText=cell_text,
        rowLabels=row_labels,
        colLabels=month_labels,
        cellLoc="center",
        rowLoc="center",
        colLoc="center",
        loc="center",
        bbox=[0.00, 0.06, 1.00, 0.88],
        colWidths=[0.070] * 12,
    )

    table.auto_set_font_size(False)
    table.set_fontsize(fontsize)
    table.scale(1.0, 1.32)   # 표 세로 높이 확대

    for (r, c), cell in table.get_celld().items():
        cell.set_linewidth(0.35)
        cell.PAD = 0.025
        cell.get_text().set_clip_on(False)

        if r == 0:
            cell.set_facecolor("#F2F2F2")
            cell.set_text_props(weight="bold")

        if c == -1:
            cell.set_width(0.11)
            cell.set_facecolor("#F7F7F7")
            cell.set_text_props(weight="bold")

        if c >= 0:
            cell.set_width(0.072)

def _draw_monthly_stacked_bar(
    category_key: str,
    category_label: str,
    grr_before: dict,
    grr_after: dict,
    grr_afterN: dict,
    datatype: str = "source_uses",
    ax: plt.Axes | None = None
) -> np.ndarray:
    """월별 stacked bar"""

    if ax is None:
        _, ax = plt.subplots()

    month_labels = np.arange(1, 13)
    bottom_before = np.zeros(12)
    bottom_after  = np.zeros(12)
    bottom_afterN = np.zeros(12)

    for et_key, et_label in ENERGY_TYPES:
        bvals = np.asarray(
            _energy_values(
                grr_before[datatype].get(category_key, {}),
                et_key,
            ),
            dtype=float
        )
        avals = np.asarray(
            _energy_values(
                grr_after[datatype].get(category_key, {}),
                et_key,
            ),
            dtype=float
        )
        nvals = np.asarray(
            _energy_values(
                grr_afterN[datatype].get(category_key, {}),
                et_key,
            ),
            dtype=float
        )

        bvals = np.nan_to_num(bvals, nan=0.0)
        avals = np.nan_to_num(avals, nan=0.0)
        nvals = np.nan_to_num(nvals, nan=0.0)

        color = DEFAULT_COLORS_BEFORE[et_key]

        ax.bar(
            month_labels - 0.25, bvals, width=0.25, bottom=bottom_before,
            label=f"{et_label} (전)", fc=color
        )
        ax.bar(
            month_labels - 0.25, bvals, width=0.25, bottom=bottom_before,
            ec=None, fc="none", zorder=5, lw=1.0
        )

        ax.bar(
            month_labels, avals, width=0.25, bottom=bottom_after,
            label=f"{et_label} (후)",
            ec=None, fc=color + "40", hatch="//////", lw=0.8
        )
        ax.bar(
            month_labels, avals, width=0.25, bottom=bottom_after,
            ec=None, fc="none", zorder=5, lw=1.0
        )

        ax.bar(
            month_labels + 0.25, nvals, width=0.25, bottom=bottom_afterN,
            label=f"{et_label} (N)",
            ec=None, fc=color + "40", zorder=5, lw=1.0
        )

        bottom_before += bvals
        bottom_after += avals
        bottom_afterN += nvals

    monthly_totals = np.vstack([
        bottom_before,
        bottom_after,
        bottom_afterN,
    ])

    ax.set_xticks(month_labels)
    ax.set_xticklabels([f"{m}월" for m in month_labels], fontsize=9)
    ax.tick_params(axis="y", labelsize=9)

    ax.set_ylabel("(kWh/$\\mathrm{m^2\\cdot}$월)", fontsize=11)
    ax.set_title(category_label, pad=10, fontsize=13, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.margins(x=0.03)

    ymax = monthly_totals.max() if monthly_totals.size > 0 else 0
    ax.set_ylim(0, max(5, ymax * 1.12))

    return monthly_totals


def _draw_monthly_stacked_bars(
    fig: plt.Figure,
    grr_before: dict,
    grr_after: dict,
    grr_afterN: dict,
    datatype: str = "source_uses",
) -> None:

    fig.clear()
    fig.set_constrained_layout(False)

    # 기존보다 세로는 조금 줄이고, 가로는 조금 넓힘
    fig.set_size_inches(11.6, 12)

    # 각 블록 = [그래프, 표, spacer]
    # 그래프 높이는 줄이고 표는 키움
    gs = fig.add_gridspec(
        nrows=9,
        ncols=2,
        height_ratios=[
            1.75, 1.08, 0.25,
            1.75, 1.08, 0.25,
            1.75, 1.08, 0.25,
        ],
        left=0.065,
        right=0.985,
        top=0.925,
        bottom=0.105,
        wspace=0.18,
        hspace=0.00,
    )

    for cat_idx, (cat_key, cat_label) in enumerate(GRAPH_ORDER):
        block = cat_idx // 2
        col = cat_idx % 2

        graph_row = block * 3
        table_row = graph_row + 1

        ax_graph = fig.add_subplot(gs[graph_row, col])
        ax_table = fig.add_subplot(gs[table_row, col])

        values_3x12 = _draw_monthly_stacked_bar(
            cat_key,
            cat_label,
            grr_before,
            grr_after,
            grr_afterN,
            datatype,
            ax=ax_graph,
        )

        _draw_monthly_value_table(
            ax_table,
            values_3x12,
            digits=1,      # 소수점 한자리
            fontsize=8.2,  # 8pt 이상
        )

    handles = []
    labels = []

    for et_key, et_label in ENERGY_TYPES:
        for l_idx, label in enumerate(["GR 이전", "GR 이후", "운영특성 반영"]):
            color = DEFAULT_COLORS_BEFORE[et_key]
            handles.append(
                Patch(
                    ec=None,
                    lw=0.8,
                    fc=[color, color + "40", color + "40"][l_idx],
                    hatch=[None, "//////", None][l_idx],
                )
            )
            labels.append(f"{et_label} {label}")

    fig.legend(
        handles=handles,
        labels=labels,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.020),
        ncol=4,
        fontsize=9.5,
        frameon=True,
        borderaxespad=0.15,
        handletextpad=0.45,
        columnspacing=1.2,
        labelspacing=0.30,
    )


def _draw_annual_by_purpose(
    ax: plt.Axes,
    grr_before: dict,
    grr_after: dict,
    grr_afterN: dict,
    datatype="source_uses",
) -> np.ndarray:
    """연간 용도별 stacked bar"""

    x = np.arange(len(GRAPH_ORDER))
    width = 0.25

    scenario_totals = np.zeros((3, len(GRAPH_ORDER)), dtype=float)

    ymax = 0.0

    for idx, (label, dataset) in enumerate([
        ("GR 이전", grr_before),
        ("GR 이후", grr_after),
        ("운영특성 반영", grr_afterN),
    ]):
        bottoms = np.zeros(len(GRAPH_ORDER))

        for et_key, et_label in ENERGY_TYPES:
            vals = np.asarray([
                _energy_values(dataset[datatype].get(cat_key, {}), et_key).sum()
                for cat_key, _ in GRAPH_ORDER
            ], dtype=float)

            color = DEFAULT_COLORS_BEFORE[et_key]

            ax.bar(
                x + (idx - 1) * width,
                vals,
                width=width,
                bottom=bottoms,
                label=f"{et_label} {label}",
                ec=None,
                lw=0.8,
                fc=[color, color + "40", color + "40"][idx],
                hatch=[None, "//////", None][idx],
                zorder=3,
            )

            ax.bar(
                x + (idx - 1) * width,
                vals,
                width=width,
                bottom=bottoms,
                ec=None,
                fc="none",
                zorder=5,
                lw=1.0,
            )

            bottoms += vals

        scenario_totals[idx, :] = bottoms
        ymax = max(ymax, bottoms.max())

    ax.set_ylim(0, max(5, ymax * 1.15))

    ax.set_xticks(x)
    ax.set_xticklabels([lbl.replace("/", "/\n") for _, lbl in GRAPH_ORDER])
    ax.set_ylabel("연간 합계 (kWh/$\\mathrm{m^2\\cdot}$연)")
    ax.set_title("연간 용도별 1차에너지소요량", fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    return scenario_totals

def _draw_total_monthly_bar(
    ax: plt.Axes,
    grr_before: dict,
    grr_after: dict,
    grr_afterN: dict,
    datatype="source_uses",
) -> None:
    """HTML의 bar-total (월별 총합 비교 - 막대그래프)"""
    months = np.arange(1, 13)
    
    # 막대 너비 설정
    width = 0.25 

    before_vals = _sum_grr_monthly_totals(grr_before, datatype)
    after_vals = _sum_grr_monthly_totals(grr_after, datatype)
    afterN_vals = _sum_grr_monthly_totals(grr_afterN, datatype)

    # x축 위치를 조정하여 막대를 그립니다 (왼쪽, 가운데, 오른쪽)
    # zorder=3을 주어 그리드 위로 막대가 올라오게 합니다.
    ax.bar(months - width, before_vals, width=width, color=PALETTE[0], label="GR 이전", zorder=3)
    ax.bar(months, after_vals, width=width, color=PALETTE[1], label="GR 이후", zorder=3)
    
    # 운영특성 반영은 기존 스타일(점선/빈 원)을 반영하여 빗금(hatch)이나 테두리 스타일로 표현
    ax.bar(months + width, afterN_vals, width=width, 
           color='white', edgecolor=PALETTE[2], hatch='////', linewidth=1.0, 
           label="운영특성 반영", zorder=3)

    ax.set_ylim(bottom=0)
    ax.set_xticks(months)
    ax.set_xticklabels([f"{m}월" for m in months])
    ax.set_ylabel("월별 합계 (kWh/$\\mathrm{m^2\\cdot}$월)")
    ax.set_title("월별 1차에너지소요량", y=1.1)
    
    # 그리드가 막대 뒤로 가도록 설정
    ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=0) 
    ax.legend(fontsize=8, loc="upper center", ncol=3, bbox_to_anchor=(0.5, -0.15))


def draw_mainfigures(
    grr_before: dict,
    grr_after: dict,
    grr_afterN: dict,
):
    """
    matplotlib로 두 개의 Figure(메인 그래프, 요약 그래프)를 생성하여 반환
    Returns:
        fig1 (Figure): 용도별, 월별 사용량 비교 (상단 큰 그래프)
        fig2 (Figure): 연간 용도별 비교 및 월별 총합 라인 (하단 요약 그래프)
    """
    
    # --- Figure 1: 월별 스택 바 (메인) ---
    # 기존 비율(3:1.2)을 고려하여 세로 길이를 적절히 배분 (예: 높이 8)
    fig1 = plt.figure(figsize=(9, 8), constrained_layout=True)
    
    # 기존 helper 함수가 Figure 객체를 받아 subplot을 추가한다고 가정
    _draw_monthly_stacked_bars(fig1, grr_before, grr_after, grr_afterN)

    fig1.suptitle('월간 단위면적당 1차에너지소요량', fontsize=16, fontweight='bold')


    # --- Figure 2: 요약 (하단 2개 그래프) ---
    # 높이를 작게 설정 (예: 높이 4)
    fig2 = plt.figure(figsize=(9, 3), constrained_layout=True)
    
    # 1행 2열로 서브플롯 생성
    summary_ax = fig2.subplots(1, 1)

    # (3) 월별 총합 라인 그래프
    draw_3step_bargraph(
        "면적당 1차에너지소요량 (연간)",
        [
            [
                _sum_grr_energy_total(result, "source_uses", et_key)
                for et_key, _ in ENERGY_TYPES
            ]
            for result in [grr_before, grr_after, grr_afterN]
        ],
        ["GR이전","GR이후","운영특성 반영"],
        ylabel = "1차에너지 (kWh/$\\mathrm{m^2\\cdot}$년)",
        ax = summary_ax
    )
    
    return fig1, fig2

def draw_page3_summaryfigures(
    grr_before: dict,
    grr_after: dict,
    grr_afterN: dict,
) -> plt.Figure:

    fig = plt.figure(figsize=(11.6, 4.9), constrained_layout=False)

    gs = fig.add_gridspec(
        nrows=2,
        ncols=2,
        height_ratios=[2.45, 1.35],  # 표 row를 monthly stacked 쪽에 가깝게 키움
        left=0.070,
        right=0.985,
        top=0.82,
        bottom=0.075,  # legend 제거했으므로 아래 여백 축소
        wspace=0.22,
        hspace=0.035,  # 그래프와 표는 붙여 보이게
    )

    ax_energy = fig.add_subplot(gs[0, 0])
    ax_co2 = fig.add_subplot(gs[0, 1])

    ax_energy_table = fig.add_subplot(gs[1, 0])
    ax_co2_table = fig.add_subplot(gs[1, 1])

    scenario_labels = ["GR이전", "GR이후", "운영특성 반영"]

    # ------------------------------------------------------------------
    # 1) 좌측: 연간 용도별 1차에너지
    #    그래프 x축 = 용도
    #    표 열 = 용도
    # ------------------------------------------------------------------
    energy_values_3x6 = _draw_annual_by_purpose(
        ax_energy,
        grr_before,
        grr_after,
        grr_afterN,
        "source_uses",
    )

    _draw_value_table(
        ax_energy_table,
        energy_values_3x6,
        row_labels=["이전", "이후", "운영"],
        col_labels=[lbl.replace("/", "/\n") for _, lbl in GRAPH_ORDER],
        digits=1,
        fontsize=8.2,
        row_label_width=0.14,
    )

    # ------------------------------------------------------------------
    # 2) 우측: 연간 온실가스 배출량
    #    그래프 x축 = GR이전 / GR이후 / 운영특성 반영
    #    따라서 표 열도 동일하게 scenario 3개로 구성
    # ------------------------------------------------------------------
    co2_values_3x4 = [
        [
            _sum_grr_energy_total(result, "co2", et_key)
            for et_key, _ in ENERGY_TYPES
        ]
        for result in [grr_before, grr_after, grr_afterN]
    ]

    co2_values_3x4 = draw_3step_bargraph(
        "면적당 온실가스 배출량 (연간)",
        co2_values_3x4,
        scenario_labels,
        ylabel=r"$\mathrm{CO_2,eq}$ (kg/$\mathrm{m^2\cdot}$년)",
        ax=ax_co2,
        scenario_style=True,
        show_legend=False,  # page3에는 legend 없음
    )

    # 표는 에너지원 행 × scenario 열
    _draw_value_table(
        ax_co2_table,
        co2_values_3x4.T,
        row_labels=[et_label for _, et_label in ENERGY_TYPES],
        col_labels=scenario_labels,
        digits=1,
        fontsize=8.2,
        row_label_width=0.18,
    )

    fig.suptitle("요약", fontsize=16, fontweight="bold", y=0.96)

    return fig
    

# ---------------------------------------------------------------------------- #
#                                   MAIN FUNC                                  #
# ---------------------------------------------------------------------------- #

def escape_str(v:str):
    
    v = v.replace(r"_",r"\_")
    v = v.replace(r"&", r"\&")
    v = v.replace(r"%", r"\%")
    v = v.replace(r"~", r"\textasciitilde{}")
    v = v.replace(r"#", r"\#")
    
    return v

def preprocess_diff_dicts(
    diffs:list[dict]
    ) -> list[dict]:
    
    def mapper(v):
        
        if isinstance(v, str):
            v = escape_str(v)
        
        if isinstance(v, int|float):
            v = f"{v:.10f}".rstrip("0").rstrip(".")
        
        return v
    
    return [
        {k:mapper(v) for k, v in d.items()
        }
        for d in diffs
    ]
    

def summarytable(
    grrbefore:dict,
    grrafter :dict,
    grrafterN:dict,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    
    df1 = pd.DataFrame(
        [
            ["A", "B", "B'"],
            ["a", "a", "b" ],
            [
                _sum_grr_annual_total(grrbefore, "source_uses"),
                _sum_grr_annual_total(grrafter, "source_uses"),
                _sum_grr_annual_total(grrafterN, "source_uses"),
            ],
            [
                _sum_grr_annual_total(grrbefore, "co2"),
                _sum_grr_annual_total(grrafter, "co2"),
                _sum_grr_annual_total(grrafterN, "co2"),
            ],
        ],
        columns=["GR 이전 (①)", "GR 이후 (②)", "운영특성 반영시 (③)"],
        index  =["건물특성","운영특성","1차에너지[$kWh/m^2$]", "온실가스[$kgCO_{2,eq}/m^2$]"]
    )
    
    df2 = pd.DataFrame(
        columns=["GR 감축량 (①-②)","운영특성 반영 감축량 (①-③)","운영특성 반영 영향 (③-②)"],
        index  =["1차에너지[$kWh/m^2$]", "온실가스[$kgCO_{2,eq}/m^2$]"]
        )
    df2["GR 감축량 (①-②)"] = df1["GR 이전 (①)"][2:] - df1["GR 이후 (②)"][2:]
    df2["운영특성 반영 감축량 (①-③)"] = df1["GR 이전 (①)"][2:] - df1["운영특성 반영시 (③)"][2:]
    df2["운영특성 반영 영향 (③-②)"] = df1["운영특성 반영시 (③)"][2:] - df1["GR 이후 (②)"][2:]
    
    return df1, df2

def parse_activechange(
    grm1:GreenRetrofitModel,
    grm2:GreenRetrofitModel,
    ) -> tuple[str]:
    
    # heating and cooling hvac
    def hvac2str(zone:Zone) -> str:
        
        if zone.heating_supply is None:
            heatingstr =  ""
        else:
            heatingstr =  f"{zone.heating_supply}\n{zone.heating_supply.source}"
            
        if zone.cooling_supply is None:
            coolingstr =  ""
        else:
            coolingstr =  f"{zone.cooling_supply}\n{zone.cooling_supply.source}"

        return heatingstr, coolingstr
    
    hvacdict1 = {
        zone.name: hvac2str(zone)
        for zone in grm1.zone
    }
    hvacdict2 = {
        zone.name: hvac2str(zone)
        for zone in grm2.zone
    }
    
    heatingchanged = 0
    coolingchanged = 0
    for zonename in hvacdict1.keys():
        if zonename in hvacdict2.keys() and (hvacdict1[zonename][0] != hvacdict2[zonename][0]):
            heatingchanged += 1
        if zonename in hvacdict2.keys() and (hvacdict1[zonename][1] != hvacdict2[zonename][1]):
            coolingchanged += 1
    
    if heatingchanged == 0:
        heatingchangestr = "변화 없음."
    else:
        heatingchangestr = f"{heatingchanged}개 실에 영향을 주는 교체 있음."
        
    if coolingchanged == 0:
        coolingchangestr = "변화 없음."
    else:
        coolingchangestr = f"{coolingchanged}개 실에 영향을 주는 교체 있음."
    
    # ventilation
    ventdict1 = {
        zone.name: zone.ventilation_system
        for zone in grm1.zone
    }
    ventdict2 = {
        zone.name: zone.ventilation_system
        for zone in grm2.zone
    }
    
    ventadded   = 0 
    ventchanged = 0
    for zonename in ventdict1.keys():
        if zonename in ventdict2.keys():
            if ventdict1[zonename] is None and ventdict2[zonename] is not None:
                ventadded += 1
            elif str(ventdict1[zonename]) != str(ventdict2[zonename]):
                ventchanged += 1
    
    if ventadded == 0 and ventchanged == 0:
        ventchangedstr = "변화 없음."
    elif ventadded == 0 and ventchanged > 0:
        ventchangedstr = f"{ventchanged}개 실에서 전열교환기 교체됨."
    elif ventadded > 0 and ventchanged == 0:
        ventchangedstr = f"{ventadded}개 실에서 전열교환기 추가됨."
    else:
        ventchangedstr =  f"{ventadded}개 실에 전열교환기 추가, {ventchanged}개 실에서 전열교환기 교체됨."
    
    return heatingchangestr, coolingchangestr, ventchangedstr   
    
def parse_majorchange(masterdict: dict) -> str:

    def is_missing(v) -> bool:
        return v is None or (isinstance(v, str) and v.strip() == "") or pd.isna(v)

    def fmt_num(v, digits: int = 3) -> str:
        if is_missing(v):
            return "-"
        v = float(v)
        return f"{v:.{digits}f}".rstrip("0").rstrip(".")

    def fmt_pct_from_ratio(v, digits: int = 1) -> str:
        if is_missing(v):
            return "-"
        return f"{float(v) * 100:.{digits}f}".rstrip("0").rstrip(".") + r"\%"

    def fmt_pct_direct(v, digits: int = 1) -> str:
        if is_missing(v):
            return "-"
        return f"{float(v):.{digits}f}".rstrip("0").rstrip(".") + r"\%"

    def fmt_hrv(h, c) -> str:
        if is_missing(h) and is_missing(c):
            return "-"
        return f"{fmt_pct_from_ratio(h)} / {fmt_pct_from_ratio(c)}"

    def fmt_solar(area, eff) -> str:
        if is_missing(area) and is_missing(eff):
            return "-"
        area_txt = "-" if is_missing(area) else f"{fmt_num(area, 1)} m2"
        eff_txt = "-" if is_missing(eff) else fmt_pct_direct(eff, 1)
        return f"{area_txt}, {eff_txt}"

    def heating_value(prefix: str):
        heating_type = masterdict.get(f"{prefix}_난방1_유형")
        if heating_type == "히트펌프":
            return masterdict.get(f"{prefix}_난방1_COP [W/W]")
        return masterdict.get(f"{prefix}_난방1_효율 [%]")

    def heating_note() -> str:
        types = {
            masterdict.get("GR이전_난방1_유형"),
            masterdict.get("GR이후_난방1_유형"),
            masterdict.get("N년차_난방1_유형"),
        }
        if types == {"히트펌프"}:
            return "[W/W]"
        if "히트펌프" in types:
            return r"히트펌프 [W/W], 보일러 [\%]"
        return r"[\%]"

    surveyresult, _ = parse_surveychange(masterdict)
    
    if masterdict["구분"] == "어린이집":
        time_min = {
            "기본보육 인원": 8.5 * 60,   # 07:30~16:00
            "연장보육A 인원": 2.0 * 60,  # 16:00~18:00
            "연장보육B 인원": 1.5 * 60,  # 18:00~19:30
            "야간보육 인원": 1.5 * 60,   # 19:30~21:00
        }

        def _weighted_occ(c: str) -> float:
            # 인원이 0인 보육 시간대는 평균에서 제외; 전부 0이면 재실인원 0으로 처리
            active = [
                (float(surveyresult.loc[surveyresult["항목"].eq(k), c].iloc[0]), t)
                for k, t in time_min.items()
                if float(surveyresult.loc[surveyresult["항목"].eq(k), c].iloc[0]) > 0
            ]
            if not active:
                return 0.0
            return sum(n * t for n, t in active) / sum(t for _, t in active)

        occlist = [
            _weighted_occ(c)
            for c in ["그린리모델링 이전", "그린리모델링 이후", "운영특성 반영"]
        ]
    else:
        occlist = [
            float(surveyresult.loc[surveyresult["항목"].eq("직원"), c].iloc[0])
            + (
                float(re.search(r"(\d+(?:\.\d+)?)\s*명", v).group(1))
                * float(re.search(r"(\d+(?:\.\d+)?)\s*분", v).group(1))
                / (
                    (lambda t:
                        (int(t.split("~")[1].split(":")[0]) * 60 + int(t.split("~")[1].split(":")[1]))
                        - (int(t.split("~")[0].split(":")[0]) * 60 + int(t.split("~")[0].split(":")[1]))
                    )(surveyresult.loc[surveyresult["항목"].eq("운영시간"), c].iloc[0])
                )
            )
            for c in ["그린리모델링 이전", "그린리모델링 이후", "그린리모델링 이후"]
            for v in [surveyresult.loc[surveyresult["항목"].str.contains("방문객수"), c].iloc[0]]
        ]
    
    rows = [
        [
            fmt_num(masterdict.get("GR이전_외벽_열관류율 [W/m2·K]"), 3),
            fmt_num(masterdict.get("GR이후_외벽_열관류율 [W/m2·K]"), 3),
            fmt_num(masterdict.get("N년차_외벽_열관류율 [W/m2·K]"), 3),
            "[W/m2·K]",
        ],
        [
            fmt_num(masterdict.get("GR이전_창 및 문_열관류율 [W/m2·K]"), 3),
            fmt_num(masterdict.get("GR이후_창 및 문_열관류율 [W/m2·K]"), 3),
            fmt_num(masterdict.get("N년차_창 및 문_열관류율 [W/m2·K]"), 3),
            "[W/m2·K]",
        ],
        [
            fmt_num(masterdict.get("GR이전_냉방1_COP [W/W]"), 2),
            fmt_num(masterdict.get("GR이후_냉방1_COP [W/W]"), 2),
            fmt_num(masterdict.get("N년차_냉방1_COP [W/W]"), 2),
            "[W/W]",
        ],
        [
            fmt_num(heating_value("GR이전"), 2),
            fmt_num(heating_value("GR이후"), 2),
            fmt_num(heating_value("N년차"), 2),
            heating_note(),
        ],
        [
            fmt_hrv(
                masterdict.get("GR이전_전열 교환기_난방[%]"),
                masterdict.get("GR이전_전열 교환기_냉방[%]")
            ),
            fmt_hrv(
                masterdict.get("GR이후_전열 교환기_난방[%]"),
                masterdict.get("GR이후_전열 교환기_냉방[%]")
            ),
            fmt_hrv(
                masterdict.get("N년차_전열 교환기_난방[%]"),
                masterdict.get("N년차_전열 교환기_냉방[%]")
            ),
            r"[난방] / [냉방]",
        ],
        [
            fmt_num(masterdict.get("GR이전_조명밀도 [W/m2]"), 2),
            fmt_num(masterdict.get("GR이후_조명밀도 [W/m2]"), 2),
            fmt_num(masterdict.get("N년차_조명밀도 [W/m2]"), 2),
            "[W/m2]",
        ],
        [
            fmt_solar(
                masterdict.get("GR이전_태양광_면적[m2]"),
                masterdict.get("GR이전_태양광_효율[%]")
            ),
            fmt_solar(
                masterdict.get("GR이후_태양광_면적[m2]"),
                masterdict.get("GR이후_태양광_효율[%]")
            ),
            fmt_solar(
                masterdict.get("N년차_태양광_면적[m2]"),
                masterdict.get("N년차_태양광_효율[%]")
            ),
            r"[면적 m2], [효율 \%]",
        ],
        [f"{v:.1f}" for v in occlist] + ["명, 운영시간 평균"],
        [f"{float(v):.1f}" for v in surveyresult.query("항목 == '난방 설정온도(℃)'").iloc[0].values[1:]] + ["℃"],
        [f"{float(v):.1f}" for v in surveyresult.query("항목 == '냉방 설정온도(℃)'").iloc[0].values[1:]] + ["℃"],
    ]

    df = pd.DataFrame(
        rows,
        columns=["GR이전", "GR이후", "N년차", "비고"],
        index=pd.MultiIndex.from_tuples(
            [
                ("기술요소", "외피"),
                ("기술요소", "창호"),
                ("기술요소", "냉방"),
                ("기술요소", "난방"),
                ("기술요소", "환기"),
                ("기술요소", "조명"),
                ("기술요소", "신재생"),
                ("운영특성", "재실인원"),
                ("운영특성", "난방설정온도"),
                ("운영특성", "냉방설정온도"),
            ],
            names=["대분류", "구분"]
        )
    )

    df = df[df[["GR이전", "GR이후", "N년차"]].nunique(axis=1) > 1]

    tex = df.style.hide(axis="index", names=True).to_latex(
        hrules=True,
        clines="all;data",
        sparse_index=True,
        multirow_align="c",
        column_format=(
            r">{\centering\arraybackslash}p{2cm}|"
            r">{\centering\arraybackslash}p{2cm}|"
            r">{\centering\arraybackslash}p{3.2cm}|"
            r">{\centering\arraybackslash}p{3.2cm}|"
            r">{\centering\arraybackslash}p{3.2cm}|"
            r">{\centering\arraybackslash}p{2.8cm}"
        ),
    )

    tex = tex.replace(r"\toprule", r"\hline")
    tex = tex.replace(r"\midrule", r"\hline")
    tex = tex.replace(r"\bottomrule", r"\hline")

    tex = tex.replace(
        "& & GR이전 & GR이후 & N년차 & 비고 \\\n",
        r"\multicolumn{2}{c|}{구분} & GR이전 & GR이후 & N년차 & 비고 \\" + "\n"
    )

    tex = tex.replace(r"\cline{1-6} \cline{2-6}", r"\hline")

    return tex


def parse_perfchange(masterdict: dict) -> str:

    def 유형열원(prefix:str, equipment:str) -> str:
        유형 = masterdict.get(f"{prefix}_{equipment}_유형")
        열원 = masterdict.get(f"{prefix}_{equipment}_열원")
        return f"{'-' if pd.isna(유형) else 유형} / {'-' if pd.isna(열원) else 열원}"

    def 근거(part:str) -> str:
        values = set()
        for prefix in ["GR이전", "GR이후", "N년차"]:
            v = masterdict.get(f"{prefix}_{part}_근거")
            values.add("-" if pd.isna(v) else v)
        return "/".join(values - {"-"})

    def 수치(prefix:str, col:str) -> str:
        v = masterdict.get(f"{prefix}_{col}")
        return "-" if pd.isna(v) else f"{v:.2f}"

    # [메모 · 2026-09-14]
    #   외벽/창호/지붕/바닥 값은 masterdb 만 읽는다. 시뮬레이션 입력 엑셀·.grr 과는 코드상 연결이 없다
    #   (build_report 가 엑셀에서 쓰는 건 건물명·주소·허가일자뿐).
    #   실제 IDF(result_idf)와 대조한 결과: 외벽·창호는 masterdb 와 일치하고, 지붕·바닥의 1.16 도
    #   엔진의 실제 동작(구조체 미입력 시 '층간바닥' 행 사용 — epsimple/core/construction.py
    #   get_regulated_construction 의 주석 참고)과 일치한다. 즉 masterdb 가 시뮬레이션 입력값과 같다.
    #   엔진 값을 따로 계산해 masterdb 와 대조·게이팅하는 시도는 같은 날 되돌렸다(동작 변경 없음).
    df = pd.DataFrame(
        [
            [
                "외벽 열관류율 [W/m2·K]",
                수치("GR이전", "외벽_열관류율 [W/m2·K]"),
                수치("GR이후", "외벽_열관류율 [W/m2·K]"),
                수치("N년차" , "외벽_열관류율 [W/m2·K]"),
                근거("외벽")
            ],
            [
                "창호 열관류율 [W/m2·K]",
                수치("GR이전", "창 및 문_열관류율 [W/m2·K]"),
                수치("GR이후", "창 및 문_열관류율 [W/m2·K]"),
                수치("N년차" , "창 및 문_열관류율 [W/m2·K]"),
                근거("창 및 문")
            ],
            [
                "창호 취득계수(SHGC)",
                수치("GR이전", "창 및 문_취득계수"),
                수치("GR이후", "창 및 문_취득계수"),
                수치("N년차" , "창 및 문_취득계수"),
                근거("창 및 문")
            ],
            [
                "지붕 열관류율 [W/m2·K]",
                수치("GR이전", "지붕_열관류율 [W/m2·K]"),
                수치("GR이후", "지붕_열관류율 [W/m2·K]"),
                수치("N년차" , "지붕_열관류율 [W/m2·K]"),
                근거("지붕")
            ],
            [
                "바닥 열관류율 [W/m2·K]",
                수치("GR이전", "바닥_열관류율 [W/m2·K]"),
                수치("GR이후", "바닥_열관류율 [W/m2·K]"),
                수치("N년차" , "바닥_열관류율 [W/m2·K]"),
                근거("바닥")
            ],
            [
                "조명밀도",
                수치("GR이전", "조명밀도 [W/m2]"),
                수치("GR이후", "조명밀도 [W/m2]"),
                수치("N년차" , "조명밀도 [W/m2]"),
                "-"
            ],
            [
                "침기율",
                수치("GR이전", "침기율 [ACH]"),
                수치("GR이후", "침기율 [ACH]"),
                수치("N년차" , "침기율 [ACH]"),
                "-",
            ],
            [
                "난방1 유형/열원",
                유형열원("GR이전", "난방1"),
                유형열원("GR이후", "난방1"),
                유형열원("N년차" , "난방1"),
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_난방1_근거")) else masterdict.get("GR이전_난방1_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_난방1_근거")) else masterdict.get("GR이후_난방1_근거"),
                    "-" if pd.isna(masterdict.get("N년차_난방1_근거")) else masterdict.get("N년차_난방1_근거"),
                ]) - {"-"})
            ],
            [
                "난방1 용량 [kW]",
                "-" if pd.isna(masterdict.get("GR이전_난방1_용량 [W]")) else f"{masterdict.get('GR이전_난방1_용량 [W]')*1E-3:.2f}",
                "-" if pd.isna(masterdict.get("GR이후_난방1_용량 [W]")) else f"{masterdict.get('GR이후_난방1_용량 [W]')*1E-3:.2f}",
                "-" if pd.isna(masterdict.get("N년차_난방1_용량 [W]")) else f"{masterdict.get('N년차_난방1_용량 [W]')*1E-3:.2f}",
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_난방1_근거")) else masterdict.get("GR이전_난방1_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_난방1_근거")) else masterdict.get("GR이후_난방1_근거"),
                    "-" if pd.isna(masterdict.get("N년차_난방1_근거")) else masterdict.get("N년차_난방1_근거"),
                ]) - {"-"})
            ],
            [
                "난방1 COP [W/W]",
                "-" if pd.isna(masterdict.get("GR이전_난방1_COP [W/W]")) else f"{masterdict.get('GR이전_난방1_COP [W/W]'):.2f}",
                "-" if pd.isna(masterdict.get("GR이후_난방1_COP [W/W]")) else f"{masterdict.get('GR이후_난방1_COP [W/W]'):.2f}",
                "-" if pd.isna(masterdict.get("N년차_난방1_COP [W/W]")) else f"{masterdict.get('N년차_난방1_COP [W/W]'):.2f}",
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_난방1_근거")) else masterdict.get("GR이전_난방1_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_난방1_근거")) else masterdict.get("GR이후_난방1_근거"),
                    "-" if pd.isna(masterdict.get("N년차_난방1_근거")) else masterdict.get("N년차_난방1_근거"),
                ]) - {"-"})
            ],
            [
                "난방1 효율 [%]",
                "-" if pd.isna(masterdict.get("GR이전_난방1_효율 [%]")) else f"{masterdict.get('GR이전_난방1_효율 [%]'):.1f}",
                "-" if pd.isna(masterdict.get("GR이후_난방1_효율 [%]")) else f"{masterdict.get('GR이후_난방1_효율 [%]'):.1f}",
                "-" if pd.isna(masterdict.get("N년차_난방1_효율 [%]")) else f"{masterdict.get('N년차_난방1_효율 [%]'):.1f}",
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_난방1_근거")) else masterdict.get("GR이전_난방1_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_난방1_근거")) else masterdict.get("GR이후_난방1_근거"),
                    "-" if pd.isna(masterdict.get("N년차_난방1_근거")) else masterdict.get("N년차_난방1_근거"),
                ]) - {"-"})
            ],
            [
                "냉방1 유형/열원",
                유형열원("GR이전", "냉방1"),
                유형열원("GR이후", "냉방1"),
                유형열원("N년차" , "냉방1"),
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_냉방1_근거")) else masterdict.get("GR이전_냉방1_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_냉방1_근거")) else masterdict.get("GR이후_냉방1_근거"),
                    "-" if pd.isna(masterdict.get("N년차_냉방1_근거")) else masterdict.get("N년차_냉방1_근거"),
                ]) - {"-"})
            ],
            [
                "냉방1 용량 [kW]",
                "-" if pd.isna(masterdict.get("GR이전_냉방1_용량 [W]")) else f"{masterdict.get('GR이전_냉방1_용량 [W]')*1E-3:.2f}",
                "-" if pd.isna(masterdict.get("GR이후_냉방1_용량 [W]")) else f"{masterdict.get('GR이후_냉방1_용량 [W]')*1E-3:.2f}",
                "-" if pd.isna(masterdict.get("N년차_냉방1_용량 [W]")) else f"{masterdict.get('N년차_냉방1_용량 [W]')*1E-3:.2f}",
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_냉방1_근거")) else masterdict.get("GR이전_냉방1_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_냉방1_근거")) else masterdict.get("GR이후_냉방1_근거"),
                    "-" if pd.isna(masterdict.get("N년차_냉방1_근거")) else masterdict.get("N년차_냉방1_근거"),
                ]) - {"-"})
            ],
            [
                "냉방1 COP [W/W]",
                "-" if pd.isna(masterdict.get("GR이전_냉방1_COP [W/W]")) else f"{masterdict.get('GR이전_냉방1_COP [W/W]'):.2f}",
                "-" if pd.isna(masterdict.get("GR이후_냉방1_COP [W/W]")) else f"{masterdict.get('GR이후_냉방1_COP [W/W]'):.2f}",
                "-" if pd.isna(masterdict.get("N년차_냉방1_COP [W/W]")) else f"{masterdict.get('N년차_냉방1_COP [W/W]'):.2f}",
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_냉방1_근거")) else masterdict.get("GR이전_냉방1_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_냉방1_근거")) else masterdict.get("GR이후_냉방1_근거"),
                    "-" if pd.isna(masterdict.get("N년차_냉방1_근거")) else masterdict.get("N년차_냉방1_근거"),
                ]) - {"-"})
            ],
            [
                "냉방1 효율 [%]",
                "-" if pd.isna(masterdict.get("GR이전_냉방1_효율 [%]")) else f"{masterdict.get('GR이전_냉방1_효율 [%]'):.1f}",
                "-" if pd.isna(masterdict.get("GR이후_냉방1_효율 [%]")) else f"{masterdict.get('GR이후_냉방1_효율 [%]'):.1f}",
                "-" if pd.isna(masterdict.get("N년차_냉방1_효율 [%]")) else f"{masterdict.get('N년차_냉방1_효율 [%]'):.1f}",
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_냉방1_근거")) else masterdict.get("GR이전_냉방1_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_냉방1_근거")) else masterdict.get("GR이후_냉방1_근거"),
                    "-" if pd.isna(masterdict.get("N년차_냉방1_근거")) else masterdict.get("N년차_냉방1_근거"),
                ]) - {"-"})
            ],
            [
                "전열교환기 효율(난방)",
                "-" if pd.isna(masterdict.get("GR이전_전열 교환기_난방[%]")) else f"{masterdict.get('GR이전_전열 교환기_난방[%]'):.1f}%",
                "-" if pd.isna(masterdict.get("GR이후_전열 교환기_난방[%]")) else f"{masterdict.get('GR이후_전열 교환기_난방[%]'):.1f}%",
                "-" if pd.isna(masterdict.get("N년차_전열 교환기_난방[%]")) else f"{masterdict.get('N년차_전열 교환기_난방[%]'):.1f}%",
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_전열 교환기_근거")) else masterdict.get("GR이전_전열 교환기_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_전열 교환기_근거")) else masterdict.get("GR이후_전열 교환기_근거"),
                    "-" if pd.isna(masterdict.get("N년차_전열 교환기_근거")) else masterdict.get("N년차_전열 교환기_근거"),
                ]) - {"-"})
            ],
            [
                "전열교환기 효율(냉방)",
                "-" if pd.isna(masterdict.get("GR이전_전열 교환기_냉방[%]")) else f"{masterdict.get('GR이전_전열 교환기_냉방[%]'):.1f}%",
                "-" if pd.isna(masterdict.get("GR이후_전열 교환기_냉방[%]")) else f"{masterdict.get('GR이후_전열 교환기_냉방[%]'):.1f}%",
                "-" if pd.isna(masterdict.get("N년차_전열 교환기_냉방[%]")) else f"{masterdict.get('N년차_전열 교환기_냉방[%]'):.1f}%", 
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_전열 교환기_근거")) else masterdict.get("GR이전_전열 교환기_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_전열 교환기_근거")) else masterdict.get("GR이후_전열 교환기_근거"),
                    "-" if pd.isna(masterdict.get("N년차_전열 교환기_근거")) else masterdict.get("N년차_전열 교환기_근거"),
                ]) - {"-"})
            ],
            [
                "태양광 설치 여부",
                "O" if not pd.isna(masterdict.get("GR이전_태양광_면적[m2]")) and masterdict.get("GR이전_태양광_면적[m2]") > 0 else "X",
                "O" if not pd.isna(masterdict.get("GR이후_태양광_면적[m2]")) and masterdict.get("GR이후_태양광_면적[m2]") > 0 else "X",
                "O" if not pd.isna(masterdict.get("N년차_태양광_면적[m2]")) and masterdict.get("N년차_태양광_면적[m2]") > 0 else "X",
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_태양광_근거")) else masterdict.get("GR이전_태양광_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_태양광_근거")) else masterdict.get("GR이후_태양광_근거"),
                    "-" if pd.isna(masterdict.get("N년차_태양광_근거")) else masterdict.get("N년차_태양광_근거"),
                ]) - {"-"})
            ],
            [
                "태양광 면적[m2]",
                f"{masterdict.get('GR이전_태양광_면적[m2]'):.1f}" if not pd.isna(masterdict.get("GR이전_태양광_면적[m2]")) else "-",
                f"{masterdict.get('GR이후_태양광_면적[m2]'):.1f}" if not pd.isna(masterdict.get("GR이후_태양광_면적[m2]")) else "-",
                f"{masterdict.get('N년차_태양광_면적[m2]'):.1f}" if not pd.isna(masterdict.get("N년차_태양광_면적[m2]")) else "-",
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_태양광_근거")) else masterdict.get("GR이전_태양광_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_태양광_근거")) else masterdict.get("GR이후_태양광_근거"),
                    "-" if pd.isna(masterdict.get("N년차_태양광_근거")) else masterdict.get("N년차_태양광_근거"),
                ]) - {"-"})
            ],
            [
                "태양광 효율[%]",
                f"{masterdict.get('GR이전_태양광_효율[%]'):.1f}" if not pd.isna(masterdict.get("GR이전_태양광_효율[%]")) else "-",
                f"{masterdict.get('GR이후_태양광_효율[%]'):.1f}" if not pd.isna(masterdict.get("GR이후_태양광_효율[%]")) else "-",
                f"{masterdict.get('N년차_태양광_효율[%]'):.1f}" if not pd.isna(masterdict.get("N년차_태양광_효율[%]")) else "-",
                "/".join(set([
                    "-" if pd.isna(masterdict.get("GR이전_태양광_근거")) else masterdict.get("GR이전_태양광_근거"),
                    "-" if pd.isna(masterdict.get("GR이후_태양광_근거")) else masterdict.get("GR이후_태양광_근거"),
                    "-" if pd.isna(masterdict.get("N년차_태양광_근거")) else masterdict.get("N년차_태양광_근거"),
                ]) - {"-"})
            ]
        ],
        columns = ["항목","그린리모델링 이전", "그린리모델링 이후", "운영특성 반영", "근거"],
    )
    
    def prettify_latex_table(
        tex: str,
        header_color: str = "EAEAEA",
        arraystretch: float = 1.1,
        fontsize: str = r"\small",
    ) -> str:
        lines = tex.splitlines()
        new_lines = []
        in_tabular = False
        header_done = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith(r"\begin{tabular}"):
                in_tabular = True
                new_lines.append(r"\begingroup")
                new_lines.append(fontsize)
                new_lines.append(rf"\renewcommand{{\arraystretch}}{{{arraystretch}}}")
                new_lines.append(line)
                new_lines.append(r"\hline")
                continue

            if stripped.startswith(r"\end{tabular}"):
                in_tabular = False
                new_lines.append(line)
                new_lines.append(r"\renewcommand{\arraystretch}{1}")
                new_lines.append(r"\endgroup")
                continue

            if in_tabular and stripped.endswith(r"\\"):
                if not header_done:
                    new_lines.append(rf"\rowcolor[HTML]{{{header_color}}}")
                    header_done = True
                new_lines.append(line)
                new_lines.append(r"\hline")
                continue

            new_lines.append(line)

        return "\n".join(new_lines)
    
    def highlight_changed_row(row):
        cols = ["그린리모델링 이전", "그린리모델링 이후", "운영특성 반영"]

        # "-", NaN 등은 문자열로 통일해서 비교
        values = [str(row[c]).strip() for c in cols]

        changed = len(set(values)) > 1

        if changed:
            return [
                "background-color: #FFF2CC; font-weight: bold;"
                for _ in row
            ]
        else:
            return ["" for _ in row]
    
    tex = (
        df.style
        .hide(axis="index")
        .apply(highlight_changed_row, axis=1)
        .format(escape="latex")
        .to_latex(
            hrules=False,
            convert_css=True,
            column_format=(
                r">{\centering\arraybackslash}p{4cm}|"
                r">{\centering\arraybackslash}p{2.5cm}|"
                r">{\centering\arraybackslash}p{2.5cm}|"
                r">{\centering\arraybackslash}p{2.5cm}|"
                r">{\centering\arraybackslash}p{4.5cm}"
            ),
        )
        .replace("~", "-")
    )

    tex = prettify_latex_table(tex, header_color="EAEAEA")
    return tex

def parse_surveychange(masterdict: dict) -> str:
    
    if masterdict.get("구분") == "어린이집":
        df = pd.DataFrame(
            [
                [
                    "기본보육 인원",
                    f"{(0 if pd.isna(masterdict.get("GR이전_어린이집_기본보육교사수")) else masterdict.get("GR이전_어린이집_기본보육교사수")) + (0 if pd.isna(masterdict.get("GR이전_어린이집_기본보육 원생수")) else masterdict.get("GR이전_어린이집_기본보육 원생수")):.0f}",
                    f"{(0 if pd.isna(masterdict.get("GR이후_어린이집_기본보육교사수")) else masterdict.get("GR이후_어린이집_기본보육교사수")) + (0 if pd.isna(masterdict.get("GR이후_어린이집_기본보육 원생수")) else masterdict.get("GR이후_어린이집_기본보육 원생수")):.0f}",
                    f"{(0 if pd.isna(masterdict.get("N년차_어린이집_기본보육교사수")) else masterdict.get("N년차_어린이집_기본보육교사수")) + (0 if pd.isna(masterdict.get("N년차_어린이집_기본보육 원생수")) else masterdict.get("N년차_어린이집_기본보육 원생수")):.0f}",
                ],
                [
                    "연장보육A 인원",
                    f"{(0 if pd.isna(masterdict.get("GR이전_어린이집_연장보육A교사수")) else masterdict.get("GR이전_어린이집_연장보육A교사수")) + (0 if pd.isna(masterdict.get("GR이전_어린이집_연장보육A원생수")) else masterdict.get("GR이전_어린이집_연장보육A원생수")):.0f}",
                    f"{(0 if pd.isna(masterdict.get("GR이후_어린이집_연장보육A교사수")) else masterdict.get("GR이후_어린이집_연장보육A교사수")) + (0 if pd.isna(masterdict.get("GR이후_어린이집_연장보육A원생수")) else masterdict.get("GR이후_어린이집_연장보육A원생수")):.0f}",
                    f"{(0 if pd.isna(masterdict.get("N년차_어린이집_연장보육A교사수")) else masterdict.get("N년차_어린이집_연장보육A교사수")) + (0 if pd.isna(masterdict.get("N년차_어린이집_연장보육A원생수")) else masterdict.get("N년차_어린이집_연장보육A원생수")):.0f}",
                ],
                [
                    "연장보육B 인원",
                    f"{(0 if pd.isna(masterdict.get("GR이전_어린이집_연장보육B교사수")) else masterdict.get("GR이전_어린이집_연장보육B교사수")) + (0 if pd.isna(masterdict.get("GR이전_어린이집_연장보육B원생수")) else masterdict.get("GR이전_어린이집_연장보육B원생수")):.0f}",
                    f"{(0 if pd.isna(masterdict.get("GR이후_어린이집_연장보육B교사수")) else masterdict.get("GR이후_어린이집_연장보육B교사수")) + (0 if pd.isna(masterdict.get("GR이후_어린이집_연장보육B원생수")) else masterdict.get("GR이후_어린이집_연장보육B원생수")):.0f}",
                    f"{(0 if pd.isna(masterdict.get("N년차_어린이집_연장보육B교사수")) else masterdict.get("N년차_어린이집_연장보육B교사수")) + (0 if pd.isna(masterdict.get("N년차_어린이집_연장보육B원생수")) else masterdict.get("N년차_어린이집_연장보육B원생수")):.0f}",
                ],
                [
                    "야간보육 인원",
                    f"{(0 if pd.isna(masterdict.get("GR이전_어린이집_야간보육 교사수")) else masterdict.get("GR이전_어린이집_야간보육 교사수")) + (0 if pd.isna(masterdict.get("GR이전_어린이집_야간보육 원생수")) else masterdict.get("GR이전_어린이집_야간보육 원생수")):.0f}",
                    f"{(0 if pd.isna(masterdict.get("GR이후_어린이집_야간보육 교사수")) else masterdict.get("GR이후_어린이집_야간보육 교사수")) + (0 if pd.isna(masterdict.get("GR이후_어린이집_야간보육 원생수")) else masterdict.get("GR이후_어린이집_야간보육 원생수")):.0f}",
                    f"{(0 if pd.isna(masterdict.get("N년차_어린이집_야간보육 교사수")) else masterdict.get("N년차_어린이집_야간보육 교사수")) + (0 if pd.isna(masterdict.get("N년차_어린이집_야간보육 원생수")) else masterdict.get("N년차_어린이집_야간보육 원생수")):.0f}",
                ],
                [
                    "주말보육 인원",
                    f"{(0 if pd.isna(masterdict.get("GR이전_어린이집_주말보육 교사수")) else masterdict.get("GR이전_어린이집_주말보육 교사수")) + (0 if pd.isna(masterdict.get("GR이전_어린이집_주말보육 원생수")) else masterdict.get("GR이전_어린이집_주말보육 원생수")):.0f}",
                    f"{(0 if pd.isna(masterdict.get("GR이후_어린이집_주말보육 교사수")) else masterdict.get("GR이후_어린이집_주말보육 교사수")) + (0 if pd.isna(masterdict.get("GR이후_어린이집_주말보육 원생수")) else masterdict.get("GR이후_어린이집_주말보육 원생수")):.0f}",
                    f"{(0 if pd.isna(masterdict.get("N년차_어린이집_주말보육 교사수")) else masterdict.get("N년차_어린이집_주말보육 교사수")) + (0 if pd.isna(masterdict.get("N년차_어린이집_주말보육 원생수")) else masterdict.get("N년차_어린이집_주말보육 원생수")):.0f}",
                ],
                [
                    "난방 사용기간",
                    masterdict.get("GR이전_일반존_난방1 사용기간"),
                    masterdict.get("GR이후_일반존_난방1 사용기간"),
                    masterdict.get("N년차_일반존_난방1 사용기간"),
                ],
                [
                    "난방 사용시간",
                    masterdict.get("GR이전_일반존_난방1 사용시간"),
                    masterdict.get("GR이후_일반존_난방1 사용시간"),
                    masterdict.get("N년차_일반존_난방1 사용시간"),
                ],
                [
                    "난방 설정온도(℃)",
                    f"{masterdict.get('GR이전_일반존_난방1 설정온도'):.0f}" if not pd.isna(masterdict.get("GR이전_일반존_난방1 설정온도")) else "-",
                    f"{masterdict.get('GR이후_일반존_난방1 설정온도'):.0f}" if not pd.isna(masterdict.get("GR이후_일반존_난방1 설정온도")) else "-",
                    f"{masterdict.get('N년차_일반존_난방1 설정온도'):.0f}" if not pd.isna(masterdict.get("N년차_일반존_난방1 설정온도")) else "-",
                ],
                [
                    "냉방 사용기간",
                    masterdict.get("GR이전_일반존_냉방1 사용기간"),
                    masterdict.get("GR이후_일반존_냉방1 사용기간"),
                    masterdict.get("N년차_일반존_냉방1 사용기간"),
                ],
                [
                    "냉방 사용시간",
                    masterdict.get("GR이전_일반존_냉방1 사용시간"),
                    masterdict.get("GR이후_일반존_냉방1 사용시간"),
                    masterdict.get("N년차_일반존_냉방1 사용시간"),
                ],
                [
                    "냉방 설정온도(℃)",
                    f"{masterdict.get('GR이전_일반존_냉방1 설정온도'):.0f}" if not pd.isna(masterdict.get("GR이전_일반존_냉방1 설정온도")) else "-",
                    f"{masterdict.get('GR이후_일반존_냉방1 설정온도'):.0f}" if not pd.isna(masterdict.get("GR이후_일반존_냉방1 설정온도")) else "-",
                    f"{masterdict.get('N년차_일반존_냉방1 설정온도'):.0f}" if not pd.isna(masterdict.get("N년차_일반존_냉방1 설정온도")) else "-",
                ],
            ],
            columns = ["항목","그린리모델링 이전", "그린리모델링 이후", "운영특성 반영"],
        )
    else:
        df = pd.DataFrame(
            [
                [
                    "운영시간",
                    masterdict.get("GR이전_보건지소·진료소_기본운영 시간"),
                    masterdict.get("GR이후_보건지소·진료소_기본운영 시간"),
                    masterdict.get("N년차_보건지소·진료소_기본운영 시간"),
                ],
                [
                    "외근시간",
                    masterdict.get("GR이전_보건지소·진료소_외근시간"),
                    masterdict.get("GR이후_보건지소·진료소_외근시간"),
                    masterdict.get("N년차_보건지소·진료소_외근시간"),
                ],
                [
                    "외근요일",
                    masterdict.get("GR이전_보건지소·진료소_외근요일"),
                    masterdict.get("GR이후_보건지소·진료소_외근요일"),
                    masterdict.get("N년차_보건지소·진료소_외근요일"),
                ],
                [
                    "직원",
                    f"{masterdict.get('GR이전_보건지소·진료소_직원수'):.0f}" if not pd.isna(masterdict.get("GR이전_보건지소·진료소_직원수")) else "-",
                    f"{masterdict.get('GR이후_보건지소·진료소_직원수'):.0f}" if not pd.isna(masterdict.get("GR이후_보건지소·진료소_직원수")) else "-",
                    f"{masterdict.get('N년차_보건지소·진료소_직원수'):.0f}" if not pd.isna(masterdict.get("N년차_보건지소·진료소_직원수")) else "-",
                ],
                [
                    "방문객수 / 체류시간",
                    f"{(0 if pd.isna(masterdict.get('GR이전_보건지소·진료소_오전 방문객수')) else masterdict.get('GR이전_보건지소·진료소_오전 방문객수'))+(0 if pd.isna(masterdict.get('GR이전_보건지소·진료소_오후 방문객수')) else masterdict.get('GR이전_보건지소·진료소_오후 방문객수')):.0f}명 / {(0 if pd.isna((masterdict.get('GR이전_보건지소·진료소_오전 체류시간')+masterdict.get("GR이전_보건지소·진료소_오후 체류시간"))/2) else (masterdict.get('GR이전_보건지소·진료소_오전 체류시간')+masterdict.get("GR이전_보건지소·진료소_오후 체류시간"))/2):.0f}분",
                    f"{(0 if pd.isna(masterdict.get('GR이후_보건지소·진료소_오전 방문객수')) else masterdict.get('GR이후_보건지소·진료소_오전 방문객수'))+(0 if pd.isna(masterdict.get('GR이후_보건지소·진료소_오후 방문객수')) else masterdict.get('GR이후_보건지소·진료소_오후 방문객수')):.0f}명 / {(0 if pd.isna((masterdict.get('GR이후_보건지소·진료소_오전 체류시간')+masterdict.get("GR이후_보건지소·진료소_오후 체류시간"))/2) else (masterdict.get('GR이후_보건지소·진료소_오전 체류시간')+masterdict.get("GR이후_보건지소·진료소_오후 체류시간"))/2):.0f}분",
                    f"{(0 if pd.isna(masterdict.get('N년차_보건지소·진료소_오전 방문객수')) else masterdict.get('N년차_보건지소·진료소_오전 방문객수'))+(0 if pd.isna(masterdict.get('N년차_보건지소·진료소_오후 방문객수')) else masterdict.get('N년차_보건지소·진료소_오후 방문객수')):.0f}명 / {(0 if pd.isna((masterdict.get('N년차_보건지소·진료소_오전 체류시간')+masterdict.get("N년차_보건지소·진료소_오후 체류시간"))/2) else (masterdict.get('N년차_보건지소·진료소_오전 체류시간')+masterdict.get("N년차_보건지소·진료소_오후 체류시간"))/2):.0f}분"
                ],
                [
                    "관사 수",
                    "-" if pd.isna(masterdict.get("GR이전_특화존2_사용 관사수")) else f"{masterdict.get("GR이전_특화존2_사용 관사수"):.0f}",
                    "-" if pd.isna(masterdict.get("GR이후_특화존2_사용 관사수")) else f"{masterdict.get("GR이후_특화존2_사용 관사수"):.0f}",
                    "-" if pd.isna(masterdict.get("N년차_특화존2_사용 관사수")) else f"{masterdict.get("N년차_특화존2_사용 관사수"):.0f}",

                ],
                [
                    "난방 사용기간",
                    masterdict.get("GR이전_일반존_난방1 사용기간"),
                    masterdict.get("GR이후_일반존_난방1 사용기간"),
                    masterdict.get("N년차_일반존_난방1 사용기간"),
                ],
                [
                    "난방 사용시간",
                    masterdict.get("GR이전_일반존_난방1 사용시간"),
                    masterdict.get("GR이후_일반존_난방1 사용시간"),
                    masterdict.get("N년차_일반존_난방1 사용시간"),
                ],
                [
                    "난방 설정온도(℃)",
                    f"{masterdict.get('GR이전_일반존_난방1 설정온도'):.0f}" if not pd.isna(masterdict.get("GR이전_일반존_난방1 설정온도")) else "-",
                    f"{masterdict.get('GR이후_일반존_난방1 설정온도'):.0f}" if not pd.isna(masterdict.get("GR이후_일반존_난방1 설정온도")) else "-",
                    f"{masterdict.get('N년차_일반존_난방1 설정온도'):.0f}" if not pd.isna(masterdict.get("N년차_일반존_난방1 설정온도")) else "-",
                ],
                [
                    "냉방 사용기간",
                    masterdict.get("GR이전_일반존_냉방1 사용기간"),
                    masterdict.get("GR이후_일반존_냉방1 사용기간"),
                    masterdict.get("N년차_일반존_냉방1 사용기간"),

                ],
                [
                    "냉방 사용시간",
                    masterdict.get("GR이전_일반존_냉방1 사용시간"),
                    masterdict.get("GR이후_일반존_냉방1 사용시간"),
                    masterdict.get("N년차_일반존_냉방1 사용시간"),
                ],
                [
                    "냉방 설정온도(℃)",
                    f"{masterdict.get('GR이전_일반존_냉방1 설정온도'):.0f}" if not pd.isna(masterdict.get("GR이전_일반존_냉방1 설정온도")) else "-",
                    f"{masterdict.get('GR이후_일반존_냉방1 설정온도'):.0f}" if not pd.isna(masterdict.get("GR이후_일반존_냉방1 설정온도")) else "-",
                    f"{masterdict.get('N년차_일반존_냉방1 설정온도'):.0f}" if not pd.isna(masterdict.get("N년차_일반존_냉방1 설정온도")) else "-",
                ],
            ],
            columns = ["항목","그린리모델링 이전", "그린리모델링 이후", "운영특성 반영"],
        )
    
    def prettify_latex_table(
        tex: str,
        header_color: str = "EAEAEA",
        arraystretch: float = 1.1,
        fontsize: str = r"\small",
    ) -> str:
        lines = tex.splitlines()
        new_lines = []
        in_tabular = False
        header_done = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith(r"\begin{tabular}"):
                in_tabular = True
                new_lines.append(r"\begingroup")
                new_lines.append(fontsize)
                new_lines.append(rf"\renewcommand{{\arraystretch}}{{{arraystretch}}}")
                new_lines.append(line)
                new_lines.append(r"\hline")
                continue

            if stripped.startswith(r"\end{tabular}"):
                in_tabular = False
                new_lines.append(line)
                new_lines.append(r"\renewcommand{\arraystretch}{1}")
                new_lines.append(r"\endgroup")
                continue

            if in_tabular and stripped.endswith(r"\\"):
                if not header_done:
                    new_lines.append(rf"\rowcolor[HTML]{{{header_color}}}")
                    header_done = True
                new_lines.append(line)
                new_lines.append(r"\hline")
                continue

            new_lines.append(line)

        return "\n".join(new_lines)
    
    def highlight_changed_row(row):
        cols = ["그린리모델링 이전", "그린리모델링 이후", "운영특성 반영"]

        # "-", NaN 등은 문자열로 통일해서 비교
        values = [str(row[c]).strip() for c in cols]

        changed = len(set(values)) > 1

        if changed:
            return [
                "background-color: #FFF2CC; font-weight: bold;"
                for _ in row
            ]
        else:
            return ["" for _ in row]
    
    tex = (
        df.style
        .hide(axis="index")
        .apply(highlight_changed_row, axis=1)
        .format(escape="latex")   # %, _, & 같은 LaTeX 특수문자 자동 처리
        .to_latex(
            hrules=False,
            convert_css=True,
            column_format=(
                r">{\centering\arraybackslash}p{4cm}|"
                r">{\centering\arraybackslash}p{4cm}|"
                r">{\centering\arraybackslash}p{4cm}|"
                r">{\centering\arraybackslash}p{4cm}"
            ),
        )
        .replace("~", "-")
    )

    tex = prettify_latex_table(tex, header_color="EAEAEA")
    return df,tex


def parse_equinity(masterdict: dict) -> str:
    
    df = pd.DataFrame(
        [
            [
                "벽체단열",
                masterdict.get("GR이후_그린리모델링 공사내역_벽체단열_보고서"),
                masterdict.get("GR이후_그린리모델링 공사내역_벽체단열_현장확인"),
                masterdict.get("GR이후_그린리모델링 공사내역_벽체단열_일치여부"),
                "",
            ],
            [
                "지붕단열",
                masterdict.get("GR이후_그린리모델링 공사내역_지붕단열_보고서"),
                masterdict.get("GR이후_그린리모델링 공사내역_지붕단열_현장확인"),
                masterdict.get("GR이후_그린리모델링 공사내역_지붕단열_일치여부"),
                "",
            ],
            [
                "바닥단열",
                masterdict.get("GR이후_그린리모델링 공사내역_바닥단열_보고서"),
                masterdict.get("GR이후_그린리모델링 공사내역_바닥단열_현장확인"),
                masterdict.get("GR이후_그린리모델링 공사내역_바닥단열_일치여부"),
                "",
            ],
            [
                "창호",
                masterdict.get("GR이후_그린리모델링 공사내역_창호_보고서"),
                masterdict.get("GR이후_그린리모델링 공사내역_창호_현장확인"),
                masterdict.get("GR이후_그린리모델링 공사내역_창호_일치여부"),
                "",
            ],
            [
                "환기장치",
                masterdict.get("GR이후_그린리모델링 공사내역_환기장치_보고서"),
                masterdict.get("GR이후_그린리모델링 공사내역_환기장치_현장확인"),
                masterdict.get("GR이후_그린리모델링 공사내역_환기장치_일치여부"),
                "",
            ],
            [
                "냉난방장치",
                masterdict.get("GR이후_그린리모델링 공사내역_냉난방장치_보고서"),
                masterdict.get("GR이후_그린리모델링 공사내역_냉난방장치_현장확인"),
                masterdict.get("GR이후_그린리모델링 공사내역_냉난방장치_일치여부"),
                "",
            ],
            [
                "고효율 보일러",
                masterdict.get("GR이후_그린리모델링 공사내역_고효율 보일러_보고서"),
                masterdict.get("GR이후_그린리모델링 공사내역_고효율 보일러_현장확인"),
                masterdict.get("GR이후_그린리모델링 공사내역_고효율 보일러_일치여부"),
                "",
            ],
            [
                "조명(LED)",
                masterdict.get("GR이후_그린리모델링 공사내역_조명(LED)_보고서"),
                masterdict.get("GR이후_그린리모델링 공사내역_조명(LED)_현장확인"),
                masterdict.get("GR이후_그린리모델링 공사내역_조명(LED)_일치여부"),
                "",
            ]
        ],
        columns = ["항목","보고서","현장확인","일치여부","비고"],
    )
    
    def prettify_latex_table(tex: str, header_color: str = "EAEAEA", arraystretch: float = 1) -> str:
        lines = tex.splitlines()
        new_lines = []
        in_tabular = False
        header_done = False

        for line in lines:
            stripped = line.strip()

            if stripped.startswith(r"\begin{tabular}"):
                in_tabular = True
                new_lines.append(rf"\renewcommand{{\arraystretch}}{{{arraystretch}}}")
                new_lines.append(line)
                new_lines.append(r"\hline")
                continue

            if stripped.startswith(r"\end{tabular}"):
                in_tabular = False
                new_lines.append(line)
                new_lines.append(r"\renewcommand{\arraystretch}{1}")
                continue

            if in_tabular and stripped.endswith(r"\\"):
                if not header_done:
                    new_lines.append(rf"\rowcolor[HTML]{{{header_color}}}")
                    header_done = True
                new_lines.append(line)
                new_lines.append(r"\hline")
                continue

            new_lines.append(line)

        return "\n".join(new_lines)
        
    tex = (
        df.style
        .hide(axis="index")
        .format(escape="latex")   # %, _, & 같은 LaTeX 특수문자 자동 처리
        .to_latex(
            hrules=False,         # hline은 우리가 직접 넣을 것
            column_format=(
                r">{\centering\arraybackslash}p{4cm}|"
                r">{\centering\arraybackslash}p{2.5cm}|"
                r">{\centering\arraybackslash}p{2.5cm}|"
                r">{\centering\arraybackslash}p{2.5cm}|"
                r">{\centering\arraybackslash}p{4.5cm}"
            ),
        )
        .replace("~", "-")
    )

    tex = prettify_latex_table(tex, header_color="EAEAEA")
    return tex

def build_report(
    before_rebexcelpath:str,
    after_rebexcelpath :str,
    afterN_rebexcelpath:str,
    before_grrpath:str,
    after_grrpath :str,
    afterN_grrpath:str,
    commentdict   :dict[str,str],
    masterdict    :dict,
    pdfpath:str,
    ) -> None:
    
    # resultdata
    with open(before_grrpath, "r") as f:
        grrbefore = json.load(f)
    with open(after_grrpath, "r") as f:
        grrafter  = json.load(f)
    with open(afterN_grrpath, "r") as f:
        grrafterN = json.load(f)
    
    # checklist
    checklistbefore = 현장조사체크리스트.from_excel(before_rebexcelpath)
    checklistafter  = 현장조사체크리스트.from_excel(after_rebexcelpath)
    checklistafterN = 현장조사체크리스트.from_excel(afterN_rebexcelpath)
    
    # metadata
    building_info = pd.read_excel(before_rebexcelpath, sheet_name="건물정보", usecols=range(6), nrows=1).iloc[0]
    metadata = MetaData(
        escape_str(building_info["건물명"])     ,
        f"{grrbefore["building"]["total_area"]:.1f}",
        building_info["주소"],
        building_info["허가일자"]   , 
    )
    
    # get figures
    fig_detail, fig_summary = draw_mainfigures(grrbefore, grrafter, grrafterN)
    fig_detail.savefig(FIG_DIR / "simulation_results.png", dpi=400, format="png", bbox_inches="tight")
    fig_summary.savefig(FIG_DIR / "energy_summary.png", dpi=400, format="png", bbox_inches="tight")
    
    # get figures (by weather)
    fig_page3_summary = draw_page3_summaryfigures(grrbefore, grrafter, grrafterN)
    fig_page3_summary.savefig(FIG_DIR / "page3_summary.png", dpi=400, format="png", bbox_inches="tight")
        
    # arrange the results
    summarytablestyle = {
    "column_format":">{\\centering\\arraybackslash}p{4cm}" + "|>{\\centering\\arraybackslash}p{4.5cm}" * 3,
    "clines":"all;data",  
    "hrules":True,
    }
    
    lpguse_conditions = [k for k, v in parse_lpg_usage(masterdict).items() if v]
    if len(lpguse_conditions) == 0:
        lpgusetext = ""
    else:
        lpgusetext = ", ".join(lpguse_conditions) + " 에서 LPG보일러 사용하는 건물임"

    pk_value = masterdict.get("관리건축물대장PK")

    if pd.isna(pk_value) or str(pk_value).strip() == "":
        building_register_pk = "-"
    elif isinstance(pk_value, float) and pk_value.is_integer():
        building_register_pk = str(int(pk_value))
    else:
        building_register_pk = str(pk_value).strip()

    building_register_pk = escape_str(building_register_pk)

    # 결측 시 'nan' 인쇄 방지: GR 준공일자, 층수
    date_value = masterdict.get("GR이후_그린리모델링 허가일자")
    gr_completion_date = "-" if pd.isna(date_value) else escape_str(str(date_value).strip())

    def _floor_str(col: str) -> str:
        v = masterdict.get(col)
        return "-" if pd.isna(v) else f"{v:.0f}"
    floors_below = _floor_str("GR이전_규모_지하")
    floors_above = _floor_str("GR이전_규모_지상")

    context = {
        "metadata": metadata,
        "master"  : masterdict,
        "imagesrc": (Path(__file__).parent / "imagesrc").resolve().as_posix(),
        "surveychangetex": parse_surveychange(masterdict)[1],
        "majorchangetex" :  parse_majorchange(masterdict),
        "perfchangetex"   : parse_perfchange(masterdict),
        "equinitytex"    : parse_equinity(masterdict),
        "lpgusetext"    : lpgusetext,
        "summarytabletex" : [df.style.format(lambda x: f"{x:>6,.1f}" if isinstance(x, int|float) else x).to_latex(**summarytablestyle).replace(r"\toprule", r"\hline").replace(r"\midrule", r"\hline").replace(r"\bottomrule", r"\hline") for df in summarytable(grrbefore, grrafter, grrafterN)],
        "comment": {k:escape_str(v) for k,v in commentdict.items()},
        "building_register_pk": building_register_pk,
        "gr_completion_date": gr_completion_date,
        "floors_below": floors_below,
        "floors_above": floors_above,
    }
    
    # build
    template = Template(TEMPLATEPATH.read_text(encoding="utf-8"))
    rendered_tex = template.render(**context)
    texpath = BUILD_DIR / "report.tex"
    os.makedirs(BUILD_DIR, exist_ok=True)
    with open(texpath, "w", encoding="utf-8") as f:
        f.write(rendered_tex)
    
    cmd = ["latexmk", "-xelatex", "-interaction=nonstopmode", "-halt-on-error", texpath.name]
    subprocess.run(cmd, cwd=str(BUILD_DIR), check=True)
    
    shutil.copy(str(texpath).replace(".tex",".pdf"), pdfpath)
    
    return
