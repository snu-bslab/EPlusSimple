
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import math
from copy     import deepcopy
from types    import SimpleNamespace
from datetime import datetime
from typing   import Literal

# third-party modules
import pandas as pd

# local modules
from idragon import (
    dragon,
)
from idragon.dragon import (
    SurfaceType             ,
    SurfaceBoundaryCondition,
)
from idragon.utils import (
    validate_type ,
    validate_range,
    validate_enum ,
)
from ..constants import (
    Unit,
    ConvectionHeatTransfer,
    Directory ,
    SpecialTag,
    AUTOID_PREFIX ,
)

# ---------------------------------------------------------------------------- #
#                            CONSTRUCTION COMPONENTS                           #
# ---------------------------------------------------------------------------- #

class Material:
    
    _DB_filepath = Directory.CONSTRUCTION_DIR / "material.csv"
    _DB = {}
    
    def __init__(self,
        name:str,
        conductivity :int|float,
        density      :int|float,
        specific_heat:int|float,
        *,
        ID:str|None=None
        ) -> None:
        
        # user properties
        self.name=name
        
        # fundamental properties
        self.conductivity =conductivity
        self.density      =density
        self.specific_heat=specific_heat
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.MATERIAL}AUTOID{hex(id(self))}"
        self.__ID = ID
        
    """ fundamental properties
    """
    
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
        
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
        
    def __eq__(self, other:Material) -> bool:
        
        # type validation
        if not isinstance(other, Material):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
        
        # two materials are equal if thermal properties are equal
        return (self.conductivity  == other.conductivity ) and\
               (self.density       == other.density      ) and\
               (self.specific_heat == other.specific_heat)
        
    """ in-out
    """
        
    @staticmethod
    def from_json(
        input:SimpleNamespace
        ) -> Material:
        
        return Material(
            input.name,
            input.conductivity ,
            input.density      ,
            input.specific_heat,
            ID=input.id
        )
    
    def to_dragon(self) -> dragon.Material:
        
        return dragon.Material(
            self.ID,
            self.conductivity ,
            self.density      ,
            self.specific_heat,
        )    
    
    @staticmethod
    def load_DB() -> None:
        
        # load dataframe from csv file
        df_material = pd.read_csv(Material._DB_filepath)
        df_material.set_index("name", inplace=True)
        
        # set the database
        Material._DB = {
            row.name: Material(
                row.name,
                row["conductivity"] ,
                row["density"]      ,
                row["heat_capacity"],
                ID = f"{SpecialTag.DB}{row.name}"
            )
            for _, row in df_material.iterrows()
        }
    
    @staticmethod
    def get_DB(
        key:str,
        *,
        as_dict:bool=False
        ) -> Material|list[Material]|str|dict:
        
        # special key for stable DB operation
        if key is None:
            return None
        
        # special key to get path of the database
        if key == "__path__":
            return str(Material._DB_filepath)
        
        # special key to get all items in the database
        if key == "__all__":
            return [
                Material.get_DB(_key, as_dict=as_dict)
                for _key in Material._DB.keys()
            ]
        
        #check if the key is a valid item name
        if key not in Material._DB.keys():
            raise KeyError(
                f"{key} is not a valid key of the Material DB"
            )
        
        #return the material
        else:
            material =  Material._DB[key]
        
        # convert the object to a dictionary if required
        if not as_dict:
            return material
        else:
            return material.to_dict()
        
    """ representation
    """
        
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "conductivity" :self.conductivity,
            "density"      :self.density,
            "specific_heat":self.specific_heat
        }
        
    def __str__(self) -> str:
        return f"Material {self.name} (ID={self.ID}): k={self.conductivity:.1f}W/mK, rho={self.density:.1f}kg/m3, Cp={self.specific_heat:.1f}J/kgK"
    
    def __repr__(self) -> str:
        return f"<Material {self.name} (ID={self.ID}) at {hex(id(self))}>"
    

