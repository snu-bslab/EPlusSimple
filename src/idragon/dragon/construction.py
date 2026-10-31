

# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import math
from enum   import Enum
from typing import (
    overload     ,
    TYPE_CHECKING,
)

# third-party modules

# local modules
from ..imugi import (
    IdfObject,
)
from ..utils import (
    validate_type ,
    validate_range,
    validate_enum ,
)

# settings
if TYPE_CHECKING:
    from .shape import Surface

# ---------------------------------------------------------------------------- #
#                                    CLASSES                                   #
# ---------------------------------------------------------------------------- #


class MaterialRoughness(str, Enum):
    
    VERYROUGH   ="VeryRough"
    ROUGH       ="Rough"
    MEDIUMROUGH ="MediumRough"
    MEDIUMSMOOTH="MediumSmooth"
    SMOOTH      ="Smooth"

    def __str__(self) -> str:
        return self.value
    
    
class Material:
    
    def __init__(self,
        name         :str      ,
        conductivity :int|float,
        density      :int|float,
        specific_heat:int|float,
        *,
        thermal_absorptance:int|float=0.9,
        solar_absorptance  :int|float=0.7,
        visible_absorptance:int|float=0.7,
        roughness          :MaterialRoughness=MaterialRoughness.ROUGH,
        ) -> None:
        
        self.name         =name
        self.roughness    =roughness
        self.conductivity =conductivity
        self.density      =density
        self.specific_heat=specific_heat
        self.thermal_absorptance =thermal_absorptance
        self.solar_absorptance   =solar_absorptance
        self.visible_absorptance =visible_absorptance
    
    """ fundamental properties
    """
    
    @property
    def roughness(self) -> int|float:
        return self.__roughness
    
    @roughness.setter
    @validate_enum(*list(MaterialRoughness))
    @validate_type(str, MaterialRoughness)
    def roughness(self, value: int|float) -> None:
        self.__roughness = MaterialRoughness(value)

    @property
    def conductivity(self) -> int|float:
        return self.__conductivity
    
    @conductivity.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float)
    def conductivity(self, value: int|float) -> None:
        self.__conductivity = value
        
    @property
    def density(self) -> int|float:
        return self.__density
    
    @density.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float)
    def density(self, value: int|float) -> None:
        self.__density = value
    
    @property
    def specific_heat(self) -> int|float:
        return self.__specific_heat
    
    @specific_heat.setter
    @validate_range(min=100)
    @validate_type(int, float)
    def specific_heat(self, value: int|float) -> None:
        self.__specific_heat = value
    
    @property
    def thermal_absorptance(self) -> int|float:
        return self.__thermal_absorptance
    
    @thermal_absorptance.setter
    @validate_range(min=0, max=1)
    @validate_type(int, float)
    def thermal_absorptance(self, value: int|float) -> None:
        self.__thermal_absorptance = value
        
    @property
    def solar_absorptance(self) -> int|float:
        return self.__solar_absorptance
    
    @solar_absorptance.setter
    @validate_range(min=0, max=1)
    @validate_type(int, float)
    def solar_absorptance(self, value: int|float) -> None:
        self.__solar_absorptance = value
        
    @property
    def visible_absorptance(self) -> int|float:
        return self.__visible_absorptance
    
    @visible_absorptance.setter
    @validate_range(min=0, max=1)
    @validate_type(int, float)
    def visible_absorptance(self, value: int|float) -> None:
        self.__visible_absorptance = value
        
    
    def __eq__(self, other:Material) -> bool:
        
        if not isinstance(other, Material):
            raise TypeError(
                f"Cannot compare Material with {type(other)}"
            )
            
        return all(getattr(self, attr) == getattr(other, attr) for attr in ["name","conductivity","density","specific_heat"])

class Layer:

    def __init__(self,
        name     :str      ,
        material :Material ,
        thickness:int|float,
        ) -> None:
        
        self.name      = name
        self.material  = material
        self.thickness = thickness # m
    
    @property
    def material(self) -> Material:
        return self.__material
    
    @material.setter
    @validate_type(Material)
    def material(self, value:Material) -> None:
        self.__material = value
        
    @property
    def thickness(self) -> int|float:
        return self.__thickness
    
    @thickness.setter
    @validate_type(int, float)
    @validate_range(min=math.nextafter(0.003,math.inf))
    def thickness(self, value:int|float) -> None:
        self.__thickness = value
    
    @property
    def U(self) -> float: # W/m2K
        return self.material.conductivity / self.thickness
    
    @property
    def heat_capacity(self) -> float: # J/m2K
        return self.material.specific_heat * self.material.density * self.thickness
    
    def to_idf_object(self) -> IdfObject:
        
        return IdfObject(
            "Material",
            [
                self.name                   ,
                str(self.material.roughness),
                self.thickness              ,
                self.material.conductivity  ,
                self.material.density       ,
                self.material.specific_heat ,
                self.material.thermal_absorptance,
                self.material.solar_absorptance  ,
                self.material.visible_absorptance,
            ]
        )
    
    def __eq__(self, other:Layer):
        return (self.material == other.material) and (self.thickness==other.thickness)

    def __hash__(self):
        return hash(self.name)
    
