
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
import os
import re
import sys
import json
import warnings
import importlib
import subprocess
from uuid     import uuid4
from copy     import deepcopy
from datetime import datetime
from typing   import (
    Any          ,
    TYPE_CHECKING,
)

# third-party modules
import pandas as pd

# local modules
from .constants import Unit
if TYPE_CHECKING:
    from .core.construction import SurfaceConstruction

# ---------------------------------------------------------------------------- #
#                              PACKAGE MANAGEMENT                              #
# ---------------------------------------------------------------------------- #

def check_modules(modules:list[str]):
    
    # check if all required modules are importable
    missing_module = []
    for mod in modules:
        try:
            importlib.import_module(mod)
        except ImportError:
                missing_module.append(mod)
    
    # If any modules are missing,
    if missing_module:
        
        # check whether the user wants to install the modules
        print(
            f"Required modules that are not installed: {', '.join(missing_module)}"
        )
        want_import = input("Do you want to install the modules? [Y/N]")
        
        if want_import == "Y":
            
            # install missing modules and check failures
            failed_module = [] 
            for mod in missing_module:
                result = subprocess.run([sys.executable, "-m", "pip", "install", mod])
                if result.returncode != 0:
                    failed_module.append(mod)
            
            # if failed module exists,
            # return error code (1)
            if failed_module:
                print(f"Failed to install: {', '.join(failed_module)}")
                return 1, failed_module
            
            # else (successfully installed all required modules),
            # return normal code (0)
            else:
                return 0, []
        
        # if the user does not want to install modules automatically,
        # return error code (1)
        else:
            return 1, missing_module
    
    # if there's no missing module,
    # return normal code (0)
    else:
        return 0, []

# ---------------------------------------------------------------------------- #
#                             EXCEL GUI: VARIABLES                             #
# ---------------------------------------------------------------------------- #

# Row index (0-based) of the header row in the input excel sheets.
# The 2026 dataset template places headers on the 2nd row (index 1),
# reserving the 1st row for annotations and the 1st two columns for legends.
HEADER_ROW = 1

# Number of the material layers a surface construction sheet can hold
MAX_SURFACE_LAYERS = 5

VALID_COLUMNS = {
    "건물정보"     : ["건물명","용도","north_axis [°]","주소","허가일자"],
    "실"           : ["이름","층","천장고 [m]", "용도프로필","조명밀도 [W/m2]","침기율 [ACH@50]"], # v-070 수정사항
    "면"           : ["이름","소속 실","유형","경계조건","면적 [m2]","향 [°]","인접존 이름","구조체 이름", "쿨루프 반사율 [%]"],
    "개구부"       : ["이름","소속 면","유형","면적 [m2]","구조체 이름", "블라인드"],
    "구조체_면"    : ["이름","법규기준벽체 레이어순서","레이어1_재료","레이어1_두께 [mm]","레이어2_재료","레이어2_두께 [mm]","레이어3_재료","레이어3_두께 [mm]","레이어4_재료","레이어4_두께 [mm]","레이어5_재료","레이어5_두께 [mm]"],
    "구조체_개구부": ["이름","투명여부","열관류율 [W/m2·K]","태양열취득계수"],
    "재료"         : ["이름","열전도율 [W/m·K]", "밀도 [kg/m3]","비열 [J/kg·K]"],
    "공급설비"     : ["이름","유형","냉방용량 [W]","난방용량 [W]","냉방COP [W/W]","대수","생산설비명","공급 실"],
    "생산설비"     : ["이름","유형","냉방용량 [W]","난방용량 [W]","냉방COP [W/W]","난방COP [W/W]","효율 [%]","급탕용","연료종류", "압축기 종류", "냉각탑 종류","냉각탑 용량 [W]", "냉각탑 제어방식", "연동보일러 효율 [%]"],
    "환기설비"     : ["이름", "난방효율 [%]", "냉방효율 [%]", "용량 [CMH]", "대수", "공급 실"],
    "PV패널"      : ["이름","면적","효율 [%]","방위각 [°]","경사각 [°]"],
}

ID_PREFIX = {
    "실"           :"ZONE",
    "면"           :"SURF",
    "개구부"       :"FNST",
    "구조체_면"    :"CTSF",
    "구조체_개구부":"CTFN",
    "재료"         :"MTRL",
    "공급설비"     :"SUPL",
    "생산설비"     :"SRCE",
    "환기설비"     :"ERVT",
    "PV패널"       :"PVPN",
}

