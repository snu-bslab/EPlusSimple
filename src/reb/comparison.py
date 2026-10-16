
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import os
from abc import ABC, abstractmethod

# third-party modules
import pandas as pd

# local modules
from epsimple.utils import HEADER_ROW, VALID_COLUMNS # v-070 수정사항
from .preprocess import process_excel_file
from .postprocess import ( # v-070 수정사항
    용도프로필적용,
    용도프로필,
    프로필설비,
)


# ---------------------------------------------------------------------------- #
#                              DIFFERENCE CLASSES                              #
# ---------------------------------------------------------------------------- #

class ExcelDifference(ABC):
    
    def __init__(self,
        zonename:str,
        prop    :str,
        before  :int|float|str,
        after   :int|float|str,
        unit    :str,
        ) -> None:
        
        self.zonename = zonename
        self.prop     = prop
        self.before   = before
        self.after    = after
        self.unit     = unit
    
    @classmethod
    @abstractmethod
    def compare(cls,
        before: dict[str, pd.DataFrame],
        after : dict[str, pd.DataFrame]
        ) -> list[ExcelDifference]: ...
    
    def to_dict(self) -> dict:
        return {
            "zonename": self.zonename,
            "type"    : self.KoreanNAME,
            "prop"    : self.prop,
            "before"  : self.before,
            "after"   : self.after,
            "unit"    : self.unit,
        }

class ZoneDifference(ExcelDifference):
    
    KoreanNAME = "존 생성/삭제"
    
    @classmethod
    def compare(cls,
        before: dict[str, pd.DataFrame],
        after : dict[str, pd.DataFrame],
        ) -> list[ZoneDifference]:
        
        diffs = []
        for _, row in before["실"].iterrows():
            if (zonename:=row["이름"]) not in after["실"]["이름"]:
                diffs.append(cls(zonename, "존재", "소멸", "-","-"))
        
        for _, row in after["실"].iterrows():
            if (zonename:=row["이름"]) not in before["실"]["이름"]:
                diffs.append(cls(zonename, "존재", "-", "신규","-"))
                
        return diffs

class WindowDifference(ExcelDifference):
    
    KoreanNAME = "창호 변경"
    
    @classmethod
    def compare(cls,
        before: dict[str, pd.DataFrame],
        after : dict[str, pd.DataFrame]
        ) -> list[WindowDifference]: 
        
        # data
        before_Udict = {
            row["이름"]: row["열관류율 [W/m2·K]"]
            for _, row in before["구조체_개구부"].iterrows()
        }
        after_Udict = {
            row["이름"]: row["열관류율 [W/m2·K]"]
            for _, row in after["구조체_개구부"].iterrows()
        }
        before_SHGCdict = {
            row["이름"]: row["태양열취득계수"]
            for _, row in before["구조체_개구부"].iterrows()
        }
        after_SHGCdict = {
            row["이름"]: row["태양열취득계수"]
            for _, row in after["구조체_개구부"].iterrows()
        }
        
        # main
        diffs = []
        for _, row in before["실"].iterrows():
            
            zonename = row["이름"]
            if zonename not in after["실"]["이름"].values:
                continue
            
            # windowdata: before
            before_walls   = before["면"].loc[before["면"]["소속 실"] == zonename]
            before_windows = before["개구부"].loc[before["개구부"]["소속 면"].map(lambda v: v in before_walls["이름"].values)]
            before_winarea = before_windows["면적 [m2]"].sum()
            
            # windowdata: after
            after_walls   = after["면"].loc[after["면"]["소속 실"] == zonename]
            after_windows = after["개구부"].loc[after["개구부"]["소속 면"].map(lambda v: v in after_walls["이름"].values)]
            after_winarea  = after_windows["면적 [m2]"].sum()
            
            # area comparison
            if abs(before_winarea - after_winarea) > 0.1:
                diffs.append(cls(zonename, "면적", before_winarea, after_winarea, "m2"))
                
            if (before_winarea > 0 and after_winarea > 0):
                
                # U valud comparison
                before_U = float(sum(
                    row["면적 [m2]"]*before_Udict[row["구조체 이름"]]
                    for _, row in before_windows.iterrows()
                    )/before_winarea)
                after_U = float(sum(
                    row["면적 [m2]"]*after_Udict[row["구조체 이름"]]
                    for _, row in after_windows.iterrows()
                    )/after_winarea)

                if abs(before_U - after_U) > 0.1:
                    diffs.append(cls(zonename, "평균열관류율", round(before_U,2), round(after_U,2), "W/m2K"))
                
                # SHGC comparison
                before_SHGC = float(sum(
                    row["면적 [m2]"]*before_SHGCdict[row["구조체 이름"]]
                    for _, row in before_windows.iterrows()
                    )/before_winarea)
                after_SHGC = float(sum(
                    row["면적 [m2]"]*after_SHGCdict[row["구조체 이름"]]
                    for _, row in after_windows.iterrows()
                    )/after_winarea)

                if abs(before_SHGC - after_SHGC) > 0.1:
                    diffs.append(cls(zonename, "태양열취득계수", round(before_SHGC,3), round(after_SHGC,3), "-"))     
        
        return diffs



