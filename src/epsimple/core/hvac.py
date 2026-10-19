
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import math
from enum   import Enum
from types  import SimpleNamespace

# third-party modules

# local modules
from idragon import dragon
from idragon.utils import (
    validate_type ,
    validate_enum ,
    validate_range,
)
from ..constants import (
    Unit      ,
    SpecialTag,
    AUTOID_PREFIX ,
)



# ---------------------------------------------------------------------------- #
#                                 SOURCE SYSTEM                                #
# ---------------------------------------------------------------------------- #

class Fuel(str, Enum):
    
    ELECTRICITY     = "electricity"
    NATURALGAS      = "natural_gas"
    LPG             = "lpg"
    OIL             = "oil"
    BIOMASS         = "biomass"
    DISTRICTHEATING = "district_heating"
    DISTRICTCOOLING = "district_cooling"
    
    def __str__(self) -> str:
        return self.value
    
    def to_dragon(self) -> dragon.Fuel:
        
        match self:
            case Fuel.ELECTRICITY:
                return dragon.Fuel.ELECTRICITY
            case Fuel.NATURALGAS:
                return dragon.Fuel.NATURALGAS
            case Fuel.LPG:
                return dragon.Fuel.PROPANE
            case Fuel.OIL:
                return dragon.Fuel.DIESEL
            case Fuel.BIOMASS:
                return dragon.Fuel.COAL
            case Fuel.DISTRICTHEATING:
                return dragon.Fuel.OTHERFUEL1
            case Fuel.DISTRICTCOOLING:
                return dragon.Fuel.OTHERFUEL2


class SourceSystem:
    TYPE_MAPPER={}
    

