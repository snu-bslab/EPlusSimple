"""
v-070 수정사항: 입력 엑셀(GR이전, GR이후, N년차)로 개별 보고서의 표를 만든다 (masterdb 대신)

  stages = {"GR이전": read_stage(엑셀), "GR이후": ..., "N년차": ...}
  majorchange_table(stages), perfchange_table(stages), survey_table(stages, 구분), equinity_table()

  외피, 창호, 조명, 침기 : 시뮬레이션 모델(GreenRetrofitModel)의 면적 가중 평균 (법규기준 구조체 포함)
  난방1, 냉방1          : 공급설비에 연결된 생산설비(+ 패키지에어컨, 전기방열기) 중 용량 합이 가장 큰 유형
  운영                  : 용도프로필 탭. 인원은 합계, 시간·온도는 가장 넓은 바닥면적에 적용된 값
  엑셀에 없는 현장조사 항목은 (미기입)
"""

import os

import pandas as pd

from epsimple import GreenRetrofitModel
from .preprocess import process_excel_file
from .postprocess import 용도프로필적용
from .comparison import time_text

MISSING = "(미기입)"
STAGES  = ["GR이전", "GR이후", "N년차"]
COLUMNS = ["그린리모델링 이전", "그린리모델링 이후", "운영특성 반영"]
SHEETS  = ["실", "구조체_면", "구조체_개구부", "공급설비", "생산설비", "환기설비", "PV패널"]
DAYS    = {"monday": "월", "tuesday": "화", "wednesday": "수", "thursday": "목", "friday": "금", "saturday": "토", "sunday": "일"}
BASIS   = {
    "외피"    : [("구조체_면", "구조체_근거")],
    "창호"    : [("구조체_개구부", "개구부구조체_근거")],
    "조명밀도": [("실", "조명밀도_근거")],
    "침기율"  : [("실", "침기율_근거")],
    "설비"    : [("생산설비", "생산설비_근거"), ("공급설비", "공급설비_근거")],
    "환기"    : [("환기설비", "환기설비_근거")],
    "태양광"  : [("PV패널", "PV패널_근거")],
}
EQUINITY_ITEMS = ["벽체단열", "지붕단열", "바닥단열", "창호", "환기장치", "냉난방장치", "고효율 보일러", "조명(LED)"]


# ---------------------------------------------------------------------------- #
#                                  READ EXCEL                                  #
# ---------------------------------------------------------------------------- #

def read_stage(path:str) -> dict:
    """엑셀 하나에서 보고서에 쓰는 값을 모은다"""

    sheets = {name: read_sheet(path, name) for name in SHEETS}
    stage  = envelope_values(path)
    heating_units = find_heating_units(sheets)
    stage["난방"]   = main_system(heating_units)
    stage["냉방"]   = main_system(find_cooling_units(sheets))
    stage["환기"]   = ventilation(sheets["환기설비"])
    stage["태양광"] = solar(sheets["PV패널"])
    stage["LPG"]    = any("LPG" in str(unit["열원"]).upper() for unit in heating_units)
    stage["근거"]   = {part: basis(sheets, columns) for part, columns in BASIS.items()}
    stage["운영"]   = operation(path, sheets["실"])
    return stage


def read_sheet(path:str, name:str) -> pd.DataFrame:
    """2행이 머리글인 탭. 이름이 빈 행은 버린다"""
    try:
        sheet = pd.read_excel(path, sheet_name=name, header=1)
    except ValueError:
        return pd.DataFrame(columns=["이름"])
    return sheet.loc[sheet["이름"].notna()]


def envelope_values(path:str) -> dict:
    processed = process_excel_file(path, verbose=False)
    try:
        grm = GreenRetrofitModel.from_excel(processed)
    finally:
        os.remove(processed)

    windows     = grm.exteriorwindows
    window_area = sum(window.area for window in windows)
    return {
        "외벽"    : positive(grm.averaged_exteriorwall_Uvalue),
        "지붕"    : positive(grm.averaged_exteriorroof_Uvalue),
        "바닥"    : positive(grm.averaged_exteriorfloor_Uvalue),
        "창호"    : positive(grm.averaged_window_Uvalue),
        "SHGC"    : sum(window.area * window.construction.g for window in windows) / window_area if window_area > 0 else None,
        "조명밀도": positive(grm.averaged_lightdensity),
        "침기율"  : grm.averaged_infiltration,
    }


