"""
v-070 수정사항: 3단계 엑셀(GR이전, GR이후, N년차)과 시뮬레이션 결과(grr)로 개별 엑셀 보고서를 만든다

  build_excel_report({"GR이전": 엑셀, ...}, {"GR이전": grr dict, ...}, 출력.xlsx, comment=...)

표와 건물 정보는 입력 엑셀에서 만든다 (report_tables.py). 엑셀에 없는 현장조사 항목은 (미기입).
comment.csv 가 있으면 조사자 의견과 만족도를 채우고, 없으면 (미기입).
"""

import os
import tempfile

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import report
from .auxiliary import MAPPING_DIR
from .filename import read_filename
from .weather import find_station, station_name, tmy_filepath, STATIONS
from .excel_report import render_report, export_pdf
from .report_tables import (
    MISSING, read_stage, building_kind,
    majorchange_table, perfchange_table, survey_table, equinity_table,
)

TEMPLATE   = os.path.join(MAPPING_DIR, "report_template.xlsx")
STAGES     = ["GR이전", "GR이후", "N년차"]
POINT_KEYS = ["동절기 실내 온도", "동절기 실내 습도", "하절기 실내 온도", "하절기 실내 습도", "공기질", "음환경", "빛환경"]
COMMENT_KEYS = ["연면적", "hvac", "occupant", "satisfaction", "conclusion", "point"] + POINT_KEYS


def build_excel_report(
    excel_paths:dict,
    grrs       :dict,
    out_xlsx   :str,
    *,
    comment    :str|None=None,
    template   :str|None=None,
    pdf        :bool=True,
    ) -> tuple[list[str], list[str]]:
    """보고서를 만들고 (만든 파일들, 알림 메시지들) 을 돌려준다"""

    messages = []
    info     = read_filename(excel_paths["GR이전"])
    building = read_building_sheet(excel_paths["GR이전"])
    before, after, afterN = grrs["GR이전"], grrs["GR이후"], grrs["N년차"]

    # 엑셀 (같은 파일을 여러 시점에 쓰면 한 번만 읽는다)
    read = {}
    for stage in STAGES:
        if excel_paths[stage] not in read:
            read[excel_paths[stage]] = read_stage(excel_paths[stage])
    stages = {stage: read[excel_paths[stage]] for stage in STAGES}
    kind   = building_kind(info["건물명"] or building.get("건물명"))

    commentdict = {key: MISSING for key in COMMENT_KEYS}
    if comment:
        try:
            commentdict = find_comment(comment, info, building)
        except Exception as error:
            messages.append(f"comment.csv 에서 건물을 찾지 못해 조사자 의견을 (미기입)으로 두었습니다. ({error})")
    else:
        messages.append("comment.csv 가 없어 조사자 의견과 만족도를 (미기입)으로 두었습니다.")
    commentdict["연면적"] = f"{before['building']['total_area']:.1f}"

    # 표
    summary1, summary2 = report.summarytable(before, after, afterN)
    summary1.index = ["건물특성", "운영특성", "1차에너지 [kWh/m²]", "온실가스 [kgCO₂eq/m²]"]
    summary2.index = ["1차에너지 [kWh/m²]", "온실가스 [kgCO₂eq/m²]"]
    tables = {
        "majorchange" : majorchange_table(stages),
        "summary1"    : summary1,
        "summary2"    : summary2,
        "perfchange"  : perfchange_table(stages),
        "surveychange": survey_table(stages, kind),
        "equinity"    : equinity_table(),
    }

    # 값
    weather = weather_info(excel_paths)
    lpg     = [stage for stage in STAGES if stages[stage]["LPG"]]
    pk      = info["PK"] or building.get("PK코드")
    if isinstance(pk, float) and not pd.isna(pk):
        pk = int(pk)
    context = {
        "building_number": info["번호"] or "-",
        "metadata": {
            "name": building.get("건물명", "-"),
            "addr": building.get("주소", "-"),
            "date": text_or_dash(building.get("허가일자"))[:10],
        },
        "master"  : {"구분": kind},
        "comment" : commentdict,
        "building_register_pk": text_or_dash(pk),
        "gr_completion_date"  : f"{info['연도']}년" if info["연도"] else MISSING,
        "floors_below"  : floor(building.get("지하층수")),
        "floors_above"  : floor(building.get("지상층수")),
        "engine_version": "EPlusSimple V0.7.0",
        "weather"       : weather,
        "weather_text"  : weather["text"],
        "lpgusetext"    : "" if not lpg else "※ " + ", ".join(lpg) + " 에서 LPG보일러 사용하는 건물임",
    }

    # 그림과 렌더링
    with tempfile.TemporaryDirectory() as figure_dir:
        fig_detail, fig_summary = report.draw_mainfigures(before, after, afterN)
        fig_page3 = report.draw_page3_summaryfigures(before, after, afterN)
        images = {
            "energy_summary"    : (os.path.join(figure_dir, "energy_summary.png")    , 520, fig_summary),
            "page3_summary"     : (os.path.join(figure_dir, "page3_summary.png")     , 600, fig_page3  ),
            "simulation_results": (os.path.join(figure_dir, "simulation_results.png"), 600, fig_detail ),
        }
        for path, width, fig in images.values():
            fig.savefig(path, dpi=200, bbox_inches="tight")
            plt.close(fig)
        images = {name: (path, width) for name, (path, width, fig) in images.items()}
        render_report(template or TEMPLATE, out_xlsx, context, tables, images)

    files = [out_xlsx]
    if pdf:
        try:
            files.append(export_pdf(out_xlsx, out_xlsx.replace(".xlsx", ".pdf")))
        except Exception as error:
            messages.append(f"PDF 변환은 엑셀(Microsoft Excel)이 있어야 합니다. 엑셀 보고서만 만들었습니다. ({error})")

    return files, messages