class HeatPump(SourceSystem):
    
    SUPPORTED_FUELS = [
        Fuel.ELECTRICITY,
        Fuel.NATURALGAS ,
    ]
    
    def __init__(self,
        name:str,
        fuel            :str|Fuel ,
        heating_cop     :int|float|None=None,
        cooling_cop     :int|float|None=None,
        heating_capacity:int|float|None=None,
        cooling_capacity:int|float|None=None,
        *,
        ID:str|None=None
        ) -> None:
        
        # user properties
        self.name = name
        
        # fundamental properties (w/ default values)
        self.fuel = Fuel(fuel)
        self.heating_cop      = 3.0  if heating_cop      is None else heating_cop
        self.cooling_cop      = 3.0  if cooling_cop      is None else cooling_cop
        self.heating_capacity = None if heating_capacity is None else heating_capacity
        self.cooling_capacity = None if cooling_capacity is None else cooling_capacity
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SOURCE_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ fundamental properties
    """
    
    @property
    def fuel(self) -> Fuel:
        return self.__fuel
    
    @fuel.setter
    @validate_enum(Fuel)
    def fuel(self, value: str) -> None:
        
        if value not in self.SUPPORTED_FUELS:
            raise ValueError(
                f"Unsupported fuel type for HeatPump: {value}. "
                f"Supported fuels are: {[str(f) for f in self.SUPPORTED_FUELS]}"
            )
        
        self.__fuel = value
    
    @property
    def heating_cop(self) -> int|float:
        return self.__heating_cop
    
    @heating_cop.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float)
    def heating_cop(self, value: int|float) -> None:
        self.__heating_cop = value
    
    @property
    def cooling_cop(self) -> int|float:
        return self.__cooling_cop
    
    @cooling_cop.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float)
    def cooling_cop(self, value: int|float) -> None:
        self.__cooling_cop = value
    
    @property
    def heating_capacity(self) -> int|float:
        return self.__heating_capacity
    
    @heating_capacity.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float, allow_none=True)
    def heating_capacity(self, value: int|float) -> None:
        self.__heating_capacity = value
        
    @property
    def cooling_capacity(self) -> int|float:
        return self.__cooling_capacity
    
    @cooling_capacity.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float, allow_none=True)
    def cooling_capacity(self, value: int|float) -> None:
        self.__cooling_capacity = value
        
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:HeatPump) -> bool:
        
        # type validation
        if not isinstance(other, HeatPump):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two packaged air conditioners are equal if fuel, COPs, and capacities are equal
        return (self.fuel             == other.fuel            ) and\
               (self.heating_cop      == other.heating_cop     ) and\
               (self.cooling_cop      == other.cooling_cop     ) and\
               (self.heating_capacity == other.heating_capacity) and\
               (self.cooling_capacity == other.cooling_capacity)
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace
        ) -> HeatPump:
        
        return HeatPump(
            input.name,
            input.fuel_type,
            getattr(input, "cop_heating", None),
            getattr(input, "cop_cooling", None),
            getattr(input, "capacity_heating", None),
            getattr(input, "capacity_cooling", None),
            ID=input.id
        )
    
    def to_dragon(self) -> dragon.HeatPump:
        
        return dragon.HeatPump(
            self.ID,
            self.fuel.to_dragon(),
            self.heating_cop,
            self.cooling_cop,
            self.heating_capacity,
            self.cooling_capacity,
        )
        
    """ representation
    """
    
    def __str__(self) -> str:
        
        # formatting capacity
        heating_cap_str = f"{self.heating_capacity*Unit.W_TO_KW:4,.1f}kW" if self.heating_capacity is not None else "autosize"
        cooling_cap_str = f"{self.cooling_capacity*Unit.W_TO_KW:4,.1f}kW" if self.cooling_capacity is not None else "autosize"
        
        return (
            f"{self.fuel} HeatPump {self.name} (ID={self.ID})\n"
            f"\t- heating capacity={heating_cap_str}, COP={self.heating_cop:4.2f}\n"
            f"\t- cooling capacity={cooling_cap_str}, COP={self.cooling_cop:4.2f}"
        )
    
    def __repr__(self) -> str:
        return f"<HeatPump {self.name} (ID={self.ID}) at {hex(id(self))}>"
    

class GeothermalHeatPump(HeatPump):
    
    SUPPORTED_FUELS = [
        Fuel.ELECTRICITY,
        Fuel.NATURALGAS ,
    ]
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace
        ) -> GeothermalHeatPump:
        
        return GeothermalHeatPump(
            input.name,
            input.fuel_type,
            getattr(input, "cop_heating", None),
            getattr(input, "cop_cooling", None),
            getattr(input, "capacity_heating", None),
            getattr(input, "capacity_cooling", None),
            ID=input.id
        )
        
    def to_dragon(self):
        
        return dragon.HeatPump(
            self.ID,
            self.fuel.to_dragon(),
            self.heating_cop,
            self.cooling_cop,
            self.heating_capacity,
            self.cooling_capacity,
        )
        
    """ representation
    """
    
    def __str__(self) -> str:
        
        # formatting capacity
        heating_cap_str = f"{self.heating_capacity*Unit.W_TO_KW:4,.1f}kW" if self.heating_capacity is not None else "autosize"
        cooling_cap_str = f"{self.cooling_capacity*Unit.W_TO_KW:4,.1f}kW" if self.cooling_capacity is not None else "autosize"
        
        return (
            f"{self.fuel} GeothermalHeatPump {self.name} (ID={self.ID})\n"
            f"\t- heating capacity={heating_cap_str}, COP={self.heating_cop:4.2f}\n"
            f"\t- cooling capacity={cooling_cap_str}, COP={self.cooling_cop:4.2f}"
        )
    
    def __repr__(self) -> str:
        return f"<GeothermalHeatPump {self.name} (ID={self.ID}) at {hex(id(self))}>"
    

class CompressorType(str, Enum):
    
    TURBO         = "turbo"
    SCREW         = "screw"
    RECIPROCATING = "reciprocating"
    
    def __str__(self) -> str:
        return self.value
    
    def to_dragon(self) -> dragon.CompressorType:
        return dragon.CompressorType(self.value)
    
    
class CoolingTowerType(str, Enum):
    
    CLOSED = "closed"
    OPEN   = "open"
    
    def __str__(self) -> str:
        return self.value
    
    
class CoolingTowerControl(str, Enum):
    
    SINGLESPEED = "single-speed"
    TWOSPEED    = "two-speed"
    
    def __str__(self) -> str:
        return self.value


class Chiller(SourceSystem):
    
    def __init__(self,
        name:str     ,
        compressor_type      :str|CompressorType,
        coolingtower_type    :str|CoolingTowerType,
        coolingtower_control :str|CoolingTowerControl,
        cop     :int|float|None=None,
        capacity:int|float|None=None,
        coolingtower_capacity:int|float|None=None,
        *,
        ID:str|None=None,
        ) -> None:
        
        # user properties
        self.name = name
        
        # fundamental properties
        self.cop             = 3.0  if cop      is None else cop
        self.capacity        = None if capacity is None else capacity
        self.compressor_type = compressor_type
        
        # secondary source system (cooling tower) properties
        self.coolingtower_type     = coolingtower_type
        self.coolingtower_control  = coolingtower_control
        self.coolingtower_capacity = None if coolingtower_capacity is None else coolingtower_capacity
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SOURCE_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
         
    """ fundamental properties
    """
    
    @property
    def cop(self) -> int|float:
        return self.__cop
    
    @cop.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float)
    def cop(self, value: int|float) -> None:
        self.__cop = value
    
    @property
    def capacity(self) -> int|float:
        return self.__capacity
    
    @capacity.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float, allow_none=True)
    def capacity(self, value: int|float) -> None:
        self.__capacity = value
        
    @property
    def compressor_type(self) -> str:
        return str(self.__compressor_type)
    
    @compressor_type.setter
    @validate_enum(CompressorType)
    def compressor_type(self, value: str) -> None:
        self.__compressor_type = CompressorType(value)
    
    @property
    def coolingtower_type(self) -> str:
        return str(self.__coolingtower_type)
    
    @coolingtower_type.setter
    @validate_enum(CoolingTowerType)
    def coolingtower_type(self, value: str) -> None:
        self.__coolingtower_type = CoolingTowerType(value)
        
    @property
    def coolingtower_capacity(self) -> int|float:
        return self.__coolingtower_capacity
    
    @coolingtower_capacity.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float, allow_none=True)
    def coolingtower_capacity(self, value: int|float) -> None:
        self.__coolingtower_capacity = value
        
    @property
    def coolingtower_control(self) -> str:
        return str(self.__coolingtower_control)
    
    @coolingtower_control.setter
    @validate_enum(CoolingTowerControl)
    def coolingtower_control(self, value: str) -> None:
        self.__coolingtower_control = CoolingTowerControl(value)
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:Chiller) -> bool:
        
        # type validation
        if not isinstance(other, Chiller):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two chillers are equal if all fundamental properties are equal
        return (self.cop             == other.cop            ) and\
               (self.capacity        == other.capacity       ) and\
               (self.compressor_type == other.compressor_type) and\
               (self.coolingtower_type     == other.coolingtower_type    ) and\
               (self.coolingtower_capacity == other.coolingtower_capacity) and\
               (self.coolingtower_control  == other.coolingtower_control )
    
    """ in-out
    """
        
    @staticmethod
    def from_json(
        input:SimpleNamespace
    ) -> Chiller:
        
        return Chiller(
            input.name,
            input.compressor_type ,
            input.coolingtower_type    ,
            input.coolingtower_control ,
            getattr(input, "cop_cooling", None)     ,
            getattr(input, "capacity_cooling", None),
            getattr(input, "coolingtower_capacity", None),
            ID=input.id,
        )
    
    def to_dragon(self) -> dragon.Chiller:
        
        
        coolingtower_name = f"CoolingTower_for_{self.ID}"
        
        match (self.coolingtower_type, self.coolingtower_control):
            case (CoolingTowerType.OPEN, CoolingTowerControl.SINGLESPEED):
                coolingtower = dragon.OpenSingleSpeedCoolingTower(
                    coolingtower_name,
                    self.coolingtower_capacity,
                )
            case (CoolingTowerType.OPEN, CoolingTowerControl.TWOSPEED):
                coolingtower = dragon.OpenTwoSpeedCoolingTower(
                    coolingtower_name,
                    self.coolingtower_capacity
                )
            case (CoolingTowerType.CLOSED, CoolingTowerControl.SINGLESPEED):
                coolingtower = dragon.ClosedSingleSpeedCoolingTower(
                    coolingtower_name,
                    self.coolingtower_capacity
                )
            case (CoolingTowerType.CLOSED, CoolingTowerControl.TWOSPEED):
                coolingtower = dragon.ClosedTwoSpeedCoolingTower(
                    coolingtower_name,
                    self.coolingtower_capacity
                )
        
        dragonized_chiller = dragon.Chiller(
            self.ID,
            self.cop,
            self.capacity,
            CompressorType(self.compressor_type).to_dragon(),
            coolingtower,
        )
        
        return dragonized_chiller
    
    """ representation
    """
    
    def __str__(self) -> str:
        
        # formatting capacity
        chiller_cap_str = f"{self.capacity*Unit.W_TO_KW:4,.1f}kW" if self.capacity is not None else "autosize"
        coolingtower_cap_str = f"{self.coolingtower_capacity*Unit.W_TO_KW:4,.1f}kW" if self.coolingtower_capacity is not None else "autosize"
        
        return (
            f"Electric Chiller {self.name} (ID={self.ID})\n"
            f"\t- capacity={chiller_cap_str}, COP={self.cop:4.2f}\n"
            f"\t- connected cooling tower ({coolingtower_cap_str}): {self.coolingtower_type} type, {self.coolingtower_control} controlled"
        )
    
    def __repr__(self) -> str:
        return f"<Chiller {self.name} (ID={self.ID}) at {hex(id(self))}>"
    
    
class AbsorptionChiller(SourceSystem):
    
    SUPPORTED_BOILER_FUELS = [
        Fuel.ELECTRICITY,
        Fuel.NATURALGAS,
        Fuel.LPG       ,
        Fuel.OIL       ,
        Fuel.BIOMASS   ,
    ]
    
    def __init__(self,
        name:str     ,
        cop     :int|float|None=None,
        capacity:int|float|None=None,
        boiler_fuel      :str|Fuel|None=None,
        boiler_efficiency:int|float|None=None,
        *,
        ID:str|None=None
        ) -> None:
        
        # user properties
        self.name = name
        
        # fundamental properties
        self.cop      = 0.9  if cop      is None else cop
        self.capacity = None if capacity is None else capacity
        
        # secondary source system (boiler) properties
        if boiler_fuel is None:
            boiler_fuel = "natural_gas"
        self.boiler_fuel       = Fuel(boiler_fuel)
        self.boiler_efficiency = 0.85 if boiler_efficiency is None else boiler_efficiency

        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SOURCE_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ fundamental properties
    """
    
    @property
    def cop(self) -> int|float:
        return self.__cop
    
    @cop.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float)
    def cop(self, value: int|float) -> None:
        self.__cop = value
    
    @property
    def capacity(self) -> int|float:
        return self.__capacity
    
    @capacity.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float, allow_none=True)
    def capacity(self, value: int|float) -> None:
        self.__capacity = value
    
    @property
    def boiler_efficiency(self) -> int|float:
        return self.__boiler_efficiency
    
    @boiler_efficiency.setter
    @validate_range(min=math.nextafter(0,math.inf), max=1)
    @validate_type(int, float, allow_none=True)
    def boiler_efficiency(self, value: int|float) -> None:
        self.__boiler_efficiency = value
        
    @property
    def boiler_fuel(self) -> Fuel:
        return self.__boiler_fuel
    
    @boiler_fuel.setter
    @validate_enum(Fuel)
    def boiler_fuel(self, value: str) -> None:
        if value not in self.SUPPORTED_BOILER_FUELS:
            raise ValueError(
                f"Unsupported fuel type for AbsorptionChiller boiler: {value}. "
                f"Supported fuels are: {[str(f) for f in self.SUPPORTED_BOILER_FUELS]}"
            )
        
        self.__boiler_fuel = value
        
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:AbsorptionChiller) -> bool:
        
        # type validation
        if not isinstance(other, AbsorptionChiller):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two chillers are equal if all fundamental properties are equal
        return (self.cop               == other.cop              ) and\
               (self.capacity          == other.capacity         ) and\
               (self.boiler_efficiency == other.boiler_efficiency)
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace
    ) -> AbsorptionChiller:
        
        return AbsorptionChiller(
            input.name,
            getattr(input,"cop_cooling", None),
            getattr(input,"capacity_cooling", None),
            input.fuel_type,
            getattr(input,"boiler_efficiency", None),
            ID=input.id
        )
        
    def to_dragon(self) -> dragon.AbsorptionChiller:
        
        boiler = dragon.Boiler(
            f"Boiler_for_{self.ID}",
            self.boiler_fuel.to_dragon(),
            self.boiler_efficiency
        )
        
        coolingtower = dragon.OpenSingleSpeedCoolingTower(
            f"CoolingTower_for_{self.ID}",
            self.capacity,
        )
        
        return dragon.AbsorptionChiller(
            self.ID,
            self.cop     ,
            self.capacity,
            boiler       ,
            coolingtower ,
        )
    
    """ representation
    """
    
    def __str__(self) -> str:
        
        # formatting capacity
        cap_str = f"{self.capacity*Unit.W_TO_KW:4,.1f}kW" if self.capacity is not None else "autosize"
        
        return (
            f"AbsorptionChiller {self.name} (ID={self.ID})\n"
            f"\t- capacity={cap_str}, COP={self.cop:4.2f}\n"
            f"\t- connected boiler efficiency={self.boiler_efficiency}"
        )
    
    def __repr__(self) -> str:
        return f"<AbsorptionChiller {self.name} (ID={self.ID}) at {hex(id(self))}>"
    
    
