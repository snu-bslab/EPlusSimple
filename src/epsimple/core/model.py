
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import os
import re
import json
import math
from copy     import deepcopy
from types    import SimpleNamespace
from typing   import Iterable
from datetime import datetime

# third-party modules
import pandas as pd

# local modules
import idragon
from idragon       import dragon
from idragon.utils import (
    validate_range,
    validate_type ,
)
from ..constants import (
    Directory  ,
    Unit       ,
    Site2Source,
    Site2Cost  ,
    Site2CO2   ,
    SpecialTag ,
)
from . import (
    # construction
    Material                ,
    SurfaceConstruction     ,
    OpenConstruction         ,
    UnknownConstruction     ,
    FenestrationConstruction,
    # profile
    Profile,
    # hvac
    Fuel,
    SourceSystem      ,
    Boiler            ,
    DistrictHeating   ,
    SupplySystem      ,
    VentilationSystem ,
    PhotoVoltaicSystem,
    NoneSource        ,
    # shape
    Surface                 ,
    Window                  ,
    SurfaceBoundaryCondition,
    SurfaceType             ,
    Zone                    ,
)
from ..utils import (
    excel2grjson,
)


# ---------------------------------------------------------------------------- #
#                                   VARIABLES                                  #
# ---------------------------------------------------------------------------- #

ADDR_WEATHER_TABLE = pd.read_csv(os.path.join(Directory.WEATHER_META_DIR, "행정구역별기상데이터.csv")).set_index("행정구역명")
CLIMATE_TABLE      = pd.read_csv(os.path.join(Directory.WEATHER_META_DIR, "기후지역.csv"          )).set_index("행정구역명")

# ---------------------------------------------------------------------------- #
#                                  EXCEPTIONS                                  #
# ---------------------------------------------------------------------------- #

class InvalidAddressError(Exception):
    pass

class EnergyPlusError(Exception):
    
    def __init__(self, err:pd.DataFrame):
        
        if err is not None:
            err_message = "===EnergyPlusError===\n" +\
                "\n".join(err.query("type=='Severe' | type=='Fatal'")["title"].values)
        else:
            err_message = "EP ERROR파일조차 생성되지 않음."
                      
        super().__init__(err_message)
        

# ---------------------------------------------------------------------------- #
#                             GRIM SIMULATOR MODEL                             #
# ---------------------------------------------------------------------------- #

def address_to_weather(
    address:str     ,
    vintage:datetime,
    ) -> tuple[str, str, str]:
    
    sigungu_match = re.search(r"^[\w ]+[시군구](?= |$)", address)
    if sigungu_match is None:
        raise InvalidAddressError(
            f"Cannot find '시' or '군' or '구' from '{address}'"
        )
    
    sigungu = sigungu_match.group(0)
    sigungu_info = ADDR_WEATHER_TABLE.loc[sigungu]
    
    terrain = sigungu_info["terrain"]
    weather_location = sigungu_info["기상지역명"]
    weather_filepath = Directory.WEATHER_DATA_DIR /  sigungu_info["EPW파일명"]
    
    climate = CLIMATE_TABLE.at[sigungu, max(datestr for datestr in CLIMATE_TABLE.columns if datestr <= vintage.strftime(r"%Y%m%d"))]
    
    return terrain, climate, weather_location, weather_filepath