COLUMN_RENAME_DICT = {
    # 건물정보
    "건물명"  :"name",
    "용도"    :"is_multifamily_housing",
    "주소"    :"address",
    "허가일자": "vintage",
    # 실
    "이름"      : "name",
    "층"        : "floor_number",
    "천장고"    : "height",
    "용도프로필": "profile",
    "조명밀도" : "light_density",
    "침기율"   : "infiltration", # v-070 수정사항
    # 면
    "소속 실"    : "parent_zone_name",
    "유형"       : "type",
    "경계조건"   : "boundary_condition",
    "면적"       : "area",
    "향"         : "azimuth",
    "인접존 이름": "adj_zone_name",
    "구조체 이름": "construction_name",
    "쿨루프 반사율": "coolroof_reflectance",
    # 개구부
    "소속 면": "parent_surface_name",
    "블라인드": "blind",
    # 구조체_면
    "법규기준벽체 레이어순서": "regulated_wall_position",
    "레이어1_재료": "layer1_material",
    "레이어1_두께": "layer1_thickness",
    "레이어2_재료": "layer2_material",
    "레이어2_두께": "layer2_thickness",
    "레이어3_재료": "layer3_material",
    "레이어3_두께": "layer3_thickness",
    "레이어4_재료": "layer4_material",
    "레이어4_두께": "layer4_thickness",
    "레이어5_재료": "layer5_material",
    "레이어5_두께": "layer5_thickness",
    # 구조체_개구부
    "투명여부"      : "is_transparent",
    "열관류율"      : "u",
    "태양열취득계수": "g",
    # 재료
    "열전도율": "conductivity",
    "밀도"    : "density",
    "비열"    : "specific_heat",
    # 공급설비
    "냉방용량": "capacity_cooling",
    "난방용량": "capacity_heating",
    "냉방COP" : "cop_cooling",
    "생산설비명": "source_sys_name",
    "대수"    : "count",
    "공급 실" : "zone_name",
    # 생산설비
    "난방COP" : "cop_heating",
    "효율"    : "efficiency",
    "급탕용"  : "hotwater_supply",
    "연료종류": "fuel_type",
    "압축기 종류" : "compressor_type",
    "냉각탑 종류" : "coolingtower_type",
    "냉각탑 용량" : "coolingtower_capacity",
    "냉각탑 제어방식": "coolingtower_control",
    "연동보일러 효율": "boiler_efficiency",
    # 환기설비
    "난방효율" : "efficiency_heating",
    "냉방효율" : "efficiency_cooling",
    "용량"     : "airflow_rate",
    # PV패널
    "방위각": "azimuth",
    "경사각": "tilt"   ,
}

PROPERTY_RENAME_DICT = {
    "source_type": {
        "히트펌프": "heatpump",
        "지열히트펌프": "geothermal_heatpump",
        "냉동기"  : "chiller",
        "흡수식냉동기": "absorption_chiller",
        "지역난방": "district_heating",
        "보일러"  : "boiler"  ,
    },
    "supply_type": {
        "공조기": "air_handling_unit",
        "팬코일유닛": "fan_coil_unit",
        "바닥난방":"radiant_floor",
        "전기바닥난방":"electric_radiant_floor",
        "패키지에어컨": "packaged_air_conditioner",
        "방열기" : "radiator",
        "전기방열기" : "electric_radiator"
    },
    "fuel_type": {
        "전기"   : "electricity",
        "도시가스": "natural_gas",
        "LPG"    : "lpg"        ,
        "난방유" : "oil"        ,
        "지역난방": "district_heating",
    },
    "compressor_type": {
        "터보식": "turbo",
        "스크류식": "screw",
        "왕복동식": "reciprocating",
    },
    "coolingtower_type": {
        "개방형": "open",
        "밀폐형": "closed",
    },
    "is_transparent": {
        "투명": True,
        "불투명": False,
    },
    "is_multifamily_housing": {
        "공동주택"  : True ,
        "공동주택 외": False,
    },
}

# Usage profile names offered by the 2026 template ('참조' sheet)
# that differ from the names of the built-in profile DB (KoreanUsageProfile.csv).
# The other names are identical and passed through.
PROFILE_RENAME_DICT = {
    "회의 및 세미나실": "회의실 및 세미나실",
    "강의실"         : "강의실(대학)",
    "매장"           : "매장(상점/백화점)",
    "전시실"         : "전시실(전시관/박물관)",
    "열람실"         : "열람실(도서관)",
}

# Options of the '법규기준벽체 레이어순서' column ('참조' sheet of the 2026 template),
# other than the '레이어n 뒤' pattern
REGULATED_WALL_NOT_REFERENCED = "참조안함"
REGULATED_WALL_OUTERMOST      = "최외측"
REGULATED_WALL_INNERMOST      = "최내측"
REGULATED_WALL_AFTER_LAYER    = re.compile(r"레이어(\d+) 뒤")

GRJSON_FORMAT =  {
    "building":{
        "name"      : "",
        "north_axis": 0,
        "address"   : "",
        "vintage"   : [1900,1,1],
        "is_multifamily_housing": False,
        "floors"        : [],
        "supply_systems": {},
        "source_systems": {},
        "ventilation_systems": [],
        "photovoltaic_systems": [],
    },
    "materials":[],
    "surface_constructions"     :[],
    "fenestration_constructions":[],
}



# ---------------------------------------------------------------------------- #
#                             EXCEL GUI: FUNCTIONS                             #
# ---------------------------------------------------------------------------- #