def used_sources(sheets:dict) -> pd.DataFrame:
    """공급설비에 연결된 생산설비 (급탕 전용 등 연결 안 된 설비는 뺀다)"""
    names = set(sheets["공급설비"]["생산설비명"].dropna()) if "생산설비명" in sheets["공급설비"] else set()
    return sheets["생산설비"].loc[sheets["생산설비"]["이름"].isin(names)]


def unit(kind, fuel, capacity, cop=None, efficiency=None) -> dict:
    return {"유형": kind, "열원": fuel, "용량": number(capacity), "COP": number(cop), "효율": number(efficiency)}


def find_heating_units(sheets:dict) -> list[dict]:
    units = []
    for _, row in used_sources(sheets).iterrows():
        if pd.notna(row.get("난방용량 [W]")) or row["유형"] == "지역난방":
            efficiency = row.get("효율 [%]") if pd.notna(row.get("효율 [%]")) else row.get("연동보일러 효율 [%]")
            units.append(unit(row["유형"], row.get("연료종류"), row.get("난방용량 [W]"), row.get("난방COP [W/W]"), efficiency))
    for _, row in sheets["공급설비"].iterrows():
        if row["유형"] == "전기방열기":
            units.append(unit("전기방열기", "전기", times(row.get("난방용량 [W]"), row.get("대수"))))
        if row["유형"] == "전기바닥난방":
            units.append(unit("전기바닥난방", "전기", None))
    return units


def find_cooling_units(sheets:dict) -> list[dict]:
    units = []
    for _, row in used_sources(sheets).iterrows():
        if pd.notna(row.get("냉방용량 [W]")):
            units.append(unit(row["유형"], row.get("연료종류"), row.get("냉방용량 [W]"), row.get("냉방COP [W/W]")))
    for _, row in sheets["공급설비"].iterrows():
        if row["유형"] == "패키지에어컨":
            units.append(unit("패키지에어컨", "전기", times(row.get("냉방용량 [W]"), row.get("대수")), row.get("냉방COP [W/W]")))
    return units


def main_system(units:list[dict]) -> dict|None:
    """유형별 용량 합이 가장 큰 유형. 용량은 합, COP 와 효율은 용량 가중 평균"""
    if not units:
        return None
    groups = {}
    for item in units:
        groups.setdefault(item["유형"], []).append(item)
    kind, group = max(groups.items(), key=lambda pair: sum(item["용량"] or 0 for item in pair[1]))
    fuels = sorted({str(item["열원"]) for item in group if pd.notna(item["열원"])})
    return {
        "유형": kind,
        "열원": ", ".join(fuels) or "-",
        "용량": sum(item["용량"] or 0 for item in group) or None,
        "COP" : weighted_mean([(item["COP"], item["용량"]) for item in group]),
        "효율": weighted_mean([(item["효율"], item["용량"]) for item in group]),
    }


def ventilation(rows:pd.DataFrame) -> dict|None:
    """전열교환기 효율 [%], 풍량 x 대수 가중 평균. 엑셀에 0.74 처럼 비율로 적혀 있으면 % 로 바꾼다"""
    if rows.empty:
        return None
    weights = [times(row.get("용량 [CMH]"), row.get("대수")) for _, row in rows.iterrows()]
    return {
        "난방": weighted_mean(zip(rows["난방효율 [%]"].map(percent), weights)),
        "냉방": weighted_mean(zip(rows["냉방효율 [%]"].map(percent), weights)),
    }


def solar(rows:pd.DataFrame) -> dict|None:
    if rows.empty:
        return None
    return {"면적": rows["면적"].sum(), "효율": weighted_mean(zip(rows["효율 [%]"], rows["면적"]))}


def basis(sheets:dict, columns:list[tuple[str,str]]) -> set[str]:
    """근거 열에 적힌 값들"""
    values = set()
    for sheet, column in columns:
        if column in sheets[sheet]:
            values |= {str(v).strip() for v in sheets[sheet][column].dropna() if str(v).strip() not in ("", "-")}
    return values