class DistrictHeating(SourceSystem):
    
    def __init__(self,
        name:str,
        *,
        ID:str|None=None
        ) -> None:
        
        # user properties
        self.name = name
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SOURCE_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:DistrictHeating) -> bool:
        
        # type validation
        if not isinstance(other, DistrictHeating):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two district heating systems are always equal
        return True
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace
    ) -> DistrictHeating:
    
        return DistrictHeating(
            input.name,
            ID=input.id
        )
    
    def to_dragon(self):
        
        return dragon.DistrictHeating(
            self.ID,
        )
        
    """ representation
    """

    def __str__(self) -> str:
        
        return f"District-heating system {self.name} (ID={self.ID})"
    
    def __repr__(self) -> str:
        return f"<DistrictHeating {self.name} (ID={self.ID}) at {hex(id(self))}>"
    
    
class DistrictCooling(SourceSystem):
    
    def __init__(self,
        name:str,
        *,
        ID:str|None=None
        ) -> None:
        
        # user properties
        self.name = name
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SOURCE_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:DistrictCooling) -> bool:
        
        # type validation
        if not isinstance(other, DistrictCooling):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two district cooling systems are always equal
        return True
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace
    ) -> DistrictCooling:
    
        return DistrictCooling(
            input.name,
            ID=input.id
        )
    
    def to_dragon(self):
        
        return dragon.DistrictCooling(
            self.ID,
        )        
        
    """ representation
    """

    def __str__(self) -> str:
        
        return f"District-cooling system {self.name} (ID={self.ID})"
    
    def __repr__(self) -> str:
        return f"<DistrictCooling {self.name} (ID={self.ID}) at {hex(id(self))}>"
    