class LightDensityDifference(ExcelDifference):
    
    KoreanNAME = "조명"
    
    @classmethod
    def compare(cls,
        before: dict[str, pd.DataFrame],
        after : dict[str, pd.DataFrame]
        ) -> list[LightDensityDifference]:
        
        diffs = []
        for _, row in before["실"].iterrows():
            
            zonename = row["이름"]
            if zonename not in after["실"]["이름"].values:
                continue
            
            before_LPD=row["조명밀도 [W/m2]"]
            after_LPD =float(after["실"]["조명밀도 [W/m2]"][after["실"]["이름"] == row["이름"]].iloc[0])
            
            if abs(before_LPD - after_LPD) > 0.01:
                diffs.append(cls(zonename, "교체", before_LPD, after_LPD, "W/m2"))
                
        return diffs
    
class InfiltrationDifference(ExcelDifference):
    
    KoreanNAME = "침기율"
    
    @classmethod
    def compare(cls,
        before: dict[str, pd.DataFrame],
        after : dict[str, pd.DataFrame]
        ) -> list[LightDensityDifference]:
        
        diffs = []
        for _, row in before["실"].iterrows():
            
            zonename = row["이름"]
            if zonename not in after["실"]["이름"].values:
                continue
            
            before_LPD=row["침기율 [ACH@50]"]
            after_LPD =float(after["실"]["침기율 [ACH@50]"][after["실"]["이름"] == row["이름"]].iloc[0])
            
            # v-070 수정사항: 빈칸은 자동 계산(창 있으면 1.5, 없으면 0)이므로 '자동' 으로 표시
            if pd.isna(before_LPD):
                before_LPD = "자동"
            if pd.isna(after_LPD):
                after_LPD = "자동"
            
            if before_LPD == "자동" or after_LPD == "자동":
                if before_LPD != after_LPD:
                    diffs.append(cls(zonename, "변화", before_LPD, after_LPD, "ACH50"))
            elif abs(before_LPD - after_LPD) > 0.01:
                diffs.append(cls(zonename, "변화", before_LPD, after_LPD, "ACH50"))
                
        return diffs

# v-070 수정사항
# 070 템플릿은 실 탭이 아니라 공급설비 탭의 '공급 실' 열로 실과 설비를 연결한다

def find_supply_systems(excel:dict[str, pd.DataFrame], zonename:str) -> list[pd.Series]:
    """실에 연결된 공급설비 행들"""
    systems = []
    for _, row in excel["공급설비"].iterrows():
        if row["공급 실"] == zonename:
            systems.append(row)
    return systems


def find_source_system(excel:dict[str, pd.DataFrame], sourcename:str) -> pd.Series|None:
    """이름으로 생산설비 행 찾기 (없으면 None)"""
    for _, row in excel["생산설비"].iterrows():
        if row["이름"] == sourcename:
            return row
    return None


def number_text(value, digits:int=2) -> str:
    """숫자를 문자열로, 비어 있으면 '-'"""
    if pd.isna(value):
        return "-"
    return f"{value:.{digits}f}"


def kw_text(value_in_watt) -> str:
    """W 를 kW 문자열로, 비어 있으면 '-'"""
    if pd.isna(value_in_watt):
        return "-"
    return f"{value_in_watt*1E-3:.2f}kW"


def heating_text(supply:pd.Series, source:pd.Series|None) -> str:
    """공급설비 한 대의 난방 설명. 난방을 못 하는 설비면 빈 문자열"""
    kind = supply["유형"]

    if kind == "전기방열기":
        return f"전기방열기: {kw_text(supply['난방용량 [W]'])}"
    if kind == "전기바닥난방":
        return "전기바닥난방"

    # 아래는 생산설비가 필요한 유형
    if source is None:
        return ""
    if kind == "공조기":
        return f"공조기&{source['유형']}: COP {number_text(source['난방COP [W/W]'])}, {kw_text(source['난방용량 [W]'])}"
    if kind in ("팬코일유닛", "방열기", "바닥난방"):
        return f"{kind}&{source['유형']}: 효율 {number_text(source['효율 [%]'], 1)}%, {kw_text(source['난방용량 [W]'])}"

    return ""


