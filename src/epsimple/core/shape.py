
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import math
import hashlib
from copy  import deepcopy
from types import SimpleNamespace
from abc   import (
    ABC           ,
    abstractmethod,
)
from enum import Enum

# third-party modules

# local modules
from ..constants import (
    SpecialTag,
    AUTOID_PREFIX ,
)
from .construction import (
    Material           ,
    SurfaceConstruction,
    FenestrationConstruction,
    UnknownConstruction,
    OpenConstruction    ,
)
from .profile      import (
    Profile
)
from .hvac         import (
    SupplySystem,
    VentilationSystem,
)
from idragon import dragon
from idragon.dragon import (
    SurfaceType,
    SurfaceBoundaryCondition,
)
from idragon.utils import (
    validate_range,
    validate_type ,
    validate_enum ,
)

# ---------------------------------------------------------------------------- #
#                                   GEOMETRY                                   #
# ---------------------------------------------------------------------------- #
        
class Surface:
    
    def __init__(self,
        name    :str,
        type    :str,
        boundary:str|Zone,
        area    :int|float,
        azimuth :int|float,
        construction:SurfaceConstruction,
        fenestrations:list[Fenestration],
        *,
        reflectance  :int|float|None=None,
        adjacent_zone:Zone|None=None,
        ID           :str|None =None,
        ) -> None:
        
        # user properties
        self.name = name
        
        # fundamental properties
        self.area     = area
        self.type     = type
        self.boundary = boundary
        self.azimuth  = azimuth
        self.adjacent_zone = adjacent_zone
        self.construction  = construction
        self.reflectance   = reflectance
        
        if self.boundary in ["ground", "adiabatic"] and len(fenestrations) > 0:
            raise ValueError(
                "Cannot assign windows or doors to a surface with bounary condition == ground or adiabatic."
            )
        self.fenestrations = fenestrations
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SURFACE}AUTOID{hex(id(self))}"
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
    def azimuth(self) -> int|float:
        return self.__azimuth
    
    @azimuth.setter
    @validate_range(min=0, max=math.nextafter(360,-math.inf))
    @validate_type(int, float, allow_none=True)
    def azimuth(self, value:int|float) -> None:
        
        is_required = (self.type == SurfaceType.WALL) and (self.boundary == SurfaceBoundaryCondition.OUTDOOR)
        
        if not is_required and (value is not None):
            raise ValueError(
                f"Azimuth property is not required for {self.type} with {self.boundary} condition"
            )
        
        if is_required and not isinstance(value, int|float):
            raise ValueError(
                f"Azimuth property is required for outdoor wall"
            )
        
        self.__azimuth = value        
    
    @property
    def type(self) -> str:
        return str(self.__type)
    
    @type.setter
    @validate_enum(SurfaceType)
    def type(self, value:str|SurfaceType) -> None:
        
        if value != SurfaceType.WALL:
            self.__azimuth = None
        
        self.__type = SurfaceType(value)
        
    @property
    def boundary(self) -> str:
        return str(self.__boundary)
    
    @boundary.setter
    @validate_enum(SurfaceBoundaryCondition)
    def boundary(self, value:str|SurfaceBoundaryCondition) -> None:        
        self.__boundary = SurfaceBoundaryCondition(value)
        
        if value is not SurfaceBoundaryCondition.ZONE:
            self.adjacent_zone = None
    
    @property
    def adjacent_zone(self) -> Zone:
        return self.__adjacent_zone
    
    @adjacent_zone.setter
    def adjacent_zone(self, value:Zone|None) -> None:
        
        if (value is not None) and not isinstance(value, Zone):
            raise TypeError(
                    f"Invalid type for adjacent_zone: expected Zone, got {type(value)}"
                )
        
        self.__adjacent_zone = value
        
        if value is not None:
            self.__boundary = SurfaceBoundaryCondition.ZONE
    
    @property
    def construction(self) -> SurfaceConstruction:
        return self.__construction
    
    @construction.setter
    @validate_type(SurfaceConstruction, UnknownConstruction, OpenConstruction)
    def construction(self, value:SurfaceConstruction) -> None:
        self.__construction = value
    
    @property
    def reflectance(self) -> int|float|None:
        return self.__reflectance
    
    @reflectance.setter
    @validate_range(min=math.nextafter(0,math.inf), max=1)
    @validate_type(int, float, allow_none=True)
    def reflectance(self, value:int|float) -> None:
        self.__reflectance = value       
    
    """ useful methods
    """
    
    @property
    def num_windows(self) -> int:
        return len([fen for fen in self.fenestrations if isinstance(fen, Window)])
    
    @property
    def num_doors(self) -> int:
        return len([fen for fen in self.fenestrations if isinstance(fen, Door)])
    
    def get_unique_fenestration_constructions(self) -> dict[str, FenestrationConstruction]:
        
        return {
            fenestration.construction.ID: fenestration.construction
            for fenestration in self.fenestrations
        }
    
    def flip(self, inplace=False) -> Surface:
        
        if inplace:
            clone = self
        else:
            clone = deepcopy(self)
        
        match self.type:
            case SurfaceType.WALL:
                
                if self.boundary == SurfaceBoundaryCondition.OUTDOOR:
                    clone.azimuth = (getattr(self,"azimuth",0) + 180) % 360
                
            case SurfaceType.FLOOR:
                clone.type = SurfaceType.CEILING
            case SurfaceType.CEILING:
                clone.type = SurfaceType.FLOOR
        
        if inplace:
            return None
        else:
            return clone
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
    
    def __deepcopy__(self, memo:dict) -> Surface:
        
        clone = Surface(
            self.name + "_copied",
            self.type    ,
            self.boundary,
            self.area    ,
            self.azimuth ,
            self.construction,
            [deepcopy(fenestration) for fenestration in self.fenestrations],
            reflectance=self.reflectance ,
            ID=f"{SpecialTag.CLONE}{self.ID}"
        )
        
        memo[id(self)] = clone
        return clone
                
    
    """ in-out
    """
    
    def _get_vertex(self,
        zone_height:int|float,
        ) -> list[dragon.Vertex]:
        
        match self.type:
            case SurfaceType.CEILING:
                l = self.area ** 0.5
                return [
                    dragon.Vertex(-l/2,  l/2, zone_height),
                    dragon.Vertex(-l/2, -l/2, zone_height),
                    dragon.Vertex( l/2, -l/2, zone_height),
                    dragon.Vertex( l/2,  l/2, zone_height),
                ]
            
            case SurfaceType.FLOOR:
                l = self.area ** 0.5
                return [
                    dragon.Vertex( l/2, -l/2, 0),
                    dragon.Vertex(-l/2, -l/2, 0),
                    dragon.Vertex(-l/2,  l/2, 0),
                    dragon.Vertex( l/2,  l/2, 0),
                ]
            
            case SurfaceType.WALL:
                
                width = self.area / zone_height
                if self.azimuth is not None:
                    azimuth_radian = math.radians(self.azimuth)
                else:
                    hash_value = hashlib.sha256(self.ID.removeprefix(SpecialTag.CLONE.value).encode("utf-8")).hexdigest()
                    azimuth_radian = int(hash_value[:12], 16) / (16**12) * 2 * math.pi
                    if self.ID.startswith(SpecialTag.CLONE.value):
                        azimuth_radian = (azimuth_radian + math.pi) % (2*math.pi)
                        
                x = math.cos(azimuth_radian - 3/2*math.pi) * width/2
                y = math.sin(azimuth_radian - 3/2*math.pi) * width/2
                z = zone_height
                
                return [
                    dragon.Vertex( x, -y, z),
                    dragon.Vertex( x, -y, 0),
                    dragon.Vertex(-x,  y, 0),
                    dragon.Vertex(-x,  y, z),
                ]
    
    @staticmethod
    def from_json(
        input:SimpleNamespace,
        surface_construction_dict     :dict[str, SurfaceConstruction     ],
        fenestration_construction_dict:dict[str, FenestrationConstruction],
        ) -> Surface:
        
        match input.construction_id:
            case "open": 
                construction = OpenConstruction()
            case None:
                construction = UnknownConstruction()
            case _:
                construction = surface_construction_dict.get(input.construction_id)
        
        return Surface(
            input.name,
            input.type,
            input.boundary_condition,
            input.area,
            getattr(input, "azimuth", None),
            construction,
            [
                Fenestration.from_json(fene_input, fenestration_construction_dict)
                for fene_input in input.fenestrations
            ],
            reflectance=getattr(input, "coolroof_reflectance", None),
            ID=input.id,            
        )
        
    def to_dragon(self,
        zone_height:int|float,
        surface_construction_dict     :dict[str, SurfaceConstruction]    ,
        fenestration_construction_dict:dict[str,FenestrationConstruction],
        ) -> dragon.Surface:
        
        if self.reflectance is not None:
            construction = surface_construction_dict[f"{SpecialTag.COOLROOF}{self.construction.ID}"]
        else:
            construction = surface_construction_dict[self.construction.ID]
        
        return dragon.Surface(
            self.ID,
            self.type,
            construction,
            self.boundary,    
            self._get_vertex(zone_height),
            window=[
                fen.to_dragon(fenestration_construction_dict)
                for fen in self.fenestrations if isinstance(fen, Window|GlassDoor)
            ],
            door=[
                fen.to_dragon(fenestration_construction_dict) 
                for fen in self.fenestrations if isinstance(fen, Door)
            ]
        )


    
    """ representation
    """
    
    def __str__(self) -> str:
        
        return "\n".join([
            f"{self.type} Surface {self.name} (area={self.area:.1f}m2, ID={self.ID})",
            f"\t-adjacent to {self.boundary} {f'({self.adjacent_zone.name})' if self.boundary == SurfaceBoundaryCondition.ZONE else ''}"
            f"\t-with {self.num_windows} windows and {self.num_doors} doors"
        ])
    
    def __repr__(self) -> str:
        return f"<Surface {self.name} (ID={self.ID}) at {hex(id(self))}>"
        
    