class SurfaceConstruction:
    
    _DB_filepath = Directory.CONSTRUCTION_DIR / "construction_regulation_surface.csv"
    _DB = {}
    
    def __init__(self,
        name:str,
        *args:Material|int|float,
        ID:str|None=None,
        vintage_layer_position: Literal["inside","outside"]|None=None,
        ) -> None:
        
        # user properties
        self.name = name
        
        # parse arguments
        materials   = args[ ::2]
        thicknesses = args[1::2]
        
        # type and order validation
        # arguments must be ordered in material-numeric-material-numeric-...
        if (
            (len(args)%2 != 0) or\
            any(not isinstance(arg, Material)  for arg in materials  ) or\
            any(not isinstance(arg, int|float) for arg in thicknesses)
            ):
            
            raise ValueError(
                f"Construction requires material-thickness pairs."
            )
        
        # set layer property
        self.layers = [
            [material, thickness]
            for material, thickness in zip(materials, thicknesses)
            if thickness > 0
        ]
        self.vintage_layer_position = vintage_layer_position

        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.SURFACE_CONSTRUCTION}AUTOID{hex(id(self))}"
        self.__ID = ID
        
    """ fundamental properties
    """
    
    @property
    def U_internal(self) -> int|float:
        return 1/sum(thickness/material.conductivity for material, thickness in self.layers)
    
    @property
    def depth(self) -> int|float:
        return sum(thickness for _, thickness in self.layers)
    
    @property
    def heat_capacity(self) -> int|float:
        return sum(material.density*material.specific_heat*thickness for material, thickness in self.layers)
    
    @property
    def vintage_layer_position(self) -> str | None:
        return self.__vintage_layer_position


    @vintage_layer_position.setter
    @validate_enum("inside","outside", None)
    def vintage_layer_position(self, value: str | None) -> None:
        self.__vintage_layer_position = value
    
    """ useful methods
    """
    
    def get_U(self,
        h_in :int|float=ConvectionHeatTransfer.IN ,
        h_out:int|float=ConvectionHeatTransfer.OUT,
        ) -> int|float:
        
        """ calculate U-value considering surface heat transfer

        Args
        ----
        h_in  (int|float, default=1/0.110= 9.09)
            * interior surface heat transfer coefficient [W/m2K]
            * default: 거실의 실내표면열전달저항 (건축물의 에너지절약설계기준 [별표 5])
        h_out (int|float, default=1/0.043=23.26)
            * exterior surface heat transfer coefficient [W/m2K]
            * default: 거실의 실외(직접외기)표면열전달저항 (건축물의 에너지절약설계기준 [별표 5])
        
        Returns
        -------
        int|float
            * U-value [W/m2K]
        """
        
        return 1/(1/h_in + 1/h_out + 1/self.U_internal)
    
    def get_unique_materials(self) -> dict[str, Material]:
        
        """ returns unique dictionary of materials in the construction
            * key   : the 'ID' of the material
            * value : the material instance
        """
        
        return {
            material.ID: material
            for material, thickness in self.layers
        }
    
    @classmethod
    def create_simply(cls,
        name:str      ,
        U   :int|float,
        *,
        h_in :int|float=ConvectionHeatTransfer.IN ,
        h_out:int|float=ConvectionHeatTransfer.OUT,
        concrete_thickness:int|float=0.19,
        ID:str|None=None
        ) -> SurfaceConstruction:
        
        """ create simple (two-layer) construction given U-value
            * if given U is too large not to use insulation, concrete thickness could be adjusted
            * layers: inside-concrete-insulation-outside
        
        Args
        ----
        name (str)
            * name of the created construction
        U (int|float)
            * U-value [W/m2K]
            * should be smaller than zero-thickness wall (with default h_in & h_out: 6.54 W/m2K)
        h_in  (int|float, default=1/0.11 = 9.09)
            * interior surface heat transfer coefficient [W/m2K]
            * default: 거실의 실내표면열전달저항 (건축물의 에너지절약설계기준 [별표 5])
        h_out (int|float, default=1/0.043=23.26)
            * exterior surface heat transfer coefficient [W/m2K]
            * default: 거실의 실외(직접외기)표면열전달저항 (건축물의 에너지절약설계기준 [별표 5])
        concrete_thickness (int|float, default=0.19)
            * concrete layer thickness [m]
            * could be decreased if the given U is too large        
            * default: 내력벽의 두께 (2층이상, 건축물의 구조기준 등에 관한 규칙 제32조 제2항)
        """
        
        # calculate maximum U-value given h_in & h_out
        U_maximum = 1/(1/h_in + 1/h_out)
        
        # raise an exception if the given U-value is too large
        if U >= U_maximum:
            raise ValueError(
                f"U-value should be smaller than {U_maximum:.3f}W/m2K,"
                f" given h_in({h_in:.3f}W/m2K) and h_out({h_out:.3f}W/m2K)"
            )
        
        # default materials to construct simple wall construction
        insulation = Material.get_DB(str("insulation"))
        concrete   = Material.get_DB(str("concrete"))
        
        # calculate the thickness of insulation layer
        insulation_thickness = insulation.conductivity * (1/U - 1/h_in - 1/h_out - concrete_thickness/concrete.conductivity)
        
        # if U-value is too large not to use the insulation,
        # adjust the concrete layer
        if insulation_thickness < 0:
            insulation_thickness = 0
            concrete_thickness   = concrete.conductivity * (1/U - 1/h_in - 1/h_out)
        
        # create a construction
        return SurfaceConstruction(
            name,
            concrete  , concrete_thickness/2,
            insulation, insulation_thickness,
            concrete  , concrete_thickness/2,
            ID=ID,
        )    
        
    def reversed(self) -> SurfaceConstruction:
        
        match self.vintage_layer_position:
            case "inside":
                reversed_vintage_layer_position = "outside"
            case "outside":
                reversed_vintage_layer_position = "inside"
            case None:
                reversed_vintage_layer_position = None
        
        return SurfaceConstruction(
            self.name + "_reversed",
            *sum(self.layers[::-1],start=[]),
            ID=f"{SpecialTag.FLIP}{self.ID}",
            vintage_layer_position=reversed_vintage_layer_position
        )
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
        
    def __eq__(self, other:SurfaceConstruction) -> bool:
        
        # type validation
        if not isinstance(other, SurfaceConstruction):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
        
        # two constructions are equal if all layers have same material and thickness
        return (len(self.layers) == len(other.layers)) and\
               all(
                   (self_layer[0] == other_layer[0]) and (self_layer[1] == other_layer[1])
                   for self_layer, other_layer in zip(self.layers, other.layers)
                ) and\
                self.vintage_layer_position == other.vintage_layer_position
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace,
        material_dict:dict[str, Material]
        ) -> SurfaceConstruction:
        
        return SurfaceConstruction(
            input.name,
            *sum(
                [[material_dict[layer.material_id], layer.thickness] for layer in input.layers],
                start=[]
            ),
            ID=input.id,
            vintage_layer_position=input.vintage_layer_position,
        )
            
    def to_dragon(self,
        *,
        material_dict:dict[str, dragon.Material]=dict()
        ) -> dragon.Construction:
        
        # create dradon material object
        # note that given material dict is not changed
        material_dict = deepcopy(material_dict)
        for ID, material in self.get_unique_materials().items():
            if ID not in material_dict.keys():
                material_dict[ID] = material.to_dragon()
        
        # create a dragon-construction 
        return dragon.Construction(
            self.ID,
            *[
                dragon.Layer(f"{material.ID}_{thickness*Unit.M_TO_MM}mm", material_dict[material.ID], thickness)
                for material, thickness in self.layers
            ]
        )
    
    @staticmethod
    def load_DB() -> None:
        
        # load dataframe from csv file
        df_surface_construction = pd.read_csv(SurfaceConstruction._DB_filepath)
        df_surface_construction["시행일자"] = df_surface_construction["시행일자"].map(lambda v: str(v))
        df_surface_construction.set_index(["시행일자","부위","외기조건","용도","지역"], inplace=True)
        
        # set the database
        SurfaceConstruction._DB = {
            (row.name): SurfaceConstruction.create_simply(
                "&".join(row.name),
                float(row["열관류율"]),
                ID = f"{SpecialTag.DB}{'&'.join(row.name)}"
            )
            for _, row in df_surface_construction.iterrows()
        }
        SurfaceConstruction.REGULATION_DATES = [
            datetime.strptime(datestr, r"%Y%m%d")
            for datestr in sorted(set(df_surface_construction.index.get_level_values("시행일자")))
        ]
    
    @staticmethod
    def get_DB(
        key:str,
        *,
        as_dict:bool=False
        ) -> SurfaceConstruction|list[SurfaceConstruction]|str|dict:
        
        # special key for stable DB operation
        if key is None:
            return None
        
        # special key to get path of the database
        if key == "__path__":
            return str(SurfaceConstruction._DB_filepath)
        
        # special key to get all item in the database
        if key == "__all__":
            return [
                SurfaceConstruction.get_DB(_key, as_dict=as_dict)
                for _key in SurfaceConstruction._DB.keys()
            ]
        
        # check if the key is a valid item name
        if key not in SurfaceConstruction._DB.keys():
            raise KeyError(
                f"{key} is not a valid key of the SurfaceConstruction DB"
            )
        
        # return the construction
        else:
            construction =  SurfaceConstruction._DB[key]
        
        # convert the object to a dictionary if required
        if not as_dict:
            return construction
        else:
            return construction.to_dict()
    
    @staticmethod
    def get_regulation_key(
        vintage      :datetime ,
        surface_type :SurfaceType,
        boundary_cond:SurfaceBoundaryCondition,
        climate      :str        ,
        *,
        is_radiant_floor      :bool=False,
        is_multifamily_housing:bool=False,
        ) -> tuple[str, str, str, str, str]:
        
        """ get the regulation DB key of the construction applied to a surface
            * key: (시행일자, 부위, 외기조건, 용도, 지역)
            * the part (부위) is determined by the surface type and boundary condition
        """
        
        # type regulation
        surface_type  = SurfaceType(surface_type)
        boundary_cond = SurfaceBoundaryCondition(boundary_cond)
        
        # date
        regulation_date = max(date for date in SurfaceConstruction.REGULATION_DATES if date <= vintage)
        
        # part
        match surface_type:
            case SurfaceType.WALL   :
                    part = "외벽"
            case SurfaceType.CEILING:
                if boundary_cond is SurfaceBoundaryCondition.OUTDOOR:
                    part = "최상층 지붕"
                else:
                    if is_radiant_floor:
                        part = "바닥난방인 층간바닥"
                    else:
                        part = "바닥난방이 아닌 층간바닥"
            case SurfaceType.FLOOR  :
                if (boundary_cond is SurfaceBoundaryCondition.OUTDOOR) or (boundary_cond is SurfaceBoundaryCondition.GROUND):
                    if is_radiant_floor:
                        part = "바닥난방인 최하층 바닥"
                    else:
                        part = "바닥난방이 아닌 최하층 바닥"
                else:
                    if is_radiant_floor:
                        part = "바닥난방인 층간바닥"
                    else:
                        part = "바닥난방이 아닌 층간바닥"
        
        # usage
        if is_multifamily_housing:
            usage = "공동주택"
        else:
            usage = "공동주택 외"
        
        return (regulation_date.strftime(r"%Y%m%d"), part, "외기 직접", usage, climate)
    
    @staticmethod
    def get_regulated_construction(
        vintage      :datetime ,
        surface_type :SurfaceType,
        boundary_cond:SurfaceBoundaryCondition,
        climate      :str        ,
        *,
        is_radiant_floor      :bool=False,
        is_multifamily_housing:bool=False,
        ) -> SurfaceConstruction:
        
        """ get the regulated construction applied to a surface
            * see get_regulation_key for the key determination
        """
        
        return SurfaceConstruction.get_DB(
            SurfaceConstruction.get_regulation_key(
                vintage      ,
                surface_type ,
                boundary_cond,
                climate      ,
                is_radiant_floor      =is_radiant_floor      ,
                is_multifamily_housing=is_multifamily_housing,
            )
        )
    
    @classmethod
    def create_default_innerwall(cls) -> SurfaceConstruction:
        
        """ create the default construction for an interior wall
            whose construction is unknown
            * layers: gypsumboard 12.5mm - glasswool 50mm - gypsumboard 12.5mm
        """
        
        return cls(
            f"{SpecialTag.SPECIAL}DefaultInnerWallConstruction",
            Material.get_DB("gypsumboard"), 0.0125, 
            Material.get_DB("glasswool")  , 0.0500,
            Material.get_DB("gypsumboard"), 0.0125,
        )
    
    """ representation
    """
    
    def to_dict(self) -> dict:
        
        return {
            "name"  : self.name,
            "layers": [
                {
                    "material" : material.name,
                    "thickness": thickness,
                }
                for material, thickness in self.layers
            ],
            "materials":[
                material.to_dict()
                for material in self.get_unique_materials().values()
            ],
            "vintage_layer_position": self.vintage_layer_position if self.vintage_layer_position is not None else "no_use"
        }
    
    def __str__(self) -> str:
        return f"Construction (for surface, {self.depth*Unit.M_TO_MM:.1f}mm) {self.name} (ID={self.ID}): U_int={self.U_internal:.2f}W/m2K, Cp={self.heat_capacity:.1f}J/m2K"
    
    def __repr__(self) -> str:
        return f"<Construction (for surface) {self.name} (ID={self.ID}) at {hex(id(self))}>"
    

