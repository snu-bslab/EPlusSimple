
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import re
import math
import random
import datetime # (v0-7-0) 추가

from copy        import deepcopy
from types       import SimpleNamespace
from typing      import Literal
from dataclasses import dataclass
from abc import (
    ABC           ,
    abstractmethod,
)

# third-party modules
import pandas as pd

# local modules
from epsimple import GreenRetrofitModel
from epsimple.utils import (
    _preprocess_excel_dict ,
    _convert_supply_systems,
    _convert_source_systems,
    _replace_nan_to_none   ,
    PROFILE_RENAME_DICT # (v0-7-0) 추가
)
from epsimple.core.hvac import (
    SupplySystem,
    SourceSystem,
)
from idragon import (
    dragon     ,
    IDF        ,
    EnergyModel,
)

# settings
random.seed(hash("REB-PHIKO-SNU"))


# ---------------------------------------------------------------------------- #
#                          SUBFUNCTIONS: EXCEL TO DATA                         #
# ---------------------------------------------------------------------------- #

def row_to_timestring(row:pd.Series) -> None|str:
    
    if pd.isna(row).any():
        return None
    
    else:
        row = row.astype(int)
        return f"{row["시작시"]:02d}:{row["시작분"]:02d}~{row["종료시"]:02d}:{row["종료분"]:02d}"
    
    
def row_to_dayofweekstr(row:pd.Series) -> str:
    
    return ", ".join([dayofweek for dayofweek, condition in row.to_dict().items() if condition and (dayofweek in ["월","화","수","목","금","토","일"])])


def row_to_설비운영(row:pd.Series) -> None|설비운영:

    # 미설치/미사용 : 사용시간이 00:00~00:00 (선행판정)
    시간 = row[["시작시","시작분","종료시","종료분"]]
    if not pd.isna(시간).any() and (시간.astype(int)==0).all():
        return 설비운영(None,None,None,사용여부=False)
    
    if pd.isna(row.iloc[:6]).any():
        return None
    
    else:
        return 설비운영(
            row_to_timestring(row[["시작시","시작분","종료시","종료분"]]),
            f"{int(row["시작월"]):02d}~{int(row["종료월"]):02d}월",
            (float(v) if not pd.isna(v) else None) if not isinstance(v:=row["설정온도"], str) else v,
        )

# ---------------------------------------------------------------------------- #
#                         SUBFUNCTINOS: DATA TO DRAGON                         #
# ---------------------------------------------------------------------------- #

def parse_duration_hours(operation_str:str) -> tuple[int,int,int,int]:
    
    pattern = re.compile(r"(?P<starth>\d{1,2}):(?P<startm>\d{2}) ?(-|~) ?(?P<endh>\d{1,2}):(?P<endm>\d{2})")
    matched = re.search(pattern, operation_str)
    
    return int(matched.group("starth")), int(matched.group("startm")), int(matched.group("endh")), int(matched.group("endm"))

def parse_duration_month(operation_str:str) -> tuple[list[int, int], list[int,int]|None]:
    
    pattern = re.compile(r"(?P<startm>\d{1,2})월? ?(-|~) ?(?P<endm>\d{1,2})월")
    matched = re.search(pattern, operation_str)
    
    startm1 = int(matched.group("startm"))
    endm1   = int(matched.group("endm"))

    if endm1 >= startm1:
        return [startm1, endm1], None
    
    else:
        return [1, endm1], [startm1, 12]
    
def translate_dayofweek(korean_dow:str) -> str:
    
    dow_dict = {
        "월": "monday"   ,
        "화": "tuesday"  ,
        "수": "wednesday",
        "목": "thursday" ,
        "금": "friday"   ,
        "토": "saturday" ,
        "일": "sunday"   ,
    }
    
    return dow_dict[korean_dow]

def get_end_of_the_month(mth:int) -> int:
    
    endofthemonth_dict = {
        1:31, 2:28, 3:31,  4:30,  5:31,  6:30,
        7:31, 8:31, 9:30, 10:31, 11:30, 12:31,
    }
    
    return endofthemonth_dict[mth]

def ensure_integer_with_nan(v) -> int:
    if not pd.isna(v):
        return v
    else:
        return 0

# ---------------------------------------------------------------------------- #
#                          SUBFUNCTIONS: SCHEDULE 관련                          #
# ---------------------------------------------------------------------------- #

def make_집중진료_dayschedule_values(starth, startm, endh, endm,
                  x1, t1, x2, t2,
                  mode="random") -> list[int]:
    
    slots = [0] * 144  # 하루 전체

    # 운영시간을 슬롯 인덱스로 변환
    start_idx = (starth * 60 + startm) // 10
    end_idx   = (endh   * 60 + endm) // 10
    if end_idx > 144: end_idx = 144

    # 오전/오후 범위
    am_start, am_end = 0, 72
    pm_start, pm_end = 72, 144

    def assign_people(n, stay_min, seg_start, seg_end):
        stay_slots = math.ceil(stay_min / 10)
        # 운영시간과 교집합으로 제한
        seg_start = max(seg_start, start_idx)
        seg_end   = min(seg_end, end_idx)
        available = seg_end - seg_start
        if n == 0 or stay_slots <= 0 or available <= 0:
            return [], 0

        if mode == "random":
            if n <= (seg_end - seg_start - stay_slots + 1):
                start_points = sorted(random.sample(
                    range(seg_start, seg_end - stay_slots + 1), n
                ))
            else:
                start_points = sorted(random.choices(
                    range(seg_start, seg_end - stay_slots + 1), k=n
                ))

        else:  # 균등 배치 (실수 단위로 계산 후 반올림)
            if n == 1:
                start_points = [seg_start]
            else:
                step = (available - stay_slots) / (n - 1)
                start_points = [
                    round(seg_start + i * step)
                    for i in range(n)
                ]
                start_points = [
                    max(seg_start, min(seg_end - stay_slots, s))
                    for s in start_points
                ]

        return start_points, stay_slots

    # 오전 배정
    if x1 > 0:
        am_points, am_stay = assign_people(x1, t1, am_start, am_end)
        for s in am_points:
            for i in range(am_stay):
                slots[s+i] += 1

    # 오후 배정
    if x2 > 0:
        pm_points, pm_stay = assign_people(x2, t2, pm_start, pm_end)
        for s in pm_points:
            for i in range(pm_stay):
                slots[s+i] += 1

    return slots

# ---------------------------------------------------------------------------- #
#                                 SURVEY ITEMS                                 #
# ---------------------------------------------------------------------------- #

@dataclass
class 설비운영:
    사용시간:str
    사용기간:str
    설정온도:int
    사용여부:bool=True  # False = 미설치/미사용
    
    def get_hvac_availability_schedule(self, mode:Literal["heating","cooling"]) -> dragon.Schedule:
        
        # all-off schedule
        alloff_schedule = dragon.Schedule.from_compact(
            None,
            [("0101","1231", dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(None,[(24,0,0)], dragon.ScheduleType.ONOFF),
                dragon.DaySchedule.from_compact(None,[(24,0,0)], dragon.ScheduleType.ONOFF),
            ))]
        )

        if not self.사용여부:
            return alloff_schedule
        # 시간
        starth, startm, endh, endm = parse_duration_hours(self.사용시간)
        if starth + startm/100 < endh + endm/100:
            availability_dayschedule = dragon.DaySchedule.from_compact(
                None,
                [
                    (starth, startm, 0),
                    (endh  , endm  , 1),
                    (24    , 0     , 0),
                ],
                dragon.ScheduleType.ONOFF         
            )
        else:
            availability_dayschedule = dragon.DaySchedule.from_compact(
                None,
                [
                    (endh  , endm  , 1),
                    (starth, startm, 0),
                    (24    , 0     , 1),
                ],
                dragon.ScheduleType.ONOFF         
            )
        availability_ruleset = dragon.RuleSet(
            None,
            availability_dayschedule,
            availability_dayschedule,
        )
        
        # 기간
        
        if mode == "heating":
            availability_schedule = alloff_schedule.apply(
                availability_ruleset,
                start = "0101",
                end   = "0515",
                inplace=False
            ) 
            availability_schedule.apply(
                availability_ruleset,
                start = f"0916",
                end   = f"1231",
                inplace=True
            )
        if mode == "cooling":
            availability_schedule = alloff_schedule.apply(
                availability_ruleset,
                start = "0516",
                end   = "0915",
                inplace=False
            )
        
        return availability_schedule

    def get_setpoint_schedule(self,
        original_schedule:dragon.Schedule             ,
        mode             :Literal["heating","cooling"],
        ) -> dragon.Schedule:
        
        # uncontrolled temperature
        match mode:
            case "heating": default_temperature = -30
            case "cooling": default_temperature =  50
        
        # for invalid case: return default setpoint temperature
        if self.설정온도 == "확인불가" or self.설정온도 is None:
            match mode:
                case "heating": setpoint = original_schedule.max
                case "cooling": setpoint = original_schedule.min
        else:
            setpoint = self.설정온도
        
        constant_setpoint = dragon.Schedule.from_compact(
            None,
            [
                ("0101","1231", dragon.RuleSet(
                    None,
                    dragon.DaySchedule(None, [setpoint]*dragon.DaySchedule.DATA_INTERVAL*24, type=dragon.ScheduleType.TEMPERATURE),
                    dragon.DaySchedule(None, [setpoint]*dragon.DaySchedule.DATA_INTERVAL*24, type=dragon.ScheduleType.TEMPERATURE),
                ))
            ]
        )
        default_setpoint = dragon.Schedule.from_compact(
            None,
            [
                ("0101","1231", dragon.RuleSet(
                    None,
                    dragon.DaySchedule(None, [default_temperature]*dragon.DaySchedule.DATA_INTERVAL*24, type=dragon.ScheduleType.TEMPERATURE),
                    dragon.DaySchedule(None, [default_temperature]*dragon.DaySchedule.DATA_INTERVAL*24, type=dragon.ScheduleType.TEMPERATURE),
                ))
            ]
        )
        
        availability_schedule = self.get_hvac_availability_schedule(mode)
        operational_setpoint = constant_setpoint * availability_schedule + default_setpoint * (~availability_schedule)
        operational_setpoint.name = hex(id(operational_setpoint))
        
        return operational_setpoint