def operation(path:str, rooms:pd.DataFrame) -> dict:
    """용도프로필 탭을 건물 하나의 값으로 줄인다"""
    try:
        applied = 용도프로필적용.from_excel(path)
    except Exception:
        return {}

    zones = []
    for _, room in rooms.iterrows():
        profile = applied.profiles.get(applied.zone_profile.get(room["이름"]))
        if profile is not None:
            zones.append((profile, number(room.get("바닥 면적 [m2]")) or 0))
    occupied = [(profile, area) for profile, area in zones if profile.has_occupancy]

    values = {}
    if occupied:
        values["상주인원"] = sum(profile.상주인원 for profile, _ in occupied)
        values["방문인원"] = sum(visitors(profile) for profile, _ in occupied)
        values["체류시간"] = main_value([(profile.방문체류분, area) for profile, area in occupied if visitors(profile) > 0])
        values["재실시간"] = main_value([(f"{time_text(profile.상주시작)}~{time_text(profile.상주종료)}", area) for profile, area in occupied])
        values["운영요일"] = main_value([(",".join(DAYS[day] for day in profile.상주요일) or "-", area) for profile, area in occupied])
        values["운영기간"] = main_value([(f"{profile.운영시작월}~{profile.운영종료월}월", area) for profile, area in occupied])
        values["평균재실"] = sum(
            profile.상주인원 + visitors(profile) * profile.방문체류분 / 60 / profile.상주시간
            for profile, _ in occupied
        )
    for mode, attr in [("난방", "난방설비1"), ("냉방", "냉방설비1")]:
        values.update(equipment_values(mode, [(getattr(profile, attr), area) for profile, area in zones]))
    return values


def equipment_values(mode:str, pairs:list) -> dict:
    """난방설비(냉방설비) 항목. 비어 있으면 주용도 기준, 00:00~00:00 이면 미사용"""
    written = [(item, area) for item, area in pairs if item is not None]
    used    = [(item, area) for item, area in written if item.사용여부]
    if not used:
        text = "미사용" if written else "주용도 기준"
        return {f"{mode}기간": text, f"{mode}시간": text, f"{mode}온도": text}
    return {
        f"{mode}기간": main_value([(f"{item.시작월}~{item.종료월}월", area) for item, area in used]),
        f"{mode}시간": main_value([(f"{time_text(item.시작)}~{time_text(item.종료)}", area) for item, area in used]),
        f"{mode}온도": main_value([(item.설정온도, area) for item, area in used]),
    }


def visitors(profile) -> int:
    """시뮬레이션과 같이 방문 요일이 있을 때만 방문인원을 센다"""
    return profile.방문인원 if profile.방문요일 else 0


# ---------------------------------------------------------------------------- #
#                                    TABLES                                    #
# ---------------------------------------------------------------------------- #

def majorchange_table(stages:dict) -> pd.DataFrame:
    """1쪽 주요 변화. 세 시점 값이 다른 행만 남긴다"""

    def heating(stage):
        system = stage["난방"]
        if system is None:
            return "-"
        if "히트펌프" in system["유형"]:
            return fmt(system["COP"], 2)
        return fmt(system["효율"], 1)

    def heating_note():
        kinds = {stage["난방"]["유형"] for stage in stages.values() if stage["난방"]}
        if kinds and all("히트펌프" in kind for kind in kinds):
            return "[W/W]"
        if any("히트펌프" in kind for kind in kinds):
            return "히트펌프 [W/W], 보일러 [%]"
        return "[%]"

    rows = {
        ("기술요소", "외피")        : ([fmt(s["외벽"], 3) for s in stages.values()], "[W/m²·K]"),
        ("기술요소", "창호")        : ([fmt(s["창호"], 3) for s in stages.values()], "[W/m²·K]"),
        ("기술요소", "냉방")        : ([fmt(s["냉방"] and s["냉방"]["COP"], 2) for s in stages.values()], "[W/W]"),
        ("기술요소", "난방")        : ([heating(s) for s in stages.values()], heating_note()),
        ("기술요소", "환기")        : ([ventilation_text(s["환기"]) for s in stages.values()], "[난방] / [냉방]"),
        ("기술요소", "조명")        : ([fmt(s["조명밀도"], 2) for s in stages.values()], "[W/m²]"),
        ("기술요소", "신재생")      : ([solar_text(s["태양광"]) for s in stages.values()], "[면적 m²], [효율 %]"),
        ("운영특성", "재실인원")    : ([fmt(s["운영"].get("평균재실"), 1) for s in stages.values()], "명, 상주+방문 평균"),
        ("운영특성", "난방설정온도"): ([fmt(s["운영"].get("난방온도"), 1) for s in stages.values()], "℃"),
        ("운영특성", "냉방설정온도"): ([fmt(s["운영"].get("냉방온도"), 1) for s in stages.values()], "℃"),
    }
    df = pd.DataFrame(
        [values + [note] for values, note in rows.values()],
        columns=STAGES + ["비고"],
        index=pd.MultiIndex.from_tuples(rows.keys(), names=["대분류", "구분"]),
    )
    return df[df[STAGES].nunique(axis=1) > 1]