def cooling_text(supply:pd.Series, source:pd.Series|None) -> str:
    """공급설비 한 대의 냉방 설명. 냉방을 못 하는 설비면 빈 문자열"""
    kind = supply["유형"]

    if kind == "패키지에어컨":
        return f"패키지에어컨: COP {number_text(supply['냉방COP [W/W]'])}, {kw_text(supply['냉방용량 [W]'])}"

    if source is None:
        return ""
    if kind in ("공조기", "팬코일유닛"):
        return f"{kind}&{source['유형']}: COP {number_text(source['냉방COP [W/W]'])}, {kw_text(source['냉방용량 [W]'])}"

    return ""


def zone_hvac_text(excel:dict[str, pd.DataFrame], zonename:str, mode:str) -> str:
    """실에 연결된 설비들의 난방(또는 냉방) 설명을 ', ' 로 이어 붙인다"""
    texts = []
    for supply in find_supply_systems(excel, zonename):
        source = find_source_system(excel, supply["생산설비명"])
        if mode == "heating":
            text = heating_text(supply, source)
        else:
            text = cooling_text(supply, source)
        if text != "":
            texts.append(text)
    return ", ".join(texts)


class HeatingHVACDifference(ExcelDifference):

    KoreanNAME = "난방설비"

    @classmethod
    def compare(cls,
        before: dict[str, pd.DataFrame],
        after : dict[str, pd.DataFrame]
        ) -> list[HeatingHVACDifference]:

        diffs = []
        for _, row in before["실"].iterrows():

            zonename = row["이름"]
            if zonename not in after["실"]["이름"].values:
                continue

            beforeheating = zone_hvac_text(before, zonename, "heating")
            afterheating  = zone_hvac_text(after , zonename, "heating")

            if beforeheating != afterheating:
                diffs.append(cls(zonename, "변경", beforeheating, afterheating, "-"))

        return diffs


class CoolingHVACDifference(ExcelDifference):

    KoreanNAME = "냉방설비"

    @classmethod
    def compare(cls,
        before: dict[str, pd.DataFrame],
        after : dict[str, pd.DataFrame]
        ) -> list[CoolingHVACDifference]:

        diffs = []
        for _, row in before["실"].iterrows():

            zonename = row["이름"]
            if zonename not in after["실"]["이름"].values:
                continue

            beforecooling = zone_hvac_text(before, zonename, "cooling")
            aftercooling  = zone_hvac_text(after , zonename, "cooling")

            if beforecooling != aftercooling:
                diffs.append(cls(zonename, "변경", beforecooling, aftercooling, "-"))

        return diffs


# ---------------------------------------------------------------------------- #
#                         OPERATION DIFFERENCE CLASSES                         #
# ---------------------------------------------------------------------------- #

# v-070 수정사항
# 현장조사 시트(보건소/어린이집) 대신 용도프로필 탭을 비교한다

def time_text(hour_minute:tuple[int,int]|None) -> str:
    if hour_minute is None:
        return "-"
    return f"{hour_minute[0]:02d}:{hour_minute[1]:02d}"


def equipment_text(equipment:프로필설비|None) -> str:
    """난방/냉방 설비 항목 하나의 설명"""
    if equipment is None:
        return "주용도 기준"
    if not equipment.사용여부:
        return "미사용"
    return f"{equipment.시작월}~{equipment.종료월}월 {time_text(equipment.시작)}~{time_text(equipment.종료)}: {equipment.설정온도:.1f}℃"


def profile_texts(profile:용도프로필) -> dict[str, str]:
    """용도프로필 하나를 항목별 문자열로 정리 (비교용)"""
    texts = {}

    if profile.has_occupancy:
        texts["재실인원"] = f"상주 {profile.상주인원}명, 방문 {profile.방문인원}명 ({profile.방문체류분}분)"
        texts["재실시간"] = f"{time_text(profile.상주시작)}~{time_text(profile.상주종료)}, {profile.운영시작월}~{profile.운영종료월}월"
    else:
        texts["재실인원"] = "주용도 기준"
        texts["재실시간"] = "주용도 기준"

    texts["난방1"] = equipment_text(profile.난방설비1)
    texts["난방2"] = equipment_text(profile.난방설비2)
    texts["냉방1"] = equipment_text(profile.냉방설비1)
    texts["냉방2"] = equipment_text(profile.냉방설비2)

    return texts