@dataclass
class hvac존:
    
    # hvac
    난방설비1:설비운영
    난방설비2:설비운영
    냉방설비1:설비운영
    냉방설비2:설비운영
    
    def get_heating_setpoint_schedule(self, original_schedule:dragon.Schedule) -> dragon.Schedule:
        
        # 난방설비 1
        if self.난방설비1 is not None:
            first_equipment_setpoint = self.난방설비1.get_setpoint_schedule(original_schedule, "heating")
        
            # 난방설비 2
            if self.난방설비2 is not None:
                second_equipment_setpoint = self.난방설비2.get_setpoint_schedule(original_schedule, "heating")
                
                # 둘 다 고려 (최댓값으로)
                final_schedule = first_equipment_setpoint.element_max(second_equipment_setpoint)
                
            else:
                final_schedule = first_equipment_setpoint
        
        else:
            final_schedule = dragon.Schedule.from_compact(
                None,
                [
                    ("0101","1231", dragon.RuleSet(
                        None,
                        dragon.DaySchedule(None, [-30]*dragon.DaySchedule.DATA_INTERVAL*24, type=dragon.ScheduleType.TEMPERATURE),
                        dragon.DaySchedule(None, [-30]*dragon.DaySchedule.DATA_INTERVAL*24, type=dragon.ScheduleType.TEMPERATURE),
                    ))
                ]
            )
        
        return final_schedule
    
    def get_cooling_setpoint_schedule(self, original_schedule:dragon.Schedule) -> dragon.Schedule:
        
        # 냉방설비 1
        if self.냉방설비1 is not None:
            first_equipment_setpoint = self.냉방설비1.get_setpoint_schedule(original_schedule, "cooling")
            
            # 냉방설비 2
            if self.냉방설비2 is not None:
                second_equipment_setpoint = self.냉방설비2.get_setpoint_schedule(original_schedule, "cooling")
                
                # 둘 다 고려 (최솟값으로)
                final_schedule = first_equipment_setpoint.element_min(second_equipment_setpoint)
                
            else:
                final_schedule = first_equipment_setpoint
        
        else:
            final_schedule = dragon.Schedule.from_compact(
                None,
                [
                    ("0101","1231", dragon.RuleSet(
                        None,
                        dragon.DaySchedule(None, [50]*dragon.DaySchedule.DATA_INTERVAL*24, type=dragon.ScheduleType.TEMPERATURE),
                        dragon.DaySchedule(None, [50]*dragon.DaySchedule.DATA_INTERVAL*24, type=dragon.ScheduleType.TEMPERATURE),
                    ))
                ]
            )
        
        return final_schedule
    
    def apply_hvac_availability(self, zone:dragon.Zone):
        
        if isinstance(zone.heating_supply, dragon.hvac.SupplyGroup):
            zone.heating_supply.availabilities = [
                self.난방설비1.get_hvac_availability_schedule("heating"),
                self.난방설비2.get_hvac_availability_schedule("heating"),
                ]
            
        if isinstance(zone.cooling_supply, dragon.hvac.SupplyGroup):
            zone.cooling_supply.availabilities = [
                self.냉방설비1.get_hvac_availability_schedule("cooling"),
                self.냉방설비2.get_hvac_availability_schedule("cooling"),
            ]
    

@dataclass
class 보건소일반존(hvac존):
    # zone
    운영시간:str
    직원   :str
    외근횟수:int
    외근시간:str
    외근직원:int
    집중진료요일:str
    집중진료시간:str
    집중진료오전방문객:str
    집중진료오후방문객:str
    집중진료오전체류시간:int
    집중진료오후체류시간:int
    
    @classmethod
    def from_excel(cls, filepath:str):
        
        # components
        재실 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=5, nrows=5, usecols=[3,4,5], index_col=0)
        운영시간 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=11, nrows=4, usecols=[3,4,5,6,7], index_col=0)
        운영요일 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=16, nrows=3, usecols=[3,4,5,6,7,8], index_col=0)
        설비 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=21, nrows=5, usecols=[3,4,5,6,7,8,9,10], index_col=0)
        설비.columns = ["시작시","시작분","종료시","종료분","시작월","종료월","설정온도"]
        
        return cls(
            *[
                row_to_설비운영(row)
                for _, row in 설비.iterrows()
            ],
            row_to_timestring(운영시간.loc["기본운영"]),
            int(재실.at["직원","인원수"]),
            int(운영요일.loc["외근"].sum()),
            row_to_timestring(운영시간.loc["외근"]),
            int(v) if not pd.isna(v:=재실.at["외근직원","인원수"]) else 0,
            row_to_dayofweekstr(운영요일.loc["집중진료"]),
            row_to_timestring(운영시간.loc["집중진료"]),
            int(v) if not pd.isna(v:=재실.at["집중진료-오전","인원수"]) else 0,
            int(v) if not pd.isna(v:=재실.at["집중진료-오후","인원수"]) else 0,
            int(v) if not pd.isna(v:=재실.at["집중진료-오전","체류시간"]) else 0,
            int(v) if not pd.isna(v:=재실.at["집중진료-오후","체류시간"]) else 0,
        )
    
    def get_occupant_schedule(self) -> dragon.Schedule:
        
        # 기본 운영시간
        starth, startm, endh, endm = parse_duration_hours(self.운영시간)
        기본운영_직원_ruleset = dragon.RuleSet(
            None,
            dragon.DaySchedule.from_compact(
                None,
                [
                    (starth, startm,        0),
                    (endh  , endm  , self.직원),
                    (24    , 0     ,        0),
                ],
                dragon.ScheduleType.REAL,
            ),
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,)
        )
        final_occupant_ruleset = 기본운영_직원_ruleset
        
        # 집중진료
        if self.집중진료요일:
            # 요일 parsing
            집중진료_dayofweeks = [translate_dayofweek(s.strip()) for s in self.집중진료요일.split(",") if not s==""]
            # 시간 정하기 (random 배정)
            starth, startm, endh, endm = parse_duration_hours(self.집중진료시간)
            schedule_values = make_집중진료_dayschedule_values(
                starth, startm, endh, endm,
                self.집중진료오전방문객, self.집중진료오전체류시간, self.집중진료오후방문객, self.집중진료오후체류시간
            )
            # ruleset 만들기
            집중진료_방문객_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                **{
                    k: dragon.DaySchedule(None, schedule_values, type=dragon.ScheduleType.REAL)
                    for k in 집중진료_dayofweeks
                }
            )
            
            # 적용
            final_occupant_ruleset += 집중진료_방문객_ruleset
        
        else:
            집중진료_dayofweeks = []
        
        # 외근
        if self.외근직원 > 0:
            # 요일 정하기
            non_집중진료_dayofweeks = {"monday","tuesday","wednesday","thursday","friday"} - set(집중진료_dayofweeks)
            if len(non_집중진료_dayofweeks) >= self.외근횟수:
                외근_dayofweeks = random.sample(sorted(non_집중진료_dayofweeks), self.외근횟수)
            else:
                외근_dayofweeks = list(non_집중진료_dayofweeks) + random.sample(sorted(집중진료_dayofweeks), self.외근횟수-len(non_집중진료_dayofweeks))

            # 시간 정하기
            starth, startm, endh, endm = parse_duration_hours(self.외근시간)
            # ruleset 만들기
            외근_직원_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                **{
                    k: dragon.DaySchedule.from_compact(
                        None,
                        [
                            (starth, startm,           0),
                            (endh  , endm  , self.외근직원),
                            (24    , 0     ,           0),
                        ],
                        dragon.ScheduleType.REAL,
                    )
                    for k in 외근_dayofweeks
                }
            )
            
            final_occupant_ruleset -= 외근_직원_ruleset
            
        # 스케줄 만들기
        occupant_schedule = dragon.Schedule(
            None,
            [final_occupant_ruleset] * 365
        )
        return occupant_schedule
    
    def get_hvac_availability_schedule(self) -> dragon.Schedule:
        
        # 기본 운영시간
        starth, startm, endh, endm = parse_duration_hours(self.운영시간)
        기본운영_ruleset = dragon.RuleSet(
            None,
            dragon.DaySchedule.from_compact(
                None,
                [
                    (starth, startm, 0),
                    (endh  , endm  , 1),
                    (24    , 0     , 0),
                ],
                dragon.ScheduleType.ONOFF,
            ),
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,)
        )
        기본운영_schedule = dragon.Schedule.from_compact(
            None,
            [("0101","1231", 기본운영_ruleset)]
        )
        
        # 설비 가동스케줄 (개별)
        operation_schedules = []
        for 설비, mode in zip([self.난방설비1, self.난방설비2, self.냉방설비1, self.냉방설비2],["heating","heating","cooling","cooling"]):
            if 설비 is not None:
                operation_schedules.append(설비.get_hvac_availability_schedule(mode))
            else:
                operation_schedules.append(dragon.Schedule.from_compact(
                    None, [("0101","1231", dragon.RuleSet(
                        None,
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                    ))]
                ))
            
        # 설비 가동스케줄 (or조건으로 개별 설비 결합: 모종의 설비가 가동중)
        hvac_availability = operation_schedules[0]
        for schedule in operation_schedules[1:]:
            hvac_availability |= schedule
        
        # 최종 스케줄 = 운영중이면서, 설비 가동 중
        hvac_availability &= 기본운영_schedule
        
        return hvac_availability
    

    def apply_to(self, zones:list[dragon.Zone]) -> None:
        
        total_area = max(sum(zone.floor_area for zone in zones), 1E-6)
        occupant_schedule          = self.get_occupant_schedule()/total_area 
        hvac_availability_schedule = self.get_hvac_availability_schedule()

        for zone in zones:
            
            lighting_schedule  = zone.profile.lighting  * (occupant_schedule > 0)
            equipment_schedule = zone.profile.equipment * (occupant_schedule > 0)
            
            zone.profile = dragon.Profile(
                f"{zone.name}_일반존체크리스트",
                self.get_heating_setpoint_schedule(zone.profile.heating_setpoint), 
                self.get_cooling_setpoint_schedule(zone.profile.cooling_setpoint) , 
                hvac_availability_schedule,
                occupant_schedule         ,
                lighting_schedule         ,
                equipment_schedule        ,
            )
        
            self.apply_hvac_availability(zone)
            
        return
    