class GreenRetrofitModel:
    
    def __init__(self,
        name      :str,
        address   :str,
        vintage   :list[int]|datetime  ,
        north_axis:int|float          ,
        zone      :list[Zone]=[],
        pv        :list[PhotoVoltaicSystem]=[],
        ) -> None:
        
        # user properties
        self.name = name
        
        # fundamental properties
        self.vintage   =vintage
        self.address   =address
        self.north_axis=north_axis
        
        # childrens
        self.zone=zone
        self.pv  =pv
        
        # initialization
        self.__source_system = []
    
    """ address related
    """
    
    @property
    def address(self) -> str:
        return self.__address
    
    @address.setter
    def address(self, value:str) -> None:
        
        terrain, climate, weather_location, weather_filepath = address_to_weather(value, self.vintage)
        
        self.__terrain = terrain
        self.__climate = climate
        self.__weather = weather_location
        self.__weather_filepath = weather_filepath
        self.__address = value       
        
        return
    
    @property
    def climate(self) -> str:
        return self.__climate
    
    @property
    def terrain(self) -> str:
        return self.__terrain
    
    @property
    def weather(self) -> str:
        return self.__weather
    
    @property
    def weather_filepath(self) -> str:
        return self.__weather_filepath
    
    """ other fundamental properties
    """
    
    @property
    def vintage(self) -> datetime:
        return self.__vintage
    
    @vintage.setter
    def vintage(self, value: datetime|list[int]) -> None:
        
        if not isinstance(value, datetime):
            try:
                value = datetime(*tuple(value))
            except:
                raise ValueError(
                    f"Cannot convert {value} to datetime."
                )
                
        self.__vintage = value
        
    @property
    def north_axis(self) -> int|float:
        return self.__north_axis
    
    @north_axis.setter
    @validate_range(min=0, max=math.nextafter(360,-math.inf))
    @validate_type(int, float)
    def north_axis(self, value: int|float) -> None:
        self.__north_axis = value
        
    """ additional properties
    """
        
    @property
    def source_system(self) -> list[SourceSystem]:
        
        heating_sources = {
            zone.heating_supply.source.ID: zone.heating_supply.source
            for zone in self.zone
            if zone.heating_supply is not None and not isinstance(zone.heating_supply.source, NoneSource)
        }
        
        cooling_sources = {
            zone.cooling_supply.source.ID: zone.cooling_supply.source
            for zone in self.zone
            if zone.cooling_supply is not None and not isinstance(zone.cooling_supply.source, NoneSource)
        }
        
        unique_sources = list((heating_sources|cooling_sources).values())
        
        return self.__source_system + unique_sources
    
    @source_system.setter
    def source_system(self, value:list[SourceSystem]):
        
        if not isinstance(value, Iterable) and not all(isinstance(item, SourceSystem) for item in value):
            raise ValueError(
                f"Source system of a GreenRetrofitModel instance should be an iterable instance of SourceSystem(s)."
            )
        
        self.__source_system = list(value)
    
    @property
    def area(self) -> float:
        return sum(zone.area for zone in self.zone)
    
    @property
    def exteriorwalls(self) -> list[Surface]:
        return [
            surf for surf in sum([zone.surface for zone in self.zone], start=[])
            if (surf.boundary == SurfaceBoundaryCondition.OUTDOOR) and (surf.type == SurfaceType.WALL)
        ]
        
    @property
    def exteriorroofs(self) -> list[Surface]:
        return [
            surf for surf in sum([zone.surface for zone in self.zone], start=[])
            if (surf.boundary == SurfaceBoundaryCondition.OUTDOOR) and (surf.type == SurfaceType.CEILING)
        ]
    
    @property
    def exteriorfloors(self) -> list[Surface]:
        return [
            surf for surf in sum([zone.surface for zone in self.zone], start=[])
            if (surf.boundary == SurfaceBoundaryCondition.OUTDOOR or surf.boundary == SurfaceBoundaryCondition.GROUND) and (surf.type == SurfaceType.FLOOR)
        ]
        
    @property
    def exteriorwindows(self) -> list[Window]:
        return [
            fene for fene
            in sum([wall.fenestrations for wall in self.exteriorwalls], start=[])
            if isinstance(fene, Window)
        ]
    
    @property
    def averaged_exteriorwall_Uvalue(self) -> float:
        
        areasum = 0
        UAsum   = 0
        for wall in self.exteriorwalls:
            
            areasum += wall.area
            
            if wall.construction is UnknownConstruction():
                UAsum += wall.area * SurfaceConstruction.get_regulated_construction(
                    self.vintage    ,
                    wall.type    ,
                    wall.boundary,
                    self.climate    ,
                    is_residential=False,
                ).get_U()
                
            else:
                UAsum += wall.area * wall.construction.get_U()
        
        if areasum > 0:
            return UAsum / areasum
        else:
            return 0
    
    @property
    def averaged_exteriorroof_Uvalue(self) -> float:
        
        areasum = 0
        UAsum   = 0
        
        for roof in self.exteriorroofs:
            areasum += roof.area
            
            if roof.construction is UnknownConstruction():
                UAsum += roof.area * SurfaceConstruction.get_regulated_construction(
                    self.vintage    ,
                    roof.type    ,
                    roof.boundary,
                    self.climate    ,
                    is_residential=False,
                ).get_U()
                
            else:
                UAsum += roof.area * roof.construction.get_U()
        
        if areasum > 0:
            return UAsum / areasum
        else:
            return 0
    
    @property
    def averaged_exteriorfloor_Uvalue(self) -> float:
        
        areasum = 0
        UAsum   = 0
        
        for floor in self.exteriorfloors:
            areasum += floor.area
            
            if floor.construction is UnknownConstruction():
                UAsum += floor.area * SurfaceConstruction.get_regulated_construction(
                    self.vintage    ,
                    floor.type    ,
                    floor.boundary,
                    self.climate    ,
                    is_residential=False,
                ).get_U()
                
            else:
                UAsum += floor.area * floor.construction.get_U()
        
        if areasum > 0:
            return UAsum / areasum
        else:
            return 0
    
    @property
    def averaged_window_Uvalue(self) -> float:
        
        areasum = 0
        UAsum   = 0
        
        for win in self.exteriorwindows:
            areasum += win.area
            UAsum   += win.area * win.construction.u
        
        if areasum > 0:
            return UAsum / areasum
        else:
            return 0
        
    @property
    def averaged_lightdensity(self) -> float:
        
        areasum = 0
        lightdensity_areasum = 0
        
        for zone in self.zone:
            areasum += zone.area
            lightdensity_areasum += zone.light_density * zone.area if zone.light_density is not None else 0
        
        if areasum > 0:
            return lightdensity_areasum / areasum
        else:
            return 0
    
    @property
    def averaged_infiltration(self) -> float:
        
        volsum = 0
        infiltration_volsum = 0
        
        for zone in self.zone:
            volsum += zone.area * zone.height
            infiltration = zone.infiltration if zone.infiltration is not None else GreenRetrofitModel.get_default_infiltration(zone)
            infiltration_volsum += infiltration * zone.area * zone.height
        
        if volsum > 0:
            return infiltration_volsum / volsum
        else:
            return 0
        
    """ useful methods (unique components)
    """
    
    def get_unique_fenestration_constructions(self) -> dict[str, FenestrationConstruction]:
        
        return {
            k: v
            for zone in self.zone
            for k, v in zone.get_unique_fenestration_constructions().items()
        }
    
    def get_unique_surface_constructions(self) -> dict[str, SurfaceConstruction]:
        
        return {
            k:v
            for zone in self.zone
            for k,v in zone.get_unique_surface_constructions().items()
        }
        
    def get_unique_materials(self) -> dict[str, Material]:
        
        return {
            k:v
            for construction in self.get_unique_surface_constructions().values()
            for k,v in construction.get_unique_materials().items()
        }
        
    def get_unique_profiles(self) -> dict[str, Profile]:
        
        return {
            zone.profile.ID: zone.profile
            for zone in self.zone
        }
    
    """ model in-out
    """
    
    @classmethod
    def from_grjson(cls, filepath:str) -> GreenRetrofitModel:
        
        # read the json file
        with open(filepath, encoding="UTF-8") as f:
            input = json.load(f, object_hook=lambda d: SimpleNamespace(**d))
        
        # building info.
        name       = input.building.name
        address    = input.building.address
        vintage    = input.building.vintage
        north_axis = input.building.north_axis
        
        # create a green-retrofit-model
        grm = cls(
            name      ,
            address   ,
            vintage   ,
            north_axis,
        )
        
        # construction
        material_dict = {
            material_input.id: Material.from_json(material_input)
            for material_input in input.materials
        }
        surface_construction_dict = {
            construction_input.id: SurfaceConstruction.from_json(construction_input, material_dict)
            for construction_input in input.surface_constructions
        }
        fenestration_construction_dict = {
            fenestration_input.id: FenestrationConstruction.from_json(fenestration_input)
            for fenestration_input in input.fenestration_constructions
        }
        
        # special constructions
        surface_construction_dict["open"]    = OpenConstruction()
        surface_construction_dict["unknown"] = UnknownConstruction()
        
        # system
        source_system_dict = {
            system_input.id: SourceSystem.from_json(system_input)
            for system_input in input.building.source_systems
        }
        supply_system_dict = {
            system_input.id: SupplySystem.from_json(system_input, source_system_dict)
            for system_input in input.building.supply_systems
        }
        ventilation_system_dict = {
            ventilation_input.id: VentilationSystem.from_json(ventilation_input)
            for ventilation_input in input.building.ventilation_systems
        }
        photovoltaic_systems = {
            photovoltaic_input.id: PhotoVoltaicSystem.from_json(photovoltaic_input)
            for photovoltaic_input in input.building.photovoltaic_systems
        }
        
        # zone
        grm.zone = [
            Zone.from_json(
                zone_input                    ,
                surface_construction_dict     ,
                fenestration_construction_dict,
                supply_system_dict            ,
                ventilation_system_dict       ,
            )
            for floor_input in input.building.floors
            for zone_input  in floor_input.zones
        ]
        
        # add unused source systems
        # please refer to the definition of the supply_system property
        applied_ID = (source.ID for source in grm.source_system)
        grm.source_system = [sys for sys in source_system_dict.values() if sys.ID not in applied_ID]
        
        # pv panel
        grm.pv = list(photovoltaic_systems.values())
        
        # allocate adjacent zone information
        zone_dict = {zone.ID: zone for zone in grm.zone}
        surf_dict = {surf.ID: surf for zone in grm.zone for surf in zone.surface}
        for floor_input in input.building.floors:
            for zone_input in floor_input.zones:
                for surf_input in zone_input.surfaces:
                    if surf_input.boundary_condition == "zone":
                        surf_dict[surf_input.id].adjacent_zone = zone_dict[surf_input.adjacent_zone_id]
        
        return grm
    
    @classmethod
    def from_excel(cls, filepath:str) -> GreenRetrofitModel:
        
        _, json_path = excel2grjson(filepath)
        
        try:
            grm = cls.from_grjson(json_path)
            
        finally:
            os.remove(json_path)
        
        return grm
    
    def _dragonize_surface(self,
        surface_construction_dict     :dict[str, dragon.Construction],
        fenestration_construction_dict:dict
        ) -> dict[str, list[dragon.Surface]]:
        
        # collect surfaces
        surfaces_by_zone = {
            zone.ID: zone.surface
            for zone in self.zone
        }
        surface_dict = {
            surface.ID: surface
            for surface in sum(surfaces_by_zone.values(), start=[])
        }
        
        # allocate unknowns
        default_innerwall_construction = SurfaceConstruction(
            f"{SpecialTag.SPECIAL}DefaultInnerWallConstruction",
            Material.get_DB("gypsumboard"), 0.0125, 
            Material.get_DB("glasswool")  , 0.0500,
            Material.get_DB("gypsumboard"), 0.0125,
        )
        dragonized_default_innerwall_construction = default_innerwall_construction.to_dragon()
        unknown_surfaces = []
        for surface in surface_dict.values():
            
            if surface.construction is UnknownConstruction():
                unknown_surfaces.append(surface)
                
                # interior wall
                if (surface.type == SurfaceType.WALL) and (surface.boundary == SurfaceBoundaryCondition.ZONE):
                    surface.construction = default_innerwall_construction
                    surface_construction_dict[dragonized_default_innerwall_construction.name] = dragonized_default_innerwall_construction
                
                # exterior wall / roof / floor
                else:            
                    regulated_construction = SurfaceConstruction.get_regulated_construction(
                        self.vintage    ,
                        surface.type    ,
                        surface.boundary,
                        self.climate    ,
                        is_residential=False,
                    )
                    surface.construction = regulated_construction
                    
                    dragonized_construction = regulated_construction.to_dragon()
                    surface_construction_dict[dragonized_construction.name] = dragonized_construction
            
        # duplicate surfaces by adjacency
        adjacent_pair       = dict()
        copied_surface_dict = dict()
        for surface in surface_dict.values():
            if surface.boundary == SurfaceBoundaryCondition.ZONE:
                
                adjacent_surface = surface.flip()
                    
                surfaces_by_zone[surface.adjacent_zone.ID].append(adjacent_surface)
                copied_surface_dict[adjacent_surface.ID] = adjacent_surface
                adjacent_pair[surface.ID] = adjacent_surface.ID
                
                reversed_construction = surface.construction.reversed()
                adjacent_surface.construction = reversed_construction
                
                dragonized_construction = reversed_construction.to_dragon()
                surface_construction_dict[dragonized_construction.name] = dragonized_construction
        surface_dict |= copied_surface_dict
        
        # create special constructions for coolroof
        # allocation of the coolroof construction is handled in Surface.to_dragon
        for surface in surface_dict.values():
            if surface.reflectance is not None:
                
                # get original construction
                original_construction = surface_construction_dict[surface.construction.ID]
                
                # create coolroof layer (outside layer)
                coolroof_layer = dragon.Layer(
                    f"{SpecialTag.COOLROOF}{original_construction.layers[0].name}",
                    dragon.Material(
                        f"{SpecialTag.COOLROOF}{original_construction.layers[0].material.name}",
                        original_construction.layers[0].material.conductivity,
                        original_construction.layers[0].material.density,
                        original_construction.layers[0].material.specific_heat,
                        solar_absorptance  =1 - surface.reflectance,
                        thermal_absorptance=1 - surface.reflectance,
                    ),
                    original_construction.layers[0].thickness
                )
                
                # create coolroof construction and save to the dictionary
                coolroof_construction = dragon.Construction(
                    f"{SpecialTag.COOLROOF}{original_construction.name}",
                    coolroof_layer, *original_construction.layers[1:]
                )
                surface_construction_dict[coolroof_construction.name] = coolroof_construction
        
        # dragonize
        dragonized_surfaces_by_zone = {
            zone_id: [
                v.to_dragon(
                    zone.height,
                    surface_construction_dict     ,
                    fenestration_construction_dict,
                )
                for v in surface_list
            ]
            for zone, (zone_id, surface_list) in zip(self.zone, surfaces_by_zone.items())
        }
        
        # allocate adjacent surfaces
        dragonized_surface_dict = {
            surface.name: surface
            for surface in sum(dragonized_surfaces_by_zone.values(), start=[])
        }
        for ID in adjacent_pair.keys():
            dragonized_surface_dict[ID].boundary = dragonized_surface_dict[adjacent_pair[ID]]
        
        # reset allocated unknowns
        for surface in unknown_surfaces:
            surface.construction = UnknownConstruction()
        
        return dragonized_surfaces_by_zone
    
    @staticmethod
    def get_default_infiltration(zone: Zone) -> float:
        
        has_outdoor_window = lambda surf: (
            surf.boundary == SurfaceBoundaryCondition.OUTDOOR
        ) and any(
            isinstance(fen, Window) for fen in surf.fenestrations
        )
        
        if any(has_outdoor_window(surf) for surf in zone.surface):
            return 1.5
        
        else:
            return 0
    
    def to_dragon(self):
        
        # construction
        material_dict = {
            k: v.to_dragon()
            for k,v in self.get_unique_materials().items()
        }
        surface_construction_dict = {
            k: v.to_dragon(material_dict=material_dict)
            for k, v in self.get_unique_surface_constructions().items()
            if not isinstance(v, UnknownConstruction)
        }
        fenestration_construction_dict = {
            k: v.to_dragon()
            for k, v in self.get_unique_fenestration_constructions().items()
        }
        
        # profile
        profile_dict = {
            k: v.to_dragon()
            for k, v in self.get_unique_profiles().items()
        }
        
        # surface
        dragonized_surfaces = self._dragonize_surface(
            surface_construction_dict     ,
            fenestration_construction_dict,
        )
        
        # source / supply system
        supply_dict = dict()
        source_dict = dict()
        for zone in self.zone:
            
            if zone.heating_supply is not None:
                
                if not isinstance(zone.heating_supply.source, NoneSource) and (zone.heating_supply.source.ID not in source_dict.keys()):
                    source_dict[zone.heating_supply.source.ID] = zone.heating_supply.source.to_dragon()
                supply_dict[zone.heating_supply.ID] = zone.heating_supply.to_dragon(source_dict)
                
            if zone.cooling_supply is not None:
                
                if not isinstance(zone.cooling_supply.source, NoneSource) and (zone.cooling_supply.source.ID not in source_dict.keys()):
                    source_dict[zone.cooling_supply.source.ID] = zone.cooling_supply.source.to_dragon()
                supply_dict[zone.cooling_supply.ID] = zone.cooling_supply.to_dragon(source_dict)
        
        # ventilation system
        ventilator_dict = {
            zone.ventilation_system.ID: zone.ventilation_system.to_dragon()
            for zone in self.zone
            if zone.ventilation_system is not None
        }
        
        # photovoltaic system
        pv_dict = {
            pv.ID: pv.to_dragon()
            for pv in self.pv
        }
        
        # model
        em = idragon.EnergyModel(
            self.name      ,
            self.north_axis,
            self.terrain   ,
            [
                dragon.Zone(
                    zone.ID,
                    dragonized_surfaces[zone.ID],
                    profile_dict[zone.profile.ID],
                    (zone.infiltration if zone.infiltration is not None else GreenRetrofitModel.get_default_infiltration(zone))*Unit.ACH50_TO_ACH,
                    zone.light_density,
                    supply_dict.get(getattr(zone.cooling_supply,"ID",None), None),
                    supply_dict.get(getattr(zone.heating_supply,"ID",None), None),
                    ventilator_dict.get(getattr(zone.ventilation_system,"ID", None), None)
                )
                for zone in self.zone
            ],
            pv=list(pv_dict.values())
        )
        
        return em
    
    def to_idf(self):
        em  = self.to_dragon()
        idf = em.to_idf()
        return idf
        
    """ run
    """
    
    def run(self) -> idragon.EnergyPlusResult:
        
        idf  = self.to_idf()
        result = idf.run(str(self.weather_filepath))
        
        return GreenRetrofitResult(
            self  ,
            result,
        )
        
    """ representation
    """
    
    def __repr__(self) -> str:
        return f"<GreenRetrofitModel {self.name} at {hex(id(self))}>"
    
    def __str__(self) -> str:
        return f"GreenRetrofitModel '{self.name}' with {len(self.zone)} zones and total area of {self.area} m2."