def perfchange_table(stages:dict) -> pd.DataFrame:
    """2쪽 요소기술 성능 변화"""

    def row(label, values, part):
        return [label] + values + ["/".join(sorted(set().union(*(s["근거"][part] for s in stages.values())))) or "-"]

    def each(get):
        return [get(stage) for stage in stages.values()]

    def system(mode, key, digits=2, scale=1):
        values = []
        for stage in stages.values():
            item = stage[mode]
            if item is None:
                values.append("-")
            elif key == "유형열원":
                values.append(f"{item['유형']} / {item['열원']}")
            else:
                values.append(fmt(item[key] and item[key] * scale, digits))
        return values

    rows = [
        row("외벽 열관류율 [W/m²·K]"  , each(lambda s: fmt(s["외벽"], 3)), "외피"),
        row("창호 열관류율 [W/m²·K]"  , each(lambda s: fmt(s["창호"], 3)), "창호"),
        row("창호 취득계수(SHGC)"     , each(lambda s: fmt(s["SHGC"], 3)), "창호"),
        row("지붕 열관류율 [W/m²·K]"  , each(lambda s: fmt(s["지붕"], 3)), "외피"),
        row("바닥 열관류율 [W/m²·K]"  , each(lambda s: fmt(s["바닥"], 3)), "외피"),
        row("조명밀도 [W/m²]"         , each(lambda s: fmt(s["조명밀도"], 2)), "조명밀도"),
        row("침기율 [ACH@50]"         , each(lambda s: fmt(s["침기율"], 2)), "침기율"),
        row("난방1 유형/열원"         , system("난방", "유형열원"), "설비"),
        row("난방1 용량 [kW]"         , system("난방", "용량", 2, 1E-3), "설비"),
        row("난방1 COP [W/W]"         , system("난방", "COP"), "설비"),
        row("난방1 효율 [%]"          , system("난방", "효율", 1), "설비"),
        row("냉방1 유형/열원"         , system("냉방", "유형열원"), "설비"),
        row("냉방1 용량 [kW]"         , system("냉방", "용량", 2, 1E-3), "설비"),
        row("냉방1 COP [W/W]"         , system("냉방", "COP"), "설비"),
        row("전열교환기 난방효율 [%]" , each(lambda s: fmt(s["환기"] and s["환기"]["난방"], 1)), "환기"),
        row("전열교환기 냉방효율 [%]" , each(lambda s: fmt(s["환기"] and s["환기"]["냉방"], 1)), "환기"),
        row("태양광 설치여부"         , each(lambda s: "O" if s["태양광"] else "X"), "태양광"),
        row("태양광 면적 [m²]"        , each(lambda s: fmt(s["태양광"] and s["태양광"]["면적"], 1)), "태양광"),
        row("태양광 효율 [%]"         , each(lambda s: fmt(s["태양광"] and s["태양광"]["효율"], 1)), "태양광"),
    ]
    return pd.DataFrame(rows, columns=["항목"] + COLUMNS + ["근거"])