@dataclass
class 보건소특화존1(hvac존):
    # zone
    운영요일:str
    오전운영시간:str
    오후운영시간:str
    오전재실인원:int
    오후재실인원:int
    
    @classmethod
    def from_excel(cls, filepath:str):
        
        # components
        재실 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=29, nrows=3, usecols=[3,4], index_col=0)
        운영시간 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=33, nrows=3, usecols=[3,4,5,6,7], index_col=0)
        운영요일 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=37, nrows=2, usecols=[3,4,5,6,7,8], index_col=0)
        설비 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=41, nrows=5, usecols=[3,4,5,6,7,8,9,10], index_col=0)
        설비.columns = ["시작시","시작분","종료시","종료분","시작월","종료월","설정온도"]
        
        # ensure validity by dayofweek
        has_valid_dayofweek = bool(운영요일.loc["운영요일"].any())
        
        return cls(
            *[
                row_to_설비운영(row)
                for _, row in 설비.iterrows()
            ],
            row_to_dayofweekstr(운영요일.loc["운영요일"]),
            row_to_timestring(운영시간.loc["오전"]) if has_valid_dayofweek else None,
            row_to_timestring(운영시간.loc["오후"]) if has_valid_dayofweek else None,
            int(v) if not pd.isna(v:=재실.at["오전","인원수"]) else 0,
            int(v) if not pd.isna(v:=재실.at["오후","인원수"]) else 0,
        )
    
    def get_occupant_schedule(self) -> dragon.Schedule:
        
        # 기본 스케줄 (0명)
        occupant_ruleset = dragon.RuleSet(
            None,
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
        )
        
        # 오전 재실
        if not pd.isna(self.오전운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오전운영시간)
            dayofweeks = [translate_dayofweek(s.strip()) for s in self.운영요일.split(",") if not s==""]
            오전_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                **{
                    k: dragon.DaySchedule.from_compact(
                        None,
                        [
                            (starth, startm,              0),
                            (endh  , endm  , self.오전재실인원),
                            (24    , 0     ,              0),
                        ],
                        dragon.ScheduleType.REAL,
                    )
                    for k in dayofweeks
                }
            )
            occupant_ruleset += 오전_ruleset
        
        # 오후 재실
        if not pd.isna(self.오후운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오후운영시간)
            dayofweeks = [translate_dayofweek(s.strip()) for s in self.운영요일.split(",") if not s==""]
            오후_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                **{
                    k: dragon.DaySchedule.from_compact(
                        None,
                        [
                            (starth, startm,              0),
                            (endh  , endm  , self.오후재실인원),
                            (24    , 0     ,              0),
                        ],
                        dragon.ScheduleType.REAL,
                    )
                    for k in dayofweeks
                }
            )
            occupant_ruleset += 오후_ruleset

        # 둘이 합치기
        occupant_schedule = dragon.Schedule.from_compact(
            None,
            [("0101","1231", occupant_ruleset)]
        )
        
        return occupant_schedule
    
    def get_hvac_availability_schedule(self) -> dragon.Schedule:
        
        # 기본 운영시간
        기본운영_ruleset = dragon.RuleSet(
            None,
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,),
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,),
        )
        
        # 오전 운영시간
        if not pd.isna(self.오전운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오전운영시간)
            오전운영_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(
                    None,
                    [
                        (starth, startm, 0),
                        (endh  , endm  , 1),
                        (24    , 0     , 0),
                    ],
                    dragon.ScheduleType.ONOFF,
                ),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,)
            )
            기본운영_ruleset |= 오전운영_ruleset
        
        # 오후 운영시간
        if not pd.isna(self.오후운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오후운영시간)
            오후운영_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(
                    None,
                    [
                        (starth, startm, 0),
                        (endh  , endm  , 1),
                        (24    , 0     , 0),
                    ],
                    dragon.ScheduleType.ONOFF,
                ),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,)
            )
            기본운영_ruleset |= 오후운영_ruleset
        
        # 기본 운영 schedule 정리
        기본운영_schedule = dragon.Schedule.from_compact(
            None,
            [("0101","1231", 기본운영_ruleset)]
        )
        
        # 설비 가동스케줄 (개별)
        operation_schedules = []
        for 설비,mode in zip([self.난방설비1, self.난방설비2, self.냉방설비1, self.냉방설비2],["heating","heating","cooling","cooling"]):
            if 설비 is not None:
                operation_schedules.append(설비.get_hvac_availability_schedule(mode))
            else:
                operation_schedules.append(dragon.Schedule.from_compact(
                    None, [("0101","1231", dragon.RuleSet(
                        None,
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                    ))]
                ))
        
        # 설비 가동스케줄 (or조건으로 개별 설비 결합: 모종의 설비가 가동중)
        hvac_availability = operation_schedules[0]
        for schedule in operation_schedules[1:]:
            hvac_availability |= schedule
        
        # 최종 스케줄 = 운영중이면서, 설비 가동 중
        hvac_availability &= 기본운영_schedule
        
        return hvac_availability

    def apply_to(self, zones:list[dragon.Zone]) -> None:
        
        total_area = max(sum(zone.floor_area for zone in zones), 1E-6)
        occupant_schedule          = self.get_occupant_schedule()/total_area 
        hvac_availability_schedule = self.get_hvac_availability_schedule()
        
        for zone in zones:
            
            lighting_schedule  = (occupant_schedule > 0)
            equipment_schedule = dragon.Schedule.from_constant(None, zone.profile.equipment.max) * (occupant_schedule > 0)
        
            zone.profile = dragon.Profile(
                f"{zone.name}_특화존1체크리스트",
                self.get_heating_setpoint_schedule(zone.profile.heating_setpoint), 
                self.get_cooling_setpoint_schedule(zone.profile.cooling_setpoint), 
                hvac_availability_schedule,
                occupant_schedule         ,
                lighting_schedule     ,
                equipment_schedule    ,
            )
            
            self.apply_hvac_availability(zone)
            
        return
    
    
