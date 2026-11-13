
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


# ---------------------------------------------------------------------------- #
#                                   VARIABLES                                  #
# ---------------------------------------------------------------------------- #

WEATHTERDATA_DIR   = os.path.join(os.path.dirname(__file__), "data")
WEATHERDATA_MAPPER = pd.read_csv(os.path.join(WEATHTERDATA_DIR, "weatherdata_mapping.csv"), encoding="cp949")


# ---------------------------------------------------------------------------- #
#                                   FUNCTIONS                                  #
# ---------------------------------------------------------------------------- #

def find_weatherdata(
    loc    :str,
    simtype:Literal["이전","이후","N년차"],
    *,
    weather_year: int | None = None
    ) -> str:
    
    if loc not in WEATHERDATA_MAPPER["시·군·구"].values: loc = re.search(r"[\w ]+(?= \w+)", loc).group()
    loc_idx = WEATHERDATA_MAPPER.index[WEATHERDATA_MAPPER["시·군·구"] == loc][0]
    
    weatherloc  = WEATHERDATA_MAPPER.at[loc_idx, "Station_num"]
    weatheryear = weather_year if weather_year is not None else WEATHERDATA_MAPPER.at[loc_idx, f"기준연도_{simtype}"]
    
    weatherdata_filename = f"{weatherloc}_{weatheryear}.epw"
    weatherdata_filepath = os.path.join(WEATHTERDATA_DIR, weatherdata_filename)
    
    return weatherdata_filepath