class Fenestration(ABC):
    
    def __init__(self,
        name,
        area,
        construction,
        *,
        ID:str|None=None
        ) -> None:
        
        self.name = name
        self.area = area
        self.construction = construction
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.FENESTRATION}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ fundamental properties
    """
    
    @property
    def construction(self) -> FenestrationConstruction:
        return self.__construction
    
    @construction.setter
    @abstractmethod
    def construction(self, value) -> None: ...
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
        
    def __deepcopy__(self, memo:dict) -> Fenestration:
        
        clone = type(self)(
            self.name + "_copied",
            self.area,
            self.construction,
            ID=f"{SpecialTag.CLONE}{self.ID}"
        )
        
        memo[id(self)] = clone
        return clone
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace,
        fenestration_construction_dict:dict[str, FenestrationConstruction]
        ) -> Fenestration:
        
        type_mapper = {
            "window"   : Window   ,
            "door"     : Door     ,
            "glassdoor": GlassDoor,
        }
        
        return type_mapper[input.type].from_json(
            input,
            fenestration_construction_dict
        )

    @abstractmethod
    def to_dragon(self): ...


class BlindType(str, Enum):
    SHADE    = "shade"
    VENETIAN = "venetian"

    def __str__(self) -> str:
        return self.value
    
class Window(Fenestration):
    
    dragonized_blind = dragon.Blind(
        "default_blind",
        0.05,
        0.05,
        90,
        0.5,
        0.5,
    )
    
    dragonized_shade = dragon.Shade(
        "default_shade",
        0.5,
        0.4
    )
    
    def __init__(self, *args, blind:BlindType|None=None, **kwargs):
        
        self.blind = blind
        super().__init__(*args, **kwargs)
    
    """ fundamental properties
    """
    
    @property
    def blind(self) -> str:
        
        if isinstance(self.__blind, BlindType):
            return str(self.__blind)
        else:
            return self.__blind
    
    @blind.setter
    @validate_enum(BlindType, None)
    def blind(self, value:BlindType|None) -> None:
        if value is not None:
            self.__blind = BlindType(value)
        else:
            self.__blind = value
    
    @Fenestration.construction.setter
    def construction(self, value:FenestrationConstruction) -> None:
        
        if not value.is_transparent:
            raise ValueError(
                f"Construction for an {type(self)} should be transparent"
            )
        
        else:
            self._Fenestration__construction = value
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace,
        fenestration_construction_dict:dict[str, FenestrationConstruction]
        ) -> Window:
        
        return Window(
            input.name,
            input.area,
            fenestration_construction_dict[input.construction_id],
            blind=getattr(input, "blind", None),
            ID   =input.id
        )
    
    def to_dragon(self,
        glazing_dict  :dict[str, dragon.Glazing]) -> dragon.Window:
        
        match self.blind:
            case None:
                blind = None
            case BlindType.SHADE:
                blind = Window.dragonized_shade
            case BlindType.VENETIAN:
                blind = Window.dragonized_blind
            
        return dragon.Window(
            self.ID,
            glazing_dict[self.construction.ID],
            self.area,
            blind   ,
        )

    
class Door(Fenestration):
    
    """ fundamental properties
    """
    
    @Fenestration.construction.setter
    def construction(self, value:FenestrationConstruction) -> None:
        
        if value.is_transparent:
            raise ValueError(
                f"Construction for an {type(self)} should be not transparent"
            )
            
        else:
            self._Fenestration__construction = value
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace,
        fenestration_construction_dict:dict[str, FenestrationConstruction]
        ) -> Door:
        
        return Door(
            input.name,
            input.area,
            fenestration_construction_dict[input.construction_id],
            ID   =input.id
        )
    
    def to_dragon(self,
        nomass_construction_dict:dict[str, dragon.NoMassConstruction]
        ) -> dragon.Door:
        
        return dragon.Door(
            self.ID,
            nomass_construction_dict[self.construction.ID],
            self.area
        )


class GlassDoor(Window):
    """ is identital to the Window class """
    pass
    
# ---------------------------------------------------------------------------- #
#                                     ZONE                                     #
# ---------------------------------------------------------------------------- #

class Zone:
    
    def __init__(
        self,
        name    :str,
        height  :int|float,
        surfaces:list[Surface],
        profile :Profile,
        light_density:int|float,
        infiltration :int|float|None=None,
        heating_supply_system:SupplySystem=None,
        cooling_supply_system:SupplySystem=None,
        ventilation_system   :VentilationSystem=None,
        *,
        floor:int|None=None,
        ID:str|None = None
        ) -> None:
        
        # user property
        self.name   = name
        
        # fundamental properties
        self.floor  = floor
        self.height = height
        self.surface = surfaces
        self.profile = profile
        self.light_density = light_density
        self.infiltration  = infiltration
        self.heating_supply = heating_supply_system
        self.cooling_supply = cooling_supply_system
        self.ventilation_system    = ventilation_system
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.ZONE}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ fundamental properties
    """
    
    @property
    def height(self) -> int|float:
        return self.__height
    
    @height.setter
    @validate_range(min=math.nextafter(0,math.inf))
    def height(self, value: int|float) -> None:
        self.__height = value
    
    @property
    def heating_supply(self) -> SupplySystem:
        return self.__heating_supply
    
    @heating_supply.setter
    @validate_type(SupplySystem, allow_none=True)
    def heating_supply(self, value:SupplySystem) -> None:
        
        if (value is not None) and (not value.heatable):
            raise ValueError(
                f"Tried to set non-heatable supply system {value.name} ({type(value)}) as heating_supply for zone {self.name}"
            )
            
        self.__heating_supply = value
    
    @property
    def cooling_supply(self) -> SupplySystem:
        return self.__cooling_supply
    
    @cooling_supply.setter
    @validate_type(SupplySystem, allow_none=True)
    def cooling_supply(self, value:SupplySystem) -> None:
        
        if (value is not None) and (not value.coolable):
            raise ValueError(
                f"Tried to set non-coolable supply system {value.name} ({type(value)}) as cooling_supply for zone {self.name}"
            )
            
        self.__cooling_supply = value
    
    """ useful methods
    """
    
    @property
    def area(self) -> int|float:
        return sum(surface.area for surface in self.surface if surface.type == str(SurfaceType.FLOOR))
    
    def get_unique_fenestration_constructions(self) -> dict[str, FenestrationConstruction]:
        
        return {
            k: v
            for surface in self.surface
            for k, v in surface.get_unique_fenestration_constructions().items()
        }
    
    def get_unique_surface_constructions(self) -> dict[str, SurfaceConstruction]:
        
        return {
            surface.construction.ID: surface.construction
            for surface in self.surface
        }
    
    def get_unique_materials(self) -> dict[str, Material]:
        
        return {
            k:v
            for construction in self.get_unique_surface_constructions().values()
            for k,v in construction.get_unique_materials().items()
        }
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
        
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace,
        surface_construction_dict     :dict[str, SurfaceConstruction],
        fenestration_construction_dict:dict[str, FenestrationConstruction],
        supply_system_dict     :dict[str, SupplySystem     ],
        ventilation_system_dict:dict[str, VentilationSystem],
        ) -> Zone:
        
        return Zone(
            input.name,
            input.height,
            [Surface.from_json(surf_input, surface_construction_dict, fenestration_construction_dict) for surf_input in input.surfaces],
            Profile._DB[input.profile],
            input.light_density,
            input.infiltration,
            supply_system_dict.get(input.supply_system_heating_id),
            supply_system_dict.get(input.supply_system_cooling_id),
            ventilation_system_dict.get(input.ventilation_system_id),
            ID=input.id
        )
        
    def to_dragon(self,
        ) -> None:
        
        raise NotImplementedError(
            f"이거 쓰지 마세요"
        )