@dataclass
class 보건소특화존2(hvac존):
    #zone
    사용관사수:int
    동거인수:int
    운영요일:str

    @classmethod
    def from_excel(cls, filepath:str):
        
        # components
        재실 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=49, nrows=3, usecols=[3,4], index_col=0)
        운영요일 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=53, nrows=2, usecols=[3,4,5,6,7,8,9,10], index_col=0)
        설비 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=57, nrows=5, usecols=[3,4,5,6,7,8,9,10], index_col=0)
        설비.columns = ["시작시","시작분","종료시","종료분","시작월","종료월","설정온도"]
        
        return cls(
            *[
                row_to_설비운영(row)
                for _, row in 설비.iterrows()
            ],
            int(v) if not pd.isna(v:=재실.at["사용관사수","인원수"]) else 0,
            int(v) if not pd.isna(v:=재실.at["동거인수","인원수"]) else 0,
            row_to_dayofweekstr(운영요일.loc["운영요일"]),   
        )
    
    def get_occupant_schedule(self) -> dragon.Schedule:
        
        dayofweeks = [translate_dayofweek(s.strip()) for s in self.운영요일.split(",") if not s==""]
        occupant_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                **{
                    k: dragon.DaySchedule.from_compact(
                        None,
                        [
                            (24, 0, self.사용관사수+self.동거인수),
                        ],
                        dragon.ScheduleType.REAL,
                    )
                    for k in dayofweeks
                }
            )

        occupant_schedule = dragon.Schedule.from_compact(
            None,
            [("0101","1231", occupant_ruleset)]
        )
        
        return occupant_schedule
    
    def get_hvac_availability_schedule(self) -> dragon.Schedule:
        
        기본운영_schedule = (self.get_occupant_schedule() > 0)
        
        # 설비 가동스케줄 (개별)
        operation_schedules = []
        for 설비,mode in zip([self.난방설비1, self.난방설비2, self.냉방설비1, self.냉방설비2],["heating","heating","cooling","cooling"]):
            if 설비 is not None:
                operation_schedules.append(설비.get_hvac_availability_schedule(mode))
            else:
                operation_schedules.append(dragon.Schedule.from_compact(
                    None, [("0101","1231", dragon.RuleSet(
                        None,
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                    ))]
                ))
        
        # 설비 가동스케줄 (or조건으로 개별 설비 결합: 모종의 설비가 가동중)
        hvac_availability = operation_schedules[0]
        for schedule in operation_schedules[1:]:
            hvac_availability |= schedule
        
        # 최종 스케줄 = 운영중이면서, 설비 가동 중
        hvac_availability &= 기본운영_schedule
        
        return hvac_availability

    def apply_to(self, zones:list[dragon.Zone]) -> None:
        
        total_area = max(sum(zone.floor_area for zone in zones), 1E-6)
        occupant_schedule = self.get_occupant_schedule()/total_area
        hvac_availability_schedule = self.get_hvac_availability_schedule()
        
        for zone in zones:
            
            lighting_schedule  = zone.profile.lighting  * (occupant_schedule > 0)
            equipment_schedule = zone.profile.equipment * (occupant_schedule > 0)
            
            zone.profile = dragon.Profile(
                f"{zone.name}_특화존2체크리스트",
                self.get_heating_setpoint_schedule(zone.profile.heating_setpoint), 
                self.get_cooling_setpoint_schedule(zone.profile.cooling_setpoint), 
                hvac_availability_schedule,
                occupant_schedule         ,
                lighting_schedule     ,
                equipment_schedule    ,
            )
            
            self.apply_hvac_availability(zone)
            
        return
    

@dataclass
class 어린이집일반존(hvac존):
    # zone
    기본보육교사:int
    기본보육원생:int
    연장보육A교사:int
    연장보육A원생:int
    연장보육B교사:int
    연장보육B원생:int
    야간보육교사:int
    야간보육원생:int
    주말보육시간:str
    주말보육교사:int
    주말보육원생:int
            
    @classmethod
    def from_excel(cls, filepath:str):
        
        재실 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=5, nrows=6, usecols=[3,4,5], index_col=0)
        주말보육시간 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=12, nrows=2, usecols=[3,4,5,6,7], index_col=0)
        설비 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=16, nrows=5, usecols=[3,4,5,6,7,8,9,10], index_col=0)
        설비.columns = ["시작시","시작분","종료시","종료분","시작월","종료월","설정온도"]
        
        return cls(
            *[
                row_to_설비운영(row)
                for _, row in 설비.iterrows()
            ],
            int(재실.at["기본보육","교사"]),
            int(재실.at["기본보육","원생"]),
            int(v) if not pd.isna(v:=재실.at["연장보육A","교사"]) else 0,
            int(v) if not pd.isna(v:=재실.at["연장보육A","교사"]) else 0,
            int(v) if not pd.isna(v:=재실.at["연장보육B","교사"]) else 0,
            int(v) if not pd.isna(v:=재실.at["연장보육B","교사"]) else 0,
            int(v) if not pd.isna(v:= 재실.at["야간보육","교사"]) else v,
            int(v) if not pd.isna(v:= 재실.at["야간보육","원생"]) else v,
            row_to_timestring(주말보육시간.loc["주말보육"]),
            int(v) if not pd.isna(v:=재실.at["주말보육","교사"]) else 0,
            int(v) if not pd.isna(v:=재실.at["주말보육","원생"]) else 0,
        )
    
    def get_occupant_schedule(self) -> dragon.Schedule:
        
        # 평일
        기본보육인원 = self.기본보육교사 + self.기본보육원생
        연장보육A인원 = ensure_integer_with_nan(self.연장보육A교사) + ensure_integer_with_nan(self.연장보육A원생)
        연장보육B인원 = ensure_integer_with_nan(self.연장보육B교사) + ensure_integer_with_nan(self.연장보육B원생)
        야간보육인원 = ensure_integer_with_nan(self.야간보육교사) + ensure_integer_with_nan(self.야간보육원생)
        평일_dayschedule = dragon.DaySchedule.from_compact(
                None, [
                    (7, 30, 0),
                    (16,  0, 기본보육인원),
                    (18,  0, 연장보육A인원),
                    (19, 30, 연장보육B인원),
                    (21,  0, 야간보육인원),
                    (24,  0,  0),
                ],
                dragon.ScheduleType.REAL
            )
        
        # 주말
        if not pd.isna(self.주말보육시간):
            starth, startm, endh, endm = parse_duration_hours(self.주말보육시간)
            주말보육인원 = ensure_integer_with_nan(self.주말보육교사) + ensure_integer_with_nan(self.주말보육원생)
            주말_dayschedule = dragon.DaySchedule.from_compact(
                    None, [
                        (starth, startm, 0),
                        (endh, endm, 주말보육인원),
                        (24, 0, 0)
                    ],
                    dragon.ScheduleType.REAL
                )
        else:
            주말_dayschedule = dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.REAL)
        
        # 스케줄
        occupant_ruleset = dragon.RuleSet(
            None,
            평일_dayschedule,
            주말_dayschedule,            
        )
        
        occupant_schedule = dragon.Schedule.from_compact(
            None,
            [("0101","1231", occupant_ruleset)]
        )
        
        return occupant_schedule
    
    def get_hvac_availability_schedule(self) -> dragon.Schedule:
        
        # 평일
        연장보육A인원 = ensure_integer_with_nan(self.연장보육A교사) + ensure_integer_with_nan(self.연장보육A원생)
        연장보육B인원 = ensure_integer_with_nan(self.연장보육B교사) + ensure_integer_with_nan(self.연장보육B원생)
        야간보육인원 = ensure_integer_with_nan(self.야간보육교사) + ensure_integer_with_nan(self.야간보육원생)
        평일_dayschedule = dragon.DaySchedule.from_compact(
                None, [
                    (7, 30, 0),
                    (16,  0, 1),
                    (18,  0, int(연장보육A인원 > 0)),
                    (19, 30, int(연장보육B인원 > 0)),
                    (21,  0, int(야간보육인원 > 0)),
                    (24,  0,  0),
                ],
                dragon.ScheduleType.ONOFF
            )
        
        # 주말
        if not pd.isna(self.주말보육시간):
            starth, startm, endh, endm = parse_duration_hours(self.주말보육시간)
            주말_dayschedule = dragon.DaySchedule.from_compact(
                    None, [
                        (starth, startm, 0),
                        (endh   , endm, 1),
                        (24, 0, 0)
                    ],
                    dragon.ScheduleType.ONOFF
                )
        else:
            주말_dayschedule = dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF)
        
        # 스케줄
        기본운영_ruleset = dragon.RuleSet(
            None,
            평일_dayschedule,
            주말_dayschedule,            
        )
        
        기본운영_schedule = dragon.Schedule.from_compact(
            None,
            [("0101","1231", 기본운영_ruleset)]
        )
        
        # 설비 가동스케줄 (개별)
        operation_schedules = []
        for 설비,mode in zip([self.난방설비1, self.난방설비2, self.냉방설비1, self.냉방설비2],["heating","heating","cooling","cooling"]):
            if 설비 is not None:
                operation_schedules.append(설비.get_hvac_availability_schedule(mode))
            else:
                operation_schedules.append(dragon.Schedule.from_compact(
                    None, [("0101","1231", dragon.RuleSet(
                        None,
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                    ))]
                ))
                
        # 설비 가동스케줄 (or조건으로 개별 설비 결합: 모종의 설비가 가동중)
        hvac_availability = operation_schedules[0]
        for schedule in operation_schedules[1:]:
            hvac_availability |= schedule
        
        # 최종 스케줄 = 운영중이면서, 설비 가동 중
        hvac_availability &= 기본운영_schedule
        
        return hvac_availability

    def apply_to(self, zones:list[dragon.Zone]) -> None:
        
        total_area = max(sum(zone.floor_area for zone in zones), 1E-6)
        occupant_schedule          = self.get_occupant_schedule()/total_area 
        hvac_availability_schedule = self.get_hvac_availability_schedule()
        
        for zone in zones:
            
            lighting_schedule  = zone.profile.lighting  * (occupant_schedule > 0)
            equipment_schedule = zone.profile.equipment * (occupant_schedule > 0)
            
            zone.profile = dragon.Profile(
                f"{zone.name}_일반존체크리스트",
                self.get_heating_setpoint_schedule(zone.profile.heating_setpoint), 
                self.get_cooling_setpoint_schedule(zone.profile.cooling_setpoint), 
                hvac_availability_schedule,
                occupant_schedule         ,
                lighting_schedule    ,
                equipment_schedule    ,
            )
            
            self.apply_hvac_availability(zone)
            
        return