def _clean_column_names(
    df:pd.DataFrame
    ) -> pd.DataFrame:
    
    # Create a copy of the DataFrame to avoid modifying the original
    df_cleaned = df.copy()
    
    # Remove units
    df_cleaned.columns = df_cleaned.columns.str.replace(r"\[[\w/·%°@]+\]", "", regex=True,).str.strip()
    
    # Rename columns
    df_cleaned.rename(columns=COLUMN_RENAME_DICT, inplace=True)
    
    return df_cleaned


def _format_id(
    sheetname:str,
    index    :int,
    ) -> str:

    # ID convention: <prefix of the sheet>-0x<6-digit hexadecimal index>
    return f"{ID_PREFIX[sheetname]}-0x{index:06X}"


def _assign_id(
    df       :pd.DataFrame,
    sheetname:str         ,
    ) -> pd.DataFrame:
    
    # Create a copy of the DataFrame to avoid modifying the original
    df_assigned = df.copy()
    
    # If no ID is required for the sheet, return the copy itself
    if sheetname in ["건물정보"]:
        return df_assigned
    
    # Check uniqueness of the names
    # If not, raise an exception
    if not all((name_bin:=df_assigned["name"].value_counts()) == 1):
        duplicated_name_str = ", ".join([
            f"{name} ({count} times)"
            for name, count in zip(name_bin[name_bin>1].index, name_bin[name_bin>1].values)
        ])
        raise ValueError(
            f"Duplicated name detected in the sheet '{sheetname}': {duplicated_name_str}"
        )
    
    # Assign id using the index
    # For safety, reset the index before the assigning
    df_assigned.reset_index(inplace=True, drop=True)
    df_assigned.insert(0, "id", df_assigned.index.map(lambda v: _format_id(sheetname, v)))
    
    return df_assigned


def _replace_nan_to_none(
    obj:Any
    ) -> Any:
    
    # Revursively apply the function to the items: dict
    if isinstance(obj, dict):
        return {k: _replace_nan_to_none(v) for k, v in obj.items()}
    
    # Revursively apply the function to the items: list
    elif isinstance(obj, list):
        return [_replace_nan_to_none(v) for v in obj]
    
    # Convert the nan instance to the None
    # to export 'null' into the result JSON
    if pd.isna(obj):
        obj =  None
    
    return obj
    

def _name_to_id(
    df  :pd.DataFrame,
    name:str         ,
    ) -> str:
    
    # If no name is provided, return None (for json: null)
    # This is designed for empty use of the reference inputs (e.g. zone:supply_system_heating_id)
    if pd.isna(name):
        return None    

    # Find the 'name' in the given dataframe
    target_row = df.loc[df['name'] == name, 'id']
    
    # If there's no 'name' in the dataframe
    if target_row.empty:
        raise KeyError(f"ID for name '{name}' not found.")
    
    # If there's two or more 'name' in the dataframe (duplicated name usage)
    if len(target_row) > 1:
        raise KeyError(f"Multiple ({len(target_row)}) IDs found for name '{name}'. Please check for duplicate entries.")
    
    # Return the ID matching the 'name'
    target_id = target_row.iloc[0]
    return target_id
    
    
def _preprocess_excel_dict(
    excel_dict: dict[str, pd.DataFrame]
    ) -> dict[str, pd.DataFrame]:
    
    # Filter unused sheets
    excel_dict = {k:v for k,v in excel_dict.items() if k in VALID_COLUMNS.keys()}
    
    for sheetname, df in excel_dict.items():
        
        # v-070 수정사항: 템플릿에 없는 열(예: 침기율)은 빈 열로 채워 이전 템플릿도 읽히게 한다
        for column in VALID_COLUMNS[sheetname]:
            if column not in df.columns:
                df[column] = pd.NA
        
        # Delete unused columns (auto-calculated columns)
        df_valid = df[VALID_COLUMNS[sheetname]]
        
        # Delete unused rows (unintended rows)
        df_valid = df_valid.replace(r'^\s*$', pd.NA, regex=True)
        df_valid = df_valid.loc[~df_valid.isna().all(axis=1),:]
        
        # Rename columns (removing units, translating Korean to English)
        df_cleaned = _clean_column_names(df_valid)
        
        # Assign ID for objects
        df_assigned = _assign_id(df_cleaned, sheetname)

        # Save the pre-processed dataframe
        excel_dict[sheetname] = df_assigned
    
    return excel_dict

def _rename_properties(
    row_dict  :dict,
    *args:tuple[str, str] # [mapper key name, row column name]
    ) -> None:
    
    for key, col in args:
        
        mapper = PROPERTY_RENAME_DICT[key]
        v      = row_dict[col]
        row_dict[col] = mapper[v] if not pd.isna(v) else v
        
    return
        
def _group_systems_by_type(
    system_list:list[dict]
    ) -> dict[str, list[dict]]:
    
    """ Group the converted system dicts by their type.
    
    The grjson schema nests systems under their type
    (e.g. {"air_handling_unit": [...], "radiant_floor": [...]}),
    which GreenRetrofitModel.from_grjson consumes through
    SupplySystem.TYPE_MAPPER / SourceSystem.TYPE_MAPPER.
    The 'type' key itself is dropped since it is carried by the group.
    """
    
    grouped = {}
    for system in system_list:
        grouped.setdefault(system["type"], []).append(
            {k:v for k,v in system.items() if k != "type"}
        )
    
    return grouped