class ProfileDifference(ExcelDifference):

    KoreanNAME = "프로필변동"

    @classmethod
    def compare(cls,
        before: dict[str, pd.DataFrame],
        after : dict[str, pd.DataFrame],
        profilebefore: 용도프로필적용,
        profileafter : 용도프로필적용,
        ) -> list[ProfileDifference]:

        diffs = []
        for zonename in profilebefore.zone_profile:

            if zonename not in profileafter.zone_profile:
                continue

            # 실 탭에 적힌 프로필 이름 (빈칸은 "")
            namebefore = profilebefore.zone_profile[zonename]
            nameafter  = profileafter.zone_profile[zonename]
            if pd.isna(namebefore):
                namebefore = ""
            if pd.isna(nameafter):
                nameafter = ""

            # 이름이 다르면 프로필 자체가 바뀐 것
            if namebefore != nameafter:
                diffs.append(cls(zonename, "프로필변경", namebefore, nameafter, "-"))
                continue

            # 이름이 같고 용도프로필 탭에 정의된 것이면 항목별로 비교
            if namebefore not in profilebefore.profiles:
                continue
            if nameafter not in profileafter.profiles:
                continue

            textsbefore = profile_texts(profilebefore.profiles[namebefore])
            textsafter  = profile_texts(profileafter.profiles[nameafter])
            for item in textsbefore:
                if textsbefore[item] != textsafter[item]:
                    diffs.append(cls(zonename, item, textsbefore[item], textsafter[item], "-"))

        return diffs


# ---------------------------------------------------------------------------- #
#                                 SUBFUNCTIONS                                 #
# ---------------------------------------------------------------------------- #

PERFORMANCE_DIFFLIST = [
    WindowDifference      ,
    LightDensityDifference,
    InfiltrationDifference,
    HeatingHVACDifference ,
    CoolingHVACDifference ,
]

OPERATION_DIFFLIST = [ # v-070 수정사항
    ProfileDifference,
]

def compare_performance(
    excelbefore:dict[str, pd.DataFrame],
    excelafter :dict[str, pd.DataFrame],
    ) -> list[ExcelDifference]:
    
    diffs = []
    for diff in PERFORMANCE_DIFFLIST:
        diffs += diff.compare(excelbefore, excelafter)
    
    return diffs


def compare_operation(
    excelbefore:dict[str, pd.DataFrame],
    excelafter :dict[str, pd.DataFrame],
    profilebefore: 용도프로필적용, # v-070 수정사항
    profileafter : 용도프로필적용, # v-070 수정사항
    ) -> list[ExcelDifference]:

    diffs = []
    for diff in OPERATION_DIFFLIST: # v-070 수정사항
        diffs += diff.compare(
            excelbefore  ,
            excelafter   ,
            profilebefore,
            profileafter ,
        )

    return diffs

# ---------------------------------------------------------------------------- #
#                                   MAIN FUNC                                  #
# ---------------------------------------------------------------------------- #

def compare_rebexcel(
    excelbeforepath:dict[str, pd.DataFrame],
    excelafterpath :dict[str, pd.DataFrame],
    ) -> tuple[list[ExcelDifference]]:
    
    # before data
    processedbeforepath = process_excel_file(excelbeforepath, verbose=False)
    excelbefore         = pd.read_excel(processedbeforepath, sheet_name=list(VALID_COLUMNS.keys()), header=HEADER_ROW) # v-070 수정사항
    os.remove(processedbeforepath)

    # after data
    processedafterpath = process_excel_file(excelafterpath, verbose=False)
    excelafter         = pd.read_excel(processedafterpath, sheet_name=list(VALID_COLUMNS.keys()), header=HEADER_ROW) # v-070 수정사항
    os.remove(processedafterpath)

    # profile data (원본 파일에서 읽는다. 전처리 파일은 실 탭의 프로필 이름이 주용도로 바뀌어 있음)
    profilebefore = 용도프로필적용.from_excel(excelbeforepath) # v-070 수정사항
    profileafter  = 용도프로필적용.from_excel(excelafterpath)  # v-070 수정사항

    # compare
    performance_differences = compare_performance(excelbefore, excelafter)
    operation_differences   = compare_operation(excelbefore, excelafter, profilebefore, profileafter) # v-070 수정사항

    performance_differences = pd.DataFrame([diff.to_dict() for diff in performance_differences])
    operation_differences   = pd.DataFrame([diff.to_dict() for diff in operation_differences])
    
    return performance_differences, operation_differences
    