@dataclass
class 어린이집특화존1(hvac존):
    # zone
    오전운영시간:str
    오후운영시간:str
    오전인원:int
    오후인원:int
        
    @classmethod
    def from_excel(cls, filepath:str):
        
        재실 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=24, nrows=3, usecols=[3,4], index_col=0)
        운영시간 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=28, nrows=3, usecols=[3,4,5,6,7], index_col=0)
        설비 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=33, nrows=5, usecols=[3,4,5,6,7,8,9,10], index_col=0)
        설비.columns = ["시작시","시작분","종료시","종료분","시작월","종료월","설정온도"]
        
        return cls(
            *[
                row_to_설비운영(row)
                for _, row in 설비.iterrows()
            ],
            row_to_timestring(운영시간.loc["오전"]),
            row_to_timestring(운영시간.loc["오후"]),
            int(v) if not pd.isna(v:=재실.at["오전","인원"]) else pd.NA,
            int(v) if not pd.isna(v:=재실.at["오후","인원"]) else pd.NA,
        )
    
    def get_occupant_schedule(self) -> dragon.Schedule:
        
        # 기본 스케줄 (0명)
        occupant_ruleset = dragon.RuleSet(
            None,
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
        )
        
        
        # 오전 재실
        if not pd.isna(self.오전운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오전운영시간)
            오전_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(None, [
                    (starth, startm,              0),
                    (endh  , endm  , self.오전인원),
                    (24    , 0     ,              0),
                ],dragon.ScheduleType.REAL,),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
            )
            occupant_ruleset += 오전_ruleset
        
        # 오후 재실
        if not pd.isna(self.오후운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오후운영시간)
            오후_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(None, [
                    (starth, startm,              0),
                    (endh  , endm  , self.오후인원),
                    (24    , 0     ,              0),
                ],dragon.ScheduleType.REAL,),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
            )
            occupant_ruleset += 오후_ruleset
        
        # 둘이 합치기
        occupant_schedule = dragon.Schedule.from_compact(
            None,
            [("0101","1231", occupant_ruleset)]
        )

        return occupant_schedule
    
    def get_hvac_availability_schedule(self) -> dragon.Schedule:
        
        # 기본 운영시간
        기본운영_ruleset = dragon.RuleSet(
            None,
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,),
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,),
        )
        
        # 오전 운영시간
        if not pd.isna(self.오전운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오전운영시간)
            오전운영_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(
                    None,
                    [
                        (starth, startm, 0),
                        (endh  , endm  , 1),
                        (24    , 0     , 0),
                    ],
                    dragon.ScheduleType.ONOFF,
                ),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,)
            )
            기본운영_ruleset |= 오전운영_ruleset
        
        # 오후 운영시간
        if not pd.isna(self.오후운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오후운영시간)
            오후운영_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(
                    None,
                    [
                        (starth, startm, 0),
                        (endh  , endm  , 1),
                        (24    , 0     , 0),
                    ],
                    dragon.ScheduleType.ONOFF,
                ),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,)
            )
            기본운영_ruleset |= 오후운영_ruleset
        
        # 기본 운영 schedule 정리
        기본운영_schedule = dragon.Schedule.from_compact(
            None,
            [("0101","1231", 기본운영_ruleset)]
        )
        
        # 설비 가동스케줄 (개별)
        operation_schedules = []
        for 설비,mode in zip([self.난방설비1, self.난방설비2, self.냉방설비1, self.냉방설비2],["heating","heating","cooling","cooling"]):
            if 설비 is not None:
                operation_schedules.append(설비.get_hvac_availability_schedule(mode))
            else:
                operation_schedules.append(dragon.Schedule.from_compact(
                    None, [("0101","1231", dragon.RuleSet(
                        None,
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                    ))]
                ))
                
        # 설비 가동스케줄 (or조건으로 개별 설비 결합: 모종의 설비가 가동중)
        hvac_availability = operation_schedules[0]
        for schedule in operation_schedules[1:]:
            hvac_availability |= schedule
        
        # 최종 스케줄 = 운영중이면서, 설비 가동 중
        hvac_availability &= 기본운영_schedule
        
        return hvac_availability

    def apply_to(self, zones:list[dragon.Zone]) -> None:
        
        total_area = max(sum(zone.floor_area for zone in zones), 1E-6)
        occupant_schedule          = self.get_occupant_schedule()/total_area 
        hvac_availability_schedule = self.get_hvac_availability_schedule()
        
        for zone in zones:
            
            lighting_schedule  = zone.profile.lighting  * (occupant_schedule > 0)
            equipment_schedule = zone.profile.equipment * (occupant_schedule > 0)
            
            zone.profile = dragon.Profile(
                f"{zone.name}_특화존1체크리스트",
                self.get_heating_setpoint_schedule(zone.profile.heating_setpoint), 
                self.get_cooling_setpoint_schedule(zone.profile.cooling_setpoint), 
                hvac_availability_schedule,
                occupant_schedule         ,
                lighting_schedule,
                equipment_schedule    ,
            )
            
            self.apply_hvac_availability(zone)
            
        return
    