def survey_table(stages:dict, kind:str) -> pd.DataFrame:
    """2쪽 운영특성. 용도프로필 탭 값, 엑셀에 없는 현장조사 항목은 (미기입)"""

    def each(key, digits=None, unit=""):
        values = []
        for stage in stages.values():
            value = stage["운영"].get(key)
            if value is None:
                values.append("-")
            elif digits is not None and not isinstance(value, str):
                values.append(f"{value:.{digits}f}{unit}")
            else:
                values.append(str(value))
        return values

    visit = [
        "-" if stage["운영"].get("방문인원") is None
        else f"{stage['운영']['방문인원']}명 / {stage['운영'].get('체류시간') or 0}분"
        for stage in stages.values()
    ]
    rows = [
        ["상주인원 [명]"       ] + each("상주인원", 0),
        ["방문인원 / 체류시간" ] + visit,
        ["재실시간"            ] + each("재실시간"),
        ["운영요일"            ] + each("운영요일"),
        ["운영기간"            ] + each("운영기간"),
        ["난방 사용기간"       ] + each("난방기간"),
        ["난방 사용시간"       ] + each("난방시간"),
        ["난방 설정온도(℃)"   ] + each("난방온도", 1),
        ["냉방 사용기간"       ] + each("냉방기간"),
        ["냉방 사용시간"       ] + each("냉방시간"),
        ["냉방 설정온도(℃)"   ] + each("냉방온도", 1),
    ]
    if kind == "어린이집":
        survey_only = ["기본보육 인원", "연장보육A 인원", "연장보육B 인원", "야간보육 인원", "주말보육 인원"]
    else:
        survey_only = ["외근시간", "외근요일", "관사 수"]
    rows += [[item] + [MISSING] * 3 for item in survey_only]
    return pd.DataFrame(rows, columns=["항목"] + COLUMNS)


def equinity_table() -> pd.DataFrame:
    """4쪽 공사내역 일치 여부. 현장조사 항목이라 (미기입)"""
    return pd.DataFrame(
        [[item, MISSING, MISSING, MISSING, ""] for item in EQUINITY_ITEMS],
        columns=["항목", "보고서", "현장확인", "일치여부", "비고"],
    )


def building_kind(name:str) -> str:
    """건물명으로 구분 (masterdb 총괄리스트의 '구분' 값과 같은 이름)"""
    for kind in ["어린이집", "보건진료소", "보건지소", "보건소", "요양병원"]:
        if kind in str(name).replace(" ", ""):
            return kind
    return MISSING


# ---------------------------------------------------------------------------- #
#                                    HELPERS                                   #
# ---------------------------------------------------------------------------- #

def number(value) -> float|None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(value) else value


def positive(value) -> float|None:
    """모델 평균값은 해당 면이 없으면 0 이므로 0 은 '없음'"""
    value = number(value)
    return value if value else None


def times(value, count) -> float|None:
    """값 x 대수 (대수가 비어 있으면 1대)"""
    value = number(value)
    if value is None:
        return None
    return value * (number(count) or 1)


def percent(value) -> float|None:
    value = number(value)
    if value is None:
        return None
    return value * 100 if value <= 1 else value


def weighted_mean(pairs) -> float|None:
    """(값, 가중치) 평균. 가중치가 모두 비어 있으면 단순 평균"""
    pairs = [(number(value), number(weight) or 0) for value, weight in pairs if number(value) is not None]
    if not pairs:
        return None
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        return sum(value for value, _ in pairs) / len(pairs)
    return sum(value * weight for value, weight in pairs) / total


def main_value(pairs:list):
    """(값, 바닥면적) 중 면적 합이 가장 큰 값"""
    areas = {}
    for value, area in pairs:
        areas[value] = areas.get(value, 0) + area
    if not areas:
        return None
    return max(areas, key=areas.get)


def fmt(value, digits:int) -> str:
    if isinstance(value, str):
        return value
    value = number(value)
    return "-" if value is None else f"{value:.{digits}f}"


def ventilation_text(values:dict|None) -> str:
    if values is None:
        return "-"
    return f"{fmt(values['난방'], 1)}% / {fmt(values['냉방'], 1)}%"


def solar_text(values:dict|None) -> str:
    if values is None:
        return "-"
    return f"{fmt(values['면적'], 1)} m², {fmt(values['효율'], 1)}%"
