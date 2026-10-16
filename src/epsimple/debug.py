
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import json
import datetime # v-070 수정사항
from types import SimpleNamespace
from enum import (
    Enum,
    auto,
)
from abc import (
    ABC,
    abstractmethod
)

# third-party modules
import pandas as pd

# local modules
from .utils import (
    HEADER_ROW   ,
    VALID_COLUMNS,
    PROFILE_RENAME_DICT, # v-070 수정사항
)
from .core.profile import Profile # v-070 수정사항

# ---------------------------------------------------------------------------- #
#                                   CONSTANTS                                  #
# ---------------------------------------------------------------------------- #

# Supply system types capable of heating / cooling a zone.
# Mirrors the '난방 공급 설비' / '냉방 공급 설비' formulas of the input template.
HEATING_SUPPLY_TYPES = ("공조기", "팬코일유닛", "방열기", "전기방열기", "바닥난방", "전기바닥난방")
COOLING_SUPPLY_TYPES = ("패키지에어컨", "공조기", "팬코일유닛")

# Supply system types occupying the floor of a zone
RADIANT_FLOOR_SUPPLY_TYPES = ("바닥난방", "전기바닥난방")

# Source system types each supply system type can be driven by.
# Mirrors the _heatable_sources / _coolable_sources of the SupplySystem
# subclasses in core.hvac; an empty tuple means the supply system runs on
# its own and ignores whatever '생산설비명' holds.
COMPATIBLE_SOURCE_TYPES = {
    "패키지에어컨": ()                                         ,
    "전기방열기"  : ()                                         ,
    "전기바닥난방": ()                                         ,
    "공조기"      : ("히트펌프", "지열히트펌프")                 ,
    "팬코일유닛"  : ("보일러", "지역난방", "냉동기", "흡수식냉동기"),
    "방열기"      : ("보일러", "지역난방")                      ,
    "바닥난방"    : ("보일러", "지역난방")                      ,
}


def _to_bool(
    series:pd.Series
    ) -> pd.Series:
    
    # Treat an empty cell as False, so that TRUE/FALSE columns
    # can be tested regardless of the dtype pandas inferred
    return series.map(lambda value: False if pd.isna(value) else bool(value))