@dataclass
class 어린이집특화존2(hvac존):
    # zone
    오전운영시간:str
    오후운영시간:str
    운영요일:str
    오전인원:int
    오후인원:int
        
    @classmethod
    def from_excel(cls, filepath:str):
        
        재실 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=41, nrows=3, usecols=[3,4], index_col=0)
        운영시간 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=45, nrows=3, usecols=[3,4,5,6,7], index_col=0)
        운영요일 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=49, nrows=2, usecols=[3,4,5,6,7,8], index_col=0)
        설비 = pd.read_excel(filepath, sheet_name="현장조사", skiprows=53, nrows=5, usecols=[3,4,5,6,7,8,9,10], index_col=0)
        설비.columns = ["시작시","시작분","종료시","종료분","시작월","종료월","설정온도"]
        
        return cls(
            *[
                row_to_설비운영(row)
                for _, row in 설비.iterrows()
            ],
            row_to_timestring(운영시간.loc["오전"]),
            row_to_timestring(운영시간.loc["오후"]),
            row_to_dayofweekstr(운영요일.loc["운영요일"]),
            int(v) if not pd.isna(v:=재실.at["오전","인원"]) else pd.NA,
            int(v) if not pd.isna(v:=재실.at["오후","인원"]) else pd.NA,
        )
    
    def get_occupant_schedule(self) -> dragon.Schedule:
        
        # 기본 스케줄 (0명)
        occupant_ruleset = dragon.RuleSet(
            None,
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
        )
        
        # 오전 재실
        if not pd.isna(self.오전운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오전운영시간)
            dayofweeks = [translate_dayofweek(s.strip()) for s in self.운영요일.split(",") if not s==""]
            오전_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                **{
                    k: dragon.DaySchedule.from_compact(
                        None,
                        [
                            (starth, startm,              0),
                            (endh  , endm  , self.오전인원),
                            (24    , 0     ,              0),
                        ],
                        dragon.ScheduleType.REAL,
                    )
                    for k in dayofweeks
                }
            )
            occupant_ruleset += 오전_ruleset
        
        # 오후 재실
        if not pd.isna(self.오후운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오후운영시간)
            dayofweeks = [translate_dayofweek(s.strip()) for s in self.운영요일.split(",") if not s==""]
            오후_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.REAL,),
                **{
                    k: dragon.DaySchedule.from_compact(
                        None,
                        [
                            (starth, startm,              0),
                            (endh  , endm  , self.오후인원),
                            (24    , 0     ,              0),
                        ],
                        dragon.ScheduleType.REAL,
                    )
                    for k in dayofweeks
                }
            )
            occupant_ruleset += 오후_ruleset

        # 둘이 합치기
        occupant_schedule = dragon.Schedule.from_compact(
            None,
            [("0101","1231", occupant_ruleset)]
        )
        
        return occupant_schedule
    
    def get_hvac_availability_schedule(self) -> dragon.Schedule:
        
        # 기본 운영시간
        기본운영_ruleset = dragon.RuleSet(
            None,
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,),
            dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,),
        )
        
        # 오전 운영시간
        if not pd.isna(self.오전운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오전운영시간)
            오전운영_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(
                    None,
                    [
                        (starth, startm, 0),
                        (endh  , endm  , 1),
                        (24    , 0     , 0),
                    ],
                    dragon.ScheduleType.ONOFF,
                ),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,)
            )
            기본운영_ruleset |= 오전운영_ruleset
        
        # 오후 운영시간
        if not pd.isna(self.오후운영시간):
            starth, startm, endh, endm = parse_duration_hours(self.오후운영시간)
            오후운영_ruleset = dragon.RuleSet(
                None,
                dragon.DaySchedule.from_compact(
                    None,
                    [
                        (starth, startm, 0),
                        (endh  , endm  , 1),
                        (24    , 0     , 0),
                    ],
                    dragon.ScheduleType.ONOFF,
                ),
                dragon.DaySchedule.from_compact(None, [(24,0,0)],dragon.ScheduleType.ONOFF,)
            )
            기본운영_ruleset |= 오후운영_ruleset
        
        # 기본 운영 schedule 정리
        기본운영_schedule = dragon.Schedule.from_compact(
            None,
            [("0101","1231", 기본운영_ruleset)]
        )
        
        # 설비 가동스케줄 (개별)
        operation_schedules = []
        for 설비,mode in zip([self.난방설비1, self.난방설비2, self.냉방설비1, self.냉방설비2],["heating","heating","cooling","cooling"]):
            if 설비 is not None:
                operation_schedules.append(설비.get_hvac_availability_schedule(mode))
            else:
                operation_schedules.append(dragon.Schedule.from_compact(
                    None, [("0101","1231", dragon.RuleSet(
                        None,
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                        dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.ONOFF),
                    ))]
                ))
        
        # 설비 가동스케줄 (or조건으로 개별 설비 결합: 모종의 설비가 가동중)
        hvac_availability = operation_schedules[0]
        for schedule in operation_schedules[1:]:
            hvac_availability |= schedule
        
        # 최종 스케줄 = 운영중이면서, 설비 가동 중
        hvac_availability &= 기본운영_schedule
        
        return hvac_availability


    def apply_to(self, zones:list[dragon.Zone]) -> None:
        
        total_area = max(sum(zone.floor_area for zone in zones), 1E-6)
        occupant_schedule          = self.get_occupant_schedule()/total_area 
        hvac_availability_schedule = self.get_hvac_availability_schedule()
        
        for zone in zones:
            
            lighting_schedule  = zone.profile.lighting  * (occupant_schedule > 0)
            equipment_schedule = zone.profile.equipment * (occupant_schedule > 0)
            
            zone.profile = dragon.Profile(
                f"{zone.name}_특화존2체크리스트",
                self.get_heating_setpoint_schedule(zone.profile.heating_setpoint), 
                self.get_cooling_setpoint_schedule(zone.profile.cooling_setpoint), 
                hvac_availability_schedule,
                occupant_schedule         ,
                lighting_schedule  ,
                equipment_schedule    ,
            )
            
            self.apply_hvac_availability(zone)
            
        return

# ---------------------------------------------------------------------------- #
#                                     MAIN                                     #
# ---------------------------------------------------------------------------- #

class 현장조사체크리스트(ABC):
    
    """ input
    """
    
    @classmethod
    def from_row(cls, row:pd.Series) -> 현장조사체크리스트: ...
    
    @classmethod
    def from_dataframe(cls, df:pd.DataFrame) -> list[현장조사체크리스트]:
        return [cls.from_row(row) for _, row in df.iterrows()]
    
    @staticmethod
    def from_excel(
        filepath:str,
        ) -> None:
        
        building_type = pd.read_excel(filepath, sheet_name="현장조사", nrows=1, usecols=[0]).at[0,"현장조사유형"]
        
        match building_type:
            case "보건소":
                return 보건소체크리스트.from_excel(filepath)
            case "어린이집":
                return 어린이집체크리스트.from_excel(filepath)
    
    """ output
    """
    
    @abstractmethod
    def apply_to(self, grm:GreenRetrofitModel) -> IDF: ...
    
    @staticmethod
    def apply_dualhvac(
        em       :EnergyModel            ,
        grm      :GreenRetrofitModel     ,
        exceldata:dict[str, pd.DataFrame],
        ) -> None:
        
        zonedata = exceldata["실"].loc[~pd.isna(exceldata["실"].iloc[:,0])].iloc[:,:11].sort_values(by="층", ascending=True).reset_index(drop=True)
        processed_excel = _preprocess_excel_dict(exceldata)
        source_json = _replace_nan_to_none(_convert_source_systems(processed_excel["생산설비"]))
        supply_json = _replace_nan_to_none(_convert_supply_systems(processed_excel["공급설비"], processed_excel["생산설비"]))
        
        source_dict = {sys.ID: sys for sys in [SourceSystem.from_json(SimpleNamespace(**d)) for d in source_json]}
        supply_dict = {sys.ID: sys for sys in [SupplySystem.from_json(SimpleNamespace(**d), source_dict) for d in supply_json]}
        
        dragonsource_dict = {k: v.to_dragon() for k, v in source_dict.items()}
        for v in dragonsource_dict.values():
            v.name = f"$FOR_SECOND${v.name}"
        dragonsupply_dict = {k: v.to_dragon(dragonsource_dict) for k, v in supply_dict.items()}
        for v in dragonsupply_dict.values():
            v.name = f"$FOR_SECOND${v.name}"
            
        # 난방 공급 설비2
        for  zone, grmzone in zip( em.zone, grm.zone):
            
            row = zonedata.query("이름==@grmzone.name").iloc[0]
            if pd.isna(row["난방 공급 설비2"]):
                continue
            
            공급설비 = exceldata["공급설비"].query("이름 == @row['난방 공급 설비2']")
            if isinstance(zone.heating_supply, dragon.hvac.AirHandlingUnit):
                first_heating = deepcopy(zone.heating_supply)
            else:
                first_heating = zone.heating_supply
            first_heating.name = f"{first_heating.name}forHeating"
            second_heating = dragonsupply_dict[[k for  k, v in supply_dict.items() if v.name == 공급설비["이름"].values[0]][0]]
            if isinstance(second_heating, dragon.hvac.AirHandlingUnit):
                second_heating = deepcopy(second_heating)
            second_heating.name = f"{second_heating.name}forHeating"
            
            zone.heating_supply = dragon.hvac.SupplyGroup(
                [first_heating, second_heating]
            )                
            
        # 냉방 공급 설비2
        for (_, row), zone in zip(zonedata.iterrows(), em.zone):
            
            if pd.isna(row["냉방 공급 설비2"]):
                continue  
            
            공급설비 = exceldata["공급설비"].query("이름 == @row['냉방 공급 설비2']")
            if isinstance(zone.cooling_supply, dragon.hvac.AirHandlingUnit):
                first_cooling = deepcopy(zone.cooling_supply)
            else:
                first_cooling = zone.cooling_supply
            first_cooling.name = f"{first_cooling.name}forCooling"
            second_cooling = dragonsupply_dict[[k for  k, v in supply_dict.items() if v.name == 공급설비["이름"].values[0]][0]]
            if isinstance(second_cooling, dragon.hvac.AirHandlingUnit):
                second_cooling = deepcopy(second_cooling)
            second_cooling.name = f"{second_cooling.name}forCooling"
            
            zone.cooling_supply = dragon.hvac.SupplyGroup(
                [first_cooling, second_cooling]
            )
        