def _convert_source_systems(
    df_source:pd.DataFrame
    ) -> dict[str, list[dict]]:
    
    # Define required properties by the source system type
    VALID_PROPERTIES = {
        "heatpump"            : ["capacity_heating", "capacity_cooling", "cop_heating", "cop_cooling", "fuel_type"],
        "geothermal_heatpump" : ["capacity_heating", "capacity_cooling", "cop_heating", "cop_cooling", "fuel_type"],
        "chiller"             : ["capacity_cooling","cop_cooling","compressor_type","coolingtower_type","coolingtower_capacity","coolingtower_control","fuel_type"],
        "absorption_chiller"  : ["capacity_cooling", "cop_cooling","boiler_efficiency","fuel_type"],
        "boiler"              : ["capacity_heating", "efficiency","hotwater_supply", "fuel_type"],
        "district_heating"    : ["hotwater_supply"],
    }
    
    source_list = []
    for _, row in df_source.iterrows():
        
        # Convert the row to a dictionary
        source_dict = row.to_dict()
        
        # Rename values
        _rename_properties(source_dict,
            ("source_type"      , "type"            ),
            ("fuel_type"        , "fuel_type"       ),
            ("compressor_type"  , "compressor_type" ),
            ("coolingtower_type","coolingtower_type"),
        )
                
        # convert the value type
        if "hotwater_supply" in source_dict.keys():
            source_dict["hotwater_supply"] = bool(source_dict["hotwater_supply"]) if not pd.isna(source_dict["hotwater_supply"]) else False
 
        # convert units
        source_dict["efficiency"]        *= Unit.PERCENT_TO_FRACTION
        source_dict["boiler_efficiency"] *= Unit.PERCENT_TO_FRACTION
         
        # Remove unused properties
        source_dict = {k:v for k,v in source_dict.items() if k in VALID_PROPERTIES[source_dict["type"]] + ["name", "id", "type"]}

        # Append to the list
        source_list.append(source_dict)
    
    return _group_systems_by_type(source_list)


def _convert_supply_systems(
    df_supply:pd.DataFrame,
    df_source:pd.DataFrame,
    ) -> dict[str, list[dict]]:
    
    # Define required properties by the supply system type
    VALID_PROPERTIES = {
        "packaged_air_conditioner": ["capacity_cooling","cop_cooling"],
        "air_handling_unit"       : [],
        "fan_coil_unit"           : [],
        "radiator"                : ["capacity_heating"],
        "electric_radiator"       : ["capacity_heating"],
        "radiant_floor"           : [],
        "electric_radiant_floor"  : [],
    }
    
    supply_list = []
    for _, row in df_supply.iterrows():
        
        # Convert the row to a dictionary
        supply_dict = row.to_dict()
        
        # Rename values
        _rename_properties(supply_dict,
            ("supply_type", "type")
        )
        
        # Get ID of the reference properties (source system)
        supply_dict["source_system_id"] = _name_to_id(df_source, supply_dict["source_sys_name"])
        
        # Remove unused properties
        supply_dict = {k:v for k,v in supply_dict.items() if k in VALID_PROPERTIES[supply_dict["type"]] + ["name", "id", "type","source_system_id"]}
        
        # Append to the list
        supply_list.append(supply_dict)
    
    return _group_systems_by_type(supply_list)


def _convert_ventilation_systems(
    df_ventilation:pd.DataFrame
    ) -> list[dict]:
    
    ventilation_list = []
    for _, row in df_ventilation.iterrows():
        
        # Convert the row to a dictionary
        ventilation_dict = row.to_dict()
        
        # convert units
        ventilation_dict["efficiency_heating"] *= Unit.PERCENT_TO_FRACTION
        ventilation_dict["efficiency_cooling"] *= Unit.PERCENT_TO_FRACTION
        if ventilation_dict["airflow_rate"] is not None:
            ventilation_dict["airflow_rate"]       *= Unit.CMH_TO_M3_PER_S
        
        # Remove unused properties
        # ('count' and 'zone_name' belong to the zone that the system supplies)
        ventilation_dict.pop("count")
        ventilation_dict.pop("zone_name")
        
        # Append to the list
        ventilation_list.append(ventilation_dict)
    
    return ventilation_list


def _convert_photovoltaic_systems(
    df_photovoltaic:pd.DataFrame
    ) -> list[dict]:
    
    photovoltaic_list = []
    for _, row in df_photovoltaic.iterrows():
        
        # Convert the row to a dictionary
        photovoltaic_dict = row.to_dict()
        
        # convert units
        photovoltaic_dict["efficiency"] *= Unit.PERCENT_TO_FRACTION
        
        # Append to the list
        photovoltaic_list.append(photovoltaic_dict)
    
    return photovoltaic_list


