
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import math
from abc  import ABC
from enum import Enum
from copy import deepcopy

# third-party modules

# local modules
from ..imugi import (
    # classes
    IdfObject,
)
from ..utils import (
    validate_type ,
)
from .construction import (
    Construction      ,
    Glazing           ,
    NoMassConstruction,
)
from .profile import (
    Schedule,
    ScheduleType,
)
from .hvac import (
    SupplySystem,
)
from ..constants import Unit

# ---------------------------------------------------------------------------- #
#                                    CLASSES                                   #
# ---------------------------------------------------------------------------- #

class Vertex:
    """ 3-dimensional vertex / vector
    """
    
    def __init__(self,
        x:int|float=0,
        y:int|float=0,
        z:int|float=0,
        ) -> None:
        """ Create a vertex instance
        
        Args
        ----
            x (int|float): 1st coordinate. Default to 0
            y (int|float): 2nd coordinate. Default to 0
            z (int|float): 3rd coordinate. Default to 0
            
        Examples
        --------
            >>> pt = Vertex(3,4,5)
            >>> print(pt)
            (3,4,5)
            >>> pt = Vertex(3,4)
            >>> print(pt)
            (3,4,0)
            >>> pt = Vertex(z=4)
            >>> print(pt)
            (0,0,4)
        """
        
        self.x = x
        self.y = y
        self.z = z
        
        return
    
    """ fundamental properties
    """
    
    @property
    def x(self) -> int|float:
        return self.__x
    
    @x.setter
    @validate_type(int, float)
    def x(self, value:int|float) -> None:
        self.__x = value
        
    @property
    def y(self) -> int|float:
        return self.__y
    
    @y.setter
    @validate_type(int, float)
    def y(self, value:int|float) -> None:
        self.__y = value
        
    @property
    def z(self) -> int|float:
        return self.__z
    
    @z.setter
    @validate_type(int, float)
    def z(self, value:int|float) -> None:
        self.__z = value
    
    
    """ numeric properties
    """
    
    @property
    def norm(self):
        return (self.x**2 + self.y**2 + self.z**2)**(1/2)
    
    @property
    def unit(self):
        
        if self.norm == 0:
            return Vertex(0,0,0)
        else:
            return self/self.norm
    
    def distance(self, other:Vertex) -> float:
        return (self - other).norm
    
    """ vector calculations
    """
    
    def dot(self, other:Vertex) -> int|float:
        return self.x*other.x + self.y*other.y + self.z*other.z
    
    def cross(self, other:Vertex) -> Vertex:
        return Vertex(
            self.y*other.z - self.z*other.y,
            self.z*other.x - self.x*other.z,
            self.x*other.y - self.y*other.x,
            )
    
    def __add__(self, other:Vertex|int) -> Vertex:
        
        # for 'sum' method, allow adding a vertex to 0
        if not isinstance(other, Vertex) and (other == 0):
            return deepcopy(self)
        
        return Vertex(self.x+other.x, self.y+other.y, self.z+other.z)
    
    def __radd__(self, other:Vertex|int) -> Vertex:
        return self.__add__(other)
    
    def __sub__(self, other:Vertex) -> Vertex:
        return self.__add__(other.__mul__(-1))
    
    def __mul__(self, value:int|float) -> Vertex:
        return Vertex(self.x*value, self.y*value, self.z*value)
    
    def __rmul__(self, value:int|float) -> Vertex:
        return self.__mul__(value)
    
    def __truediv__(self, value:int|float) -> Vertex:
        return Vertex(self.x/value, self.y/value, self.z/value)
    
    def __eq__(self, other:Vertex) -> bool:
        return math.isclose(self.x, other.x) and math.isclose(self.y, other.y) and math.isclose(self.z, other.z)
    
    """ advanced calculations
    """
    
    @classmethod
    def are_coplanar(cls, *args:Vertex) -> bool:
        """ check if all the vertex arguments are in one plane
        """
        
        # type check
        if not all(isinstance(item, Vertex) for item in args):
            raise TypeError(
                f"All arguments should be vertex instances"
            )
        
        # if less than 4 vertices are given,
        # they are always in a plane
        if len(args) <= 3:
            return True
        
        # calculate normal vector
        # a plane is defined by first 3 vertices with the normal vector and the first vertex
        normal = (args[1] - args[0]).cross(args[2]-args[0]).unit
        
        # if any of the other vertices are out of the plane,
        # the vertices are not in the one plane
        for point in args[3:]:
            if abs(normal.dot((point - args[0]).unit)) > 1E-15:
                return False
        
        return True
    
    """ additional methods
    """
    
    def __deepcopy__(self, memo) -> Vertex:
        
        copied = Vertex(self.x, self.y, self.z) 
        memo[id(self)] = copied
        
        return copied
    
    def __iter__(self):
        yield self.x
        yield self.y
        yield self.z
        
    """ printing
    """
    
    def __str__(self) -> str:
        return str(tuple(self))
    
    def __repr__(self) -> str:
        return f"<Vertex {self.x:.2f},{self.y:.2f},{self.z:.2f} at {hex(id(self))}>"