class SpecialConstruction:

    # special constructions are singleton classes
    _instance = None    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    # special constructions do not contain any materials
    def get_unique_materials(self) -> dict[str, Material]:
        return {}
    
    # special constructions can't be reversed
    def reversed(self) -> SurfaceConstruction:
        return self

class OpenConstruction(SpecialConstruction):
    
    # ID for singleton instance
    ID = f"{SpecialTag.SPECIAL}{AUTOID_PREFIX.SURFACE_CONSTRUCTION}OPEN"
    
    # open construction is corresponding to the air-boundary with default ACH
    def to_dragon(self, *, material_dict:dict[str, dragon.Material]=dict()) -> dragon.AirBoundary:
        return dragon.AirBoundary("DefaultAirBoundary")
    
    
class VintageConstruction(SpecialConstruction):
    
    # ID for singleton instance
    ID = f"{SpecialTag.SPECIAL}{AUTOID_PREFIX.SURFACE_CONSTRUCTION}VINTAGE_REGULATION"
    
    # unknown constructions cannot be converted to a dragon object
    # they must be resolved into a specific construction using regulation DB
    def to_dragon(self, *, material_dict:dict[str, dragon.Material]=dict()) -> None:
        return None


class CurrentConstruction(SpecialConstruction):

    _instance = None

    ID = f"{SpecialTag.SPECIAL}{AUTOID_PREFIX.SURFACE_CONSTRUCTION}CURRENT_REGULATION"

    def to_dragon(
        self,
        *,
        material_dict: dict[str, dragon.Material] = dict(),
    ) -> None:
        return None
    