class GreenRetrofitResult:
    
    VALID_DIGITS = 2
    
    def __init__(self,
        model :GreenRetrofitModel,
        result:idragon.EnergyPlusResult
        ) -> None:
        
        self.model  = model
        self.result = result
        
        if result.tbl is None:
            raise EnergyPlusError(self.result.err)
    
    @property
    def area(self) -> float:
        return self.model.area
    
    def get_domestic_hotwater_energy(self) -> list[float]:
        
        energy = [0] * 12
        for zone in self.model.zone:
            for dayschedule, date in zip(zone.profile._get_occupied_mask().dayschedules, dragon.Schedule.TIME_TUPLE):
                if dayschedule.has_positive:
                    energy[date.month-1] += zone.profile.domestic_hotwater * zone.area * 1E-3
        
        return energy
    
    def get_dhw_servers(self) -> list[SourceSystem]:
        dhw_servers = [
            source
            for source in self.model.source_system
            if hasattr(source, "hotwater_supply") and source.hotwater_supply
        ]

        if len(dhw_servers) == 0:
            dhw_servers = [
                Boiler(
                    "HotWaterBoiler",
                    Fuel.NATURALGAS,
                    True,
                    0.85,
                    None,
                )
            ]

        return list({server.ID: server for server in dhw_servers}.values())
    
    def calc_domestic_hotwater_site_energy(self) -> dict[str, list[float]]:
        demand = self.get_domestic_hotwater_energy()
        dhw_servers = self.get_dhw_servers()

        demand_per_server = [
            v / self.area / len(dhw_servers)
            for v in demand
        ]

        hotwater_energy = {
            fuel.name: [0.0] * 12
            for fuel in Fuel
        }

        for server in dhw_servers:
            if isinstance(server, DistrictHeating):
                fuel = Fuel.DISTRICTHEATING.name
                efficiency = 1.0

            elif isinstance(server, Boiler):
                fuel = Fuel(server.fuel).name
                efficiency = server.efficiency

            else:
                raise RuntimeError(
                    f"Unsupported DHW server: {type(server).__name__}"
                )

            hotwater_energy[fuel] = [
                round(v_org + v_add / efficiency, GreenRetrofitResult.VALID_DIGITS)
                for v_org, v_add in zip(hotwater_energy[fuel], demand_per_server)
            ]

        return hotwater_energy
    
    def to_site_uses(self) -> pd.DataFrame:
        
        usecol_map = {
            "heating"    : ["HEATING"],
            "cooling"    : ["COOLING"],
            "lighting"   : ["INTERIORLIGHTS","EXTERIORLIGHTS"],
            "circulation": ["FANS","PUMPS","HEATRECOVERY"],
            "hotwater"   : ["WATERSYSTEMS"],
            "generators" : []
        }
        
        fuel_name_in_energyplus = {
            Fuel.ELECTRICITY    : "Electricity",
            Fuel.NATURALGAS     : "NaturalGas" ,
            Fuel.OIL            : "Diesel"    ,
            Fuel.DISTRICTHEATING: "OtherFuels" ,
        }
        
        df_site = pd.DataFrame(index=[v.name for v in Fuel], columns=list(usecol_map.keys())).map(lambda _: [float(0)]*12)
        for fuel_type in Fuel:
            
            # check if the fuel is used
            table_name = f"EndUseEnergyConsumption{fuel_name_in_energyplus[fuel_type]}Monthly"
            if table_name not in self.result.tbl:
                continue
            
            # get use 
            df   = self.result.tbl[table_name]
            fuel = fuel_type.name
            for use in df_site.columns:
                target_cols = [col for col in df.columns if any(col.startswith(usecol) for usecol in usecol_map[use])]                
                df_site.loc[fuel,use] = list(df[target_cols].sum(axis=1)[:12].astype(float).map(lambda v: round(v/self.area, GreenRetrofitResult.VALID_DIGITS)))
        
        # temporary calculation for the domestic hot water (DHW) energy consumption
        hotwater_energy_dict = self.calc_domestic_hotwater_site_energy()
        for fuel, energy in hotwater_energy_dict.items():
            df_site.loc[fuel, "hotwater"] = energy
        
        # On-site PV generation used within the facility
        table_name = "ELECTRICITYBALANCEMONTHLY"

        if table_name in self.result.tbl:
            df_electricity_balance = self.result.tbl[table_name]
            df_electricity_balance.columns = [re.sub(r" \[\w*\]","",col) for col in df_electricity_balance.columns]

            electricity_produced = (df_electricity_balance["ELECTRICITYPRODUCED:FACILITY"   ].iloc[:12].astype(float))
            electricity_surplus  = (df_electricity_balance["ELECTRICITYSURPLUSSOLD:FACILITY"].iloc[:12].astype(float))
            electricity_used_onsite = (electricity_produced - electricity_surplus).clip(lower=0.0)

            df_site.loc["ELECTRICITY","generators",] = [
                round(value / self.area, GreenRetrofitResult.VALID_DIGITS,)
                for value in electricity_used_onsite
            ]
        
        return df_site
    
    def to_source_uses(self) -> pd.DataFrame:
        
        df_source = deepcopy(self.to_site_uses())
        for idx in df_source.index:
            coeff = Site2Source[idx].value
            df_source.loc[idx] = df_source.loc[idx].map(lambda l: [round(v*coeff,GreenRetrofitResult.VALID_DIGITS) for v in l])
        
        return df_source
    
    def to_co2(self) -> pd.DataFrame:
        
        df_co2 = deepcopy(self.to_site_uses())
        for idx in df_co2.index:
            coeff = Site2CO2[idx].value
            df_co2.loc[idx] = df_co2.loc[idx].map(lambda l: [round(v*coeff,GreenRetrofitResult.VALID_DIGITS) for v in l])
        
        return df_co2
    
    def to_cost(self) -> pd.DataFrame:
        
        df_cost = deepcopy(self.to_site_uses())
        for idx in df_cost.index:
            coeff = Site2Cost[idx].value
            df_cost.loc[idx] = df_cost.loc[idx].map(lambda l: [round(v*coeff,GreenRetrofitResult.VALID_DIGITS) for v in l])
        
        return df_cost
    
    def summarize(self, df:pd.DataFrame, *, gross:bool) -> dict:
        
        # 컬럼 구분
        use_cols = ["heating", "cooling", "lighting", "circulation", "hotwater"]
        gen_cols = ["generators"]
        
        # total
        monthly_use = [
            round(sum(x),GreenRetrofitResult.VALID_DIGITS)
            for x in zip(*list(df[use_cols].values.flatten()))
        ]
        monthly_gen = [
            round(sum(x),GreenRetrofitResult.VALID_DIGITS)
            for x in zip(*list(df[gen_cols].values.flatten()))
        ]
        monthly_sum = [use-gen for use, gen in zip(monthly_use, monthly_gen)]

        # fuel sum
        fuel_sum = df.apply(
            lambda row: (
                sum(sum(row[c]) for c in use_cols) -  # 소비 용도 합산
                sum(sum(row[c]) for c in gen_cols)    # 발전 용도 차감
            ), 
            axis=1
        ).to_dict()
        fuel_sum_gross = {k: round(v*self.area, GreenRetrofitResult.VALID_DIGITS) for k,v in fuel_sum.items()}
        
        # usage sum
        usage_sum = df.apply(lambda col: sum(sum(x) for x in col), axis=0).to_dict()
        usage_sum_gross = {k: round(v*self.area, GreenRetrofitResult.VALID_DIGITS) for k,v in usage_sum.items()}
        
        if gross:
            summary = fuel_sum_gross|usage_sum_gross|{
                "total_monthly": [round(v*self.area,GreenRetrofitResult.VALID_DIGITS) for v in monthly_sum]           ,
                "total_annual" : round(sum(monthly_sum)*self.area, GreenRetrofitResult.VALID_DIGITS)        ,
            }
        else:
            summary = fuel_sum|usage_sum|{
                "total_monthly": monthly_sum,
                "total_annual" : round(sum(monthly_sum), GreenRetrofitResult.VALID_DIGITS),
        } 
               
        return summary
    
    def to_dict(self) -> dict:
        
        # convert result dataframe to a dictionary tree
        result_dict = {
            "building": {
                "total_area":self.area,
            },
            "constants":{
                key:{
                    str(fuel): getattr(enum, fuel.name)
                    for fuel in tuple(Fuel)
                }
                for enum, key in zip(
                    [Site2Source  , Site2CO2  , Site2Cost  ],
                    ["site2source", "site2co2", "site2cost"],
                )
            }
        }

        # site uses
        df_site = self.to_site_uses()
        result_dict["site_uses"] = df_site.to_dict()
        
        # source uses
        df_source = self.to_source_uses()
        result_dict["source_uses"] = df_source.to_dict()
        
        # co2
        df_co2 = self.to_co2()
        result_dict["co2"] = df_co2.to_dict()
                
        # cost
        df_cost = self.to_cost()
        result_dict["cost"] = df_cost.to_dict()
        
        # summary
        result_dict["summary_per_area"] = {
            name: self.summarize(df, gross=False)
            for name, df in zip(["site_uses","source_uses","co2","cost"],[df_site, df_source, df_co2, df_cost])
        }
        result_dict["summary_gross"] = {
            name: self.summarize(df, gross=True)
            for name, df in zip(["site_uses","source_uses","co2","cost"],[df_site, df_source, df_co2, df_cost])
        }        
        
        return result_dict
    
    def write(self,
        filepath:str
        ) -> None:
        
        # convert the result to a dictionary tree
        result_dict = self.to_dict()

        # write the dictionary tree as json format
        with open(filepath, "w", encoding="UTF-8") as f:
            # format the dictionrary into a json string
            json_str = json.dumps(result_dict, ensure_ascii=False, indent=4)
            # revise the multiline-list to a line
            json_str = re.sub(r"\[\s+([^\[\]]+?)\s+\]", lambda m: f"[{' '.join(m.group(1).split())}]", json_str)
            # write
            f.write(json_str)
  
        return
  