def _convert_fenestrations(
    df_fenestration             :pd.DataFrame,
    df_construction_fenestration:pd.DataFrame,
    ) -> list[dict]:
    
    fenestration_list = []
    for _, row in df_fenestration.iterrows():

        # Convert the row to a dictionary
        fenestration_dict = row.to_dict()
        
        # Get ID of the reference properties (construction)
        fenestration_dict["construction_id"] = _name_to_id(df_construction_fenestration, fenestration_dict["construction_name"])
        
        # Remove unused properties
        fenestration_dict.pop("parent_surface_name")
        fenestration_dict.pop("construction_name")
        
        # assign the default shade
        if fenestration_dict["blind"] == 1.0:
            fenestration_dict["blind"] = "shade"
        else:
            fenestration_dict["blind"] = None
        
        # Append to the list
        fenestration_list.append(fenestration_dict)
    
    return fenestration_list


def _convert_surfaces(
    df_surface     :pd.DataFrame,
    df_zone        :pd.DataFrame,
    df_fenestration:pd.DataFrame,
    df_construction_surface     :pd.DataFrame,
    df_construction_fenestration:pd.DataFrame,
    ) -> list[dict]:
    
    surf_list = []
    for _, row in df_surface.iterrows():
        
        # Convert the row to a dictionary
        surf_dict = row.to_dict()
            
        # Get ID of the reference properties (adjacent zone),
        # if required
        if surf_dict["boundary_condition"] == "zone":
            surf_dict["adjacent_zone_id"] = _name_to_id(df_zone, surf_dict["adj_zone_name"])
        
        # Get ID of the reference properties (construction)
        # '오픈' -> "open", 빈 칸 -> "unknown"
        match surf_dict["construction_name"]:
            case "오픈":
                surf_dict["construction_id"] ="open"
            case _:
                surf_dict["construction_id"] = _name_to_id(df_construction_surface, surf_dict["construction_name"])
        
        # remove unused properties
        surf_dict.pop("parent_zone_name")
        surf_dict.pop("adj_zone_name")
        surf_dict.pop("construction_name")
        
        # convert units
        if surf_dict["coolroof_reflectance"] is not None:
            surf_dict["coolroof_reflectance"] *= Unit.PERCENT_TO_FRACTION
        
        # Remove unused properties,
        # if required 1 (no azimuth except for outdoor-wall)
        if (surf_dict["type"] != "wall") or (surf_dict["boundary_condition"] != "outdoors"):
            surf_dict.pop("azimuth")
        # if required 2 (no coolroof_reflectance except for outside-ceiling)
        if (surf_dict["type"] != "ceiling") or (surf_dict["boundary_condition"] != "outdoors"):
            surf_dict.pop("coolroof_reflectance")
        
        # Find child fenestration objects,
        child_fenestrations = df_fenestration.query("parent_surface_name == @row['name']")
        # and convert the child fenestrations to dicts
        fen_list = _convert_fenestrations(child_fenestrations, df_construction_fenestration)
        surf_dict["fenestrations"] = fen_list
        
        # Append to the list
        surf_list.append(surf_dict)
    
    return surf_list


def _ventilation_count(
    row:pd.Series
    ) -> int:
    
    # An empty '대수' cell means a single unit
    count = row["count"]
    return 1 if pd.isna(count) else int(count)


def _collect_supply_system_ids(
    df_supply:pd.DataFrame,
    zone_name:str         ,
    ) -> list[str]:
    
    """ Collect the supply system IDs serving the given zone.
    
    A zone cannot reference the same supply system twice
    (see Zone.supply_systems), and the grjson schema offers no place
    for an installed count on the supply side, unlike ventilation.
    The '대수' column is therefore not reflected here.
    """
    
    serving = df_supply.loc[df_supply["zone_name"] == zone_name]
    
    return list(dict.fromkeys(serving["id"]))


def _collect_ventilation_systems(
    df_ventilation:pd.DataFrame,
    zone_name     :str         ,
    ) -> list[dict]:
    
    """ Collect the ventilation systems serving the given zone.
    
    Unlike supply systems, Zone.from_json reads the installed count
    from the reference itself, so it is kept as a property.
    """
    
    return [
        {"id": row["id"], "count": _ventilation_count(row)}
        for _, row in df_ventilation.loc[df_ventilation["zone_name"] == zone_name].iterrows()
    ]


