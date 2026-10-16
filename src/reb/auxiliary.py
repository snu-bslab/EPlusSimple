
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
import os
import re
from typing import Literal

# third-party modules
import pandas as pd

# local modules
from epsimple.constants import Directory # v-070 수정사항


# ---------------------------------------------------------------------------- #
#                                   VARIABLES                                  #
# ---------------------------------------------------------------------------- #

MAPPING_DIR        = os.path.join(os.path.dirname(__file__), "data")           # v-070 수정사항: 매핑표만 저장소에 둔다
WEATHTERDATA_DIR   = str(Directory.WEATHER_DATA_DIR.parent / "AMY")           # v-070 수정사항: epw 는 runtime/Weather/AMY (run setup 이 내려받음)
WEATHERDATA_MAPPER = pd.read_csv(os.path.join(MAPPING_DIR, "weatherdata_mapping.csv"), encoding="cp949")


# ---------------------------------------------------------------------------- #
#                                   FUNCTIONS                                  #
# ---------------------------------------------------------------------------- #

def find_weatherdata(
    loc    :str,
    simtype:Literal["이전","이후","N년차"]
    ) -> str:
    
    if loc not in WEATHERDATA_MAPPER["시·군·구"].values: loc = re.search(r"[\w ]+(?= \w+)", loc).group()
    loc_idx = WEATHERDATA_MAPPER.index[WEATHERDATA_MAPPER["시·군·구"] == loc][0]
    
    weatherloc  = WEATHERDATA_MAPPER.at[loc_idx, "Station_num"]
    weatheryear = WEATHERDATA_MAPPER.at[loc_idx, f"기준연도_{simtype}"]
    
    weatherdata_filename = f"{weatherloc}_{weatheryear}.epw"
    weatherdata_filepath = os.path.join(WEATHTERDATA_DIR, weatherdata_filename)
    
    return weatherdata_filepath