def _assigned_supply_systems(
    exceldata:dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
    
    # Supply systems actually assigned to an existing zone.
    # The supply system references the zone it serves ('공급 실'),
    # so the linkage is read from the supply sheet.
    zone_names = set(exceldata["실"]["이름"].dropna())
    supply     = exceldata["공급설비"]
    
    return supply.loc[supply["공급 실"].isin(zone_names)]


# ---------------------------------------------------------------------------- #
#                                JSON EXCEPTIONS                               #
# ---------------------------------------------------------------------------- #

class JsonException(Exception, ABC):
    
    def __init__(self,
        class_name :str,
        object_name:str,
        *,
        subcategory:str|None=None,
        ) -> None:
        
        self.sheet_name  = class_name
        self.object_name = object_name
        self.subcategory = subcategory

        return

    @staticmethod
    @abstractmethod
    def inspect(jsondata:SimpleNamespace) -> list[ExcelException]: ...

    def to_dict(self) -> dict[str,str]:
        
        return {
            "importance" : "ERROR",
            "category"   : type(self).__name__,
            "subcategory": self.subcategory.value if self.subcategory is not None else 0   ,
            "type"       : self.sheet_name    ,
            "object"     : self.object_name   ,
            "message"    : self.message       ,
        }

# ---------------------------------------------------------------------------- #
#                               EXCEL EXCEPTIONS                               #
# ---------------------------------------------------------------------------- #

class ExcelException(Exception, ABC):
    
    def __init__(self,
        sheet_name :str,
        object_name:str,
        *,
        subcategory:str|None=None,
        ) -> None:
        
        self.sheet_name  = sheet_name
        self.object_name = object_name
        self.subcategory = subcategory

        return
    
    @staticmethod
    @abstractmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[ExcelException]: ...
    
    def to_dict(self) -> dict[str,str]:
        
        return {
            "importance" : "ERROR",
            "category"   : type(self).__name__,
            "subcategory": self.subcategory.value if self.subcategory is not None else 0   ,
            "type"       : self.sheet_name    ,
            "object"     : self.object_name   ,
            "message"    : self.message       ,
        }


class InSufficientSurfaceForZoneSubCategory(str, Enum):
    
    NO_FLOOR   = auto()
    NO_CEILING = auto()
    NO_WALL    = auto()

class InsufficientSurfaceForZone(ExcelException):
    
    def __init__(self,
        subcategory:InSufficientSurfaceForZoneSubCategory,
        object_name:str,
        ) -> None:
        
        super().__init__("면", object_name, subcategory=subcategory)
        match subcategory:
            case InSufficientSurfaceForZoneSubCategory.NO_FLOOR:
                self.message = f"실 '{object_name}'에 바닥면이 없습니다."
            case InSufficientSurfaceForZoneSubCategory.NO_CEILING:
                self.message = f"실 '{object_name}'에 천장면이 없습니다."
            case InSufficientSurfaceForZoneSubCategory.NO_WALL:
                self.message = f"실 '{object_name}'에 벽체가 없습니다."
    
    @staticmethod
    def inspect_floor(zonename:str, floor_sheet:pd.DataFrame, ceiling_sheet:pd.DataFrame):
        
        if (zonename not in floor_sheet["소속 실"].values) and (zonename not in ceiling_sheet["인접존 이름"].values):
            return InsufficientSurfaceForZone(
                InSufficientSurfaceForZoneSubCategory.NO_FLOOR,
                zonename,
            )
        
        else:
            return
        
    @staticmethod
    def inspect_ceiling(zonename:str, ceiling_sheet:pd.DataFrame, floor_sheet:pd.DataFrame):
        
        if (zonename not in ceiling_sheet["소속 실"].values) and (zonename not in floor_sheet["인접존 이름"].values):
            return InsufficientSurfaceForZone(
                InSufficientSurfaceForZoneSubCategory.NO_CEILING,
                zonename,
            )
        
        else:
            return
    
    @staticmethod
    def inspect_wall(zonename:str, wall_sheet:pd.DataFrame):
        
        if (zonename not in wall_sheet["소속 실"].values) and (zonename not in wall_sheet["인접존 이름"].values):
            return InsufficientSurfaceForZone(
                InSufficientSurfaceForZoneSubCategory.NO_WALL,
                zonename,
            )
        
        else:
            return
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[InsufficientSurfaceForZone]:
        
        # for reference
        floors   = exceldata["면"].loc[~pd.isna(exceldata["면"]["이름"])].query("유형 == 'floor'")
        ceilings = exceldata["면"].loc[~pd.isna(exceldata["면"]["이름"])].query("유형 == 'ceiling'")
        walls    = exceldata["면"].loc[~pd.isna(exceldata["면"]["이름"])].query("유형 == 'wall'")
        
        exceptions = []
        for _, row in exceldata["실"].iterrows():
            
            # skip empty rows
            if pd.isna(row["이름"]):
                break
            
            # inspect each surface type
            exception_floor   = InsufficientSurfaceForZone.inspect_floor(row["이름"], floors, ceilings)
            exception_ceiling = InsufficientSurfaceForZone.inspect_ceiling(row["이름"], ceilings, floors)
            exception_wall    = InsufficientSurfaceForZone.inspect_wall(row["이름"], walls)
            
            # append to the exception list
            exceptions += [
                exception for exception
                in [exception_floor, exception_ceiling, exception_wall]
                if isinstance(exception, InsufficientSurfaceForZone)
            ]
            
        return exceptions
    

class InvalidFenestrationConstructionSubCategory(str, Enum):
    
    INVALID_CONSTRUCTION_NAME      = auto()
    TRANSPARENT_FOR_DOOR           = auto()
    OPAQUE_FOR_WINDOW_OR_GLASSDOOR = auto()

class InvalidFenestrationConstruction(ExcelException):
    
    def __init__(self,
        subcategory:InvalidFenestrationConstructionSubCategory,
        object_name      :str,
        fenestration_type:str,
        construction_name:str,
        ) -> None:
        
        super().__init__("개구부", object_name, subcategory=subcategory)
        
        match subcategory:
            
            case InvalidFenestrationConstructionSubCategory.INVALID_CONSTRUCTION_NAME:
                self.message = f"개구부 '{object_name}'의 구조체로 입력된 '{construction_name}'는 존재하지 않는 구조체입니다."
            
            case InvalidFenestrationConstructionSubCategory.TRANSPARENT_FOR_DOOR:
                self.message = f"'{fenestration_type}'유형 개구부 '{object_name}'은/는 투명한 구조체 '{construction_name}'를 사용할 수 없습니다."
                
            case InvalidFenestrationConstructionSubCategory.OPAQUE_FOR_WINDOW_OR_GLASSDOOR:
                self.message = f"'{fenestration_type}'유형 개구부 '{object_name}'은/는 불투명한 구조체 '{construction_name}'를 사용할 수 없습니다."
        
        return
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[InsufficientSurfaceForZone]: 
        
        # reference data
        fenestration_construction = exceldata["구조체_개구부"].set_index("이름")
        
        # check
        exceptions = []
        for _, row in exceldata["개구부"].iterrows():
            
            # 그냥 존재하지도 않는 경우
            if row["구조체 이름"] not in fenestration_construction.index:
                exceptions.append(
                    InvalidFenestrationConstruction(
                        InvalidFenestrationConstructionSubCategory.INVALID_CONSTRUCTION_NAME,
                        row["이름"],
                        row["유형"],
                        row["구조체 이름"],
                    )
                )
                continue
            
            # 존재하면 검사
            match row["유형"]:
                
                case "window"|"glassdoor":
                    if fenestration_construction.loc[row["구조체 이름"], "투명여부"] == "불투명":
                        exceptions.append(
                            InvalidFenestrationConstruction(
                                InvalidFenestrationConstructionSubCategory.OPAQUE_FOR_WINDOW_OR_GLASSDOOR,
                                row["이름"],
                                row["유형"],
                                row["구조체 이름"],
                            )
                        )
                
                case "door":
                    if fenestration_construction.loc[row["구조체 이름"], "투명여부"] == "투명":
                        exceptions.append(
                            InvalidFenestrationConstruction(
                                InvalidFenestrationConstructionSubCategory.TRANSPARENT_FOR_DOOR,
                                row["이름"],
                                row["유형"],
                                row["구조체 이름"],
                            )
                        )
                        
        return exceptions
    
    
    
class InvalidSurfaceConstructionSubCategory(str, Enum):
    
    INVALID_CONSTRUCTION_NAME      = auto()
    
class InvalidSurfaceConstruction(ExcelException):
    
    def __init__(self,
        subcategory:InvalidFenestrationConstructionSubCategory,
        object_name      :str,
        fenestration_type:str,
        construction_name:str,
        ) -> None:
        
        super().__init__("면", object_name, subcategory=subcategory)
        match subcategory:
            
            case InvalidSurfaceConstructionSubCategory.INVALID_CONSTRUCTION_NAME:
                self.message = f"면 '{object_name}'의 구조체로 입력된 '{construction_name}'는 존재하지 않는 구조체입니다."
            
        return
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[InsufficientSurfaceForZone]: 
        
        # reference data
        surface_construction = exceldata["구조체_면"].set_index("이름")
        
        # check
        exceptions = []
        for _, row in exceldata["면"].iterrows():
            
            # skip empty rows
            if pd.isna(row["이름"]):
                break
            
            # check
            if (not pd.isna(row["구조체 이름"]) and (row["구조체 이름"] not in surface_construction.index)):
                exceptions.append(
                    InvalidSurfaceConstruction(
                        InvalidSurfaceConstructionSubCategory.INVALID_CONSTRUCTION_NAME,
                        row["이름"],
                        row["유형"],
                        row["구조체 이름"],
                    )
                )
                continue
            
                # 또 에러날 이유 있으면 subcategory 추가하고 검사
        
        return exceptions
    

class BlindForNonOutdoorWindow(ExcelException):
    
    def __init__(self,
        object_name :str,
        surface_name:str,
        ) -> None:
        
        super().__init__("개구부", object_name)
        self.message = f"경계조건이 'outdoors'가 아닌 면 '{surface_name}'에 소속된 개구부 '{object_name}'의 블라인드는 False 이어야 합니다."

    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[BlindForNonOutdoorWindow]:
        
        # reference data
        interzone_surfaces = exceldata["면"].query("경계조건 != 'outdoors'")["이름"].tolist()
        
        exceptions = []
        for _, row in exceldata["개구부"].iterrows():
            
            if (row["소속 면"] in interzone_surfaces) and (row["블라인드"] != 0.0):
                exceptions.append(
                    BlindForNonOutdoorWindow(
                        row["이름"],
                        row["소속 면"],
                    )
                )
        
        return exceptions


class InsufficientMaterialDefinition(ExcelException):
    
    def __init__(self, 
        object_name   :str      ,
        property_names:list[str],
        ) -> None:
        
        super().__init__("재료", object_name)
        self.message = f"재료 '{object_name}'의 {','.join(property_names)}가 정의되지 않았습니다."
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[InsufficientMaterialDefinition]:
    
        exceptions = []
        for _, row in exceldata["재료"].iterrows():
            
            # skip empty rows
            if pd.isna(row["이름"]):
                break
            
            if bool(pd.isna(row.iloc[1:4]).any()):
                exceptions.append(
                    InsufficientMaterialDefinition(
                        row["이름"],
                        list(row.index[1:4][pd.isna(row.iloc[1:4]).values]),
                    )
                )
            
        return exceptions
    
class InvalidAdjacentZoneName(ExcelException):
    
    def __init__(self, object_name:str, inputted_adjacent_zone_name:str) -> None:
        
        super().__init__("면", object_name)
        self.message = f"면 '{self.object_name}'의 인접존으로 입력된 '{inputted_adjacent_zone_name}'은 존재하지 않는 존 이름입니다."
        
        return
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[InvalidAdjacentZoneName]: 
        
        # reference data
        existing_zones = exceldata["실"]["이름"].to_list()
        
        # check
        exceptions = []
        for _, row in exceldata["면"].iterrows():
            
            if not pd.isna(row["인접존 이름"]) and row["인접존 이름"] not in existing_zones:
                exceptions.append(
                    InvalidAdjacentZoneName(
                        row["이름"],
                        row["인접존 이름"]
                    )
                )
        
        return exceptions
    
class InvalidSourceSystemName(ExcelException):
    
    def __init__(self, object_name:str, inputted_sourcesystem_name:str) -> None:
        
        super().__init__("공급설비", object_name)
        self.message = f"공급설비 '{self.object_name}'의 생산설비명으로 입력된 '{inputted_sourcesystem_name}'은 존재하지 않는 생산설비 이름입니다."
        
        return
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[InvalidSourceSystemName]: 
        
        # reference data
        existing_sources = exceldata["생산설비"]["이름"].to_list()
        
        # check
        exceptions = []
        for _, row in exceldata["공급설비"].iterrows():
            
            if not pd.isna(row["생산설비명"]) and row["생산설비명"] not in existing_sources:
                exceptions.append(
                    InvalidSourceSystemName(
                        row["이름"],
                        row["생산설비명"]
                    )
                )
        
        return exceptions

class DuplicatedName(ExcelException):
    
    def __init__(self,
        sheet_name :str,
        object_name:str,
        ) -> None:
        
        super().__init__(sheet_name, object_name)
        self.message = f"중복된 '{object_name}' 이름이 {sheet_name}에 사용되었습니다."
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[DuplicatedName]: 
        
        exceptions = []
        for sheet_name, df in exceldata.items():
            
            if "이름" not in df.columns:
                continue
            
            name_count = df["이름"].value_counts()
            for duplicated_name in name_count[name_count > 1].index:
                
                exceptions.append(
                    DuplicatedName(sheet_name, duplicated_name)
                )
        
        return exceptions
    
class ExcessiveOpeningArea(ExcelException):
    
    def __init__(self,
        object_name :str         ,
        surface_area:int|float   ,
        df_opening  :pd.DataFrame,
        ) -> None:
        
        super().__init__("면", object_name)
        self.message = f"면 {object_name}의 {len(df_opening)}개 개구부의 면적 총합({df_opening["면적 [m2]"].sum():.2f}m2)이 면의 면적({surface_area:.2f}m2)보다 큽니다."
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[ExcessiveOpeningArea]:
        
        exceptions = []
        for _, row in exceldata["면"].iterrows():
            
            openings = exceldata["개구부"].query("`소속 면` == @row['이름']")
            opening_area = openings["면적 [m2]"].sum()
            surface_area = row["면적 [m2]"]
            
            if opening_area > surface_area:
                exceptions.append(
                    ExcessiveOpeningArea(row["이름"], surface_area, openings)
                )
                
        return exceptions

class DualRadiantFloor(ExcelException):
    
    def __init__(self, zonename:str) -> None:
        
        super().__init__("실", zonename)
        self.message = f"실 '{zonename}'에 바닥난방 공급설비가 둘 이상 입력되었습니다. (주된 보일러를 사용하는 바닥난방만 남겨주세요)"
        
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[DualRadiantFloor]:
        
        # reference data
        supply  = _assigned_supply_systems(exceldata)
        radiant = supply.loc[supply["유형"].isin(RADIANT_FLOOR_SUPPLY_TYPES)]
        
        # check
        exceptions = []
        for zone_name, zone_radiant in radiant.groupby("공급 실"):
            
            if len(zone_radiant) > 1:
                exceptions.append(
                    DualRadiantFloor(
                        zone_name
                    )
                )
        
        return exceptions    


class IncompatibleSourceSystem(ExcelException):
    
    def __init__(self,
        object_name :str      ,
        supply_type :str      ,
        source_name :str|None ,
        source_type :str|None ,
        ) -> None:
        
        super().__init__("공급설비", object_name)
        
        allowed = ", ".join(COMPATIBLE_SOURCE_TYPES[supply_type])
        
        # no source system given, though the supply system needs one
        if source_name is None:
            self.message = (
                f"공급설비 '{self.object_name}'({supply_type})에 생산설비가 입력되지 않았습니다. "
                f"다음 유형 중 하나를 입력해주세요: {allowed}"
            )
        
        # a source system is given, but of an unusable type
        else:
            self.message = (
                f"공급설비 '{self.object_name}'({supply_type})은/는 "
                f"'{source_name}'의 유형({source_type})을 사용할 수 없습니다. "
                f"사용 가능한 유형: {allowed}"
            )
        
        return
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[IncompatibleSourceSystem]:
        
        # reference data
        source_types = exceldata["생산설비"].dropna(subset=["이름"]).set_index("이름")["유형"]
        
        # check
        exceptions = []
        for _, row in exceldata["공급설비"].iterrows():
            
            supply_type = row["유형"]
            
            # skip rows that another inspector already reports
            if pd.isna(row["이름"]) or (supply_type not in COMPATIBLE_SOURCE_TYPES):
                continue
            
            allowed = COMPATIBLE_SOURCE_TYPES[supply_type]
            
            # the supply system runs on its own,
            # so whatever is written in '생산설비명' does not matter
            if not allowed:
                continue
            
            source_name = row["생산설비명"]
            
            # a source system is required but not given
            if pd.isna(source_name):
                exceptions.append(
                    IncompatibleSourceSystem(row["이름"], supply_type, None, None)
                )
                continue
            
            # an unknown name is reported by InvalidSourceSystemName
            if source_name not in source_types.index:
                continue
            
            # the given source system is of an unusable type
            source_type = source_types.loc[source_name]
            if source_type not in allowed:
                exceptions.append(
                    IncompatibleSourceSystem(row["이름"], supply_type, source_name, source_type)
                )
        
        return exceptions


# ---------------------------------------------------------------------------- #
#                                 JSON WARNINGS                                #
# ---------------------------------------------------------------------------- #

class JsonWarning(UserWarning, ABC):
    
    def __init__(self,
        class_name :str,
        object_name:str,
        *,
        subcategory:str|None=None,
        ) -> None:
        
        self.sheet_name  = class_name
        self.object_name = object_name
        self.subcategory = subcategory

        return
    
    @staticmethod
    @abstractmethod
    def inspect(jsondata:SimpleNamespace) -> list[JsonWarning]: ...

    def to_dict(self) -> dict[str,str]:
        
        return {
            "importance" : "WARNING",
            "category"   : type(self).__name__,
            "subcategory": self.subcategory.value if self.subcategory is not None else 0,
            "type"       : self.sheet_name    ,
            "object"     : self.object_name   ,
            "message"    : self.message       ,
        }

# ---------------------------------------------------------------------------- #
#                                EXCEL WARNINGS                                #
# ---------------------------------------------------------------------------- #

class ExcelWarning(UserWarning, ABC):
    
    def __init__(self,
        sheet_name :str,
        object_name:str,
        *,
        subcategory:str|None=None,
        ) -> None:
        
        self.sheet_name  = sheet_name
        self.object_name = object_name
        self.subcategory = subcategory

        return
    
    @staticmethod
    @abstractmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[ExcelWarning]: ...

    def to_dict(self) -> dict[str,str]:
        
        return {
            "importance" : "WARNING",
            "category"   : type(self).__name__   ,
            "subcategory": self.subcategory.value if self.subcategory is not None else 0,
            "type"       : self.sheet_name       ,
            "object"     : self.object_name      ,
            "message"    : self.message          ,
        }

class NotUsedSupplySystem(ExcelWarning):
    
    def __init__(self, object_name:str) -> None:
        
        # superclass properties
        super().__init__("공급설비", object_name)
        
        # class-specific properties
        self.message = f"공급설비 '{self.object_name}'은/는 어느 존에서도 사용되지 않습니다."
        
        return
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[NotUsedSupplySystem]:
        
        # reference data
        used_supply_systems = set(_assigned_supply_systems(exceldata)["이름"].dropna())
        
        # check
        warnings = []
        for _, row in exceldata["공급설비"].iterrows():
            
            if not pd.isna(row["이름"]) and (row["이름"] not in used_supply_systems):
                warnings.append(
                    NotUsedSupplySystem(
                        row["이름"]
                    )
                )
        
        return warnings
    
    
class UnreflectedSupplySystemCount(ExcelWarning):
    
    def __init__(self, object_name:str, count:int) -> None:
        
        # superclass properties
        super().__init__("공급설비", object_name)
        
        # class-specific properties
        self.message = (
            f"공급설비 '{self.object_name}'의 대수({count}대)는 계산에 반영되지 않습니다. "
            f"입력한 용량은 1대분으로 계산되므로, 전체 용량을 입력하거나 설비를 나누어 입력해주세요."
        )
        
        return
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[UnreflectedSupplySystemCount]:
        
        # check
        warnings = []
        for _, row in _assigned_supply_systems(exceldata).iterrows():
            
            count = row["대수"]
            
            if not pd.isna(count) and (count > 1):
                warnings.append(
                    UnreflectedSupplySystemCount(
                        row["이름"], int(count)
                    )
                )
        
        return warnings
    
    
class NotUsedSourceSystem(ExcelWarning):
    
    def __init__(self, object_name:str) -> None:
        
        super().__init__("생산설비", object_name)
        self.message = f"생산설비 '{self.object_name}'은/는 어느 공급설비에서도 사용되지 않습니다."
        
        return
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[NotUsedSupplySystem]:
        
        # reference data
        used_source_systems = set(exceldata["공급설비"]["생산설비명"].to_list())
        used_source_systems = [item for item in used_source_systems if not pd.isna(item)]
        
        # check
        warnings = []
        for _, row in exceldata["생산설비"].iterrows():
            
            if (row["이름"] not in used_source_systems) and (row["급탕용"] == 0.0):
                warnings.append(
                    NotUsedSourceSystem(
                        row["이름"]
                    )
                )
        
        return warnings

class NotUsedSurfaceConstruction(ExcelWarning):
    
    def __init__(self, object_name:str) -> None:
        
        super().__init__("구조체_면", object_name)
        self.message = f"구조체 '{self.object_name}'은/는 어느 면에서도 사용되지 않습니다."
        
        return
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[NotUsedSupplySystem]:
        
        # reference data
        used_constructions = set(exceldata["면"]["구조체 이름"].to_list())
        used_constructions = [item for item in used_constructions if not pd.isna(item)]
        
        # check
        warnings = []
        for _, row in exceldata["구조체_면"].iterrows():
            
            # skip empty rows
            if pd.isna(row["이름"]):
                break
            
            # check
            if row["이름"] not in used_constructions:
                warnings.append(
                    NotUsedSurfaceConstruction(
                        row["이름"]
                    )
                )
        
        return warnings
    
class NoHVACSystemAppliedSubCategory(str, Enum):
    
    NoCoolingSupply  = auto()
    NoHeatingSupply  = auto()
    NoHotwaterSource = auto()   

class NoHVACSystemApplied(ExcelWarning):
    
    def __init__(self, subcategory:NoHVACSystemAppliedSubCategory) -> None:
        
        # superclass properties
        match subcategory:
            
            case NoHVACSystemAppliedSubCategory.NoCoolingSupply:
                super().__init__("공급설비", None, subcategory=subcategory)
                self.message = f"어떠한 존에도 냉방용 공급설비가 입력되지 않아 냉방에너지가 계산되지 않습니다."
            
            case NoHVACSystemAppliedSubCategory.NoHeatingSupply:
                super().__init__("공급설비", None, subcategory=subcategory)
                self.message = f"어떠한 존에도 난방용 공급설비가 입력되지 않아 난방에너지가 계산되지 않습니다."
            
            case NoHVACSystemAppliedSubCategory.NoHotwaterSource:
                super().__init__("생산설비", None, subcategory=subcategory)
                self.message = f"급탕용 설비가 입력되지 않아 효율 85%의 가스보일러로 가정됩니다."
        
        return
    
    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[NoHVACSystemApplied]:
        
        # reference data
        assigned_types = _assigned_supply_systems(exceldata)["유형"]
        
        exceptions = []
        
        # heating
        if not assigned_types.isin(HEATING_SUPPLY_TYPES).any():
            exceptions.append(
                NoHVACSystemApplied(
                    NoHVACSystemAppliedSubCategory.NoHeatingSupply
                )
            )
            
        # cooling
        if not assigned_types.isin(COOLING_SUPPLY_TYPES).any():
            exceptions.append(
                NoHVACSystemApplied(
                    NoHVACSystemAppliedSubCategory.NoCoolingSupply
                )
            )
        
        # hotwater
        if not _to_bool(exceldata["생산설비"]["급탕용"]).any():
            exceptions.append(
                NoHVACSystemApplied(
                    NoHVACSystemAppliedSubCategory.NoHotwaterSource
                )
            )
            
        return exceptions

# ---------------------------------------------------------------------------- #
#                                DEBUG FUNCTIONS                               #
# ---------------------------------------------------------------------------- #


# v-070 수정사항
PROFILE_SHEETNAME  = "용도프로필"
PROFILE_EQUIPMENTS = ("난방설비", "난방설비2", "냉방설비", "냉방설비2")
PROFILE_EQUIPMENT_ITEMS = ("종료시간", "운영시작월", "운영종료월", "설정온도")


def _user_profiles(exceldata:dict[str, pd.DataFrame]) -> pd.DataFrame:
    # 용도프로필 탭(header 없음): B열 항목 이름, C열부터 프로필 하나씩 -> 항목 x 프로필 표
    sheet = exceldata[PROFILE_SHEETNAME]
    table = sheet.set_index(1).iloc[:, 1:]
    return table.loc[:, ~pd.isna(table.loc["프로필 이름"])]


def _is_zero_time(value) -> bool:
    if isinstance(value, datetime.time):
        return (value.hour, value.minute) == (0, 0)
    return str(value).strip() in ("00:00", "0:00", "00:00:00")


class NoProfileSheet(ExcelException):

    def __init__(self) -> None:

        super().__init__(PROFILE_SHEETNAME, PROFILE_SHEETNAME)
        self.message = f"'{PROFILE_SHEETNAME}' 시트가 존재하지 않습니다."

        return

    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[NoProfileSheet]:

        if PROFILE_SHEETNAME not in exceldata:
            return [NoProfileSheet()]

        return []


class UndefinedProfile(ExcelException):

    def __init__(self, object_name:str, inputted_profile:str) -> None:

        super().__init__("실", object_name)
        self.message = f"실 '{self.object_name}'의 용도프로필 '{inputted_profile}'은 내장 프로필에도 '{PROFILE_SHEETNAME}' 시트에도 없습니다."

        return

    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[UndefinedProfile]:

        if PROFILE_SHEETNAME not in exceldata:
            return []

        # reference data
        valid_profiles = list(Profile._DB.keys()) + list(PROFILE_RENAME_DICT.keys()) + _user_profiles(exceldata).loc["프로필 이름"].to_list()

        # check
        exceptions = []
        for _, row in exceldata["실"].iterrows():

            if not pd.isna(row["용도프로필"]) and row["용도프로필"] not in valid_profiles:
                exceptions.append(
                    UndefinedProfile(
                        row["이름"],
                        row["용도프로필"]
                    )
                )

        return exceptions


class InvalidProfileBase(ExcelException):

    def __init__(self, object_name:str, inputted_base:str) -> None:

        super().__init__(PROFILE_SHEETNAME, object_name)
        self.message = f"프로필 '{self.object_name}'의 실 주용도 '{inputted_base}'은 내장 프로필에 없습니다."

        return

    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[InvalidProfileBase]:

        if PROFILE_SHEETNAME not in exceldata:
            return []

        # reference data
        valid_bases = list(Profile._DB.keys()) + list(PROFILE_RENAME_DICT.keys())

        # check
        exceptions = []
        for _, column in _user_profiles(exceldata).items():

            if pd.isna(column["실 주용도"]) or column["실 주용도"] not in valid_bases:
                exceptions.append(
                    InvalidProfileBase(
                        column["프로필 이름"],
                        column["실 주용도"]
                    )
                )

        return exceptions


class IncompleteProfileOccupancy(ExcelException):

    def __init__(self, object_name:str) -> None:

        super().__init__(PROFILE_SHEETNAME, object_name)
        self.message = f"프로필 '{self.object_name}'의 상주인원 수, 재실시작시간, 재실종료시간은 모두 입력하거나 모두 비워야 합니다."

        return

    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[IncompleteProfileOccupancy]:

        if PROFILE_SHEETNAME not in exceldata:
            return []

        # check
        exceptions = []
        for _, column in _user_profiles(exceldata).items():

            filled = [not pd.isna(column[item]) for item in ("상주인원 수 [명]", "상주인원 재실시작시간", "상주인원 재실종료시간")]
            if any(filled) and not all(filled):
                exceptions.append(
                    IncompleteProfileOccupancy(column["프로필 이름"])
                )

        return exceptions


class IncompleteProfileEquipment(ExcelException):

    def __init__(self, object_name:str, equipment:str, item:str) -> None:

        super().__init__(PROFILE_SHEETNAME, object_name)
        self.message = f"프로필 '{self.object_name}'의 {equipment} 시작시간이 입력되었으나 {equipment} {item}이 비어 있습니다."

        return

    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[IncompleteProfileEquipment]:

        if PROFILE_SHEETNAME not in exceldata:
            return []

        # check
        exceptions = []
        for _, column in _user_profiles(exceldata).items():
            for equipment in PROFILE_EQUIPMENTS:

                start = column[f"{equipment} 시작시간"]
                end   = column[f"{equipment} 종료시간"]
                if pd.isna(start):
                    continue
                # 00:00 ~ 00:00 은 미사용 표시이므로 나머지 항목 불필요
                if _is_zero_time(start) and not pd.isna(end) and _is_zero_time(end):
                    continue

                for item in PROFILE_EQUIPMENT_ITEMS:
                    if pd.isna(column[f"{equipment} {item}"]):
                        exceptions.append(
                            IncompleteProfileEquipment(column["프로필 이름"], equipment, item)
                        )

        return exceptions


class NotUsedProfile(ExcelWarning):

    def __init__(self, object_name:str) -> None:

        super().__init__(PROFILE_SHEETNAME, object_name)
        self.message = f"'{PROFILE_SHEETNAME}' 시트의 프로필 '{self.object_name}'은 어떤 실에서도 사용되지 않습니다."

        return

    @staticmethod
    def inspect(exceldata:dict[str, pd.DataFrame]) -> list[NotUsedProfile]:

        if PROFILE_SHEETNAME not in exceldata:
            return []

        # reference data
        used_profiles = exceldata["실"]["용도프로필"].to_list()

        # check
        warnings = []
        for name in _user_profiles(exceldata).loc["프로필 이름"]:

            if name not in used_profiles:
                warnings.append(NotUsedProfile(name))

        return warnings


# v-070 수정사항
EXCEL_REB_INSPECTORS = [
    # exceptions
    NoProfileSheet,
    UndefinedProfile,
    InvalidProfileBase,
    IncompleteProfileOccupancy,
    IncompleteProfileEquipment,
    # warnings
    NotUsedProfile,
]


EXCEL_INSPECTORS = [
    # exceptions
    InvalidAdjacentZoneName,
    InvalidSourceSystemName,
    InvalidSurfaceConstruction,
    InvalidFenestrationConstruction,
    InsufficientSurfaceForZone,
    BlindForNonOutdoorWindow,
    InsufficientMaterialDefinition,
    DuplicatedName,
    ExcessiveOpeningArea,
    DualRadiantFloor,
    IncompatibleSourceSystem,
    # warnings
    NotUsedSupplySystem,
    UnreflectedSupplySystemCount,
    NotUsedSourceSystem,
    NotUsedSurfaceConstruction,
    NoHVACSystemApplied,
]

JSON_INSPECTORS = [
    
]

def debug_excel(filepath:str, include_reb:bool=False) -> list[ExcelException]:
    exceldata = pd.read_excel(filepath, sheet_name=list(VALID_COLUMNS.keys()), header=HEADER_ROW)
    
    # v-070 수정사항
    if include_reb:
        with pd.ExcelFile(filepath) as f:
            if PROFILE_SHEETNAME in f.sheet_names:
                exceldata[PROFILE_SHEETNAME] = pd.read_excel(f, sheet_name=PROFILE_SHEETNAME, header=None)
    
    exceptions = []
    warnings   = []
    
    inspectors = EXCEL_INSPECTORS + EXCEL_REB_INSPECTORS if include_reb else EXCEL_INSPECTORS
    for inspector in inspectors:
        
        # check
        inspect_result = inspector.inspect(exceldata)
        # errors
        if issubclass(inspector, ExcelException):
            exceptions += inspect_result
        # and warnings
        if issubclass(inspector, ExcelWarning):
            warnings += inspect_result
    
    return exceptions, warnings


def debug_json(filepath:str) -> list[ExcelException]:
    
    with open(filepath, encoding="UTF-8") as f:
        exceldata = json.load(f, object_hook=lambda d: SimpleNamespace(**d))

    exceptions = []
    warnings   = []
    
    for inspector in JSON_INSPECTORS:
        
        # check
        inspect_result = inspector.inspect(exceldata)
        # errors
        if issubclass(inspector, ExcelException):
            exceptions += inspect_result
        # and warnings
        if issubclass(inspector, ExcelWarning):
            warnings += inspect_result
    
    return exceptions, warnings


class ReportCode(Enum):
                   
    CLEAR   = auto()
    WARNING = auto()
    SEVERE  = auto()
    
    
def report_result(exceptions:list[Exception], warnings:list[UserWarning]) -> tuple[ReportCode, pd.DataFrame]:
    
    if len(exceptions) >= 1:
        code = ReportCode.SEVERE
    elif len(warnings) >= 1:
        code = ReportCode.WARNING
    else:
        code = ReportCode.CLEAR
        
    if code is not ReportCode.CLEAR:
        report = pd.DataFrame(
            [exception.to_dict() for exception in exceptions] +\
            [warning.to_dict()   for warning   in warnings  ]
        )
        
    else:
        report = pd.DataFrame(columns = ["importance", "category", "subcategory", "type", "object", "message"])
        
    return code, report

def report_to_records(report: pd.DataFrame) -> list[dict]:
    """
    report_result()가 반환한 DataFrame을 JSON-friendly list[dict]로 변환합니다.
    """
    if report.empty:
        return []

    report = report.astype(object).where(pd.notna(report), None)
    return report.to_dict(orient="records")


def merge_report_codes(codes: list[ReportCode]) -> ReportCode:
    """
    여러 파일의 ReportCode를 하나로 병합합니다.
    우선순위: SEVERE > WARNING > CLEAR
    """
    if ReportCode.SEVERE in codes:
        return ReportCode.SEVERE

    if ReportCode.WARNING in codes:
        return ReportCode.WARNING

    return ReportCode.CLEAR