def _convert_zones(
    df_zone        :pd.DataFrame,
    df_surface     :pd.DataFrame,
    df_fenestration:pd.DataFrame,
    df_construction_surface     :pd.DataFrame,
    df_construction_fenestration:pd.DataFrame,
    df_supply_system     :pd.DataFrame,
    df_ventilation_system:pd.DataFrame,
    ) -> dict:
    
    zone_list = []
    for _, row in df_zone.iterrows():
        
        # Convert the row to a dictionary
        zone_dict = row.to_dict()

        # Rename values (profile names differing from the built-in DB)
        zone_dict["profile"] = PROFILE_RENAME_DICT.get(zone_dict["profile"], zone_dict["profile"])

        # Collect the systems supplying this zone.
        # The systems reference the zone (not the other way around),
        # so the linkage is resolved from the system sheets.
        zone_dict["supply_system_ids"]   = _collect_supply_system_ids(df_supply_system, row["name"])
        zone_dict["ventilation_systems"] = _collect_ventilation_systems(df_ventilation_system, row["name"])
        
        # Remove unused properties
        zone_dict.pop("floor_number")
        
        # Find child surface objects,
        child_surfaces = df_surface.query("parent_zone_name == @row['name']")
        # and convert the child surfaces to dicts
        surf_list = _convert_surfaces(child_surfaces, df_zone, df_fenestration, df_construction_surface, df_construction_fenestration) 
        zone_dict["surfaces"] = surf_list

        # Append to the list
        zone_list.append(zone_dict)
        
    return zone_list


def _convert_material(
    df_material:pd.DataFrame
    ) -> list[dict]:
    
    material_list = []
    for _, row in df_material.iterrows():
        
        # Convert the row to a dictionary
        material_dict = row.to_dict()
        
        # Append to the list
        material_list.append(material_dict)
        
    return material_list


def _convert_construction_surface(
    df_construction_surface:pd.DataFrame,
    df_material            :pd.DataFrame,
    ) -> list[dict]:
    
    const_list = []
    for _, row in df_construction_surface.iterrows():
        
        # Convert the row to a dictionary
        const_dict = row.to_dict()
        
        # Get ID of the reference properties (material)
        const_dict = {k:(_name_to_id(df_material, v) if k.endswith("material") else v) for k,v in const_dict.items()}
        
        # Construct layer info.:
        # Referenced by column name, so that unrelated columns
        # placed between 'name' and the layers do not shift the pairing
        layers = [
            {
                "material_id": const_dict[f"layer{n}_material"],
                "thickness"  : const_dict[f"layer{n}_thickness"]*Unit.MM_TO_M,
            }
            for n in _defined_layer_numbers(const_dict)
        ]
        
        # Reconstruct construction dict
        const_dict_structured = {
            "id"    : const_dict["id"]  ,
            "name"  : const_dict["name"],
            "layers": layers            ,
        }
        
        # Append to the list
        const_list.append(const_dict_structured)
    
    return const_list


def _defined_layer_numbers(
    row:dict|pd.Series
    ) -> list[int]:

    # Numbers of the layer columns holding a material,
    # in the outside-to-inside order of the sheet
    return [
        n for n in range(1, MAX_SURFACE_LAYERS+1)
        if not pd.isna(row.get(f"layer{n}_material"))
    ]


def _parse_regulated_wall_position(
    value:Any
    ) -> int|None:

    """ Parse a '법규기준벽체 레이어순서' cell into the number of the layer
        that the regulated wall follows

        * None               : not referenced (empty cell or '참조안함')
        * 0                  : '최외측', in front of the 1st layer
        * n                  : '레이어n 뒤', between the n-th and the (n+1)-th layers
        * MAX_SURFACE_LAYERS : '최내측', behind the last layer
    """

    if pd.isna(value):
        return None

    value = str(value).strip()

    if value in ("", REGULATED_WALL_NOT_REFERENCED):
        return None
    if value == REGULATED_WALL_OUTERMOST:
        return 0
    if value == REGULATED_WALL_INNERMOST:
        return MAX_SURFACE_LAYERS

    matched = REGULATED_WALL_AFTER_LAYER.fullmatch(value)
    if (matched is not None) and (1 <= int(matched.group(1)) <= MAX_SURFACE_LAYERS):
        return int(matched.group(1))

    raise ValueError(
        f"Invalid '법규기준벽체 레이어순서': '{value}'. "
        f"Expected one of '{REGULATED_WALL_NOT_REFERENCED}', '{REGULATED_WALL_OUTERMOST}', "
        f"'레이어1 뒤' ~ '레이어{MAX_SURFACE_LAYERS-1} 뒤' or '{REGULATED_WALL_INNERMOST}'."
    )


def _get_unknown_construction(
    surface_type      :str     ,
    boundary_condition:str     ,
    vintage           :datetime,
    climate           :str     ,
    *,
    is_radiant_floor      :bool,
    is_multifamily_housing:bool,
    ) -> tuple[str, "SurfaceConstruction"]:

    """ Resolve the construction that the model applies to an 'unknown' surface,
        mirroring GreenRetrofitModel._dragonize_surface:
        the default inner wall for an interior wall, the regulation DB otherwise

        Returns (label of the part, SurfaceConstruction)
    """

    # imported here to avoid a circular import (core.model imports this module)
    from .core import (
        SurfaceType             ,
        SurfaceBoundaryCondition,
        SurfaceConstruction     ,
    )

    # interior wall
    if (SurfaceType(surface_type) is SurfaceType.WALL) and (SurfaceBoundaryCondition(boundary_condition) is SurfaceBoundaryCondition.ZONE):
        return "내벽", SurfaceConstruction.create_default_innerwall()

    # exterior wall / roof / floor
    key = SurfaceConstruction.get_regulation_key(
        vintage           ,
        surface_type      ,
        boundary_condition,
        climate           ,
        is_radiant_floor      =is_radiant_floor      ,
        is_multifamily_housing=is_multifamily_housing,
    )
    return key[1], SurfaceConstruction.get_DB(key)