class Boiler(SourceSystem):
    
    SUPPORTED_FUELS = [
        Fuel.ELECTRICITY,
        Fuel.NATURALGAS ,
        Fuel.LPG        ,
        Fuel.OIL        ,
        Fuel.BIOMASS    ,
    ]
    
    def __init__(self,
        name:str,
        fuel           :str|Fuel ,
        efficiency     :int|float|None=None,
        capacity       :int|float|None=None,
        *,
        ID:str|None=None
    ) -> Boiler:
        
        # user properties
        self.name = name
        
        # fundamental properties        
        self.fuel            = Fuel(fuel)
        self.capacity        = None if capacity   is None else capacity
        self.efficiency      = 0.85 if efficiency is None else efficiency
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SOURCE_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ fundamental properties
    """
    
    @property
    def fuel(self) -> Fuel:
        return self.__fuel
    
    @fuel.setter
    @validate_enum(Fuel)
    def fuel(self, value: str) -> None:
        
        if value not in self.SUPPORTED_FUELS:
            raise ValueError(
                f"Unsupported fuel type for Boiler: {value}. "
                f"Supported fuels are: {[str(f) for f in self.SUPPORTED_FUELS]}"
            )
        
        self.__fuel = value
    
    @property
    def efficiency(self) -> int|float:
        return self.__efficiency
    
    @efficiency.setter
    @validate_range(min=math.nextafter(0,math.inf), max=1)
    @validate_type(int, float)
    def efficiency(self, value: int|float) -> None:
        self.__efficiency = value
    
    @property
    def capacity(self) -> int|float:
        return self.__capacity
    
    @capacity.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float, allow_none=True)
    def capacity(self, value: int|float) -> None:
        self.__capacity = value
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:Boiler) -> bool:
        
        # type validation
        if not isinstance(other, Boiler):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two boilers are equal if all fundamental properties are equal
        return (self.fuel            == other.fuel           ) and\
               (self.efficiency      == other.efficiency     ) and\
               (self.capacity        == other.capacity       ) 
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace
    ) -> Boiler:
        
        return Boiler(
            input.name,
            input.fuel_type       ,
            getattr(input,"efficiency", None),
            getattr(input,"capacity_heating", None),
            ID = input.id
        )
        
    def to_dragon(self) -> dragon.Boiler:
        
        return dragon.Boiler(
            self.ID,
            Fuel(self.fuel).to_dragon(),
            self.efficiency,
            self.capacity  ,
            pump_efficiency=0.9,
        )
        
    """ representation
    """
    
    def __str__(self) -> str:
        
        
        # formatting capacity 
        cap_str = f"{self.capacity*Unit.W_TO_KW:4,.1f}kW" if self.capacity is not None else "autosize"
        
        return (
            f"{self.fuel} Boiler {self.name} (ID={self.ID})\n"
            f"\t- capacity={cap_str}, eff.={self.efficiency*Unit.FRACTION_TO_PERCENT:.1f}%"
        )
    
    def __repr__(self) -> str:
        return f"<Boiler {self.name} (ID={self.ID}) at {hex(id(self))}>"
    

class NoneSource(SourceSystem):
    
    # ID for singleton instance
    ID = f"{SpecialTag.SPECIAL}{AUTOID_PREFIX.SOURCE_SYSTEM}-NONE"
    
    # NoneSource is a singleton class
    _instance = None    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    # none-source cannot be dragonized
    def to_dragon(self) -> None:
        return None
    


# ---------------------------------------------------------------------------- #
#                                 SUPPLY SYSTEM                                #
# ---------------------------------------------------------------------------- #

class SupplySystem:
    
    # map json input to corresponding subclasses
    # type_mapper class-variable will be defined at the end of the document
    TYPE_MAPPER={}

    # define heating/cooling capability by subclass and the connected source system
    _heatable_sources = []
    _coolable_sources = []
    
    @property
    def heatable(self) -> bool:
        return (type(self.source) in self._heatable_sources)
    
    @property
    def coolable(self) -> bool:
        return (type(self.source) in self._coolable_sources)
        
    
class DXIndoorUnit(SupplySystem):
    
    _heatable_sources = [HeatPump, GeothermalHeatPump]
    _coolable_sources = [HeatPump, GeothermalHeatPump]
    
    def __init__(self,
        name,
        source:SourceSystem,
        *,
        ID:str|None=None
        ) -> None:

        # user properties
        self.name = name
        
        # fundamental properties
        self.source = source
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SUPPLY_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ fundamental properties
    """
    
    @property
    def source(self) -> SourceSystem:
        return self.__source
    
    @source.setter
    @validate_type(*_heatable_sources, *_coolable_sources)
    def source(self, value:SourceSystem) -> None:
        self.__source = value
            
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:DXIndoorUnit) -> bool:
        
        # type validation
        if not isinstance(other, type(self)):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two air handling units are equal if source systems are identical (note: not equal)
        return (self.source is other.source)
    
    """ in-out
    """
            
    @staticmethod
    def from_json(
        input             :SimpleNamespace        ,
        source_system_dict:dict[str, SourceSystem],
        ) -> DXIndoorUnit:
        
        return DXIndoorUnit(
            input.name,
            source_system_dict[input.source_system_id],
            ID=input.id
        )
    
    def to_dragon(self, source_dict:dict[str, dragon.SourceSystem]) -> dragon.DXIndoorUnit:
        
        return dragon.DXIndoorUnit(
            self.ID,
            source_dict[self.source.ID],
        )
        
    """ representation
    """
    
    def __str__(self) -> str:
        return f"AirHandlingUnit {self.name} (ID={self.ID}) using {type(self.source).__name__} {self.source.name}"
    
    def __repr__(self) -> str:
        return f"<AirHandlingUnit {self.name} (ID={self.ID}) at {hex(id(self))}>"