class SurfaceBoundaryCondition(str, Enum):
    """ Available boundary conditions for surface
    """
    
    OUTDOOR   = "outdoors"
    GROUND    = "ground"
    ADIABATIC = "adiabatic"
    ZONE      = "zone"
    
    def __str__(self) -> str:
        return self.value
    
class SurfaceType(str, Enum):
    
    WALL    = "wall"
    CEILING = "ceiling"
    FLOOR   = "floor"
    
    def __str__(self) -> str:
        return self.value
    
    
class Surface:
    """ 2D-surface for zone
    """
    
    def __init__(self,
        name        :str         ,
        type        :SurfaceType|str,
        construction:Construction,
        boundary    :str ,
        vertex      :list[Vertex],
        window      :list[Window]=[],
        door        :list[Door]  =[],
        ) -> None:
        
        self.name = name
        self.type = type
        self.construction =construction
        self.vertex       =vertex
        self.boundary     =boundary
        self.window = window
        self.door   = door
    
    """ fundamental properties
    """
    
    @property
    def type(self):
        return self.__surface_type
    
    @type.setter
    def type(self, value:str):
        self.__surface_type = SurfaceType(value)
    
    
    @property
    def boundary(self):
        if self.__adjacent is None:
            return self.__boundary
        else:
            return self.__adjacent
    
    @boundary.setter
    def boundary(self, value:str):
        
        if isinstance(value, Surface):
            
            self.__adjacent = value
            if value.boundary is not self:
                value.boundary = self
                
            self.__boundary = SurfaceBoundaryCondition.ZONE
            
        else:
            self.__adjacent = None
            self.__boundary = SurfaceBoundaryCondition(value)
    
    @property
    def adjacent(self):
        return self.__adjacent
    
    @property
    def vertex(self):
        return self.__vertex
    
    @vertex.setter
    def vertex(self, value:list[Vertex]):
        
        if not isinstance(value, list|tuple) or not all(isinstance(item, Vertex) for item in value):
            raise TypeError(
                f"All vertices should be Vertex instances"
            )
            
        if len(value) < 3:
            raise ValueError(
                f"3 or more vertices are requried to construct a surface. (currently {len(value)})"
            )
        
        if not Vertex.are_coplanar(*value):
            Vertex.are_coplanar(*value)
            raise ValueError(
                f"Vertices constructing a surface should be in a plane"
            )
        
        self.__vertex = tuple(value)
    
    """ dependent properties
    """
    
    @property
    def normal(self) -> Vertex:
        return(self.vertex[1]-self.vertex[0]).cross(self.vertex[2]-self.vertex[0]).unit   
    
    @property
    def area(self) -> float:
             
        S = sum([
            from_vert.cross(to_vert)
            for from_vert, to_vert in zip(list(self.vertex), list(self.vertex[1:]) + [self.vertex[0]])
            ])
        
        area = S.dot(self.normal) / 2
        
        return area
    
    @property
    def height(self) -> float:
        return max(vtx.z for vtx in self.vertex) - min(vtx.z for vtx in self.vertex)
    
    @property
    def center(self) -> Vertex:
        return sum(self.vertex)/len(self.vertex)
    
    @property
    def blinded_window(self) -> list[Window]:
        return [win for win in self.window if win.blind is not None]
    
    """ useful method
    """
    
    def get_subsurface(self, area:int|float) -> list[Vertex]:
        
        if area > self.area:
            raise ValueError(
                f"Tried to create subsurface whose area ({area:.3f}m2) is larger than that of the mother surface ({self.area:.3f}m2)"
            )
            
        scale_factor = area/self.area
        center       = self.center
        
        return [center + scale_factor*(vtx - center) for vtx in self.vertex]
        
    
    """ idf
    """
    
    def _get_fenestration_width_and_height(self, opening_area:int|float) -> tuple[float, float]:
        
        # for stable calculation, opening sizes are reduced
        SAFETY_FACTOR_FOR_OPENING_SIZE = 0.999
        SAFETY_MARGIN_FOR_OPENING_SIZE = 0.001
        
        height = (self.height - SAFETY_MARGIN_FOR_OPENING_SIZE)*SAFETY_FACTOR_FOR_OPENING_SIZE
        width  = opening_area/height * SAFETY_FACTOR_FOR_OPENING_SIZE
       
        
        return width, height
    
    def to_idf_object(self, zone:Zone) -> IdfObject:
        
        SAFETY_MARGIN_FOR_OPENING_SIZE = 0.001
        
        # window and door objects
        if isinstance(self.boundary, Surface):
            window_idfobjects = [
                IdfObject("Window:Interzone",[
                    win.name,
                    win.glazing.name,
                    self.name,
                    win_copied.name,
                    1,
                    SAFETY_MARGIN_FOR_OPENING_SIZE, SAFETY_MARGIN_FOR_OPENING_SIZE,
                    *self._get_fenestration_width_and_height(win.area)
                ])
                for win, win_copied in zip(self.window, self.boundary.window)
            ]
            door_idfobjects = [
                IdfObject("Door:Interzone",[
                    door.name,
                    door.construction.name,
                    self.name,
                    door_copied.name,
                    1,
                    SAFETY_MARGIN_FOR_OPENING_SIZE, SAFETY_MARGIN_FOR_OPENING_SIZE,
                    *self._get_fenestration_width_and_height(door.area)
                ])
                for door, door_copied in zip(self.door, self.boundary.door)
            ]
        else:
            window_idfobjects = [
                IdfObject("Window",[
                    win.name,
                    win.glazing.name,
                    self.name,
                    None,
                    1,
                    SAFETY_MARGIN_FOR_OPENING_SIZE, SAFETY_MARGIN_FOR_OPENING_SIZE,
                    *self._get_fenestration_width_and_height(win.area)
                ]) 
                for win in self.window
            ]
            door_idfobjects = [
                IdfObject("Door",[
                    door.name,
                    door.construction.name,
                    self.name,
                    1,
                    SAFETY_MARGIN_FOR_OPENING_SIZE, SAFETY_MARGIN_FOR_OPENING_SIZE,
                    *self._get_fenestration_width_and_height(door.area)
                ])
                for door in self.door
            ]       
        
        # shadings
        shade_objs = []
        for win in self.blinded_window:
            shade_objs += win.blind.to_idf_object()
            shade_objs.append(IdfObject("WindowShadingControl",{
                "Name": f"{win.name}:ShadingControl",
                "Zone Name": zone.name,
                "Shading Type": "InteriorBlind" if isinstance(win.blind, Blind) else "InteriorShade",
                "Shading Control Type": "OffNightAndOnDayIfCoolingAndHighSolarOnWindow",
                "Setpoint": 20,
                "Shading Device Material Name": win.blind.name,
                "Fenestration Surface 1 Name": win.name
            }))
        
        # surface type
        match self.type:
            case SurfaceType.FLOOR:
                surface_type = "Floor"
            case SurfaceType.WALL:
                surface_type = "Wall"
            case SurfaceType.CEILING:
                if self.boundary is SurfaceBoundaryCondition.OUTDOOR:
                    surface_type = "Roof"
                else:
                    surface_type = "Ceiling"
        
        # outside boundary condition
        if isinstance(self.boundary, Surface):
            outside_boundary_condition = "Surface"
        else:
            outside_boundary_condition = str(self.boundary)
        
        # sun and wind
        if self.boundary is SurfaceBoundaryCondition.OUTDOOR:
            sun_exposed  = "SunExposed"
            wind_exposed = "WindExposed"
        else:
            sun_exposed  = "NoSun"
            wind_exposed = "NoWind"
        
        surf_objs = [
            IdfObject("BuildingSurface:Detailed", {
                "Name"             : self.name,
                "Surface Type"     : surface_type,
                "Construction Name": f"{self.construction.name}:for:{self.name}" if isinstance(self.construction, Construction) else "DefaultAirBoundary",
                "Zone Name"        : zone.name,
                "Outside Boundary Condition"       : outside_boundary_condition,
                "Outside Boundary Condition Object": self.boundary.name if isinstance(self.boundary, Surface) else None,
                "Sun Exposure" : sun_exposed,
                "Wind Exposure": wind_exposed,
            }|{
                f"Vertex {idx+1:d} {base}-coordinate": value 
                for idx, vertex in enumerate(self.vertex)
                for base, value in zip(("X","Y","Z"), tuple(vertex))
            }),
        ]
        
        return window_idfobjects + door_idfobjects + shade_objs + surf_objs
    
    """ representation
    """
    
    def __str__(self) -> str:
        return f"{len(self.vertex)}-points polygon (area: {self.area}, normal: {self.normal})\n\t" +\
            "\n\t".join([f"{idx}th vertex {vertex}" for idx, vertex in enumerate(self.vertex)])

    def __repr__(self) -> str:
        return f"<{len(self.vertex)}-points polygon at {hex(id(self))}>"
    
    