class 어린이집체크리스트:
    
    def __init__(self,
        일반존 : 어린이집일반존 ,
        특화존1: 어린이집특화존1,
        특화존2: 어린이집특화존2,
        ) -> None:
        
        # zone survey
        self.일반존  = 일반존
        self.특화존1 = 특화존1
        self.특화존2 = 특화존2
    
    @classmethod
    def from_excel(cls, filepath:str) -> 어린이집체크리스트:
        
        return cls(
            어린이집일반존.from_excel(filepath),
            어린이집특화존1.from_excel(filepath),
            어린이집특화존2.from_excel(filepath),
        )
        
    def apply_to(self,
        grm      :GreenRetrofitModel,
        exceldata:dict[str,pd.DataFrame],
        *,
        output:Literal["idf","em"] = "idf"
        ) -> IDF|EnergyModel:
        
        zoneID_category = {
            category: [
                zone.ID for zone in grm.zone
                if zone.name in list(exceldata["실"].query("현장조사프로필 == @category" )["이름"].values)
            ]
            for category in ["일반존","특화존1","특화존2"]
        }
        
        em = grm.to_dragon()
        현장조사체크리스트.apply_dualhvac(em, grm, exceldata)
        
        self.일반존.apply_to([
                zone for zone in em.zone
                if zone.name in zoneID_category["일반존"]
        ])
        self.특화존1.apply_to([
                zone for zone in em.zone
                if zone.name in zoneID_category["특화존1"]
        ])
        self.특화존2.apply_to([
                zone for zone in em.zone
                if zone.name in zoneID_category["특화존2"]
        ])
        
        match output:
            case "idf":
                return em.to_idf()
            case "em":
                return em
            case _:
                raise ValueError(
                    f"{output}은 지원되지 않는 변환 결과물입니다.. idf나 em으로 하세요..."
                )
    
class 보건소체크리스트:
    
    def __init__(self,
        일반존 : 보건소일반존 ,
        특화존1: 보건소특화존1,
        특화존2: 보건소특화존2,
        ) -> None:
        
        # zone survey
        self.일반존  = 일반존
        self.특화존1 = 특화존1
        self.특화존2 = 특화존2
    
    @classmethod
    def from_excel(cls, filepath:str) -> 보건소체크리스트:
        
        return cls(
            보건소일반존.from_excel(filepath),
            보건소특화존1.from_excel(filepath),
            보건소특화존2.from_excel(filepath),
        )
        
    def apply_to(self,
        grm      :GreenRetrofitModel,
        exceldata:dict[str,pd.DataFrame],
        *,
        output:Literal["idf","em"] = "idf"
        ) -> IDF|EnergyModel:
        
        zoneID_category = {
            category: [
                zone.ID for zone in grm.zone
                if zone.name in list(exceldata["실"].query("현장조사프로필 == @category" )["이름"].values)
            ]
            for category in ["일반존","특화존1","특화존2"]
        }
        
        em = grm.to_dragon()
        현장조사체크리스트.apply_dualhvac(em, grm, exceldata)
        
        self.일반존.apply_to([
                zone for zone in em.zone
                if zone.name in zoneID_category["일반존"]
        ])
        self.특화존1.apply_to([
                zone for zone in em.zone
                if zone.name in zoneID_category["특화존1"]
        ])
        self.특화존2.apply_to([
                zone for zone in em.zone
                if zone.name in zoneID_category["특화존2"]
        ])
        
        match output:
            case "idf":
                return em.to_idf()
            case "em":
                return em
            case _:
                raise ValueError(
                    f"{output}은 지원되지 않는 변환 결과물입니다.. idf나 em으로 하세요..."
                )


# v0-7-0 버전 수정 및 추가

# 설비가 꺼져 있을 때 설정온도
UNCONTROLLED_HEATING_SETPOINT = -30
UNCONTROLLED_COOLING_SETPOINT =  50


def to_hour_minute(value:datetime.time|str) -> tuple[int,int]:
    """엑셀 시간 셀(datetime.time) 또는 'HH:MM' 문자열 -> (시, 분)"""
    if isinstance(value, datetime.time):
        return value.hour, value.minute
    hour, minute = str(value).split(":")
    return int(hour), int(minute)

def to_dayofweeks(value:str) -> list[str]:
    """'월,화,수' -> ['monday', 'tuesday', 'wednesday'], 빈칸 -> []"""
    if pd.isna(value) or str(value).strip() == "":
        return []
    return [translate_dayofweek(s.strip()) for s in str(value).split(",") if s.strip()]

def month_periods(start_month:int, end_month:int) -> list[tuple[str,str]]:
    """운영 월 -> (시작일, 종료일) 문자열 목록. 11~3월처럼 해를 넘기면 두 구간"""
    end_day = f"{end_month:02d}{get_end_of_the_month(end_month):02d}"
    if start_month <= end_month:
        return [(f"{start_month:02d}01", end_day)]
    return [(f"{start_month:02d}01", "1231"), ("0101", end_day)]

def window_dayschedule(
    start:tuple[int,int],
    end  :tuple[int,int],
    value:int|float,
    type :dragon.ScheduleType,
    ) -> dragon.DaySchedule:
    """시작-종료 사이만 value, 나머지는 0. 종료가 시작보다 이르면 +1일"""
    if start < end:
        values = [(*start, 0), (*end, value), (24, 0, 0)]
    else:
        values = [(*end, value), (*start, 0), (24, 0, value)]
    return dragon.DaySchedule.from_compact(None, values, type)

def alloff_schedule() -> dragon.Schedule:
    return dragon.Schedule.from_constant(None, 0, dragon.ScheduleType.ONOFF)


@dataclass
class 프로필설비:
    
    시작  :tuple[int,int]   # (시, 분)
    종료  :tuple[int,int]
    시작월:int
    종료월:int
    설정온도:float
    사용여부:bool=True      # False = 00:00~00:00 (미설치/미사용)
    
    @classmethod
    def from_column(cls, column:pd.Series, prefix:str) -> "프로필설비|None":
        """비어 있으면 None(주용도 값 사용), 00:00~00:00이면 미사용, 그 외에는 나머지 항목 사용"""
        if pd.isna(column[f"{prefix} 시작시간"]):
            return None
        
        start = to_hour_minute(column[f"{prefix} 시작시간"])
        end   = to_hour_minute(column[f"{prefix} 종료시간"])
        if (start == (0, 0)) and (end == (0, 0)):
            return cls(start, end, 1, 12, 0.0, 사용여부=False)
        
        return cls(
            start, end,
            int  (column[f"{prefix} 운영시작월"]),
            int  (column[f"{prefix} 운영종료월"]),
            float(column[f"{prefix} 설정온도"]),
        )
    
    def get_availability_schedule(self) -> dragon.Schedule:
        """운영 월 안에서 매일 시작~종료 시간에만 1. 미사용이면 항상 0"""
        if not self.사용여부:
            return alloff_schedule()
        dayschedule = window_dayschedule(self.시작, self.종료, 1, dragon.ScheduleType.ONOFF)
        ruleset     = dragon.RuleSet(None, dayschedule, dayschedule)
        schedule    = alloff_schedule()
        for start, end in month_periods(self.시작월, self.종료월):
            schedule.apply(ruleset, start=start, end=end)
        return schedule
    
    def get_setpoint_schedule(self, mode:Literal["heating","cooling"]) -> dragon.Schedule:
        """가동 중에는 설정온도, 아니면 냉난방이 걸리지 않는 온도. 미사용이면 항상 후자"""
        uncontrolled = UNCONTROLLED_HEATING_SETPOINT if mode == "heating" else UNCONTROLLED_COOLING_SETPOINT
        if not self.사용여부:
            return dragon.Schedule.from_constant(None, uncontrolled, dragon.ScheduleType.TEMPERATURE)
        availability = self.get_availability_schedule()
        setpoint_on  = dragon.Schedule.from_constant(None, self.설정온도, dragon.ScheduleType.TEMPERATURE)
        setpoint_off = dragon.Schedule.from_constant(None, uncontrolled, dragon.ScheduleType.TEMPERATURE)
        return setpoint_on * availability + setpoint_off * (~availability)