class FanCoilUnit(DXIndoorUnit):
    
    _heatable_sources = [Boiler, DistrictHeating]
    _coolable_sources = [Chiller, AbsorptionChiller, DistrictCooling]
    
    def __init__(self,
        name,
        source:SourceSystem,
        *,
        ID:str|None=None
        ) -> None:

        # user properties
        self.name = name
        
        # fundamental properties
        self.source = source
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SUPPLY_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ fundamental properties
    """
    
    @property
    def source(self) -> SourceSystem:
        return self.__source
    
    @source.setter
    @validate_type(*_heatable_sources, *_coolable_sources)
    def source(self, value:SourceSystem) -> None:
        self.__source = value
            
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:FanCoilUnit) -> bool:
        
        # type validation
        if not isinstance(other, type(self)):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two fan coil units are equal if source systems are identical (note: not equal)
        return (self.source is other.source)
    
    """ in-out
    """
            
    @staticmethod
    def from_json(
        input             :SimpleNamespace        ,
        source_system_dict:dict[str, SourceSystem],
        ) -> FanCoilUnit:
        
        return FanCoilUnit(
            input.name,
            source_system_dict[input.source_system_id],
            ID=input.id
        )
    
    def to_dragon(self, source_dict:dict[str, dragon.SourceSystem]) -> dragon.FanCoilUnit:
        
        return dragon.FanCoilUnit(
            self.ID,
            source_dict[self.source.ID],
        )
        
    """ representation
    """
    
    def __str__(self) -> str:
        return f"FanCoilUnit {self.name} (ID={self.ID}) using {type(self.source).__name__} {self.source.name}"
    
    def __repr__(self) -> str:
        return f"<FanCoilUnit {self.name} (ID={self.ID}) at {hex(id(self))}>"
    
        
class Radiator(SupplySystem):
    
    _heatable_sources = [Boiler, DistrictHeating]
    _coolable_sources = []
    
    def __init__(self,
        name:str,
        source  :SourceSystem,
        capacity:int|float|None=None,
        *,
        ID:str|None=None
        ) -> None:
        
        # user property
        self.name = name
        
        # fundamental properties
        self.capacity = None if capacity is None else capacity
        self.source   = source
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SUPPLY_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
        
    """ fundamental properties
    """
    
    @property
    def capacity(self) -> int|float:
        return self.__capacity
    
    @capacity.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float, allow_none=True)
    def capacity(self, value: int|float) -> None:
        self.__capacity = value
    
    @property
    def source(self) -> SourceSystem:
        return self.__source
    
    @source.setter
    @validate_type(*_heatable_sources, *_coolable_sources)
    def source(self, value:SourceSystem) -> None:
        self.__source = value
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:Radiator) -> bool:
        
        # type validation
        if not isinstance(other, Radiator):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two air handling units are equal if capacities are equal and source systems are identical (note: not equal)
        return (self.capacity == other.capacity) and\
               (self.source   is other.source  )
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input             :SimpleNamespace        ,
        source_system_dict:dict[str, SourceSystem],
    ) -> Radiator:
        
        return Radiator(
            input.name,
            source_system_dict[input.source_system_id],
            getattr(input,"capacity_heating", None),
            ID=input.id
        )
    
    def to_dragon(self, source_dict:dict[str, dragon.SourceSystem]) -> dragon.Radiator:
        
        return dragon.Radiator(
            self.ID,
            self.capacity,
            source_dict[self.source.ID],
        )
        
    """ representation
    """
    
    def __str__(self) -> str:
        return f"Radiator {self.name} (ID={self.ID}) using {type(self.source).__name__} {self.source.name}"
    
    def __repr__(self) -> str:
        return f"<Radiator {self.name} (ID={self.ID}) at {hex(id(self))}>"
    
    
class ElectricRadiator(SupplySystem):
    
    _heatable_sources = [NoneSource]
    _coolable_sources = []
    
    def __init__(self,
        name:str,
        capacity:int|float|None=None,
        *,
        ID:str|None=None
        ) -> None:
        
        # user property
        self.name = name
        
        # fundamental properties
        self.capacity = None if capacity is None else capacity
        
        # a packaged air conditioner doesn't require source system
        self.__source = NoneSource()
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SUPPLY_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
        
    """ fundamental properties
    """
    
    @property
    def capacity(self) -> int|float|None:
        return self.__capacity
    
    @capacity.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float, allow_none=True)
    def capacity(self, value: int|float|None) -> None:
        self.__capacity = value
        
    @property
    def source(self) -> NoneSource:
        return self.__source
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:ElectricRadiator) -> bool:
        
        # type validation
        if not isinstance(other, ElectricRadiator):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two air handling units are equal if capacities are equal 
        return (self.capacity == other.capacity)
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input             :SimpleNamespace        ,
        source_system_dict:dict[str, SourceSystem],
    ) -> ElectricRadiator:
        
        return ElectricRadiator(
            input.name,
            getattr(input,"capacity_heating", None),
            ID=input.id,
        )
        
    def to_dragon(self, source_dict:dict[str, dragon.SourceSystem]) -> dragon.ElectricRadiator:
        
        return dragon.ElectricRadiator(
            self.ID,
            self.capacity,
        )
    
    """ representation
    """
    
    def __str__(self) -> str:
        
        # formatting capacity
        cap_str = f"{self.capacity*Unit.W_TO_KW:4,.1f}kW" if self.capacity is not None else "autosize"
        
        return f"Electric radiator {self.name} with capacity={cap_str} (ID={self.ID})"
    
    def __repr__(self) -> str:
        return f"<ElectricRadiator {self.name} (ID={self.ID}) at {hex(id(self))}>"
        
        
class RadiantFloor(SupplySystem):
    
    _heatable_sources = [Boiler, DistrictHeating]
    _coolable_sources = []
    
    def __init__(self,
        name,
        source:SourceSystem,
        *,
        ID:str|None=None
        ) -> None:

        # user properties
        self.name = name
        
        # fundamental properties
        self.source = source
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SUPPLY_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ fundamental properties
    """
    
    @property
    def source(self) -> SourceSystem:
        return self.__source
    
    @source.setter
    @validate_type(*_heatable_sources, *_coolable_sources)
    def source(self, value:SourceSystem) -> None:
        self.__source = value
    
    @property
    def heatable(self) -> bool:
        return True
    
    @property
    def coolable(self) -> bool:
        return False
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:RadiantFloor) -> bool:
        
        # type validation
        if not isinstance(other, RadiantFloor):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two radiant floors are equal if source systems are identical (note: not equal)
        return (self.source is other.source)
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input             :SimpleNamespace        ,
        source_system_dict:dict[str, SourceSystem],
        ) -> RadiantFloor:   
        
        return RadiantFloor(
            input.name,
            source_system_dict[input.source_system_id],
            ID=input.id
        )
        
    def to_dragon(self, source_dict:dict[str, dragon.SourceSystem]) -> dragon.RadiantFloor:
        
        return dragon.RadiantFloor(
            self.ID,
            source_dict[self.source.ID]
        )
        
    """ representation
    """
    
    def __str__(self) -> str:
        return f"Radiant floor {self.name} (ID={self.ID}) using {type(self.source).__name__} {self.source.name}"
    
    def __repr__(self) -> str:
        return f"<RadiantFloor {self.name} (ID={self.ID}) at {hex(id(self))}>"
            

