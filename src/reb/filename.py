# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #
"""
REB 엑셀 파일명 규칙 (v-070 수정사항)

    GR준공연도_파일번호_PK코드_건물명_시점.xlsx
    예) 2020_191_30170-30467_대전광역시 서구 보건소_GR이후.xlsx

v0.6 파일명 '번호_건물명_시점_운영.xlsx' 도 읽는다. 이때 연도와 PK 는 None.
시점 뒤에 붙는 '_운영', '_preprocess' 는 무시한다.
"""

# built-in modules
import os


# ---------------------------------------------------------------------------- #
#                                   VARIABLES                                  #
# ---------------------------------------------------------------------------- #

CONDITIONS = ["GR이전", "GR이후", "N년차"]


# ---------------------------------------------------------------------------- #
#                                   MAIN FUNC                                  #
# ---------------------------------------------------------------------------- #

def read_filename(filepath:str) -> dict:
    """파일명에서 연도, 번호, PK, 건물명, 시점을 읽는다. 못 읽은 항목은 None"""

    stem  = os.path.splitext(os.path.basename(filepath))[0]
    parts = stem.split("_")
    info  = {"연도": None, "번호": None, "PK": None, "건물명": None, "시점": None}

    # 시점 위치
    position = None
    for i, part in enumerate(parts):
        if part in CONDITIONS:
            position = i
            break
    if position is None:
        return info
    info["시점"] = parts[position]

    # 2026 형식: 연도_번호_PK_건물명_시점
    first = parts[0]
    if len(first) == 4 and first.isdigit() and position >= 4:
        info["연도"]   = first
        info["번호"]   = parts[1]
        info["PK"]     = parts[2]
        info["건물명"] = "_".join(parts[3:position])

    # v0.6 형식: 번호_건물명_시점
    elif position >= 2:
        info["번호"]   = first
        info["건물명"] = "_".join(parts[1:position])

    return info