@dataclass
class 용도프로필:
    
    이름  :str
    주용도:str                        # 내장 프로필 이름. 조명, 기기, 급탕은 항상 여기서, 나머지는 비어 있을 때 여기서
    상주인원:int|None
    상주시작:tuple[int,int]|None
    상주종료:tuple[int,int]|None
    상주요일:list[str]
    방문인원:int
    방문체류분:int
    방문요일:list[str]
    운영시작월:int
    운영종료월:int
    난방설비1:"프로필설비|None"
    난방설비2:"프로필설비|None"
    냉방설비1:"프로필설비|None"
    냉방설비2:"프로필설비|None"
    
    @classmethod
    def from_column(cls, column:pd.Series) -> "용도프로필":
        """용도프로필 탭의 한 열(프로필 하나)을 ㅇ릭음"""
        return cls(
            str(column["프로필 이름"]),
            str(column["실 주용도"]),
            None if pd.isna(column["상주인원 수 [명]"])      else int(column["상주인원 수 [명]"]),
            None if pd.isna(column["상주인원 재실시작시간"]) else to_hour_minute(column["상주인원 재실시작시간"]),
            None if pd.isna(column["상주인원 재실종료시간"]) else to_hour_minute(column["상주인원 재실종료시간"]),
            to_dayofweeks(column["상주인원 요일"]),
            0 if pd.isna(column["방문인원 수 [명]"])      else int(column["방문인원 수 [명]"]),
            0 if pd.isna(column["방문인원 체류시간 [분]"]) else int(column["방문인원 체류시간 [분]"]),
            to_dayofweeks(column["방문인원 요일"]),
            1  if pd.isna(column["재실운영 시작월"]) else int(column["재실운영 시작월"]),
            12 if pd.isna(column["재실운영 종료월"]) else int(column["재실운영 종료월"]),
            프로필설비.from_column(column, "난방설비" ),
            프로필설비.from_column(column, "난방설비2"),
            프로필설비.from_column(column, "냉방설비" ),
            프로필설비.from_column(column, "냉방설비2"),
        )
    
    @property
    def has_occupancy(self) -> bool:
        """상주인원 항목 입력 여부(없으면 주용도의 재실 사용)"""
        return (self.상주인원 is not None) and (self.상주시작 is not None) and (self.상주종료 is not None)
    
    @property
    def has_heating(self) -> bool:
        return (self.난방설비1 is not None) or (self.난방설비2 is not None)
    
    @property
    def has_cooling(self) -> bool:
        return (self.냉방설비1 is not None) or (self.냉방설비2 is not None)
    
    @property
    def 상주시간(self) -> float:
        """하루 재실 시간 [h]"""
        hours = (self.상주종료[0] + self.상주종료[1]/60) - (self.상주시작[0] + self.상주시작[1]/60)
        return hours if hours > 0 else hours + 24
    
    def get_occupant_schedule(self) -> dragon.Schedule:
        """존 안의 사람 수 [명]. 운영 월 밖은 0"""
        
        nobody = dragon.DaySchedule.from_compact(None, [(24,0,0)], dragon.ScheduleType.REAL)
        
        # 상주인원: 상주 요일의 재실 시간 동안
        상주    = window_dayschedule(self.상주시작, self.상주종료, self.상주인원, dragon.ScheduleType.REAL)
        ruleset = dragon.RuleSet(None, nobody, nobody, **{day: 상주 for day in self.상주요일})
        
        # 방문인원: 하루 방문 인원 x 체류시간을 재실 시간에 고르게 펼친 평균 동시 체류 인원
        if (self.방문인원 > 0) and self.방문요일:
            동시체류 = self.방문인원 * (self.방문체류분/60) / self.상주시간
            방문     = window_dayschedule(self.상주시작, self.상주종료, 동시체류, dragon.ScheduleType.REAL)
            ruleset  = ruleset + dragon.RuleSet(None, nobody, nobody, **{day: 방문 for day in self.방문요일})
        
        schedule = dragon.Schedule.from_constant(None, 0, dragon.ScheduleType.REAL)
        for start, end in month_periods(self.운영시작월, self.운영종료월):
            schedule.apply(ruleset, start=start, end=end)
        return schedule
    
    def get_hvac_availability_schedule(self) -> dragon.Schedule:
        """설비 중 하나라도 가동 중이면 1"""
        schedule = alloff_schedule()
        for 설비 in [self.난방설비1, self.난방설비2, self.냉방설비1, self.냉방설비2]:
            if 설비 is not None:
                schedule = schedule | 설비.get_availability_schedule()
        return schedule
    
    def get_setpoint_schedule(self, mode:Literal["heating","cooling"]) -> dragon.Schedule:
        """설치된 설비의 설정온도. 둘 다 있으면 난방은 높은 쪽, 냉방은 낮은 쪽"""
        if mode == "heating":
            설비들, uncontrolled = [self.난방설비1, self.난방설비2], UNCONTROLLED_HEATING_SETPOINT
        else:
            설비들, uncontrolled = [self.냉방설비1, self.냉방설비2], UNCONTROLLED_COOLING_SETPOINT
        
        schedules = [설비.get_setpoint_schedule(mode) for 설비 in 설비들 if 설비 is not None]
        if not schedules:
            return dragon.Schedule.from_constant(None, uncontrolled, dragon.ScheduleType.TEMPERATURE)
        
        schedule = schedules[0]
        for other in schedules[1:]:
            schedule = schedule.element_max(other) if mode == "heating" else schedule.element_min(other)
        return schedule
    
    def get_equipment_availability_schedules(self, count:int) -> list["dragon.Schedule|None"]:
        """실에 연결된 설비 순서대로 가동 스케줄. 1번째 = 설비1, 2번째 = 설비2.
        입력이 없는 설비는 None (제한 없음)"""
        pairs = [(self.난방설비1, self.냉방설비1), (self.난방설비2, self.냉방설비2)]
        
        schedules = []
        for i in range(count):
            if (i >= len(pairs)) or all(설비 is None for 설비 in pairs[i]):
                schedules.append(None)
                continue
            schedule = alloff_schedule()
            for 설비 in pairs[i]:
                if 설비 is not None:
                    schedule = schedule | 설비.get_availability_schedule()
            schedules.append(schedule)
        return schedules


def apply_profile(zone:dragon.Zone, profile:용도프로필) -> None:
    # 존의 프로필을 사용자 프로필로 변경, 탭에 입력된 항목만 덮어쓰고 나머지는 주용도 값 유지
    
    base = zone.profile
    
    # 재실: 탭 값이 있으면 사람 수를 바닥면적으로 나눔, 없으면 주용도 그대로
    if profile.has_occupancy:
        occupant  = profile.get_occupant_schedule() / max(zone.floor_area, 1E-6)
        occupied  = occupant > 0
        lighting  = base.lighting  * occupied
        equipment = base.equipment * occupied
    else:
        occupant, lighting, equipment = base.occupant, base.lighting, base.equipment
    
    # 설비: 존에 공급설비가 있고, 탭에 설비 항목이 있을 때만 덮어씀
    use_tab_hvac = (zone.supply is not None) and (profile.has_heating or profile.has_cooling)
    
    zone.profile = dragon.Profile(
        f"{zone.name}_{profile.이름}",
        heating_setpoint =profile.get_setpoint_schedule("heating")  if use_tab_hvac and profile.has_heating else base.heating_setpoint,
        cooling_setpoint =profile.get_setpoint_schedule("cooling")  if use_tab_hvac and profile.has_cooling else base.cooling_setpoint,
        hvac_availability=profile.get_hvac_availability_schedule()  if use_tab_hvac                         else base.hvac_availability,
        occupant =occupant ,
        lighting =lighting ,
        equipment=equipment,
        hotwater =base.hotwater,
    )
    
    if use_tab_hvac:
        zone.supply.availabilities = tuple(
            profile.get_equipment_availability_schedules(len(zone.supply.systems))
        )


class 용도프로필적용:
    
    def __init__(self,
        profiles    :dict[str, 용도프로필],   # 프로필 이름 -> 프로필
        zone_profile:dict[str, str]      ,   # 실 이름 -> 실 탭의 용도프로필 값
        ) -> None:
        
        self.profiles     = profiles
        self.zone_profile = zone_profile
    
    @classmethod
    def from_excel(cls, filepath:str) -> "용도프로필적용":
        
        # 용도프로필 탭: B열이 항목 이름, C열부터 프로필 하나씩 (세로 배치)
        sheet = pd.read_excel(filepath, sheet_name="용도프로필", header=None)
        table = sheet.set_index(1).iloc[:, 1:]
        
        profiles = {}
        for _, column in table.items():
            if pd.isna(column["프로필 이름"]):
                continue
            profile = 용도프로필.from_column(column)
            profiles[profile.이름] = profile
        
        # 실 탭: 실 이름 -> 용도프로필
        zones = pd.read_excel(filepath, sheet_name="실", header=1)
        zones = zones.loc[~pd.isna(zones["이름"])]
        zone_profile = dict(zip(zones["이름"], zones["용도프로필"]))
        
        return cls(profiles, zone_profile)
    
    def apply_to(self,
        grm      :GreenRetrofitModel,
        exceldata:dict[str, pd.DataFrame]|None=None,   # core.py 호출부를 바꾸지 않기 위해 유지
        ) -> IDF:
        
        em = grm.to_dragon()
        
        # grm.zone과 em.zone은 같은 순서
        for grmzone, zone in zip(grm.zone, em.zone):
            name = self.zone_profile.get(grmzone.name)
            if name in self.profiles:
                apply_profile(zone, self.profiles[name])
        
        return em.to_idf()