def _resolve_regulated_wall_layers(
    grjson                 :dict        ,
    df_construction_surface:pd.DataFrame,
    ) -> None:

    """ Splice the regulated wall layers into the surface constructions
        referencing it by the '법규기준벽체 레이어순서' column

    The grjson schema has no attribute for the reference, so the layers
    that the model would apply to an 'unknown' surface (the regulation DB
    by the vintage, climate and usage of the building, and the part of
    the surface) are inserted at the given position in advance.

    The part depends on the surface, so a construction shared by surfaces
    of different parts (e.g. an exterior wall and a roof) is split into
    one construction per part, and the surfaces are re-linked to them.
    A construction used by no surface is treated as an exterior wall.

    The grjson is modified in place: 'surface_constructions', 'materials',
    and the 'construction_id' of the surfaces.
    """

    # Positions of the regulated wall by the construction id
    positions = {}
    for _, row in df_construction_surface.iterrows():
        try:
            position = _parse_regulated_wall_position(row["regulated_wall_position"])
        except ValueError as e:
            raise ValueError(f"Construction '{row['name']}': {e}") from None
        if position is not None:
            positions[row["id"]] = position

    # Nothing to do if no construction references the regulated wall
    if not positions:
        return

    # imported here to avoid a circular import (core.model imports this module)
    from .core.model import address_to_weather

    # Building information determining the regulation
    building = grjson["building"]
    vintage  = datetime(*building["vintage"])
    _, climate, _, _ = address_to_weather(building["address"], vintage)
    is_multifamily_housing = (
        bool(building["is_multifamily_housing"])
        if not pd.isna(building["is_multifamily_housing"]) else False
    )

    # Zones with a radiant floor system use the '바닥난방인' floor regulation
    radiant_floor_ids = {
        system["id"]
        for system_type in ("radiant_floor", "electric_radiant_floor")
        for system in building["supply_systems"].get(system_type, [])
    }

    # Surfaces referencing the constructions, with the radiant floor flag of the zone
    surfaces_by_construction = {construction_id: [] for construction_id in positions}
    for floor in building["floors"]:
        for zone in floor["zones"]:
            is_radiant_floor = any(system_id in radiant_floor_ids for system_id in zone["supply_system_ids"])
            for surface in zone["surfaces"]:
                if surface["construction_id"] in positions:
                    surfaces_by_construction[surface["construction_id"]].append((surface, is_radiant_floor))

    # Materials of the regulated wall, appended to the grjson on the first use
    material_ids = {}
    def _material_id(material) -> str:
        if material.ID not in material_ids:
            material_ids[material.ID] = _format_id("재료", len(grjson["materials"]))
            grjson["materials"].append({"id": material_ids[material.ID]} | material.to_dict())
        return material_ids[material.ID]

    # Splice the layers
    constructions = []
    num_added     = 0
    for construction in grjson["surface_constructions"]:

        # Constructions without the reference are kept as they are
        if construction["id"] not in positions:
            constructions.append(construction)
            continue

        # Index of the layer list to insert the regulated wall at,
        # counted by the layer numbers of the sheet (empty layer columns are skipped)
        row       = df_construction_surface.loc[df_construction_surface["id"] == construction["id"]].iloc[0]
        insert_at = sum(1 for n in _defined_layer_numbers(row) if n <= positions[construction["id"]])

        # Resolve the regulated wall of each surface and group the surfaces by the part
        variants = {}
        for surface, is_radiant_floor in surfaces_by_construction[construction["id"]]:
            label, unknown = _get_unknown_construction(
                surface["type"], surface["boundary_condition"], vintage, climate,
                is_radiant_floor      =is_radiant_floor      ,
                is_multifamily_housing=is_multifamily_housing,
            )
            variants.setdefault(label, (unknown, []))[1].append(surface)

        # A construction used by no surface is treated as an exterior wall
        if not variants:
            label, unknown = _get_unknown_construction(
                "wall", "outdoors", vintage, climate,
                is_radiant_floor      =False                 ,
                is_multifamily_housing=is_multifamily_housing,
            )
            variants[label] = (unknown, [])

        # Create a construction per part:
        # the 1st keeps the original id and the others get new ids,
        # and the names are suffixed by the part only when split
        for k, (label, (unknown, surfaces)) in enumerate(variants.items()):

            spliced = deepcopy(construction)

            if k > 0:
                spliced["id"] = _format_id("구조체_면", len(df_construction_surface) + num_added)
                num_added += 1
            if len(variants) > 1:
                spliced["name"] = f"{construction['name']} ({label})"

            spliced["layers"] = (
                construction["layers"][:insert_at] +
                [
                    {"material_id": _material_id(material), "thickness": thickness}
                    for material, thickness in unknown.layers
                ] +
                construction["layers"][insert_at:]
            )

            for surface in surfaces:
                surface["construction_id"] = spliced["id"]

            constructions.append(spliced)

    grjson["surface_constructions"] = constructions