def read_building_sheet(path:str) -> pd.Series:
    """건물정보 탭 첫 행. 070 은 2행이 머리글, v0.6 은 1행이 머리글"""

    info = pd.read_excel(path, sheet_name="건물정보", header=1, nrows=1)
    if "주소" not in info.columns:
        info = pd.read_excel(path, sheet_name="건물정보", nrows=1)
    return info.iloc[0]


def find_comment(path:str, info:dict, building:pd.Series) -> dict:
    """comment.csv 에서 번호+건물명 행을 찾아 별점(★)과 평균 점수를 만든다"""

    try:
        df = pd.read_csv(path, encoding="cp949")
    except UnicodeDecodeError:
        df = pd.read_csv(path, encoding="utf-8-sig")

    name = squeeze(info["건물명"] or building.get("건물명"))
    matched = df[df["건축물명"].map(squeeze) == name]
    if info["번호"] and str(info["번호"]).isdigit():
        matched = matched[pd.to_numeric(matched["고유번호"], errors="coerce") == int(info["번호"])]
    if matched.empty:
        raise ValueError(f"{name} 행이 없음")

    commentdict = matched.iloc[0, 2:].to_dict()
    commentdict["point"] = sum(int(commentdict[key]) for key in POINT_KEYS) / len(POINT_KEYS)
    for key in POINT_KEYS:
        commentdict[key] = "★" * int(commentdict[key]) + "☆" * (7 - int(commentdict[key]))
    return {
        key: f"{value:.1f}" if not isinstance(value, str) else value.replace(r"\n", "\\")
        for key, value in commentdict.items()
    }


def weather_info(excel_paths:dict) -> dict:
    """시점별로 실제 쓴 기상자료 (연도, 기상청 지점). 세 시점 연도가 다르면 나눠서 쓴다"""

    years, option, address = {}, "실제기상(AMY)", None
    for stage in STAGES:
        building = read_building_sheet(excel_paths[stage])
        address  = building["주소"]
        if "기상데이터옵션" not in building:                                   # v0.6 엑셀: 매핑표의 기준연도
            years[stage] = int(find_station(address)["기준연도_" + stage.replace("GR", "")])
            continue
        if pd.notna(building["기상데이터옵션"]):
            option = str(building["기상데이터옵션"])
        years[stage] = None if pd.isna(building.get("기준년도")) else int(building["기준년도"])

    row = find_station(address)
    if "AMY" not in option:
        epw = os.path.basename(tmy_filepath(address))
        return {"option": option, "year": "-", "station_number": "-", "station_name": "-",
                "station_address": "-", "region": row["시·군·구"], "text": f"표준기상(TMY) {epw}"}

    station = int(row["Station_num"])
    if len(set(years.values())) == 1:
        year_text = f"{years['GR이전']}년"
    else:
        year_text = " / ".join(f"{stage} {year}" for stage, year in years.items()) + "년"
    return {
        "option"         : option,
        "year"           : year_text,
        "station_number" : station,
        "station_name"   : station_name(station),
        "station_address": STATIONS.at[station, "소재지"] if station in STATIONS.index else "-",
        "region"         : row["시·군·구"],
        "text"           : f"{year_text} 기상청 {station_name(station)}({station}) 지점",
    }


def squeeze(text) -> str:
    return str(text).replace(" ", "")


def text_or_dash(value) -> str:
    return "-" if value is None or pd.isna(value) else str(value)


def floor(value) -> str:
    return "-" if value is None or pd.isna(value) else f"{float(value):.0f}"