class Window:
    
    def __init__(self,
        name   :str,
        glazing:Glazing  ,
        area   :int|float,
        blind  :Shading|None=None,
        ) -> None:
        
        self.name    = name
        self.glazing = glazing
        self.area    = area
        self.blind   = blind
        
        return

class Door:
    
    def __init__(self,
        name:str,
        construction:NoMassConstruction,
        area        :int|float,
        ) -> None:
        
        self.name         = name
        self.construction = construction
        self.area         = area
        
        return
    
class Shading(ABC):
    ...

class Blind(Shading):
    
    def __init__(self,
        name,
        slat_width       :int|float,
        slat_separation  :int|float,
        slat_angle       :int|float,
        front_reflectance:int|float,
        back_reflectance :int|float,
        ) -> None:
        
        # user properties
        self.name = name
        
        # thermal properties
        self.slat_width        = slat_width
        self.slat_separation   = slat_separation
        self.slat_angle        = slat_angle
        self.front_reflectance = front_reflectance
        self.back_reflectance  = back_reflectance
        
    def to_idf_object(self) -> IdfObject:
        
        return [IdfObject("WindowMaterial:Blind",{
            "Name": self.name,
            "Slat Width": self.slat_width,
            "Slat Separation": self.slat_separation,
            "Slat Angle": self.slat_angle,
            "Slat Beam Visible Transmittance" : 0.0,
            "Slat Diffuse Visible Transmittance": 0.0,
            "Front Side Slat Beam Solar Reflectance"   : self.front_reflectance,
            "Back Side Slat Beam Solar Reflectance"    : self.back_reflectance ,
            "Front Side Slat Diffuse Solar Reflectance": self.front_reflectance,
            "Back Side Slat Diffuse Solar Reflectance" : self.back_reflectance ,
        }, ignore_default=False)]