def _convert_construction_fenestration(
    df_construction_fenestration:pd.DataFrame,
    ) -> list[dict]:
    
    const_list = []
    for _, row in df_construction_fenestration.iterrows():
        
        # Convert the row to a dictionary
        const_dict = row.to_dict()
        
        # Rename values
        _rename_properties(const_dict,
            ("is_transparent" ,"is_transparent")
        )
        
        # Append to the list
        const_list.append(const_dict)
    
    return const_list


def excel2grjson(
    input_filepath :str          ,
    output_filepath:str|None=None,
    save           :bool    =True,
    ) -> tuple[dict, str]:
    
    """ Convert an Excel input file to GRM-formatted JSON

    Args
    ----
    input_filepath (str)
        * path to an input Excel file
    output_filepath (str, default=None)
        * filepath of the output grjson file (grm extension recommended).
        * default to uuid-based temporary filename in the current directory
    save (bool, default=True)
        * if True, save the result grjson to the output_filepath
    
    Returns
    -------
    grjson (dict)
        * converted dictionary in the GRM JSON structure
    output_filepath (str)
        * output_filepath
        * if save==False, returns None
        * if explicitly provided and save==True, the same path is returned
    """
    
    # filter warnings
    warnings.filterwarnings("ignore", message="Data Validation extension is not supported and will be removed")
    
    # Read the excel file and preprocess:
    # filtering sheets and columns, renaming columns, assigning id
    excel_org = pd.read_excel(input_filepath, sheet_name=list(VALID_COLUMNS.keys()), header=HEADER_ROW)
    excel     = _preprocess_excel_dict(excel_org)

    # Get default grjson struct and assign building information
    grjson = deepcopy(GRJSON_FORMAT)
    grjson["building"] |= excel["건물정보"].iloc[0].to_dict()
    
    # Rename values
    _rename_properties(grjson["building"],
        ("is_multifamily_housing", "is_multifamily_housing")
    )
    
    # Convert form of the building vintage: timestamp -> list[year, month, day]
    if isinstance(grjson["building"]["vintage"], str):
        grjson["building"]["vintage"] = datetime.strptime(grjson["building"]["vintage"], r"%Y-%m-%d")
    
    grjson["building"]["vintage"] = [
        grjson["building"]["vintage"].year ,
        grjson["building"]["vintage"].month,
        grjson["building"]["vintage"].day
    ]
    
    # Get zone dict
    zone_list = _convert_zones(
        excel["실"]      , excel["면"]         , excel["개구부"]  ,
        excel["구조체_면"], excel["구조체_개구부"],
        excel["공급설비"] , excel["환기설비"]
    )
    
    # Get zone dict by floors
    for floor_num, floor_zones in excel["실"].sort_values(by="floor_number", ascending=True).groupby("floor_number"):
        
        floor_dict = {
            "floor_number": int(floor_num)    ,
            "zones"       : [zone for zone in zone_list if (zone["id"] in floor_zones["id"].values)],
        }
        grjson["building"]["floors"].append(floor_dict)
    
    # Get system dict
    grjson["building"]["supply_systems"] = _convert_supply_systems(excel["공급설비"], excel["생산설비"])
    grjson["building"]["source_systems"] = _convert_source_systems(excel["생산설비"])
    grjson["building"]["ventilation_systems"]  = _convert_ventilation_systems(excel["환기설비"])
    grjson["building"]["photovoltaic_systems"] = _convert_photovoltaic_systems(excel["PV패널"])
    
    # Get construction dict
    grjson["materials"]                  = _convert_material(excel["재료"])
    grjson["surface_constructions"]      = _convert_construction_surface(excel["구조체_면"], excel["재료"])
    grjson["fenestration_constructions"] = _convert_construction_fenestration(excel["구조체_개구부"])

    # Splice the regulated wall layers into the constructions referencing it
    # ('법규기준벽체 레이어순서'), since the grjson schema cannot carry the reference
    _resolve_regulated_wall_layers(grjson, excel["구조체_면"])

    # Finalize: replace pd.NA to None
    grjson = _replace_nan_to_none(grjson)
        
    if save: 
        # Set default output filepath by uuid
        if output_filepath is None:
            output_filepath = os.path.join(os.path.dirname(input_filepath), f"{uuid4()}.grm")
            
        # Write JSON
        with open(output_filepath, "w", encoding="utf-8") as f:
            json.dump(grjson, f, ensure_ascii=False, indent=4)
            
    else:
        # If save=False but output_filepath is provided,
        # issue a warning and reset output_filepath to None
        if output_filepath is not None:
            warnings.warn(
                "The 'output_filepath' parameter is set but will be ignored because save=False.",
                UserWarning
            )
            output_filepath = None
    
    return grjson, output_filepath