class ElectricRadiantFloor(SupplySystem):
    
    _heatable_sources = [NoneSource]
    _coolable_sources = []
    
    def __init__(self,
        name:str,
        *,
        ID:str|None=None
        ) -> None:
        
        # user property
        self.name = name
        
        # a packaged air conditioner doesn't require source system
        self.__source = NoneSource()
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SUPPLY_SYSTEM}AUTOID{hex(id(self))}"
        self.__ID = ID
        
    """ fundamental properties
    """
    
    @property
    def source(self) -> NoneSource:
        return self.__source
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:ElectricRadiantFloor) -> bool:
        
        # type validation
        if not isinstance(other, ElectricRadiantFloor):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two electric radiant floors are always equal (no fundamental properties)
        return True
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input             :SimpleNamespace        ,
        source_system_dict:dict[str, SourceSystem],
    ) -> ElectricRadiantFloor:
        
        return ElectricRadiantFloor(
            input.name,
            ID=input.id,
        )
        
    def to_dragon(self, source_dict:dict[str, dragon.SourceSystem]) -> dragon.ElectricRadiantFloor:
        
        return dragon.ElectricRadiantFloor(
            self.ID,
        )
    
    """ representation
    """
    
    def __str__(self) -> str:
        
        return f"Electric radiant floor {self.name} (ID={self.ID})"
    
    def __repr__(self) -> str:
        return f"<ElectricRadiantFloor {self.name} (ID={self.ID}) at {hex(id(self))}>"