class Construction:
    
    @overload
    def __init__(self, name:str, *args:Material|int|float): ...
    
    @overload
    def __init__(self, name:str, *args:Layer): ...
    
    def __init__(self, name, *args):
        
        self.name = name
        
        if all(isinstance(arg, Layer) for arg in args):
            self.layers = list(args)
            
        elif len(args)%2 == 0:
            
            if not (all(isinstance(arg, Material) for arg in args[::2]) and all(isinstance(arg, int|float) for arg in args[1::2])):
                raise TypeError(
                    f"Invalid arguments for Construction: {args}"
                )
            
            self.layers = [
                Layer(f"{material.name}_{int(thickness*1E3)}mm", material, thickness) 
                for material, thickness in zip(args[::2], args[1::2])
                ]
            
        else:
            raise ValueError(
                f"Invalid arguments for Construction: {args}"
            )
    
    @property
    def thickness(self) -> float: # m
        return sum(layer.thickness for layer in self.layers)
        
    @property 
    def U(self) -> float: # W/m2K
        return 1/sum(1/layer.U for layer in self.layers)
    
    @property
    def heat_capacity(self) -> float: # J/m2
        return sum(layer.heat_capacity for layer in self.layers)
    
    def reversed(self, name:str=None) -> Construction:
        if name is None:
            name = self.name + "_reversed"
        return Construction(name, *self.layers[::-1])
    
    def to_idf_object(self, surface:Surface):
        
        idf_object_construction = IdfObject("Construction",
            [f"{self.name}:for:{surface.name}"] + [layer.name for layer in self.layers]
        )
        
        return [idf_object_construction]
    
    def __eq__(self, other:Construction) -> bool:
        return (self.name == other.name) and (len(self.layers) == len(other.layers)) and all(self.layers[idx] == other.layers[idx] for idx in range(len(self.layers)))
    
    def __hash__(self):
        return hash(self.name)

class AirBoundary:
    
    def __init__(self,
        name:str,
        ACH :int|float|None=0.5
        ) -> None:
        
        self.name = name
        self.ACH  = ACH
        
    """ idf
    """
    
    def to_idf_object(self) -> IdfObject:
        
        return [
            IdfObject("Construction:AirBoundary", [
                self.name     ,
                "SimpleMixing",
                self.ACH      ,
            ])
        ]
        
    """ representation
    """
    
    def __str__(self) -> str:
        return f"Air Boundary {self.name} with ACH={self.ACH}"
    
    def __repr__(self) -> str:
        return f"<AirBoundary {self.name} at {hex(id(self))}>"
        

class Glazing:
    
    def __init__(self,
        name  :str,
        U:int|float,
        G:int|float,
        ) -> None:
        
        self.name = name
        self.U = U
        self.G = G
    
    """ fundamental properties
    """
    
    @property
    def U(self) -> int|float:
        return self.__U
    
    @U.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float)
    def U(self, value: int|float) -> None:
        self.__U = value
        
    @property
    def G(self) -> int|float:
        return self.__G
    
    @G.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float)
    def G(self, value: int|float) -> None:
        self.__G = value
    
    """ idf
    """
        
    def to_idf_object(self):
        
        name_for_material = f"$GLAZING_FOR${self.name}"        
        
        return [
            IdfObject("WindowMaterial:SimpleGlazingSystem", [
                name_for_material,
                self.U   ,
                self.G   ,
            ]),
            IdfObject("Construction",[
                self.name        ,
                name_for_material,
            ])
        ]
        
    """ representation
    """
    
    def __str__(self) -> str:
        return f"Glazing {self.name} (U={self.U:.2f}W/m2K, G={self.G:.3f})"
    
    def __repr__(self) -> str:
        return f"<Glazing {self.name} at {hex(id(self))}>"
    
    
class NoMassConstruction:
    
    def __init__(self,
        name:str,
        U   :int|float,
        ) -> None:
        
        self.name = name
        self.U = U
    
    """ fundamental properties
    """
    
    @property
    def U(self) -> int|float:
        return self.__U
    
    @U.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float)
    def U(self, value: int|float) -> None:
        self.__U = value
    
    """ idf
    """  
        
    def to_idf_object(self):
        
        name_for_material = f"$MaterialFor$_{self.name}"
        
        return [
            IdfObject("Material:NoMass", [
                name_for_material      ,
                MaterialRoughness.ROUGH,
                1/self.U               ,
            ]),
            IdfObject("Construction", [
                self.name        ,
                name_for_material,
            ])
        ]
        
    """ representation
    """
    
    def __str__(self) -> str:
        return f"No-mass construction {self.name} (U={self.U:.2f}W/m2K)"
    
    def __repr__(self) -> str:
        return f"<NoMassConstruction {self.name} at {hex(id(self))}>"
    
    
    
    
    
    
    
    
    
    
    
    
    
    
