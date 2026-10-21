
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
from enum import Enum

# third-party modules

# local modules
from ..imugi import (
    IdfObject,
    IDF      ,
)

from ..common import (
    Version,
    Setting,
)
from .construction import (
    Material    ,
    Construction,
    AirBoundary ,
)
from .shape import (
    Surface    ,
    Zone       ,
)
from .hvac import (   
    SupplySystem     ,
    SupplyGroup      ,
    PhotoVoltaicPanel,
)
from .profile import (
    ScheduleType,
    Profile     ,
)
from ..constants import (
    THERMAL
)



# ---------------------------------------------------------------------------- #
#                                    CLASSES                                   #
# ---------------------------------------------------------------------------- #


class Terrain(str, Enum):
    
    COUNTRY ="Country"
    SUBURBS ="Suburbs"
    CITY    ="City"
    OCEAN   ="Ocean"
    URBAN   ="Urban"

class EnergyModel:
    
    supported_versions = [
        Version(24,2,0)
    ]

    def __init__(self,
        name      :str,
        north_axis:int|float=0,
        terrain   :str=Terrain.SUBURBS,
        zone      :list[Zone]=[],
        *,
        pv        :list[PhotoVoltaicPanel]=[],
        ):
        
        self.name       = name
        self.north_axis = north_axis
        self.terrain    = terrain
        self.zone       = zone
        self.pv         = pv
    
    @property
    def surfaces(self) -> list[Surface]:
        return sum([zone.surface for zone in self.zone], start=[])
    
    @property
    def used_constructions(self) -> list[Construction]:
        return [construction for construction in set(surface.construction for surface in self.surfaces) if isinstance(construction, Construction)]
    
    @property
    def used_layers(self) -> list[Material]:
        return list(set(sum([construction.layers for construction in self.used_constructions],start=[])))
    
    @property
    def used_profiles(self) -> list[Profile]:
        return list({zone.profile.name: zone.profile for zone in self.zone}.values())
    
    @property
    def conditioned_zones(self) -> list[Zone]:
        return [zone for zone in self.zone if zone.is_conditioned]
    
    @property
    def unconditioned_zones(self) -> list[Zone]:
        return [zone for zone in self.zone if not zone.is_conditioned]

    """ idf-related
    """
    
    @staticmethod
    def create_default_idf() -> IDF:
        
        # default runnable idf and settings
        idf = IDF(ensure_validity=False)
        idf["SimulationControl"].append(["Yes","Yes","Yes","No","Yes","No"])
        idf["SizingPeriod:WeatherFileDays"].append(["DesignWinter",1,1,1,31])
        idf["SizingPeriod:WeatherFileDays"].append(["DesignSummer",8,1,8,31])
        idf["Timestep"].append({"Number of Timesteps per Hour": 6})
        idf["RunPeriod"].append(["Year-Round", 1, 1, Setting.DEFAULT_YEAR, 12, 31, Setting.DEFAULT_YEAR])
        idf["GlobalGeometryRules"][0] =IdfObject("GlobalGeometryRules", ["UpperLeftCorner", "CounterClockwise", "Relative"])
        
        # global objects
        for schedule_type in ScheduleType:
            idf.append(schedule_type.to_idf_object())
        idf["Schedule:Compact"].append(["ALLON" , "", "Through: 12/31", "For: AllDays", "Until: 24:00", 1])
        idf["Schedule:Compact"].append(["ALLOFF", "", "Through: 12/31", "For: AllDays", "Until: 24:00", 0])
        
        # assumptions
        idf["Schedule:Constant"].append(["$DEFAULT$PEOPLEACTIVITY", ScheduleType.REAL, THERMAL.PEOPLE_ACTIVITY_LEVEL.value])
        
        # main output
        idf["OutputControl:Table:Style"].append(["COMMA", "JtoKWH"])
        idf["Output:Table:SummaryReports"].append([
            "EndUseEnergyConsumptionElectricityMonthly",
            "EndUseEnergyConsumptionNaturalGasMonthly",
            "EndUseEnergyConsumptionDieselMonthly"   ,
            "EndUseEnergyConsumptionOtherFuelsMonthly"   ,
            "EnergyConsumptionElectricityGeneratedPropaneMonthly",
        ])
        
        idf["Output:Table:Monthly"].append([
            "ElectricityBalanceMonthly",
            3,

            "ElectricityProduced:Facility",
            "SumOrAverage",

            "ElectricitySurplusSold:Facility",
            "SumOrAverage",

            "ElectricityPurchased:Facility",
            "SumOrAverage",
        ])
        
        return idf
    
    @staticmethod
    def add_supply_system(
        idf   :IDF         ,
        zone  :Zone        , 
        supply:SupplySystem,
        *,
        for_heating:bool,
        for_cooling:bool,
        ) -> None:
        
        # get idf objects
        supply_objs, postprocesors = supply.to_idf_object(
            zone,
            for_heating=for_heating,
            for_cooling=for_cooling,
        )
        
        # append
        idf.append(*supply_objs)
        for processor in postprocesors:
            processor.run(idf)

        return
    
    def to_idf(self) -> IDF:
        
        # create default objects
        idf = EnergyModel.create_default_idf()
        
        # building
        idf["building"].append({
            "Name"      : self.name,
            "North Axis": self.north_axis,
            "Terrain"   : self.terrain,
            "Solar Distribution": "MinimalShadowing",
        })        
        
        # constructions
        idf.append(*[layer.to_idf_object() for layer in self.used_layers])            
        for surface in self.surfaces:
            
            # surface consturction
            if isinstance(surface.construction, Construction):
                idf.append(*surface.construction.to_idf_object(surface))
            
            if isinstance(surface.construction, AirBoundary):
                if surface.construction.name not in idf["Construction:AirBoundary"].names:
                    idf.append(*surface.construction.to_idf_object())
            
            # fenestration construction
            for window in surface.window:
                idf.append(*window.glazing.to_idf_object())
                    
            for door in surface.door:
                idf.append(*door.construction.to_idf_object())
                    
        # profile
        for profile in self.used_profiles:
            idf.append(*profile.to_idf_object())     
        
        # zones (zones, surfaces, loads, hvacs)
        for zone in self.zone:
            idf.append(*zone.to_idf_object())
        
        # HVAC: Source
        created_sources = set([None])
        for zone in self.conditioned_zones:
            
            if isinstance(zone.cooling_supply, SupplyGroup):
                
                for supply in zone.cooling_supply.systems:   
                    if supply.source not in created_sources:
                        source_objs = supply.source.to_idf_object()
                        idf.append(*source_objs)
                        created_sources.add(supply.source)
            
            else:
                if (zone.cooling_supply is not None) and (zone.cooling_supply.source not in created_sources):
                    source_objs = zone.cooling_supply.source.to_idf_object()
                    idf.append(*source_objs)
                    created_sources.add(zone.cooling_supply.source)
            
            if isinstance(zone.heating_supply, SupplyGroup):
                
                for supply in zone.heating_supply.systems:   
                    if supply.source not in created_sources:
                        source_objs = supply.source.to_idf_object()
                        idf.append(*source_objs)
                        created_sources.add(supply.source)
                        
            else:    
                if (zone.heating_supply is not None) and (zone.heating_supply.source not in created_sources):
                    source_objs = zone.heating_supply.source.to_idf_object()
                    idf.append(*source_objs)
                    created_sources.add(zone.heating_supply.source)
    
        # HVAC: Supply 
        # Should be after adding supply systems and zones to the idf
        for zone in self.conditioned_zones:
            
            if zone.cooling_supply is zone.heating_supply:
                EnergyModel.add_supply_system(idf,
                    zone, zone.cooling_supply,
                    for_heating=True, for_cooling=True
                )
                
            else:
                if zone.cooling_supply is not None:
                    EnergyModel.add_supply_system(idf,
                        zone, zone.cooling_supply,
                        for_heating=False, for_cooling=True
                    )
                
                # heating supply
                if zone.heating_supply is not None:
                    EnergyModel.add_supply_system(idf,
                        zone, zone.heating_supply,
                        for_heating=True, for_cooling=False
                    )          
        
        if len(self.unconditioned_zones) > 0:
            
            idf.append(
                IdfObject(
                    "HVACTemplate:Thermostat",{
                        "Name": "UNCONDITIONED_THERMOSTAT",
                        "Constant Heating Setpoint": -30,
                        "Constant Cooling Setpoint":  50,
                    }
                )
            )
            
            for zone in self.unconditioned_zones:
                idf.append(
                    IdfObject(
                        "HVACTemplate:Zone:IdealLoadsAirSystem",{
                            "Zone Name": zone.name,
                            "Template Thermostat Name": "UNCONDITIONED_THERMOSTAT",
                            "System Availability Schedule Name": "ALLON",
                        },
                    )
                )           
        
        # PV panel
        for pv in self.pv:
            idf.append(*pv.to_idf_object())
        
        return idf
    
    
    
    
    
    
    
   