class FenestrationConstruction:
    
    _DB_filepath = Directory.CONSTRUCTION_DIR / "construction_regulation_fenestration.csv"
    _DB = {}
    
    def __init__(
        self,
        name:str,
        u   :int|float     ,
        g   :int|float|None=None,
        *,
        ID:str|None=None
        ):
        
        self.name = name
        self.u = u
        self.g = g
        
        # set default ID if not specified
        if ID is None:
            ID = f"{AUTOID_PREFIX.FENESTRATION_CONSTRUCTION}AUTOID{hex(id(self))}"
        self.__ID = ID
    
    """ fundamental properties
    """
    
    @property
    def is_transparent(self) -> bool:
        return (self.g is not None) and (self.g > 0)
    
    @property
    def u(self) -> int|float:
        return self.__u
    
    @u.setter
    @validate_range(min=math.nextafter(0,math.inf))
    @validate_type(int, float)
    def u(self, value: int|float) -> None:
        self.__u = value
        
    @property
    def g(self) -> int|float:
        return self.__g
    
    @g.setter
    @validate_range(min=math.nextafter(0, math.inf), max=math.nextafter(1, -math.inf))
    @validate_type(int, float, allow_none=True)
    def g(self, value: int|float) -> None:
        self.__g = value
    
    """ identity and equality
    """
    
    @property
    def ID(self) -> str:
        return self.__ID
    
    def __hash__(self) -> int:
        return hash(self.ID)
        
    def __eq__(self, other:FenestrationConstruction) -> bool:
        
        # type validation
        if not isinstance(other, FenestrationConstruction):
            raise TypeError(
                f"Cannot compare {type(self)} instance with {type(other)} instance"
            )
        
        # two fenestration constructions are equal if thermal properties are equal
        return (self.u  == other.u) and\
               (self.g  == other.g)
    
    """ in-out
    """
    
    @staticmethod
    def from_json(
        input:SimpleNamespace
    ) -> FenestrationConstruction:
        
        if input.is_transparent:            
            return FenestrationConstruction(
                input.name,
                input.u   ,
                input.g   ,
                ID=input.id
            )
            
        else:
            return FenestrationConstruction(
                input.name,
                input.u   ,
                ID=input.id
            )
        
    def to_dragon(self) -> dragon.Construction:
        
        if self.is_transparent:
            return dragon.Glazing(
                self.ID,
                self.u ,
                self.g ,
            )
            
        else:
            return dragon.NoMassConstruction(
                self.ID,
                self.u ,
            )
    
    @staticmethod
    def load_DB() -> None:
        
        # load dataframe from csv file
        df_fenestration_construction = pd.read_csv(FenestrationConstruction._DB_filepath)
        df_fenestration_construction.set_index(["창개수","로이유리","아르곤","열교차단재","창틀","공기층"], inplace=True)
        
        # set the database
        FenestrationConstruction._DB = {
            (row.name): FenestrationConstruction(
                "&".join(row.name),
                float(row["열관류율"]),
                float(row["SHGC"]),
                ID = f"{SpecialTag.DB}{'&'.join(row.name)}"
            )
            for _, row in df_fenestration_construction.iterrows()
        }
    
    @staticmethod
    def get_DB(
        key:str,
        *,
        as_dict:bool=False
        ) -> FenestrationConstruction|list[FenestrationConstruction]|str|dict:
        
        # special key for stable DB operation
        if key is None:
            return None
        
        # special key to get path of the database
        if key == "__path__":
            return str(FenestrationConstruction._DB_filepath)
        
        # special key to get all item in the database
        if key == "__all__":
            return [
                FenestrationConstruction.get_DB(_key, as_dict=as_dict)
                for _key in FenestrationConstruction._DB.keys()
            ]
        
        # check if the key is a valid item name
        if key not in FenestrationConstruction._DB.keys():
            raise KeyError(
                f"{key} is not a valid key of the FenestrationConstruction DB"
            )
        
        # return the construction
        else:
            construction =  FenestrationConstruction._DB[key]
        
        # convert the object to a dictionary if required
        if not as_dict:
            return construction
        else:
            return construction.to_dict()
    
    """ representation
    """
    
    def to_dict(self) -> dict:
        
        return {
            "name"   : self.name,
            "U-value": self.u,
            "SHGC"   : self.g,
        }
    
    def __str__(self) -> str:
        return f"Construction (for fenestration) {self.name} (ID={self.ID}): U={self.u:.2f}W/m2K, SHGC={self.g:.2f}"
    
    def __repr__(self) -> str:
        return f"<Construction (for fenestration) {self.name} (ID={self.ID}) at {hex(id(self))}>"
        
        
# ---------------------------------------------------------------------------- #
#                      INITIALIZATION: LOAD CONSTRUCTIONS                      #
# ---------------------------------------------------------------------------- #

Material.load_DB()
SurfaceConstruction.load_DB()
FenestrationConstruction.load_DB()