class Shade(Shading):
    
    def __init__(self,
        name:str,
        transmittance:int|float,
        reflectance  :int|float,
        ) -> None:
        
        # user properties
        self.name = name
        
        # thermal properties
        self.transmittance = transmittance
        self.reflectance   = reflectance
        
        
    def to_idf_object(self) -> IdfObject:
        
        return [IdfObject("WindowMaterial:Shade",{
            "Name": self.name,
            "Solar Transmittance"  : self.transmittance,
            "Solar Reflectance"    : self.reflectance  ,
            "Visible Transmittance": self.transmittance,
            "Visible Reflectance"  : self.reflectance  ,
            "Infrared Hemispherical Emissivity": 1-self.transmittance-self.reflectance,
            "Infrared Transmittance": self.transmittance,
            "Thickness"   : 0.01,
            "Conductivity": 100,
        }, ignore_default=False)]


class Zone:
    
    def __init__(self,
        name   ,
        surface,
        profile,
        infiltration,
        light_density,
        supply_cooling,
        supply_heating,
        ventilation   ,
        ):
        
        self.name = name
        self.surface= surface
        self.profile = profile
        self.infiltration = infiltration
        self.light_density = light_density
        self.cooling_supply = supply_cooling
        self.heating_supply = supply_heating
        self.ventilation    = ventilation
    
    @property
    def heating_supply(self):
        return self.__supply_heating
    
    @heating_supply.setter
    def heating_supply(self, value:SupplySystem|None):
        self.__supply_heating = value
        
    @property
    def cooling_supply(self):
        return self.__supply_cooling
    
    @cooling_supply.setter
    def cooling_supply(self, value:SupplySystem|None):
        self.__supply_cooling = value
        
    @property
    def is_conditioned(self):
        return ((self.heating_supply is not None) or (self.cooling_supply is not None)) and (self.profile.hvac_availability is not None)
    
    @property
    def floor_surface(self) -> list[Surface]:
        return [surface for surface in self.surface if surface.type is SurfaceType.FLOOR]
    
    @property
    def floor_area(self) -> int|float:
        return sum(surface.area for surface in self.floor_surface)
    
    
    """ idf-related naming rules
    """
    
    @property
    def idf_equipmentlistname(self) -> str:
        return f"EquipmentList_for_{self.name}"
    
    @property
    def idf_airinletnodelistname(self) -> str:
        return f"{self.name} Air InletNode List"
    
    @property
    def idf_airexhaustnodelistname(self) -> str:
        return f"{self.name} Air ExhaustNode List"
    
    """ idf-related
    """
    
    def to_idf_hvac_default_object(self) -> list[IdfObject]:
        
        if not self.is_conditioned:
            return []
        
        design_objs = [
            IdfObject("DesignSpecification:OutdoorAir",{
                "Name":f"DesignSpecificationOutdoorAir_for_{self.name}",
                "Outdoor Air Schedule Name": "ALLON",
            }, ignore_default=False),
            IdfObject("DesignSpecification:ZoneAirDistribution",{
                "Name": f"DesignSpecificationZoneAirDistribution_for_{self.name}"
            }, ignore_default=False),
            IdfObject("Sizing:Zone",{
                "Zone or ZoneList Name": self.name,
                "Zone Cooling Design Supply Air Temperature": 14,
                "Zone Cooling Design Supply Air Temperature Difference": 10,
                "Zone Heating Design Supply Air Temperature": 50,
                "Zone Heating Design Supply Air Temperature Difference": 10,
                "Zone Cooling Design Supply Air Humidity Ratio": 0.009,
                "Zone Heating Design Supply Air Humidity Ratio": 0.004,
                "Design Specification Outdoor Air Object Name": f"DesignSpecificationOutdoorAir_for_{self.name}",
                "Zone Heating Sizing Factor": 1.25,
                "Zone Cooling Sizing Factor": 1.15,
                "Design Specification Zone Air Distribution Object Name": f"DesignSpecificationZoneAirDistribution_for_{self.name}",
            }, ignore_default=False)   
        ]
        
        equipment_objs = [
            IdfObject("ZoneHVAC:EquipmentList",{
                "Name": f"EquipmentList_for_{self.name}",
            }),
            IdfObject("ZoneHVAC:EquipmentConnections",{
                "Zone Name": self.name,
                "Zone Conditioning Equipment List Name": f"EquipmentList_for_{self.name}",
                "Zone Air Node Name": f"{self.name} Zone Air Node"
            }),
        ]
        
        thermostat_objs = [
            IdfObject("Schedule:Constant", [
                f"ScheduleTypeForThermostat_for_{self.name}",
                None,
                4,
            ]),
            IdfObject("ThermostatSetpoint:DualSetpoint",[
                f"DualSetPoint_for_{self.name}",
                self.profile.heating_setpoint.name,
                self.profile.cooling_setpoint.name,
            ]),
            IdfObject("ZoneControl:Thermostat",[
                f"Thermostat_for_{self.name}",
                self.name,
                f"ScheduleTypeForThermostat_for_{self.name}",
                "ThermostatSetpoint:DualSetpoint",
                f"DualSetPoint_for_{self.name}",
            ])
        ]
        
        return design_objs + equipment_objs + thermostat_objs
    
    def to_idf_load_object(self) -> list[IdfObject]:
        
        # internal loads
        load_objs = []
        
        # light
        if isinstance(self.profile.lighting, Schedule):
            load_objs.append(IdfObject("Lights",[
                f"light:{self.name}",
                self.name,
                self.profile.lighting.name,
                "Watts/Area",
                None,
                self.light_density,
            ]))
            
        # electric equipment
        if isinstance(self.profile.equipment, Schedule):
            
            load_objs.append(
                self.profile.equipment.normalize_by_max(
                    new_name=self.profile.equipment.name + f"_normalized:for:{self.name}:equipment",
                ).to_idf_object()
            )
            
            load_objs.append(IdfObject("ElectricEquipment",[
                f"electric_equipment:{self.name}",
                self.name,
                self.profile.equipment.name + f"_normalized:for:{self.name}:equipment",
                "Watts/Area",
                None,
                self.profile.equipment.max,
            ]))
            
        # people
        if isinstance(self.profile.occupant, Schedule):
            
            load_objs.append(
                self.profile.occupant.normalize_by_max(
                    new_name=self.profile.occupant.name + f"_normalized:for:{self.name}:occupant",
                ).to_idf_object()
            )
            
            occupant_object = IdfObject("People",[
                f"people:{self.name}",
                self.name,
                self.profile.occupant.name + f"_normalized:for:{self.name}:occupant",
                "People/Area",
                None,
                self.profile.occupant.max,
            ])
            occupant_object["Activity Level Schedule Name"] = "$DEFAULT$PEOPLEACTIVITY"
            load_objs.append(occupant_object)
        
        # infiltration
        if self.infiltration > 0:
            load_objs.append(IdfObject("ZoneInfiltration:DesignFlowRate",[
                f"{self.name}:infiltration",
                self.name,
                "ALLON",
                "AirChanges/Hour",
                None, None, None ,
                self.infiltration,
            ]))
            
        # ventilation
        if self.profile.occupant is not None:
            
            BASE_VENTILATION_FLOW_PER_PERSON = 8.3 * Unit.L2M3
            
            if self.ventilation is None:
                load_objs.append(IdfObject("ZoneVentilation:DesignFlowRate",{
                    "Name": f"NaturalVentilation:{self.name}",
                    "Zone or ZoneList or Space or SpaceList Name": f"{self.name}",
                    "Design Flow Rate Calculation Method": "Flow/Person",
                    "Flow Rate per Person": BASE_VENTILATION_FLOW_PER_PERSON,
                }, ignore_default=False))
            
            else:
                
                overall_efficiency = (self.ventilation.heating_efficiency+self.ventilation.cooling_efficiency)/2
                
                load_objs.append(IdfObject("ZoneVentilation:DesignFlowRate",{
                    "Name": f"NaturalVentilation:{self.name}",
                    "Zone or ZoneList or Space or SpaceList Name": f"{self.name}",
                    "Design Flow Rate Calculation Method": "Flow/Person",
                    "Flow Rate per Person": BASE_VENTILATION_FLOW_PER_PERSON * (1-overall_efficiency),
                    "Ventilation Type": "Exhaust",
                    "Fan Pressure Rise": 50 / (1-overall_efficiency),
                    "Fan Total Efficiency": 0.85,
                }, ignore_default=False))

        return load_objs
        
    def to_idf_object(self) -> list[IdfObject]:
        
        # zone
        zone_obj = [
            IdfObject("Zone",{
                "Name": self.name,
                "Zone Inside Convection Algorithm" : "TARP",
                "Zone Outside Convection Algorithm": "TARP",
                "Floor Area": self.floor_area,
            })
        ]
        
        # surfaces
        surf_objs = sum([surf.to_idf_object(self) for surf in self.surface], start=[])
        
        # loads
        load_objs = self.to_idf_load_object()
        
        # hvac (연결 가능하게 setting만)
        hvac_default_objs = self.to_idf_hvac_default_object()
        
        return zone_obj + surf_objs + hvac_default_objs + load_objs
        
        
        
        
        
        
        
        
        
        
      