# ---------------------------------------------------------------------------- #
#                                 OTHER SYSTEMS                                #
# ---------------------------------------------------------------------------- #

class VentilationSystem:
    
    def __init__(self,
        name:str,
        airflow_rate      :int|float|None=None,
        heating_efficiency:int|float|None=None,
        cooling_efficiency:int|float|None=None,
        *,
        ID:str|None=None
        ) -> None:
        
        # user property
        self.name = name
        
        # fundamental properties
        self.airflow_rate = airflow_rate
        self.heating_efficiency = 0.7  if heating_efficiency is None else heating_efficiency
        self.cooling_efficiency = 0.45 if cooling_efficiency is None else cooling_efficiency
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.HEAT_EXCHANGER}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ fundamental properties
    """
    
    @property
    def airflow_rate(self) -> int|float|None:
        return self.__airflow_rate
    
    @airflow_rate.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float,allow_none=True)
    def airflow_rate(self, value:int|float|None) -> None:
        self.__airflow_rate = value
    
    @property
    def heating_efficiency(self) -> int|float:
        return self.__heating_efficiency
    
    @heating_efficiency.setter
    @validate_range(min=math.nextafter(0,math.inf), max=math.nextafter(1,-math.inf))
    @validate_type(int, float)
    def heating_efficiency(self, value:int|float) -> None:
        self.__heating_efficiency = value
        
    @property
    def cooling_efficiency(self) -> int|float:
        return self.__cooling_efficiency
    
    @cooling_efficiency.setter
    @validate_range(min=math.nextafter(0,math.inf), max=math.nextafter(1,-math.inf))
    @validate_type(int, float)
    def cooling_efficiency(self, value:int|float) -> None:
        self.__cooling_efficiency = value
        
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:VentilationSystem) -> bool:
        
        # type validation
        if not isinstance(other, VentilationSystem):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )    
            
        # two ventilation systems are equal if all efficiencies are equal
        return (self.airflow_rate == other.airflow_rate) and\
               (self.heating_efficiency == other.heating_efficiency) and\
               (self.cooling_efficiency == other.cooling_efficiency)
               
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace
        ) -> VentilationSystem:
        
        return VentilationSystem(
            input.name,
            getattr(input, "airflow_rate", None),
            getattr(input, "efficiency_heating", None),
            getattr(input, "efficiency_cooling", None),
            ID=input.id,
        )
    
    def to_dragon(self) -> None:
        
        return dragon.EnergyRecoveryVentilator(
            self.ID,
            self.heating_efficiency,
            self.cooling_efficiency,
        )
    
    """ representation
    """
    
    def __str__(self) -> str:
        return f"Ventilator (HEX) {self.name} (ID={self.ID}) with flow rate = {self.airflow_rate*Unit.M3_PER_S_TO_CMH:.1f} CMH eff_h={self.heating_efficiency*Unit.FRACTION_TO_PERCENT:.1f}%, eff_c={self.cooling_efficiency*Unit.FRACTION_TO_PERCENT:.1f}%"
    
    def __repr__(self) -> str:
        return f"<VentilationSystem {self.name} (ID={self.ID}) at {hex(id(self))}>"
    
    
class PhotoVoltaicSystem:
    
    def __init__(self,
        name:str,
        area      :int|float,
        efficiency:int|float,
        azimuth   :int|float, # clockwise from north
        tilt      :int|float,
        *,
        ID:str|None=None
        ) -> None:
        
        # user properties
        self.name = name
        
        # fundamental properties
        self.area      =area
        self.efficiency=efficiency
        self.azimuth   =azimuth
        self.tilt      =tilt

        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.PV_PANEL}AUTOID{hex(id(self))}"
        self.__ID = ID

    """ fundamental properties
    """
    
    @property
    def area(self) -> int|float:
        return self.__area
    
    @area.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float)
    def area(self, value:int|float) -> None:
        self.__area = value
        
    @property
    def efficiency(self) -> int|float:
        return self.__efficiency
    
    @efficiency.setter
    @validate_range(min=math.nextafter(0,math.inf), max=1)
    @validate_type(int, float)
    def efficiency(self, value:int|float) -> None:
        self.__efficiency = value
        
    @property
    def azimuth(self) -> int|float:
        return self.__azimuth
    
    @azimuth.setter
    @validate_range(min=math.nextafter(-360, math.inf), max=math.nextafter(360,-math.inf))
    @validate_type(int, float)
    def azimuth(self, value:int|float) -> None:
        self.__azimuth = value
        
    @property
    def tilt(self) -> int|float:
        return self.__tilt
    
    @tilt.setter
    @validate_range(min=0, max=90)
    @validate_type(int, float)
    def tilt(self, value:int|float) -> None:
        self.__tilt = value

    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __eq__(self, other:PhotoVoltaicSystem) -> bool:
        
        # type validation
        if not isinstance(other, PhotoVoltaicSystem):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
            
        # two PV-panels are equal if physical properties and specifications are equal
        return (self.area       == other.area      ) and\
               (self.efficiency == other.efficiency) and\
               (self.azimuth    == other.azimuth   ) and\
               (self.tilt       == other.tilt      )
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace
        ) -> PhotoVoltaicSystem:
        
        return PhotoVoltaicSystem(
            input.name,
            input.area      ,
            input.efficiency,
            input.azimuth   ,
            input.tilt      ,
            ID=input.id
        )
    
    def to_dragon(self):
        
        return dragon.PhotoVoltaicPanel(
            self.ID,
            self.area      ,
            self.tilt      ,
            (360-self.azimuth)%360,
            self.efficiency,
        )
        
    """ representation
    """
    
    def __str__(self) -> str:
        return f"{self.area:.1f}m2 PV panel {self.name}: eff={self.efficiency*Unit.FRACTION_TO_PERCENT:.1f}%, azim={self.azimuth:.1f}°, tilt={self.tilt:.1f}°"
    
    def __repr__(self) -> str:
        return f"<PhotoVoltaicSystem {self.name} (ID={self.ID}) at {hex(id(self))}>"
    
    
    
# ---------------------------------------------------------------------------- #
#                                 CHILD CLASSES                                #
# ---------------------------------------------------------------------------- #

SupplySystem.TYPE_MAPPER = {
    "dx_indoor_unit"          : DXIndoorUnit       ,
    "fan_coil_unit"           : FanCoilUnit           ,
    "radiator"                : Radiator              ,
    "electric_radiator"       : ElectricRadiator      ,
    "radiant_floor"           : RadiantFloor          ,
    "electric_radiant_floor"  : ElectricRadiantFloor  ,
}

SourceSystem.TYPE_MAPPER = {
    "heatpump"           : HeatPump          ,
    "geothermal_heatpump": GeothermalHeatPump,
    "chiller"            : Chiller           ,
    "absorption_chiller" : AbsorptionChiller ,
    "district_cooling"   : DistrictCooling   ,
    "boiler"             : Boiler            ,
    "district_heating"   : DistrictHeating   ,
}







