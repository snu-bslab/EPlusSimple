
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
    WindTurbine      ,
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
        zone      :list[Zone]=None,
        *,
        pv        :list[PhotoVoltaicPanel]=None,
        wt        :list[WindTurbine] = None
        ):
        
        self.name       = name
        self.north_axis = north_axis
        self.terrain    = terrain
        self.zone       = zone if zone is not None else []
        self.pv         = pv   if pv   is not None else []
        self.wt         = wt   if wt   is not None else []
    
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
        
        # default runnable IDF and settings
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
        
        # primary outputs
        idf["OutputControl:Table:Style"].append(["COMMA", "JtoKWH"])
        idf["Output:Table:SummaryReports"].append([
            "EndUseEnergyConsumptionElectricityMonthly",
            "EndUseEnergyConsumptionNaturalGasMonthly" ,
            "EndUseEnergyConsumptionDieselMonthly"     ,
            "EndUseEnergyConsumptionFuelOilMonthly"    ,
            "EndUseEnergyConsumptionCoalMonthly"       ,
            "EndUseEnergyConsumptionPropaneMonthly"    ,
            "EndUseEnergyConsumptionGasolineMonthly"   ,
            "EndUseEnergyConsumptionOtherFuelsMonthly" ,
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
        
        idf["Output:Table:Monthly"].append([
            "EPS_DISTRICT_MONTHLY",
            3,

            "DistrictHeatingWater:Plant",
            "SumOrAverage",

            "DistrictCooling:Plant",
            "SumOrAverage",
        ])
        
        return idf
    
    @staticmethod
    def add_supply_system(
        idf   :IDF,
        zone  :Zone,
        supply:SupplyGroup,
        ) -> None:

        supply_objects, postprocessors = supply.to_idf_object(zone)

        idf.append(*supply_objects)

        for processor in postprocessors:
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
            
            # surface construction
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
        created_sources = set()
        for zone in self.conditioned_zones:

            for source in zone.supply.sources:

                if source in created_sources:
                    continue

                idf.append(*source.to_idf_object())
                created_sources.add(source)
                
        # HVAC: Supply 
        # This must run after supply systems and zones have been added to the IDF
        for zone in self.conditioned_zones:
            EnergyModel.add_supply_system(idf, zone, zone.supply)      
        
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
        
        # generators
        for pv in self.pv:
            idf.append(*pv.to_idf_object())
        for wt in self.wt:
            idf.append(*wt.to_idf_object())
        
        return idf
    
    
    
    
    
    
    
