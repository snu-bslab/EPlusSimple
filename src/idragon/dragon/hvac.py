
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import math
from abc    import (
    ABC           ,
    abstractmethod,
)
from enum        import Enum
from typing      import (
    final        ,
    TYPE_CHECKING,
)

# third-party modules

# local modules
from ..imugi import (
    IdfObject,
    IDF      ,
)
from ..utils import (
    validate_type ,
    validate_range,
    validate_enum ,
)
from ..constants import Unit
from .profile import (
    Schedule    ,
    ScheduleType,
)

# settings
if TYPE_CHECKING:
    from .shape        import Zone
    from .construction import Construction

# ---------------------------------------------------------------------------- #
#                                SOURCE SYSTEMS                                #
# ---------------------------------------------------------------------------- #

class Fuel(str, Enum):
    
    ELECTRICITY = "electricity"
    NATURALGAS  = "naturalgas"
    PROPANE     = "propane"
    FUELOILNO1  = "fueloilno1"
    FUELOILNO2  = "fueloilno2"
    COAL        = "coal"
    DIESEL      = "diesel"
    GASOLINE    = "gasoline"
    OTHER       = "other"
    
    def __str__(self) -> str:
        return self.value
    
    def to_idf_name(self) -> str:
        
        if self == Fuel.OTHER:
            return "OtherFuel1"
        else:
            return self.value
    


class SourceSystem(ABC):

    
    @abstractmethod
    def to_idf_object(self) -> list[IdfObject]: ...
    
    """ idf-related naming rules
    """
    
    @property
    def idf_objname(self) -> str:
        return f"{type(self).__name__}_named_{self.name}"
    
    @property
    @abstractmethod
    def idf_objtypename(self) -> str: ...
    
    @property
    def idf_loopname(self) -> str:
        return f"Loop_for_{self.name}"
    
    @property
    def idf_demandbranchlistname(self) -> str:
        return f"{self.idf_loopname} Demand BranchList"
    
    @property
    def idf_demandsplittername(self) -> str:
        return f"{self.idf_loopname} Demand Splitter"
    
    @property
    def idf_demandmixername(self) -> str:
        return f"{self.idf_loopname} Demand Mixer"
    
    @property
    def idf_supplybranchlistname(self) -> str:
        return f"{self.idf_loopname} Supply BranchList"
    
    @property
    def idf_supplysplittername(self) -> str:
        return f"{self.idf_loopname} Supply Splitter"
    
    @property
    def idf_supplymixername(self) -> str:
        return f"{self.idf_loopname} Supply Mixer"
    
    @property
    def idf_terminalunitlistname(self) -> str:
        return f"Terminal_Units_for_{self.idf_objname}"

class HeatPump(SourceSystem):
    
    def __init__(self,
        name:str,
        fuel            :str|Fuel ,
        heating_cop     :int|float,
        cooling_cop     :int|float,
        heating_capacity:int|float|None=None,
        cooling_capacity:int|float|None=None,
        ) -> None:
        
        # user properties
        self.name = name
        
        # fundamental properties
        self.fuel = fuel
        self.heating_cop = heating_cop
        self.cooling_cop = cooling_cop
        self.heating_capacity = heating_capacity
        self.cooling_capacity = cooling_capacity      
    
    """ idf-related
    """  
    
    @property
    def idf_objtypename(self) -> str: 
        return "AirConditioner:VariableRefrigerantFlow"
    
    def to_idf_object(self) -> list[IdfObject]:
    
        curve_obj = [
            # Cooling capacity related
            IdfObject("Curve:Biquadratic",[
                f"Curve_for_{self.idf_objname}:CoolingCapaMF_LowTemp",
                0.576882692, 0.017447952, 0.000583269, -1.76324E-06, -7.474E-09, -1.30413E-07,
                15, 24, -5, 23, None, None, "Temperature", "Temperature", "Dimensionless",
            ]),
            IdfObject("Curve:Cubic",[
                f"Curve_for_{self.idf_objname}:CoolingCapaBoundary",
                25.73473775, -0.03150043, -0.01416595, 0,
                11, 30, None, None, "Temperature",
            ]),
            IdfObject("Curve:Biquadratic",[
                f"Curve_for_{self.idf_objname}:CoolingCapaMF_HighTemp",
                0.6867358, 0.0207631, 0.0005447, -0.0016218, -4.259E-07, -0.0003392,
                15, 24, 16, 43, None, None, "Temperature", "Temperature", "Dimensionless",
            ]),
            # Cooling EIR related
            IdfObject("Curve:Biquadratic",[
                f"Curve_for_{self.idf_objname}:CoolingEIRMF_LowTemp",
                0.989010541, -0.02347967, 0.000199711, 0.005968336, -1.0289E-07, -0.00015686,
                15, 24, -5, 23, None, None, "Temperature", "Temperature", "Dimensionless",
            ]),
            IdfObject("Curve:Cubic",[
                f"Curve_for_{self.idf_objname}:CoolingEIRBoundary",
                25.73473775, -0.03150043, -0.01416595, 0,
                15, 24, None, None, "Temperature",
            ]),
            IdfObject("Curve:Biquadratic",[
                f"Curve_for_{self.idf_objname}:CoolingEIRMF_HighTemp",
                0.14351470, 0.01860035, -0.0003954, 0.02485219, 0.00016329, -0.0006244,
                15, 24, 16, 43, None, None, "Temperature", "Temperature", "Dimensionless",
            ]),
            IdfObject("Curve:Cubic",[
                f"Curve_for_{self.idf_objname}:CoolingEIRMF_LowPLR",
                0.4628123, -1.0402406, 2.17490997, -0.5974817,
                0, 1, None, None, "Temperature", "Capacity",
            ]),
            IdfObject("Curve:Linear",[
                f"Curve_for_{self.idf_objname}:CoolingEIRMF_HighPLR",
                1.0, 0.0,
                1.0, 1.5,
            ]),
            # Cooling multi-unit related
            IdfObject("Curve:Linear",[
                f"Curve_for_{self.idf_objname}:CoolingCombCorrection",
                0.618055, 0.381945,
                1.0, 1.5,
            ]),
            IdfObject("Curve:Linear",[
                f"Curve_for_{self.idf_objname}:CoolingPLRCorrelation",
                0.85, 0.15,
                0.0, 1.0,
            ]),
            # Heating capacity related
            IdfObject("Curve:Biquadratic",[
                f"Curve_for_{self.idf_objname}:HeatingCapaMF_LowTemp",
                1.014599599, -0.002506703, -0.000141599, 0.026931595, 1.83538E-06, -0.000358147,
                15, 27, -20, 15, None, None, "Temperature", "Temperature", "Dimensionless",
            ]),
            IdfObject("Curve:Cubic",[
                f"Curve_for_{self.idf_objname}:HeatingCapaBoundary",
                -7.6000882, 3.05090016, -0.1162844, 0.0,
                15, 27, None, None, "Temperature",
            ]),
            IdfObject("Curve:Biquadratic",[
                f"Curve_for_{self.idf_objname}:HeatingCapaMF_HighTemp",
                1.161134821, 0.027478868, -0.00168795, 0.001783378, 2.03208E-06, -6.8969E-05,
                15, 27, -10, 15, None, None, "Temperature", "Temperature", "Dimensionless",
            ]),
            # Heating EIR related
            IdfObject("Curve:Biquadratic",[
                f"Curve_for_{self.idf_objname}:HeatingEIRMF_LowTemp",
                0.87465501, -0.01319754, 0.00110307, -0.0133118, 0.00089017, -0.00012766,
                15, 27, -20, 12, None, None, "Temperature", "Temperature", "Dimensionless",
            ]),
            IdfObject("Curve:Cubic",[
                f"Curve_for_{self.idf_objname}:HeatingEIRBoundary",
                -7.6000882, 3.05090016, -0.1162844, 0.0,
                15, 27, -20, 15, "Temperature",
            ]),
            IdfObject("Curve:Biquadratic",[
                f"Curve_for_{self.idf_objname}:HeatingEIRMF_HighTemp",
                2.504005146, -0.05736767, 4.07336E-05, -0.12959669, 0.00135839, 0.00317047,
                15, 27, -10, 15, None, None, "Temperature", "Temperature", "Dimensionless",
            ]),
            IdfObject("Curve:Cubic",[
                f"Curve_for_{self.idf_objname}:HeatingEIRMF_LowPLR",
                0.1400093, 0.6415002, 0.1339047, 0.0845859,
                0, 1, None, None, "Dimensionless", "Dimensionless",
            ]),
            IdfObject("Curve:Quadratic",[
                f"Curve_for_{self.idf_objname}:HeatingEIRMF_HighPLR",
                2.4294355, -2.235887, 0.8064516,
                1.0, 1.5,
            ]),
            # Heating multi-unit related
            IdfObject("Curve:Linear",[
                f"Curve_for_{self.idf_objname}:HeatingCombCorrection",
                0.96034, 0.03966,
                1.0, 1.5,
            ]),
            IdfObject("Curve:Linear",[
                f"Curve_for_{self.idf_objname}:HeatingPLRCorrelation",
                0.85, 0.15,
                0.0, 1.0,
            ]),
        ]
        
        demand_listobj = [
            IdfObject("ZoneTerminalUnitList",{
                "Zone Terminal Unit List Name": self.idf_terminalunitlistname
            })
        ]
        
        outdoor_obj = [
            IdfObject("AirConditioner:VariableRefrigerantFlow",{
                # specfications
                "Heat Pump Name": self.idf_objname,
                "Availability Schedule Name": "ALLON",
                "Gross Rated Total Cooling Capacity": self.cooling_capacity if self.cooling_capacity is not None else "autosize",
                "Gross Rated Cooling COP": self.cooling_cop,
                "Fuel Type": self.fuel.to_idf_name(),
                # Cooling Curves
                "Cooling Capacity Ratio Modifier Function of Low Temperature Curve Name": f"Curve_for_{self.idf_objname}:CoolingCapaMF_LowTemp",
                "Cooling Capacity Ratio Boundary Curve Name": f"Curve_for_{self.idf_objname}:CoolingCapaBoundary",
                "Cooling Capacity Ratio Modifier Function of High Temperature Curve Name": f"Curve_for_{self.idf_objname}:CoolingCapaMF_HighTemp",
                "Cooling Energy Input Ratio Modifier Function of Low Temperature Curve Name": f"Curve_for_{self.idf_objname}:CoolingEIRMF_LowTemp",
                "Cooling Energy Input Ratio Boundary Curve Name": f"Curve_for_{self.idf_objname}:CoolingEIRBoundary",
                "Cooling Energy Input Ratio Modifier Function of High Temperature Curve Name": f"Curve_for_{self.idf_objname}:CoolingEIRMF_HighTemp",
                "Cooling Energy Input Ratio Modifier Function of Low Part-Load Ratio Curve Name": f"Curve_for_{self.idf_objname}:CoolingEIRMF_LowPLR",
                "Cooling Energy Input Ratio Modifier Function of High Part-Load Ratio Curve Name": f"Curve_for_{self.idf_objname}:CoolingEIRMF_HighPLR",
                "Cooling Combination Ratio Correction Factor Curve Name": f"Curve_for_{self.idf_objname}:CoolingCombCorrection",
                "Cooling Part-Load Fraction Correlation Curve Name": f"Curve_for_{self.idf_objname}:CoolingPLRCorrelation",
                # Heating Curves
                "Gross Rated Heating Capacity": self.heating_capacity if self.heating_capacity is not None else "autosize",
                "Gross Rated Heating COP": self.heating_cop,
                "Heating Capacity Ratio Modifier Function of Low Temperature Curve Name": f"Curve_for_{self.idf_objname}:HeatingCapaMF_LowTemp",
                "Heating Capacity Ratio Boundary Curve Name": f"Curve_for_{self.idf_objname}:HeatingCapaBoundary",
                "Heating Capacity Ratio Modifier Function of High Temperature Curve Name": f"Curve_for_{self.idf_objname}:HeatingCapaMF_HighTemp",
                "Heating Energy Input Ratio Modifier Function of Low Temperature Curve Name": f"Curve_for_{self.idf_objname}:HeatingEIRMF_LowTemp",
                "Heating Energy Input Ratio Boundary Curve Name": f"Curve_for_{self.idf_objname}:HeatingEIRBoundary",
                "Heating Energy Input Ratio Modifier Function of High Temperature Curve Name": f"Curve_for_{self.idf_objname}:HeatingEIRMF_HighTemp",
                "Heating Energy Input Ratio Modifier Function of Low Part-Load Ratio Curve Name": f"Curve_for_{self.idf_objname}:HeatingEIRMF_LowPLR",
                "Heating Energy Input Ratio Modifier Function of High Part-Load Ratio Curve Name": f"Curve_for_{self.idf_objname}:HeatingEIRMF_HighPLR",
                "Heating Combination Ratio Correction Factor Curve Name": f"Curve_for_{self.idf_objname}:HeatingCombCorrection",
                "Heating Part-Load Fraction Correlation Curve Name": f"Curve_for_{self.idf_objname}:HeatingPLRCorrelation",
                # others
                "Master Thermostat Priority Control Type": "LoadPriority",
                # connections
                "Zone Terminal Unit List Name": self.idf_terminalunitlistname,
            })
        ]
        
        return curve_obj + demand_listobj + outdoor_obj


class GeothermalHeatPump(SourceSystem):
    
    @property
    def idf_objtypename(self) -> str: 
        return

class CompressorType(str, Enum):
    
    TURBO         = "turbo"
    SCREW         = "screw"
    RECIPROCATING = "reciprocating"
    
    def __str__(self) -> str:
        return self.value

    def to_idf_curve_object(self, chiller:Chiller) -> list[IdfObject]:
        
        match self.value:
            case "turbo"        : return [
                IdfObject("Curve:Biquadratic", [
                    f"Curve_for_{chiller.idf_objname}:CoolingCapaTemp",
                    0.257183345, 0.038794102, -0.00021648, 0.046738887, -0.000940235, -0.000342491,
                    5, 10, 24, 35,
                ]),
                IdfObject("Curve:Biquadratic", [
                    f"Curve_for_{chiller.idf_objname}:CoolingCOPTemp",
                    0.933678591, -0.058199196, 0.00449937, 0.002429466, 0.000485893, -0.001214733,
                    5, 10, 24, 35,
                ]),
                IdfObject("Curve:Quadratic", [
                    f"Curve_for_{chiller.idf_objname}:CoolingCOPPLR",
                    0.222903, 0.313387, 0.46371,
                    0, 1,
                ]),
            ]
            
            case "screw"        : return [
                IdfObject("Curve:Biquadratic", [
                    f"Curve_for_{chiller.idf_objname}:CoolingCapaTemp",
                    0.907133913, 0.029260566, -0.00036511, -0.000971992, -0.0000906018, 0.000252984,
                    0, 10, 0, 50,
                ]),
                IdfObject("Curve:Biquadratic", [
                    f"Curve_for_{chiller.idf_objname}:CoolingCOPTemp",
                    0.392011698, -0.024908656, -0.001031643, 0.01429376, 0.000406631, -0.000765035,
                    0, 20, 0, 50,
                ]),
                IdfObject("Curve:Bicubic", [
                    f"Curve_for_{chiller.idf_objname}:CoolingCOPPLR",
                    0.044612112, 0.023594163, 0.0000619872, -0.353684198, 1.797965254, -0.0272333223, 0, -0.467387755, 0, 0,
                    14.56, 34.97, 0.18, 1.03,
                ]),
            ]
            
            case "reciprocating": return [
                IdfObject("Curve:Biquadratic", [
                    f"Curve_for_{chiller.idf_objname}:CoolingCapaTemp",
                    0.9441897, 0.03371079, 0.00009756685, -0.003220573, -0.00004917369, -0.0001775717,
                    5.56, 10, 23.89, 35,
                ]),
                IdfObject("Curve:Biquadratic", [
                    f"Curve_for_{chiller.idf_objname}:CoolingCOPTemp",
                    0.727387, -0.01189276, 0.0005411677, 0.001879294, 0.0004734664, -0.000711485,
                    5.56, 10, 23.89, 35,
                ]),
                IdfObject("Curve:Quadratic", [
                    f"Curve_for_{chiller.idf_objname}:CoolingCOPPLR",
                    0.04146742, 0.6543795, 0.3044125,
                    0.25, 1.01,
                ]),
            ]
    
class Chiller(SourceSystem):
    
    def __init__(self,
        name        :str               ,
        cop         :int|float         ,
        capacity    :int|float|None    ,
        compressor  :str|CompressorType,
        coolingtower:CoolingTower      ,
        *,
        pump_efficiency:int|float=0.9,
        setpoint_temperature:int|float=6,
        ) -> None:
        
        # user properties
        self.name = name
        
        # fundamental properties
        self.cop        = cop
        self.capacity   = capacity
        self.compressor = CompressorType(compressor)
        
        # connected source
        self.coolingtower = coolingtower
        
        # additional properties
        self.pump_efficiency = pump_efficiency
        self.setpoint_temperature = setpoint_temperature
        
    @property
    def idf_objtypename(self) -> str: 
        return "Chiller:Electric:EIR"
    

    def to_idf_object(self) -> list[IdfObject]:
        
        curve_obj = self.compressor.to_idf_curve_object(self)
        
        component_obj = self.coolingtower.to_idf_object(self) + [
            IdfObject(self.idf_objtypename, {
                "Name": self.idf_objname,
                "Reference Capacity": self.capacity if self.capacity is not None else "autosize",
                "Reference COP"     : self.cop,
                "Reference Chilled Water Flow Rate"  : "autosize",
                "Reference Condenser Fluid Flow Rate": "autosize",
                "Cooling Capacity Function of Temperature Curve Name"                          : f"Curve_for_{self.idf_objname}:CoolingCapaTemp",
                "Electric Input to Cooling Output Ratio Function of Temperature Curve Name"    : f"Curve_for_{self.idf_objname}:CoolingCOPTemp",
                "Electric Input to Cooling Output Ratio Function of Part Load Ratio Curve Name": f"Curve_for_{self.idf_objname}:CoolingCOPPLR",
                "Chilled Water Inlet Node Name" : f"{self.idf_objname} ChilledWater InletNode" ,
                "Chilled Water Outlet Node Name": f"{self.idf_objname} ChilledWater OutletNode",
                "Condenser Inlet Node Name" : f"{self.idf_objname} Condenser InletNode" ,
                "Condenser Outlet Node Name": f"{self.idf_objname} Condenser OutletNode",
                "Condenser Type": "WaterCooled",
            }, ignore_default=True),
            IdfObject("Pump:VariableSpeed",{
                "Name": f"VSDPump_for_{self.idf_objname}",
                "Inlet Node Name" : f"VSDPump_for_{self.idf_objname} Water InletNode" ,
                "Outlet Node Name": f"VSDPump_for_{self.idf_objname} Water OutletNode",
                "Design Maximum Flow Rate": "autosize",
                "Motor Efficiency": self.pump_efficiency,
                "Design Power Consumption": "autosize",
            }, ignore_default=False),
        ]
        
        non_functional_pipes = [
            # supply
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Supply Bypass Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Supply Bypass Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Supply Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Supply Outlet Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
            }, ignore_default=False),
            # demand
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Demand Inlet Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Demand Inlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Demand Inlet Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Demand Bypass Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Demand Bypass Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Demand Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Demand Outlet Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe OutletNode",
            }, ignore_default=False),
        ]
        
        branches = [
            # supply
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply Inlet",
                "Component 1 Object Type": "Pump:VariableSpeed",
                "Component 1 Name": f"VSDPump_for_{self.idf_objname}",
                "Component 1 Inlet Node Name" : f"VSDPump_for_{self.idf_objname} Water InletNode" ,
                "Component 1 Outlet Node Name": f"VSDPump_for_{self.idf_objname} Water OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply Bypass",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Supply Bypass Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Supply Bypass Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Supply Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply MainComponent",
                "Component 1 Object Type": self.idf_objtypename,
                "Component 1 Name": self.idf_objname,
                "Component 1 Inlet Node Name" : f"{self.idf_objname} ChilledWater InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_objname} ChilledWater OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply Outlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Supply Outlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Supply Outlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
            }, ignore_default=False),
            # supply: list
            IdfObject("BranchList", {
               "Name": self.idf_supplybranchlistname,
               "Branch 1 Name": f"{self.idf_loopname} Supply Inlet",
               "Branch 2 Name": f"{self.idf_loopname} Supply Bypass",
               "Branch 3 Name": f"{self.idf_loopname} Supply MainComponent",
               "Branch 4 Name": f"{self.idf_loopname} Supply Outlet",
            }, ignore_default=False),
            # demand
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Demand Inlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Demand Inlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Demand Inlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Demand Inlet Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Demand Bypass",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Demand Bypass Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Demand Bypass Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Demand Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Demand Outlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Demand Outlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Demand Outlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe OutletNode",
            }, ignore_default=False),
            # demand: list
            IdfObject("BranchList", {
               "Name": self.idf_demandbranchlistname,
               "Branch 1 Name": f"{self.idf_loopname} Demand Inlet",
               "Branch 2 Name": f"{self.idf_loopname} Demand Bypass",
               "Branch 3 Name": f"{self.idf_loopname} Demand Outlet",
            }, ignore_default=False),
        ]
        
        connectors = [
            # supply
            IdfObject("Connector:Splitter", {
                "Name": self.idf_supplysplittername,
                "Inlet Branch Name": f"{self.idf_loopname} Supply Inlet",
                "Outlet Branch 1 Name": f"{self.idf_loopname} Supply MainComponent",
                "Outlet Branch 2 Name": f"{self.idf_loopname} Supply Bypass",
            }, ignore_default=False),
            IdfObject("Connector:Mixer", {
                "Name": self.idf_supplymixername,
                "Outlet Branch Name": f"{self.idf_loopname} Supply Outlet",
                "Inlet Branch 1 Name": f"{self.idf_loopname} Supply MainComponent",
                "Inlet Branch 2 Name": f"{self.idf_loopname} Supply Bypass",
            }, ignore_default=False),
            IdfObject("ConnectorList",{
                "Name": f"{self.idf_loopname} Supply Connectors",
                "Connector 1 Object Type": "Connector:Splitter",
                "Connector 1 Name"       : self.idf_supplysplittername,
                "Connector 2 Object Type": "Connector:Mixer",
                "Connector 2 Name"       : self.idf_supplymixername,
            }, ignore_default=False),
            # demand
            IdfObject("Connector:Splitter", {
                "Name": self.idf_demandsplittername,
                "Inlet Branch Name": f"{self.idf_loopname} Demand Inlet",
                "Outlet Branch 1 Name": f"{self.idf_loopname} Demand Bypass",
            }, ignore_default=False),
            IdfObject("Connector:Mixer", {
                "Name": self.idf_demandmixername,
                "Outlet Branch Name": f"{self.idf_loopname} Demand Outlet",
                "Inlet Branch 1 Name": f"{self.idf_loopname} Demand Bypass",
            }, ignore_default=False),
            IdfObject("ConnectorList",{
                "Name": f"{self.idf_loopname} Demand Connectors",
                "Connector 1 Object Type": "Connector:Splitter",
                "Connector 1 Name"       : self.idf_demandsplittername,
                "Connector 2 Object Type": "Connector:Mixer",
                "Connector 2 Name"       : self.idf_demandmixername,
            }, ignore_default=False),
        ]
        
        loop_controls = [
            # load distribution
            IdfObject("PlantEquipmentList", {
                "Name": f"{self.idf_loopname} EquipmentList",
                "Equipment 1 Object Type": self.idf_objtypename,
                "Equipment 1 Name": self.idf_objname
            }, ignore_default=False),
            IdfObject("PlantEquipmentOperation:CoolingLoad", {
                "Name": f"{self.idf_loopname} Operation",
                "Load Range 1 Lower Limit":    0,
                "Load Range 1 Upper Limit": 1E20,
                "Range 1 Equipment List Name": f"{self.idf_loopname} EquipmentList",
            }, ignore_default=False),
            IdfObject("PlantEquipmentOperationSchemes", {
                "Name": f"{self.idf_loopname} OperationScheme",
                "Control Scheme 1 Object Type": "PlantEquipmentOperation:CoolingLoad",
                "Control Scheme 1 Name": f"{self.idf_loopname} Operation",
                "Control Scheme 1 Schedule Name": "ALLON"
            }, ignore_default=False),
            # setpoint
            IdfObject("Schedule:Constant", {
                "Name": f"{self.idf_loopname} SetpointTemperature",
                "Hourly Value": self.setpoint_temperature
            }, ignore_default=False),
            IdfObject("SetpointManager:Scheduled", {
                "Name":  f"{self.idf_loopname} SetpointManager",
                "Control Variable": "Temperature",
                "Schedule Name": f"{self.idf_loopname} SetpointTemperature",
                "Setpoint Node or NodeList Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",     
            }, ignore_default=False),
            # availability
            IdfObject("AvailabilityManager:Scheduled", {
                "Name": f"{self.idf_loopname} AvailabilityManager",
                "Schedule Name": "ALLON",
            }, ignore_default=False),
            IdfObject("AvailabilityManagerAssignmentList", {
                "Name": f"{self.idf_loopname} AvailabilityManagerAssignmentList",
                "Availability Manager 1 Object Type": "AvailabilityManager:Scheduled",
                "Availability Manager 1 Name": f"{self.idf_loopname} AvailabilityManager",
            }, ignore_default=False)
        ]
        
        loop = [
            IdfObject("PlantLoop", {
                "Name": self.idf_loopname,
                "Plant Equipment Operation Scheme Name": f"{self.idf_loopname} OperationScheme",
                "Loop Temperature Setpoint Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
                "Maximum Loop Temperature": 80,
                "Minimum Loop Temperature": 0.1,
                "Maximum Loop Flow Rate":"autosize",
                "Plant Side Inlet Node Name" : f"VSDPump_for_{self.idf_objname} Water InletNode",
                "Plant Side Outlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
                "Plant Side Branch List Name": self.idf_supplybranchlistname,
                "Plant Side Connector List Name": f"{self.idf_loopname} Supply Connectors",
                "Demand Side Inlet Node Name" : f"{self.idf_loopname} Demand Inlet Pipe InletNode",
                "Demand Side Outlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe OutletNode",
                "Demand Side Branch List Name": self.idf_demandbranchlistname,
                "Demand Side Connector List Name": f"{self.idf_loopname} Demand Connectors",
                "Availability Manager List Name": f"{self.idf_loopname} AvailabilityManagerAssignmentList"
            }, ignore_default=False),
            IdfObject("Sizing:Plant",{
                "Plant or Condenser Loop Name": self.idf_loopname,
                "Loop Type": "Cooling",
                "Design Loop Exit Temperature": 6,
                "Loop Design Temperature Difference": 4,
            })
        ]
        
        return curve_obj + component_obj + non_functional_pipes + branches + connectors + loop_controls + loop

class CoolingTower(ABC):
    
    def __init__(self,
        name    :str,
        capacity: int|float,
        *,
        pump_efficiency:int|float=0.9,
        ) -> None:
        
        # user properties
        self.name     = name
        
        # fundamental properties
        self.capacity       = capacity
        
        # additional properties
        self.pump_efficiency = pump_efficiency
        
    """ idf-related
    """
    
    def idf_get_objname(self, chiller:Chiller) -> str:
        return f"CT_for_{chiller.idf_objname}"
    
    def idf_get_loopname(self, chiller:Chiller) -> str:
        return f"Loop_for_{self.idf_get_objname(chiller)}"
    
    def idf_get_demandbranchlistname(self, chiller:Chiller) -> str:
        return f"{self.idf_get_loopname(chiller)} Demand BranchList"
    
    def idf_get_demandsplittername(self, chiller:Chiller) -> str:
        return f"{self.idf_get_loopname(chiller)} Demand Splitter"
    
    def idf_get_demandmixername(self, chiller:Chiller) -> str:
        return f"{self.idf_get_loopname(chiller)} Demand Mixer"

    def idf_get_supplybranchlistname(self, chiller:Chiller) -> str:
        return f"{self.idf_get_loopname(chiller)} Supply BranchList"

    def idf_get_supplysplittername(self, chiller:Chiller) -> str:
        return f"{self.idf_get_loopname(chiller)} Supply Splitter"

    def idf_get_supplymixername(self, chiller:Chiller) -> str:
        return f"{self.idf_get_loopname(chiller)} Supply Mixer"
    
    
    @property
    @abstractmethod
    def idf_objtypename(self) -> str: ...
    
    @abstractmethod
    def to_idf_main_object(self, chiller:Chiller) -> list[IdfObject]:
        ...
    
    def to_idf_object(self, chiller:Chiller) -> list[IdfObject]:
        
        component_obj = self.to_idf_main_object(chiller) + [
            IdfObject("Pump:VariableSpeed",{
                "Name": f"VSDPump_for_{self.idf_get_objname(chiller)}",
                "Inlet Node Name" : f"VSDPump_for_{self.idf_get_objname(chiller)} Water InletNode" ,
                "Outlet Node Name": f"VSDPump_for_{self.idf_get_objname(chiller)} Water OutletNode",
                "Design Maximum Flow Rate": "autosize",
                "Motor Efficiency": self.pump_efficiency,
                "Design Power Consumption": "autosize",
            }, ignore_default=False),
        ]
        
        non_functional_pipes = [
            # supply
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_get_loopname(chiller)} Supply Bypass Pipe",
                "Inlet Node Name": f"{self.idf_get_loopname(chiller)} Supply Bypass Pipe InletNode",
                "Outlet Node Name": f"{self.idf_get_loopname(chiller)} Supply Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_get_loopname(chiller)} Supply Outlet Pipe",
                "Inlet Node Name": f"{self.idf_get_loopname(chiller)} Supply Outlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_get_loopname(chiller)} Supply Outlet Pipe OutletNode",
            }, ignore_default=False),
            # demand
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_get_loopname(chiller)} Demand Inlet Pipe",
                "Inlet Node Name": f"{self.idf_get_loopname(chiller)} Demand Inlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_get_loopname(chiller)} Demand Inlet Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_get_loopname(chiller)} Demand Bypass Pipe",
                "Inlet Node Name": f"{self.idf_get_loopname(chiller)} Demand Bypass Pipe InletNode",
                "Outlet Node Name": f"{self.idf_get_loopname(chiller)} Demand Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_get_loopname(chiller)} Demand Outlet Pipe",
                "Inlet Node Name": f"{self.idf_get_loopname(chiller)} Demand Outlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_get_loopname(chiller)} Demand Outlet Pipe OutletNode",
            }, ignore_default=False),
        ]
        
        branches = [
            # supply
            IdfObject("Branch",{
                "Name": f"{self.idf_get_loopname(chiller)} Supply Inlet",
                "Component 1 Object Type": "Pump:VariableSpeed",
                "Component 1 Name": f"VSDPump_for_{self.idf_get_objname(chiller)}",
                "Component 1 Inlet Node Name" : f"VSDPump_for_{self.idf_get_objname(chiller)} Water InletNode" ,
                "Component 1 Outlet Node Name": f"VSDPump_for_{self.idf_get_objname(chiller)} Water OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_get_loopname(chiller)} Supply Bypass",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_get_loopname(chiller)} Supply Bypass Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_get_loopname(chiller)} Supply Bypass Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_get_loopname(chiller)} Supply Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_get_loopname(chiller)} Supply MainComponent",
                "Component 1 Object Type": self.idf_objtypename,
                "Component 1 Name": self.idf_get_objname(chiller),
                "Component 1 Inlet Node Name" : f"{self.idf_get_objname(chiller)} Water InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_get_objname(chiller)} Water OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_get_loopname(chiller)} Supply Outlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_get_loopname(chiller)} Supply Outlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_get_loopname(chiller)} Supply Outlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_get_loopname(chiller)} Supply Outlet Pipe OutletNode",
            }, ignore_default=False),
            # supply: list
            IdfObject("BranchList", {
               "Name": self.idf_get_supplybranchlistname(chiller),
               "Branch 1 Name": f"{self.idf_get_loopname(chiller)} Supply Inlet",
               "Branch 2 Name": f"{self.idf_get_loopname(chiller)} Supply Bypass",
               "Branch 3 Name": f"{self.idf_get_loopname(chiller)} Supply MainComponent",
               "Branch 4 Name": f"{self.idf_get_loopname(chiller)} Supply Outlet",
            }, ignore_default=False),
            # demand
            IdfObject("Branch",{
                "Name": f"{self.idf_get_loopname(chiller)} Demand Inlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_get_loopname(chiller)} Demand Inlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_get_loopname(chiller)} Demand Inlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_get_loopname(chiller)} Demand Inlet Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_get_loopname(chiller)} Demand Bypass",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_get_loopname(chiller)} Demand Bypass Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_get_loopname(chiller)} Demand Bypass Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_get_loopname(chiller)} Demand Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_get_loopname(chiller)} Demand MainChiller",
                "Component 1 Object Type": chiller.idf_objtypename,
                "Component 1 Name": chiller.idf_objname,
                "Component 1 Inlet Node Name" : f"{chiller.idf_objname} Condenser InletNode",
                "Component 1 Outlet Node Name": f"{chiller.idf_objname} Condenser OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_get_loopname(chiller)} Demand Outlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_get_loopname(chiller)} Demand Outlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_get_loopname(chiller)} Demand Outlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_get_loopname(chiller)} Demand Outlet Pipe OutletNode",
            }, ignore_default=False),
            # demand: list
            IdfObject("BranchList", {
               "Name": self.idf_get_demandbranchlistname(chiller),
               "Branch 1 Name": f"{self.idf_get_loopname(chiller)} Demand Inlet",
               "Branch 2 Name": f"{self.idf_get_loopname(chiller)} Demand Bypass",
               "Branch 3 Name": f"{self.idf_get_loopname(chiller)} Demand MainChiller",
               "Branch 4 Name": f"{self.idf_get_loopname(chiller)} Demand Outlet",
            }, ignore_default=False),
        ]
        
        connectors = [
            # supply
            IdfObject("Connector:Splitter", {
                "Name": self.idf_get_supplysplittername(chiller),
                "Inlet Branch Name": f"{self.idf_get_loopname(chiller)} Supply Inlet",
                "Outlet Branch 1 Name": f"{self.idf_get_loopname(chiller)} Supply MainComponent",
                "Outlet Branch 2 Name": f"{self.idf_get_loopname(chiller)} Supply Bypass",
            }, ignore_default=False),
            IdfObject("Connector:Mixer", {
                "Name": self.idf_get_supplymixername(chiller),
                "Outlet Branch Name": f"{self.idf_get_loopname(chiller)} Supply Outlet",
                "Inlet Branch 1 Name": f"{self.idf_get_loopname(chiller)} Supply MainComponent",
                "Inlet Branch 2 Name": f"{self.idf_get_loopname(chiller)} Supply Bypass",
            }, ignore_default=False),
            IdfObject("ConnectorList",{
                "Name": f"{self.idf_get_loopname(chiller)} Supply Connectors",
                "Connector 1 Object Type": "Connector:Splitter",
                "Connector 1 Name"       : self.idf_get_supplysplittername(chiller),
                "Connector 2 Object Type": "Connector:Mixer",
                "Connector 2 Name"       : self.idf_get_supplymixername(chiller),
            }, ignore_default=False),
            # demand
            IdfObject("Connector:Splitter", {
                "Name": self.idf_get_demandsplittername(chiller),
                "Inlet Branch Name": f"{self.idf_get_loopname(chiller)} Demand Inlet",
                "Outlet Branch 1 Name": f"{self.idf_get_loopname(chiller)} Demand Bypass",
                "Outlet Branch 2 Name": f"{self.idf_get_loopname(chiller)} Demand MainChiller",
            }, ignore_default=False),
            IdfObject("Connector:Mixer", {
                "Name": self.idf_get_demandmixername(chiller),
                "Outlet Branch Name": f"{self.idf_get_loopname(chiller)} Demand Outlet",
                "Inlet Branch 1 Name": f"{self.idf_get_loopname(chiller)} Demand Bypass",
                "Inlet Branch 2 Name": f"{self.idf_get_loopname(chiller)} Demand MainChiller",
            }, ignore_default=False),
            IdfObject("ConnectorList",{
                "Name": f"{self.idf_get_loopname(chiller)} Demand Connectors",
                "Connector 1 Object Type": "Connector:Splitter",
                "Connector 1 Name"       : self.idf_get_demandsplittername(chiller),
                "Connector 2 Object Type": "Connector:Mixer",
                "Connector 2 Name"       : self.idf_get_demandmixername(chiller),
            }, ignore_default=False),
        ]
        
        loop_controls = [
            # load distribution
            IdfObject("CondenserEquipmentList", {
                "Name": f"{self.idf_get_loopname(chiller)} EquipmentList",
                "Equipment 1 Object Type": self.idf_objtypename,
                "Equipment 1 Name": self.idf_get_objname(chiller),
            }, ignore_default=False),
            IdfObject("PlantEquipmentOperation:CoolingLoad", {
                "Name": f"{self.idf_get_loopname(chiller)} Operation",
                "Load Range 1 Lower Limit":    0,
                "Load Range 1 Upper Limit": 1E20,
                "Range 1 Equipment List Name": f"{self.idf_get_loopname(chiller)} EquipmentList",
            }, ignore_default=False),
            IdfObject("CondenserEquipmentOperationSchemes", {
                "Name": f"{self.idf_get_loopname(chiller)} OperationScheme",
                "Control Scheme 1 Object Type": "PlantEquipmentOperation:CoolingLoad",
                "Control Scheme 1 Name": f"{self.idf_get_loopname(chiller)} Operation",
                "Control Scheme 1 Schedule Name": "ALLON"
            }, ignore_default=False),
            # setpoint
            IdfObject("SetpointManager:FollowOutdoorAirTemperature", {
                "Name":  f"{self.idf_get_loopname(chiller)} SetpointManager",
                "Offset Temperature Difference": 1.5,
                "Maximum Setpoint Temperature": 50,
                "Minimum Setpoint Temperature": 20,
                "Setpoint Node or NodeList Name": f"{self.idf_get_loopname(chiller)} Supply Outlet Pipe OutletNode",     
            }, ignore_default=False),
        ]
        
        loop = [
            IdfObject("CondenserLoop", {
                "Name": self.idf_get_loopname(chiller),
                "Condenser Equipment Operation Scheme Name": f"{self.idf_get_loopname(chiller)} OperationScheme",
                "Condenser Loop Temperature Setpoint Node Name": f"{self.idf_get_loopname(chiller)} Supply Outlet Pipe OutletNode",
                "Maximum Loop Temperature": 50,
                "Minimum Loop Temperature":  5,
                "Maximum Loop Flow Rate":"autosize",
                "Minimum Loop Flow Rate": 0,
                "Condenser Side Inlet Node Name" : f"VSDPump_for_{self.idf_get_objname(chiller)} Water InletNode",
                "Condenser Side Outlet Node Name": f"{self.idf_get_loopname(chiller)} Supply Outlet Pipe OutletNode",
                "Condenser Side Branch List Name": self.idf_get_supplybranchlistname(chiller),
                "Condenser Side Connector List Name": f"{self.idf_get_loopname(chiller)} Supply Connectors",
                "Demand Side Inlet Node Name" : f"{self.idf_get_loopname(chiller)} Demand Inlet Pipe InletNode",
                "Demand Side Outlet Node Name": f"{self.idf_get_loopname(chiller)} Demand Outlet Pipe OutletNode",
                "Condenser Demand Side Branch List Name": self.idf_get_demandbranchlistname(chiller),
                "Condenser Demand Side Connector List Name": f"{self.idf_get_loopname(chiller)} Demand Connectors",
            }, ignore_default=False),
            IdfObject("Sizing:Plant",{
                "Plant or Condenser Loop Name": self.idf_get_loopname(chiller),
                "Loop Type": "Condenser",
                "Design Loop Exit Temperature": 29,
                "Loop Design Temperature Difference": 5,
            })
        ]
        
        return component_obj + non_functional_pipes + branches + connectors + loop_controls + loop
    

class OpenSingleSpeedCoolingTower(CoolingTower):
    
    @property
    def idf_objtypename(self) -> str: 
        return "CoolingTower:SingleSpeed"
    
    def to_idf_main_object(self, chiller:Chiller) -> list[IdfObject]: 

        return [
            IdfObject(self.idf_objtypename, {
                "Name": self.idf_get_objname(chiller),
                "Water Inlet Node Name": f"{self.idf_get_objname(chiller)} Water InletNode",
                "Water Outlet Node Name": f"{self.idf_get_objname(chiller)} Water OutletNode",
                "Design Water Flow Rate"          : "autosize",
                "Design Air Flow Rate"            : "autosize",
                "Design Fan Power"                : "autosize",
                "Design U-Factor Times Area Value": "autosize",
                "Free Convection Regime Air FLow Rate"            : "autocalculate",
                "Free Convection Regime U-Factor Times Area Value": "autocalculate",
                "Nominal Capacity": self.capacity if self.capacity is not None else (chiller.capacity if chiller.capacity is not None else 1E6),
                "Free Convection Capacity": "autocalculate",
                "Blowdown Makeup Water Usage Schedule Name": "ALLON"
            }, ignore_default=False)
        ]
        
class OpenTwoSpeedCoolingTower(CoolingTower):
    
    @property
    def idf_objtypename(self) -> str: 
        return "CoolingTower:TwoSpeed"
    
    def to_idf_main_object(self, chiller:Chiller) -> list[IdfObject]: 

        return [
            IdfObject(self.idf_objtypename, {
                "Name": self.idf_get_objname(chiller),
                "Water Inlet Node Name": f"{self.idf_get_objname(chiller)} Water InletNode",
                "Water Outlet Node Name": f"{self.idf_get_objname(chiller)} Water OutletNode",
                "Design Water Flow Rate"          : "autosize",
                "High Fan Speed Air Flow Rate"            : "autosize",
                "High Fan Speed Fan Power"                : "autosize",
                "High Fan Speed U-Factor Times Area Value": "autosize",
                "Low Fan Speed Air Flow Rate"            : "autocalculate",
                "Low Fan Speed Fan Power"                : "autocalculate",
                "Low Fan Speed U-Factor Times Area Value": "autocalculate",
                "Free Convection Regime Air FLow Rate"            : "autocalculate",
                "Free Convection Regime U-Factor Times Area Value": "autocalculate",
                "High Speed Nominal Capacity": self.capacity if self.capacity is not None else (chiller.capacity if chiller.capacity is not None else 1E6),
                "Low Speed Nominal Capacity": "autocalculate",
                "Free Convection Nominal Capacity": "autocalculate",
                "Blowdown Makeup Water Usage Schedule Name": "ALLON"
            }, ignore_default=False)
        ]
class ClosedSingleSpeedCoolingTower(CoolingTower):
    
    @property
    def idf_objtypename(self) -> str: 
        return "FluidCooler:SingleSpeed"
    
    def to_idf_main_object(self, chiller:Chiller) -> list[IdfObject]: 

        return [
            IdfObject(self.idf_objtypename, {
                "Name": self.idf_get_objname(chiller),
                "Water Inlet Node Name": f"{self.idf_get_objname(chiller)} Water InletNode",
                "Water Outlet Node Name": f"{self.idf_get_objname(chiller)} Water OutletNode",
                "Design Air Flow Rate U-Factor Times Area Value": "autosize",
                "Nominal Capacity": self.capacity if self.capacity is not None else (chiller.capacity if chiller.capacity is not None else 1E6),
                "Design Entering Water Temperature": 35,
                "Design Entering Air Temperature"  : 28,
                "Design Entering Air WetBulb Temperature": 25.56,
                "Design Water Flow Rate"          : "autosize",
                "Design Air Flow Rate"            : "autosize",
                "Design Air Flow Rate Fan Power"  : "autosize",
            })
        ]
class ClosedTwoSpeedCoolingTower(CoolingTower):
    
    @property
    def idf_objtypename(self) -> str: 
        return "FluidCooler:TwoSpeed"
    
    def to_idf_main_object(self, chiller:Chiller) -> list[IdfObject]: 

        return [
            IdfObject(self.idf_objtypename, {
                "Name": self.idf_get_objname(chiller),
                "Water Inlet Node Name": f"{self.idf_get_objname(chiller)} Water InletNode",
                "Water Outlet Node Name": f"{self.idf_get_objname(chiller)} Water OutletNode",
                "Performance Input Method": "UFactorTimesAreaAndDesignWaterFlowRate",
                "High Fan Speed U-Factor Times Area Value": "autosize",
                "Low Fan Speed U-Factor Times Area Value": "autocalculate",
                "Design Entering Water Temperature": 35,
                "Design Entering Air Temperature"  : 28,
                "Design Entering Air Wet-Bulb Temperature": 25.56,
                "Design Water Flow Rate"          : "autosize",
                "High Fan Speed Air Flow Rate"            : "autosize",
                "High Fan Speed Fan Power"                : "autosize",
                "Low Fan Speed Air Flow Rate"            : "autocalculate",
                "Low Fan Speed Fan Power"                : "autocalculate",
            })
        ]

class AbsorptionChiller(SourceSystem):
    
    def __init__(self,
        name:str,
        cop         :int|float,
        capacity    :int|float,
        heatsource  :Boiler   ,
        coolingtower:CoolingTower,
        *,
        pump_efficiency:int|float=0.9,
        setpoint_temperature:int|float=6,
        ) -> None: 
        
        # user properties
        self.name = name
        
        # fundamental properties
        self.cop          = cop
        self.capacity     = capacity
        self.heatsource   = heatsource
        self.coolingtower = coolingtower
        
        # additional properties
        self.pump_efficiency = pump_efficiency
        self.setpoint_temperature = setpoint_temperature
    
    @property
    def idf_objtypename(self) -> str: 
        return "Chiller:Absorption"

    def to_idf_object(self) -> list[IdfObject]:
                
        component_obj = [
            IdfObject(self.idf_objtypename, {
                "Name": self.idf_objname,
                "Nominal Capacity": self.capacity if self.capacity is not None else "autosize",
                "Nominal Pumping Power": "autosize",
                "Chilled Water Inlet Node Name" : f"{self.idf_objname} ChilledWater InletNode" ,
                "Chilled Water Outlet Node Name": f"{self.idf_objname} ChilledWater OutletNode",
                "Condenser Inlet Node Name" : f"{self.idf_objname} Condenser InletNode" ,
                "Condenser Outlet Node Name": f"{self.idf_objname} Condenser OutletNode",
                "Minimum Part Load Ratio": 0.15,
                "Maximum Part Load Ratio": 1,
                "Optimum Part Load Ratio": 0.65,
                "Design Condenser Inlet Temperature": 35,
                "Design Chilled Water Flow Rate"  : "autosize",
                "Design Condenser Water Flow Rate": "autosize",
                "Coefficient 1 of the Hot Water or Steam Use Part Load Ratio Curve": 0.03303 / self.cop,
                "Coefficient 2 of the Hot Water or Steam Use Part Load Ratio Curve": 0.6852  / self.cop,
                "Coefficient 3 of the Hot Water or Steam Use Part Load Ratio Curve": 0.2818  / self.cop,
                "Coefficient 1 of the Pump Electric Use Part Load Ratio Curve": 1,
                "Coefficient 2 of the Pump Electric Use Part Load Ratio Curve": 0,
                "Coefficient 3 of the Pump Electric Use Part Load Ratio Curve": 0,
                "Chilled Water Outlet Temperature Lower Limit": 5,
                "Generator Inlet Node Name" : f"{self.idf_objname} Generator InletNode",
                "Generator Outlet Node Name": f"{self.idf_objname} Generator OutletNode",
                "Generator Heat Source Type": "HotWater",
                "Design Generator Fluid Flow Rate": "autosize",
            }),
            IdfObject("Pump:VariableSpeed",{
                "Name": f"VSDPump_for_{self.idf_objname}",
                "Inlet Node Name" : f"VSDPump_for_{self.idf_objname} Water InletNode" ,
                "Outlet Node Name": f"VSDPump_for_{self.idf_objname} Water OutletNode",
                "Design Maximum Flow Rate": "autosize",
                "Motor Efficiency": self.pump_efficiency,
                "Design Power Consumption": "autosize",
            }, ignore_default=False),
        ]
        
        non_functional_pipes = [
            # supply
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Supply Bypass Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Supply Bypass Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Supply Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Supply Outlet Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
            }, ignore_default=False),
            # demand
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Demand Inlet Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Demand Inlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Demand Inlet Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Demand Bypass Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Demand Bypass Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Demand Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Demand Outlet Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe OutletNode",
            }, ignore_default=False),
        ]
        
        branches = [
            # supply
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply Inlet",
                "Component 1 Object Type": "Pump:VariableSpeed",
                "Component 1 Name": f"VSDPump_for_{self.idf_objname}",
                "Component 1 Inlet Node Name" : f"VSDPump_for_{self.idf_objname} Water InletNode" ,
                "Component 1 Outlet Node Name": f"VSDPump_for_{self.idf_objname} Water OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply Bypass",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Supply Bypass Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Supply Bypass Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Supply Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply MainComponent",
                "Component 1 Object Type": self.idf_objtypename,
                "Component 1 Name": self.idf_objname,
                "Component 1 Inlet Node Name" : f"{self.idf_objname} ChilledWater InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_objname} ChilledWater OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply Outlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Supply Outlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Supply Outlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
            }, ignore_default=False),
            # supply: list
            IdfObject("BranchList", {
               "Name": self.idf_supplybranchlistname,
               "Branch 1 Name": f"{self.idf_loopname} Supply Inlet",
               "Branch 2 Name": f"{self.idf_loopname} Supply Bypass",
               "Branch 3 Name": f"{self.idf_loopname} Supply MainComponent",
               "Branch 4 Name": f"{self.idf_loopname} Supply Outlet",
            }, ignore_default=False),
            # demand
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Demand Inlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Demand Inlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Demand Inlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Demand Inlet Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Demand Bypass",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Demand Bypass Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Demand Bypass Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Demand Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Demand Outlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Demand Outlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Demand Outlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe OutletNode",
            }, ignore_default=False),
            # demand: list
            IdfObject("BranchList", {
               "Name": self.idf_demandbranchlistname,
               "Branch 1 Name": f"{self.idf_loopname} Demand Inlet",
               "Branch 2 Name": f"{self.idf_loopname} Demand Bypass",
               "Branch 3 Name": f"{self.idf_loopname} Demand Outlet",
            }, ignore_default=False),
        ]
        
        connectors = [
            # supply
            IdfObject("Connector:Splitter", {
                "Name": self.idf_supplysplittername,
                "Inlet Branch Name": f"{self.idf_loopname} Supply Inlet",
                "Outlet Branch 1 Name": f"{self.idf_loopname} Supply MainComponent",
                "Outlet Branch 2 Name": f"{self.idf_loopname} Supply Bypass",
            }, ignore_default=False),
            IdfObject("Connector:Mixer", {
                "Name": self.idf_supplymixername,
                "Outlet Branch Name": f"{self.idf_loopname} Supply Outlet",
                "Inlet Branch 1 Name": f"{self.idf_loopname} Supply MainComponent",
                "Inlet Branch 2 Name": f"{self.idf_loopname} Supply Bypass",
            }, ignore_default=False),
            IdfObject("ConnectorList",{
                "Name": f"{self.idf_loopname} Supply Connectors",
                "Connector 1 Object Type": "Connector:Splitter",
                "Connector 1 Name"       : self.idf_supplysplittername,
                "Connector 2 Object Type": "Connector:Mixer",
                "Connector 2 Name"       : self.idf_supplymixername,
            }, ignore_default=False),
            # demand
            IdfObject("Connector:Splitter", {
                "Name": self.idf_demandsplittername,
                "Inlet Branch Name": f"{self.idf_loopname} Demand Inlet",
                "Outlet Branch 1 Name": f"{self.idf_loopname} Demand Bypass",
            }, ignore_default=False),
            IdfObject("Connector:Mixer", {
                "Name": self.idf_demandmixername,
                "Outlet Branch Name": f"{self.idf_loopname} Demand Outlet",
                "Inlet Branch 1 Name": f"{self.idf_loopname} Demand Bypass",
            }, ignore_default=False),
            IdfObject("ConnectorList",{
                "Name": f"{self.idf_loopname} Demand Connectors",
                "Connector 1 Object Type": "Connector:Splitter",
                "Connector 1 Name"       : self.idf_demandsplittername,
                "Connector 2 Object Type": "Connector:Mixer",
                "Connector 2 Name"       : self.idf_demandmixername,
            }, ignore_default=False),
        ]
        
        loop_controls = [
            # load distribution
            IdfObject("PlantEquipmentList", {
                "Name": f"{self.idf_loopname} EquipmentList",
                "Equipment 1 Object Type": self.idf_objtypename,
                "Equipment 1 Name": self.idf_objname
            }, ignore_default=False),
            IdfObject("PlantEquipmentOperation:CoolingLoad", {
                "Name": f"{self.idf_loopname} Operation",
                "Load Range 1 Lower Limit":    0,
                "Load Range 1 Upper Limit": 1E20,
                "Range 1 Equipment List Name": f"{self.idf_loopname} EquipmentList",
            }, ignore_default=False),
            IdfObject("PlantEquipmentOperationSchemes", {
                "Name": f"{self.idf_loopname} OperationScheme",
                "Control Scheme 1 Object Type": "PlantEquipmentOperation:CoolingLoad",
                "Control Scheme 1 Name": f"{self.idf_loopname} Operation",
                "Control Scheme 1 Schedule Name": "ALLON"
            }, ignore_default=False),
            # setpoint
            IdfObject("Schedule:Constant", {
                "Name": f"{self.idf_loopname} SetpointTemperature",
                "Hourly Value": self.setpoint_temperature
            }, ignore_default=False),
            IdfObject("SetpointManager:Scheduled", {
                "Name":  f"{self.idf_loopname} SetpointManager",
                "Control Variable": "Temperature",
                "Schedule Name": f"{self.idf_loopname} SetpointTemperature",
                "Setpoint Node or NodeList Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",     
            }, ignore_default=False),
            # availability
            IdfObject("AvailabilityManager:Scheduled", {
                "Name": f"{self.idf_loopname} AvailabilityManager",
                "Schedule Name": "ALLON",
            }, ignore_default=False),
            IdfObject("AvailabilityManagerAssignmentList", {
                "Name": f"{self.idf_loopname} AvailabilityManagerAssignmentList",
                "Availability Manager 1 Object Type": "AvailabilityManager:Scheduled",
                "Availability Manager 1 Name": f"{self.idf_loopname} AvailabilityManager",
            }, ignore_default=False)
        ]
        
        subloop_obj = self.heatsource.to_idf_object_as_generator(self) + self.coolingtower.to_idf_object(self)
        
        loop_obj = [
            IdfObject("PlantLoop", {
                "Name": self.idf_loopname,
                "Plant Equipment Operation Scheme Name": f"{self.idf_loopname} OperationScheme",
                "Loop Temperature Setpoint Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
                "Maximum Loop Temperature": 80,
                "Minimum Loop Temperature": 0.1,
                "Maximum Loop Flow Rate":"autosize",
                "Plant Side Inlet Node Name" : f"VSDPump_for_{self.idf_objname} Water InletNode",
                "Plant Side Outlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
                "Plant Side Branch List Name": self.idf_supplybranchlistname,
                "Plant Side Connector List Name": f"{self.idf_loopname} Supply Connectors",
                "Demand Side Inlet Node Name" : f"{self.idf_loopname} Demand Inlet Pipe InletNode",
                "Demand Side Outlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe OutletNode",
                "Demand Side Branch List Name": self.idf_demandbranchlistname,
                "Demand Side Connector List Name": f"{self.idf_loopname} Demand Connectors",
                "Availability Manager List Name": f"{self.idf_loopname} AvailabilityManagerAssignmentList"
            }, ignore_default=False),
            IdfObject("Sizing:Plant",{
                "Plant or Condenser Loop Name": self.idf_loopname,
                "Loop Type": "Cooling",
                "Design Loop Exit Temperature": 6,
                "Loop Design Temperature Difference": 4,
            })
        ]
        
        return component_obj+non_functional_pipes+branches+connectors+loop_controls+subloop_obj+loop_obj

class Boiler(SourceSystem):
    
    def __init__(self,
        name:str,
        fuel      :Fuel,
        efficiency:int|float,
        capacity  :int|float|None=None,
        *,
        pump_efficiency     :int|float = 0.9,
        setpoint_temperature:int|float = 60
        ) -> None:
        
        self.name = name
        self.fuel = fuel
        self.efficiency = efficiency
        self.capacity   = capacity
        
        self.pump_efficiency = pump_efficiency
        self.setpoint_temperature = setpoint_temperature
    
    """ idf-related
    """
    
    @property
    def idf_objtypename(self) -> str:
        return "Boiler:HotWater"
        
    def to_idf_object(self) -> list[IdfObject]:
        
        components = [
            IdfObject("Boiler:HotWater",{
                "Name": self.idf_objname,
                "Fuel Type": self.fuel.to_idf_name(),
                "Nominal Capacity": self.capacity if self.capacity is not None else "autosize",
                "Nominal Thermal Efficiency": self.efficiency,
                "Efficiency Curve Temperature Evaluation Variable": "LeavingBoiler",
                "Boiler Water Inlet Node Name" : f"{self.idf_objname} Water InletNode" ,
                "Boiler Water Outlet Node Name": f"{self.idf_objname} Water OutletNode",
            }, ignore_default=False),
            IdfObject("Pump:VariableSpeed",{
                "Name": f"VSDPump_for_{self.idf_objname}",
                "Inlet Node Name" : f"VSDPump_for_{self.idf_objname} Water InletNode" ,
                "Outlet Node Name": f"VSDPump_for_{self.idf_objname} Water OutletNode",
                "Design Maximum Flow Rate": "autosize",
                "Motor Efficiency": self.pump_efficiency,
                "Design Power Consumption": "autosize",
            }, ignore_default=False),
        ]
        
        non_functional_pipes = [
            # supply
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Supply Bypass Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Supply Bypass Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Supply Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Supply Outlet Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
            }, ignore_default=False),
            # demand
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Demand Inlet Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Demand Inlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Demand Inlet Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Demand Bypass Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Demand Bypass Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Demand Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Pipe:Adiabatic",{
                "Name": f"{self.idf_loopname} Demand Outlet Pipe",
                "Inlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe InletNode",
                "Outlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe OutletNode",
            }, ignore_default=False),
        ]
        
        branches = [
            # supply
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply Inlet",
                "Component 1 Object Type": "Pump:VariableSpeed",
                "Component 1 Name": f"VSDPump_for_{self.idf_objname}",
                "Component 1 Inlet Node Name" : f"VSDPump_for_{self.idf_objname} Water InletNode" ,
                "Component 1 Outlet Node Name": f"VSDPump_for_{self.idf_objname} Water OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply Bypass",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Supply Bypass Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Supply Bypass Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Supply Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply MainComponent",
                "Component 1 Object Type": "Boiler:HotWater",
                "Component 1 Name": self.idf_objname,
                "Component 1 Inlet Node Name" : f"{self.idf_objname} Water InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_objname} Water OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Supply Outlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Supply Outlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Supply Outlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
            }, ignore_default=False),
            # supply: list
            IdfObject("BranchList", {
               "Name": self.idf_supplybranchlistname,
               "Branch 1 Name": f"{self.idf_loopname} Supply Inlet",
               "Branch 2 Name": f"{self.idf_loopname} Supply Bypass",
               "Branch 3 Name": f"{self.idf_loopname} Supply MainComponent",
               "Branch 4 Name": f"{self.idf_loopname} Supply Outlet",
            }, ignore_default=False),
            # demand
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Demand Inlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Demand Inlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Demand Inlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Demand Inlet Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Demand Bypass",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Demand Bypass Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Demand Bypass Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Demand Bypass Pipe OutletNode",
            }, ignore_default=False),
            IdfObject("Branch",{
                "Name": f"{self.idf_loopname} Demand Outlet",
                "Component 1 Object Type": "Pipe:Adiabatic",
                "Component 1 Name": f"{self.idf_loopname} Demand Outlet Pipe",
                "Component 1 Inlet Node Name" : f"{self.idf_loopname} Demand Outlet Pipe InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe OutletNode",
            }, ignore_default=False),
            # demand: list
            IdfObject("BranchList", {
               "Name": self.idf_demandbranchlistname,
               "Branch 1 Name": f"{self.idf_loopname} Demand Inlet",
               "Branch 2 Name": f"{self.idf_loopname} Demand Bypass",
               "Branch 3 Name": f"{self.idf_loopname} Demand Outlet",
            }, ignore_default=False),
        ]
        
        connectors = [
            # supply
            IdfObject("Connector:Splitter", {
                "Name": self.idf_supplysplittername,
                "Inlet Branch Name": f"{self.idf_loopname} Supply Inlet",
                "Outlet Branch 1 Name": f"{self.idf_loopname} Supply MainComponent",
                "Outlet Branch 2 Name": f"{self.idf_loopname} Supply Bypass",
            }, ignore_default=False),
            IdfObject("Connector:Mixer", {
                "Name": self.idf_supplymixername,
                "Outlet Branch Name": f"{self.idf_loopname} Supply Outlet",
                "Inlet Branch 1 Name": f"{self.idf_loopname} Supply MainComponent",
                "Inlet Branch 2 Name": f"{self.idf_loopname} Supply Bypass",
            }, ignore_default=False),
            IdfObject("ConnectorList",{
                "Name": f"{self.idf_loopname} Supply Connectors",
                "Connector 1 Object Type": "Connector:Splitter",
                "Connector 1 Name"       : self.idf_supplysplittername,
                "Connector 2 Object Type": "Connector:Mixer",
                "Connector 2 Name"       : self.idf_supplymixername,
            }, ignore_default=False),
            # demand
            IdfObject("Connector:Splitter", {
                "Name": self.idf_demandsplittername,
                "Inlet Branch Name": f"{self.idf_loopname} Demand Inlet",
                "Outlet Branch 1 Name": f"{self.idf_loopname} Demand Bypass",
            }, ignore_default=False),
            IdfObject("Connector:Mixer", {
                "Name": self.idf_demandmixername,
                "Outlet Branch Name": f"{self.idf_loopname} Demand Outlet",
                "Inlet Branch 1 Name": f"{self.idf_loopname} Demand Bypass",
            }, ignore_default=False),
            IdfObject("ConnectorList",{
                "Name": f"{self.idf_loopname} Demand Connectors",
                "Connector 1 Object Type": "Connector:Splitter",
                "Connector 1 Name"       : self.idf_demandsplittername,
                "Connector 2 Object Type": "Connector:Mixer",
                "Connector 2 Name"       : self.idf_demandmixername,
            }, ignore_default=False),
        ]
        
        loop_controls = [
            # load distribution
            IdfObject("PlantEquipmentList", {
                "Name": f"{self.idf_loopname} EquipmentList",
                "Equipment 1 Object Type": "Boiler:HotWater",
                "Equipment 1 Name": self.idf_objname
            }, ignore_default=False),
            IdfObject("PlantEquipmentOperation:HeatingLoad", {
                "Name": f"{self.idf_loopname} Operation",
                "Load Range 1 Lower Limit":    0,
                "Load Range 1 Upper Limit": 1E20,
                "Range 1 Equipment List Name": f"{self.idf_loopname} EquipmentList",
            }, ignore_default=False),
            IdfObject("PlantEquipmentOperationSchemes", {
                "Name": f"{self.idf_loopname} OperationScheme",
                "Control Scheme 1 Object Type": "PlantEquipmentOperation:HeatingLoad",
                "Control Scheme 1 Name": f"{self.idf_loopname} Operation",
                "Control Scheme 1 Schedule Name": "ALLON"
            }, ignore_default=False),
            # setpoint
            IdfObject("Schedule:Constant", {
                "Name": f"{self.idf_loopname} SetpointTemperature",
                "Hourly Value": self.setpoint_temperature
            }, ignore_default=False),
            IdfObject("SetpointManager:Scheduled", {
                "Name":  f"{self.idf_loopname} SetpointManager",
                "Control Variable": "Temperature",
                "Schedule Name": f"{self.idf_loopname} SetpointTemperature",
                "Setpoint Node or NodeList Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",     
            }, ignore_default=False),
            # availability
            IdfObject("AvailabilityManager:Scheduled", {
                "Name": f"{self.idf_loopname} AvailabilityManager",
                "Schedule Name": "ALLON",
            }, ignore_default=False),
            IdfObject("AvailabilityManagerAssignmentList", {
                "Name": f"{self.idf_loopname} AvailabilityManagerAssignmentList",
                "Availability Manager 1 Object Type": "AvailabilityManager:Scheduled",
                "Availability Manager 1 Name": f"{self.idf_loopname} AvailabilityManager",
            }, ignore_default=False)
        ]
        
        loop = [
            IdfObject("PlantLoop", {
                "Name": self.idf_loopname,
                "Plant Equipment Operation Scheme Name": f"{self.idf_loopname} OperationScheme",
                "Loop Temperature Setpoint Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
                "Maximum Loop Temperature": 99.9,
                "Minimum Loop Temperature":  0.1,
                "Maximum Loop Flow Rate":"autosize",
                "Plant Side Inlet Node Name" : f"VSDPump_for_{self.idf_objname} Water InletNode",
                "Plant Side Outlet Node Name": f"{self.idf_loopname} Supply Outlet Pipe OutletNode",
                "Plant Side Branch List Name": self.idf_supplybranchlistname,
                "Plant Side Connector List Name": f"{self.idf_loopname} Supply Connectors",
                "Demand Side Inlet Node Name" : f"{self.idf_loopname} Demand Inlet Pipe InletNode",
                "Demand Side Outlet Node Name": f"{self.idf_loopname} Demand Outlet Pipe OutletNode",
                "Demand Side Branch List Name": self.idf_demandbranchlistname,
                "Demand Side Connector List Name": f"{self.idf_loopname} Demand Connectors",
                "Availability Manager List Name": f"{self.idf_loopname} AvailabilityManagerAssignmentList"
            }, ignore_default=False),
            IdfObject("Sizing:Plant",{
                "Plant or Condenser Loop Name": self.idf_loopname,
                "Loop Type": "Heating",
                "Design Loop Exit Temperature": 80,
                "Loop Design Temperature Difference": 10,
            })
        ]
        
        return components + non_functional_pipes + branches + connectors + loop_controls + loop

    def to_idf_object_as_generator(self, target:AbsorptionChiller):
        
        subloop_obj = self.to_idf_object()
        
        generatorbranch_name = f"{self.idf_loopname} Demand MainGenerator"
        generatorbranch_obj = [
            IdfObject("Branch", {
                    "Name": generatorbranch_name,
                    "Component 1 Object Type": "Chiller:Absorption",
                    "Component 1 Name": target.idf_objname,
                    "Component 1 Inlet Node Name" : f"{target.idf_objname} Generator InletNode",
                    "Component 1 Outlet Node Name": f"{target.idf_objname} Generator OutletNode",
                }),
        ]
        
         # splitter
        subloop_demandspliter_obj = [obj for obj in subloop_obj if (obj.idd.name == "Connector:Splitter") and obj["Name"] == self.idf_demandsplittername][0]
        num_current_branches = DemandBranchAppender.count_current_branches_connector(subloop_demandspliter_obj)
        subloop_demandspliter_obj[f"Outlet Branch {num_current_branches+1} Name"] = generatorbranch_name
        
        # mixer
        subloop_demandmixer_obj = [obj for obj in subloop_obj if (obj.idd.name == "Connector:Mixer") and obj["Name"] == self.idf_demandmixername][0]
        num_current_branches = DemandBranchAppender.count_current_branches_connector(subloop_demandmixer_obj)
        subloop_demandmixer_obj[f"Inlet Branch {num_current_branches+1} Name"] = generatorbranch_name
        
        # branchlist
        subloop_demandbranchlist_obj = [obj for obj in subloop_obj if (obj.idd.name == "BranchList") and obj["Name"] == self.idf_demandbranchlistname][0]
        num_current_branches = DemandBranchAppender.count_current_branches_branchlist(subloop_demandbranchlist_obj)
        lastbranch = subloop_demandbranchlist_obj[f"Branch {num_current_branches} Name"]
        subloop_demandbranchlist_obj[f"Branch {num_current_branches} Name"] = generatorbranch_name
        subloop_demandbranchlist_obj[f"Branch {num_current_branches+1} Name"] = lastbranch
        
        return subloop_obj + generatorbranch_obj
        
# ---------------------------------------------------------------------------- #
#                                SUPPLY SYSTEMS                                #
# ---------------------------------------------------------------------------- #


class SupplySystemToIdfPostProcessor(ABC):
    
    @final
    def __init__(self,
        supply:SupplySystem,
        zone  :Zone        ,
        ) -> None:
        
        self.zone   = zone
        self.supply = supply
        self.source = supply.source
    
    @abstractmethod
    def run(self, idf:IDF) -> None: ...
    
    
    
class DemandBranchAppender(SupplySystemToIdfPostProcessor):
    
    @staticmethod
    def count_current_branches_connector(splitter_or_mixer:IdfObject) -> int:
        
        # calculate all items inlcuded
        not_none_items = len({k:v for k,v in splitter_or_mixer.items() if v is not None})
        
        # exclude its name and inlet(splitter)/outlet(mixer) name
        FIXED_NONBRANCH_ITEMS = 2
        
        return not_none_items - FIXED_NONBRANCH_ITEMS
    
    @staticmethod
    def count_current_branches_branchlist(branchlist:IdfObject) -> int:
        
        # calculate all items inlcuded
        not_none_items = len({k:v for k,v in branchlist.items() if v is not None})
        
        # exclude its name 
        FIXED_NONBRANCH_ITEMS = 1
        
        return not_none_items - FIXED_NONBRANCH_ITEMS
    
    def append_to_spliter(self, idf:IDF) -> None:
        
        # find target splitter
        target_splitter = idf["Connector:Splitter"][self.source.idf_demandsplittername]
        num_current_branches = self.count_current_branches_connector(target_splitter)
        
        # append
        target_splitter[f"Outlet Branch {num_current_branches+1} Name"] = self.supply.idf_get_demandbranchname(self.zone)

        return
    
    def append_to_mixer(self, idf:IDF) -> None:
        
        # find target mixer
        target_mixer = idf["Connector:Mixer"][self.source.idf_demandmixername]
        num_current_branches = self.count_current_branches_connector(target_mixer)
        
        # append
        target_mixer[f"Inlet Branch {num_current_branches+1} Name"] = self.supply.idf_get_demandbranchname(self.zone)      
        
        return

    def append_to_branchlist(self, idf:IDF) -> None:
        
        # find target branchlist
        target_branchlist = idf["BranchList"][self.source.idf_demandbranchlistname]
        num_current_branches = self.count_current_branches_branchlist(target_branchlist)
        
        # append
        lastbranch = target_branchlist[f"Branch {num_current_branches} Name"]
        target_branchlist[f"Branch {num_current_branches} Name"] = self.supply.idf_get_demandbranchname(self.zone)
        target_branchlist[f"Branch {num_current_branches+1} Name"] = lastbranch
        
        return
    
    def run(self, idf:IDF) -> None:
        
        # connectors
        self.append_to_spliter(idf)
        self.append_to_mixer(idf)
        
        # branchlist
        self.append_to_branchlist(idf)
        
        return


class EquipmentListAppender(SupplySystemToIdfPostProcessor):
    
    @staticmethod
    def count_current_equipments(equiplist:IdfObject) -> int:
        
        for idx in range(1, 100):
            
            if equiplist[f"Zone Equipment {idx} Name"] is None:
                return idx-1
        
    def run(self, idf:IDF) -> None:
        
        # find target equipment list
        target_equiplist = idf["ZoneHVAC:EquipmentList"][self.zone.idf_equipmentlistname]
        num_current_equips = self.count_current_equipments(target_equiplist)
        
        # append
        target_equiplist.update({
            f"Zone Equipment {num_current_equips+1} Object Type": self.supply.idf_objtypename,
            f"Zone Equipment {num_current_equips+1} Name"       : self.supply.idf_get_objname(self.zone),
            f"Zone Equipment {num_current_equips+1} Cooling Sequence"           : num_current_equips+1,
            f"Zone Equipment {num_current_equips+1} Heating or No-Load Sequence": num_current_equips+1, 
        })
        
        return


class ZoneAirNodeAppender(SupplySystemToIdfPostProcessor):
    
    @staticmethod
    def ensure_nodelist_existence(idf:IDF, zone:Zone) -> None:
        
        # ensure existence of the inlet nodelist
        if zone.idf_airinletnodelistname not in idf["NodeList"].names:
            # create nodelist
            idf["NodeList"].append([zone.idf_airinletnodelistname])
            # add nodelist to the zone connection
            target_connection = idf["ZoneHVAC:EquipmentConnections"][lambda obj: obj["Zone Name"] == zone.name][0]
            target_connection["Zone Air Inlet Node or NodeList Name"] = zone.idf_airinletnodelistname
            
        # ensure existence of the exhaust nodelist
        if zone.idf_airexhaustnodelistname not in idf["NodeList"].names:
            # create nodelist
            idf["NodeList"].append([zone.idf_airexhaustnodelistname])
            # add nodelist to the zone connection
            target_connection = idf["ZoneHVAC:EquipmentConnections"][lambda obj: obj["Zone Name"] == zone.name][0]
            target_connection["Zone Air Exhaust Node or NodeList Name"] = zone.idf_airexhaustnodelistname
            
        return
    
    @staticmethod
    def count_current_nodes(nodelist:IdfObject) -> int:
        
        # calculate all items inlcuded
        not_none_items = len({k:v for k,v in nodelist.items() if v is not None})
        
        # exclude its name 
        FIXED_NONBRANCH_ITEMS = 1
        
        return not_none_items - FIXED_NONBRANCH_ITEMS
    
    def run(self, idf:IDF) -> None:
        
        # create nodelist and connect to zone if not yet
        ZoneAirNodeAppender.ensure_nodelist_existence(idf, self.zone)
        
        # add air outlet node to the zone inlet nodelist
        target_nodelist = idf["NodeList"][self.zone.idf_airinletnodelistname]
        num_current_inletnodes = ZoneAirNodeAppender.count_current_nodes(target_nodelist)
        target_nodelist[f"Node {num_current_inletnodes+1} Name"] = self.supply.idf_get_airoutletnodename(self.zone)
        
        # add air inlet node to the zone exhaust nodelist
        target_nodelist = idf["NodeList"][self.zone.idf_airexhaustnodelistname]
        num_current_inletnodes = ZoneAirNodeAppender.count_current_nodes(target_nodelist)
        target_nodelist[f"Node {num_current_inletnodes+1} Name"] = self.supply.idf_get_airinletnodename(self.zone) 
        
        return
    
class ZoneTerminalUnitAppender(SupplySystemToIdfPostProcessor):
    
    @staticmethod
    def count_current_units(nodelist:IdfObject) -> int:
        
        # calculate all items inlcuded
        not_none_items = len({k:v for k,v in nodelist.items() if v is not None})
        
        # exclude its name 
        FIXED_NONBRANCH_ITEMS = 1
        
        return not_none_items - FIXED_NONBRANCH_ITEMS
    
    def run(self, idf:IDF) -> None:
        
        # find target terminal unit list
        target_unitlist = idf["ZoneTerminalUnitList"][lambda obj: obj["Zone Terminal Unit List Name"] == self.source.idf_terminalunitlistname][0]
        num_current_units = ZoneTerminalUnitAppender.count_current_units(target_unitlist)
        
        # append
        target_unitlist[f"Zone Terminal Unit Name {num_current_units+1}"] = self.supply.idf_get_objname(self.zone)
        
        return

class SequentialLoadFractionController(SupplySystemToIdfPostProcessor):
    
    @staticmethod
    def find_target_equipment_number(equipmentlist:IdfObject, objname:str) -> int:
        
        for idx in range(1, 100):
            
            if equipmentlist[f"Zone Equipment {idx} Name"] == objname:
                return idx
            
            elif equipmentlist[f"Zone Equipment {idx} Name"] is None:
                raise ValueError(
                    f"Cannot find objname {objname} in the equipmentlist {equipmentlist['Name']}"
                )


    def get_fraction_schedules(self) -> list[Schedule]:
        
        if self.supply.availabilities is None:
            availabilities = [Schedule.from_constant(None, 1) for _ in range(len(self.supply.systems))]
        else:
            availabilities = [sche.changetype(ScheduleType.REAL) for sche in self.supply.availabilities]
            
        
        num_remained = sum(availabilities, start=Schedule.from_constant(None, 0))
        fraction_schedules = []
        
        for sche in availabilities:
            
            fraction_schedules.append( sche * (1/(num_remained+(1E-10))))
            num_remained -= sche
        
        for sche in fraction_schedules:
            sche.name = hex(id(sche))
        
        return fraction_schedules
    
    
    
    def run(self, idf:IDF) -> None:
        
        # find target equipment list
        target_equiplist = idf["ZoneHVAC:EquipmentList"][self.zone.idf_equipmentlistname]
        
        # get fraction schedules and append to the idf
        fraction_schedule = self.get_fraction_schedules()
        for sche in fraction_schedule:
            idf.append(sche.to_idf_object())
        
        for sys, f_sche in zip(self.supply.systems, fraction_schedule):
            sys_idx = SequentialLoadFractionController.find_target_equipment_number(target_equiplist, sys.idf_get_objname(self.zone))
            target_equiplist[f"Zone Equipment {sys_idx} Sequential Cooling Fraction Schedule Name"] = f_sche.name
            target_equiplist[f"Zone Equipment {sys_idx} Sequential Heating Fraction Schedule Name"] = f_sche.name
            
        return

class SupplySystem(ABC):
    
    @abstractmethod
    def to_idf_object(self,
        zone       :Zone,
        for_heating:bool,
        for_cooling:bool,
        ) -> list[IdfObject]: ...
    
    """ idf-related naming rules
    """
    
    @property
    @abstractmethod
    def idf_objtypename(self) -> str: ...
    
    def idf_get_objname(self, zone:Zone) -> str:
        return f"{type(self).__name__}_named_{self.name}_for_{zone.name}"
    
    def idf_get_demandbranchname(self, zone:Zone) -> str:
        return f"{self.source.idf_loopname} Demand Main_{type(self).__name__}_for_{zone.name}"

    def idf_get_airinletnodename(self, zone:Zone) -> str:
        return f"{self.idf_get_objname(zone)} Air InletNode"
    
    def idf_get_airoutletnodename(self, zone:Zone) -> str:
        return f"{self.idf_get_objname(zone)} Air OutletNode"
    
    """ idf-conversion-related
    """
    
    @abstractmethod
    def to_idf_object(self,
        zone       :Zone,
        for_heating:bool,
        for_cooling:bool,
        ) -> tuple[list[IdfObject], list[SupplySystemToIdfPostProcessor]]: ...
  
  
class SupplyGroup:
    
    def __init__(self,
        systems:list[SupplySystem],
        *,
        availabilities:list[Schedule] = None,
        ) -> None:
        
        self.systems        = systems
        self.availabilities = availabilities
    
    @property
    def source(self) -> list[SourceSystem]:
        return [sys.source for sys in self.systems]
    
    def to_idf_object(self,
        zone       :Zone,
        for_heating:bool,
        for_cooling:bool,
        ) -> tuple[list[IdfObject], list[SupplySystemToIdfPostProcessor]]:
        
        if self.availabilities is None:
            availabilities = [None] * len(self.systems)
        else:
            availabilities = self.availabilities
            
        idfobjects     = []
        postprocessors = []
        for sys, sche in zip(self.systems, availabilities):
            idfobject, postprocessor = sys.to_idf_object(zone, for_heating, for_cooling, availability = sche)
            idfobjects     += idfobject
            postprocessors += postprocessor
            
            if sche is not None:
                idfobjects.append(sche.to_idf_object())
        
        postprocessors.append(SequentialLoadFractionController(self, zone))
        
        return idfobjects, postprocessors       
        
    
class AirHandlingUnit(SupplySystem):
    
    def __init__(self,
        name,
        source:SourceSystem,
        *,
        fan_efficiency   = 0.7, # - 
        fan_pressure     = 100, # Pa
        motor_efficiency = 0.9, # - 
        ) -> None:

        # user properties
        self.name = name
        
        # fundamental properties
        self.source = source
        
        # additional properties
        self.fan_efficiency   = fan_efficiency
        self.fan_pressure     = fan_pressure
        self.motor_efficiency = motor_efficiency
        
    """ idf-related
    """
    
    @property
    def idf_objtypename(self) -> str:
        return "ZoneHVAC:TerminalUnit:VariableRefrigerantFlow"
    
    def to_idf_object(self,
        zone       :Zone,
        for_heating:bool,
        for_cooling:bool,
        availability:None|Schedule=None,
        ) -> tuple[list[IdfObject], list[SupplySystemToIdfPostProcessor]]:
        
        if availability is None:
            availability = zone.profile.hvac_availability
        
        curve_obj = [
            IdfObject("Curve:Cubic", [
                f"Curve_for_{self.idf_get_objname(zone)}:HeatingCapaTemp",
                -3.90708928E-01, 2.61815024E-01, -1.30431603E-02, 1.78131746E-04,
                0.0, 50, 0.5, 1.5, "Temperature", "Dimensionless",
            ]),
            IdfObject("Curve:Linear", [
                f"Curve_for_{self.idf_get_objname(zone)}:HeatingCapaFlow",
                0.8, 0.2, 0.0, 1.5
            ]),
            IdfObject("Curve:Cubic", [
                f"Curve_for_{self.idf_get_objname(zone)}:CoolingCapaTemp",
                5.04547274E-01, 2.88891279E-02, -1.08194187E-05, 1.01359395E-05,
                0.0, 50, 0.5, 1.5, "Temperature", "Dimensionless",
            ]),
            IdfObject("Curve:Linear", [
                f"Curve_for_{self.idf_get_objname(zone)}:CoolingCapaFlow",
                0.8, 0.2, 0.0, 1.5
            ]),
        ]
        
        component_obj = [
            IdfObject("Coil:Cooling:DX:VariableRefrigerantFlow", {
                "Name": f"CoolingCoil_for_{self.idf_get_objname(zone)}",
                "Availability Schedule Name": availability.name if for_cooling else "ALLOFF",
                "Gross Rated Total Cooling Capacity": "autosize" if for_cooling else 0.1,
                "Gross Rated Sensible Heat Ratio": 0.7,
                "Rated Air Flow Rate": 0.01*zone.floor_area,
                "Coil Air Inlet Node": self.idf_get_airinletnodename(zone),
                "Coil Air Outlet Node": f"{self.idf_get_objname(zone)} CoolingCoil2HeatingCoil Air MiddleNode",
                "Cooling Capacity Ratio Modifier Function of Temperature Curve Name": f"Curve_for_{self.idf_get_objname(zone)}:CoolingCapaTemp",
                "Cooling Capacity Modifier Curve Function of Flow Fraction Name": f"Curve_for_{self.idf_get_objname(zone)}:CoolingCapaFlow",            
            }),
            IdfObject("Coil:Heating:DX:VariableRefrigerantFlow", {
                "Name": f"HeatingCoil_for_{self.idf_get_objname(zone)}",
                "Availability Schedule": availability.name if for_heating else "ALLOFF",
                "Gross Rated Heating Capacity": "autosize" if for_heating else 0.1,
                "Rated Air Flow Rate": 0.01*zone.floor_area,
                "Coil Air Inlet Node": f"{self.idf_get_objname(zone)} CoolingCoil2HeatingCoil Air MiddleNode",
                "Coil Air Outlet Node": f"{self.idf_get_objname(zone)} HeatingCoil2Fan Air MiddleNode",
                "Heating Capacity Ratio Modifier Function of Temperature Curve Name": f"Curve_for_{self.idf_get_objname(zone)}:HeatingCapaTemp",
                "Heating Capacity Modifier Function of Flow Fraction Curve Name": f"Curve_for_{self.idf_get_objname(zone)}:HeatingCapaFlow",
            }),
            IdfObject("Fan:ConstantVolume", {
                "Name": f"Fan_for_{self.idf_get_objname(zone)}",
                "Availability Schedule Name": availability.name,
                "Fan Total Efficiency": self.fan_efficiency,
                "Pressure Rise": self.fan_pressure,
                "Maximum Flow Rate": 0.01*zone.floor_area,
                "Motor Efficiency": self.motor_efficiency,
                "Air Inlet Node Name" : f"{self.idf_get_objname(zone)} HeatingCoil2Fan Air MiddleNode",
                "Air Outlet Node Name": self.idf_get_airoutletnodename(zone)
            })
        ]
        
        indoor_obj = [
            IdfObject(self.idf_objtypename,{
                "Zone Terminal Unit Name": self.idf_get_objname(zone),
                "Terminal Unit Availability Schedule": availability.name,
                "Terminal Unit Air Inlet Node Name": self.idf_get_airinletnodename(zone),
                "Terminal Unit Air Outlet Node Name": self.idf_get_airoutletnodename(zone),
                "Cooling Supply Air Flow Rate"   : "autosize",
                "No Cooling Supply Air Flow Rate": "autosize",
                "Heating Supply Air Flow Rate"   : "autosize",
                "No Heating Supply Air Flow Rate": "autosize",
                "Cooling Outdoor Air Flow Rate": 0,
                "Heating Outdoor Air Flow Rate": 0,
                "No Load Outdoor Air Flow Rate": 0,
                "Supply Air Fan Operating Mode Schedule Name": "ALLON",
                "Supply Air Fan Placement": "DrawThrough",
                "Supply Air Fan Object Name": f"Fan_for_{self.idf_get_objname(zone)}",
                "Cooling Coil Object Type": "Coil:Cooling:DX:VariableRefrigerantFlow",
                "Cooling Coil Object Name": f"CoolingCoil_for_{self.idf_get_objname(zone)}",
                "Heating Coil Object Type": "Coil:Heating:DX:VariableRefrigerantFlow",
                "Heating Coil Object Name": f"HeatingCoil_for_{self.idf_get_objname(zone)}",
                "Zone Terminal Unit On Parasitic Electric Energy Use" : 30,
                "Zone Terminal Unit Off Parasitic Electric Energy Use": 20,
            })
        ]

        postprocessors = [
            ZoneAirNodeAppender(self, zone),
            ZoneTerminalUnitAppender(self, zone),
            EquipmentListAppender(self, zone),
        ]
        
        return curve_obj + component_obj + indoor_obj, postprocessors
    
    """ representation
    """
    
    def __deepcopy__(self, memo):
        
        if id(self) in memo:
            return memo[id(self)]
        
        clone =  AirHandlingUnit(
            name             = f"{self.name}:COPY",
            source           = self.source,
            fan_efficiency   = self.fan_efficiency,
            fan_pressure     = self.fan_pressure,
            motor_efficiency = self.motor_efficiency,
        )
        memo[id(self)] = clone
        return clone
    
    
class FanCoilUnit(SupplySystem):
    
    def __init__(self,
        name,
        source:SourceSystem,
        *,
        fan_efficiency   = 0.7, # - 
        fan_pressure     = 100, # Pa
        motor_efficiency = 0.9, # - 
        ) -> None:

        # user properties
        self.name = name
        
        # fundamental properties
        self.source = source
        
        # additional properties
        self.fan_efficiency   = fan_efficiency
        self.fan_pressure     = fan_pressure
        self.motor_efficiency = motor_efficiency
    
    """ idf-related
    """
    
    @property
    def idf_objtypename(self) -> str:
        return "ZoneHVAC:FourPipeFanCoil"
    
    def to_idf_object(self,
        zone       :Zone,
        for_heating:bool,
        for_cooling:bool,
        availability:None|Schedule=None,
        ) -> tuple[list[IdfObject], list[SupplySystemToIdfPostProcessor]]:
        
        if availability is None:
            availability = zone.profile.hvac_availability
        
        curve_obj = [
            IdfObject("Curve:Exponent",[
                f"Curve_for_{self.idf_get_objname(zone)}:PowerSpeedRatio",
                0,1,3,
                0,1.5,0.01,1.5,
            ]),
            IdfObject("Curve:Cubic",[
                f"Curve_for_{self.idf_get_objname(zone)}:EffSpeedRatio",
                0.33856828, 1.72644131, -1.49280132, 0.42776208,
                0,1.5,0.3,1
            ]),
        ]
        
        component_obj = [
            IdfObject("OutdoorAir:Mixer",{
                "Name": f"OAmixer_for_{self.idf_get_objname(zone)}",
                "Mixed Air Node Name"         : f"{self.idf_get_objname(zone)} OAmixer2Fan Air MiddleNode",
                "Outdoor Air Stream Node Name": f"OAmixer_for_{self.idf_get_objname(zone)} Air OutdoorNode",
                "Relief Air Stream Node Name" : f"OAmixer_for_{self.idf_get_objname(zone)} Air ReliefNode",
                "Return Air Stream Node Name" : self.idf_get_airinletnodename(zone),
            }),
            IdfObject("OutdoorAir:NodeList", [
                f"OAmixer_for_{self.idf_get_objname(zone)} Air OutdoorNode",
            ]),
            IdfObject("Fan:OnOff", {
                "Name": f"Fan_for_{self.idf_get_objname(zone)}",
                "Availability Schedule Name": availability.name,
                "Fan Total Efficiency": self.fan_efficiency,
                "Pressure Rise": self.fan_pressure,
                "Maximum Flow Rate": "autosize",
                "Motor Efficiency": self.motor_efficiency,
                "Air Inlet Node Name": f"{self.idf_get_objname(zone)} OAmixer2Fan Air MiddleNode",
                "Air Outlet Node Name": f"{self.idf_get_objname(zone)} Fan2CoolingCoil Air MiddleNode",
                "Fan Power Ratio Function of Speed Ratio Curve Name": f"Curve_for_{self.idf_get_objname(zone)}:PowerSpeedRatio",
                "Fan Efficiency Ratio Function of Speed Ratio Curve Name": f"Curve_for_{self.idf_get_objname(zone)}:EffSpeedRatio"
            }),
            IdfObject("Coil:Cooling:Water", {
                "Name": f"CoolingCoil_for_{self.idf_get_objname(zone)}",
                "Availability Schedule Name": availability.name if for_cooling else "ALLOFF",
                "Water Inlet Node Name": f"CoolingCOil_for_{self.idf_get_objname(zone)} Water InletNode",
                "Water Outlet Node Name": f"CoolingCoil_for_{self.idf_get_objname(zone)} Water OutletNode",
                "Air Inlet Node Name": f"{self.idf_get_objname(zone)} Fan2CoolingCoil Air MiddleNode",
                "Air Outlet Node Name": f"{self.idf_get_objname(zone)} CoolingCoil2HeatingCoil Air MiddleNode",
            }),
            IdfObject("Coil:Heating:Water", {
                "Name": f"HeatingCoil_for_{self.idf_get_objname(zone)}",
                "Availability Schedule Name": availability.name if for_heating else "ALLOFF",
                "Water Inlet Node Name": f"HeatingCoil_for_{self.idf_get_objname(zone)} Water InletNode",
                "Water Outlet Node Name": f"HeatingCoil_for_{self.idf_get_objname(zone)} Water OutletNode",
                "Air Inlet Node Name": f"{self.idf_get_objname(zone)} CoolingCoil2HeatingCoil Air MiddleNode",
                "Air Outlet Node Name": self.idf_get_airoutletnodename(zone),
            }),
        ]
        
        fcu_obj = [
            IdfObject("ZoneHVAC:FourPipeFanCoil", {
                "Name": self.idf_get_objname(zone),
                "Availability Schedule Name": availability.name,
                "Capacity Control Method": "ConstantFanVariableFlow",
                "Maximum Supply Air Flow Rate": "autosize",
                "Maximum Outdoor Air Flow Rate": 0,
                "Air Inlet Node Name": self.idf_get_airinletnodename(zone),
                "Air Outlet Node Name": self.idf_get_airoutletnodename(zone),
                "Outdoor Air Mixer Object Type": "OutdoorAir:Mixer",
                "Outdoor Air Mixer Name": f"OAmixer_for_{self.idf_get_objname(zone)}",
                "Supply Air Fan Object Type": "Fan:OnOff",
                "Supply Air Fan Name": f"Fan_for_{self.idf_get_objname(zone)}",
                "Cooling Coil Object Type": "Coil:Cooling:Water",
                "Cooling Coil Name": f"CoolingCoil_for_{self.idf_get_objname(zone)}",
                "Maximum Cold Water Flow Rate": "autosize" if for_cooling else 0,
                "Minimum Cold Water Flow Rate": 0,
                "Heating Coil Object Type": "Coil:Heating:Water",
                "Heating Coil Name": f"HeatingCoil_for_{self.idf_get_objname(zone)}",
                "Maximum Hot Water Flow Rate": "autosize" if for_heating else 0,
                "Minimum Hot Water Flow Rate": 0,
            })
        ]
        
        if for_heating:
            branch_obj = [
                IdfObject("Branch", {
                    "Name": self.idf_get_demandbranchname(zone),
                    "Component 1 Object Type": "Coil:Heating:Water",
                    "Component 1 Name": f"HeatingCoil_for_{self.idf_get_objname(zone)}",
                    "Component 1 Inlet Node Name" : f"HeatingCoil_for_{self.idf_get_objname(zone)} Water InletNode" ,
                    "Component 1 Outlet Node Name": f"HeatingCoil_for_{self.idf_get_objname(zone)} Water OutletNode",
                }),
                IdfObject("Branch", {
                    "Name": f"NonUsed_{self.idf_get_demandbranchname(zone)}",
                    "Component 1 Object Type": "Coil:Cooling:Water",
                    "Component 1 Name": f"CoolingCoil_for_{self.idf_get_objname(zone)}",
                    "Component 1 Inlet Node Name" : f"CoolingCoil_for_{self.idf_get_objname(zone)} Water InletNode" ,
                    "Component 1 Outlet Node Name": f"CoolingCoil_for_{self.idf_get_objname(zone)} Water OutletNode",
                }),
            ]
            
            nonusedsource = Chiller(
                f"NonUsedChiller_for_{self.idf_get_objname(zone)}",
                1E-10,
                1E-10,
                "turbo",
                OpenSingleSpeedCoolingTower(
                    f"NonUsedCoolingTower_for_{self.idf_get_objname(zone)}",
                    1E-10
                )
            )
            nonusedloop_obj = nonusedsource.to_idf_object()
            
        if for_cooling:
            branch_obj = [
                IdfObject("Branch", {
                    "Name": f"NonUsed_{self.idf_get_demandbranchname(zone)}",
                    "Component 1 Object Type": "Coil:Heating:Water",
                    "Component 1 Name": f"HeatingCoil_for_{self.idf_get_objname(zone)}",
                    "Component 1 Inlet Node Name" : f"HeatingCoil_for_{self.idf_get_objname(zone)} Water InletNode" ,
                    "Component 1 Outlet Node Name": f"HeatingCoil_for_{self.idf_get_objname(zone)} Water OutletNode",
                }),
                IdfObject("Branch", {
                    "Name": self.idf_get_demandbranchname(zone),
                    "Component 1 Object Type": "Coil:Cooling:Water",
                    "Component 1 Name": f"CoolingCoil_for_{self.idf_get_objname(zone)}",
                    "Component 1 Inlet Node Name" : f"CoolingCoil_for_{self.idf_get_objname(zone)} Water InletNode" ,
                    "Component 1 Outlet Node Name": f"CoolingCoil_for_{self.idf_get_objname(zone)} Water OutletNode",
                }),
            ]
            
            nonusedsource = Boiler(
                f"NonUsedBoiler_for_{self.idf_get_objname(zone)}",
                Fuel.COAL,
                1E-10,
                1E-10,
            )
            nonusedloop_obj = nonusedsource.to_idf_object()
        
        # off     
        nonusedloop_availability_obj = [obj for obj in nonusedloop_obj if obj.idd.name == "AvailabilityManager:Scheduled"][0]
        nonusedloop_availability_obj["Schedule Name"] = "ALLOFF"
        
        # splitter
        nonusedloop_demandspliter_obj = [obj for obj in nonusedloop_obj if (obj.idd.name == "Connector:Splitter") and obj["Name"] == nonusedsource.idf_demandsplittername][0]
        num_current_branches = DemandBranchAppender.count_current_branches_connector(nonusedloop_demandspliter_obj)
        nonusedloop_demandspliter_obj[f"Outlet Branch {num_current_branches+1} Name"] = f"NonUsed_{self.idf_get_demandbranchname(zone)}"
        
        # mixer
        nonusedloop_demandmixer_obj = [obj for obj in nonusedloop_obj if (obj.idd.name == "Connector:Mixer") and obj["Name"] == nonusedsource.idf_demandmixername][0]
        num_current_branches = DemandBranchAppender.count_current_branches_connector(nonusedloop_demandmixer_obj)
        nonusedloop_demandmixer_obj[f"Inlet Branch {num_current_branches+1} Name"] = f"NonUsed_{self.idf_get_demandbranchname(zone)}"
        
        # branchlist
        nonusedloop_demandbranchlist_obj = [obj for obj in nonusedloop_obj if (obj.idd.name == "BranchList") and obj["Name"] == nonusedsource.idf_demandbranchlistname][0]
        num_current_branches = DemandBranchAppender.count_current_branches_branchlist(nonusedloop_demandbranchlist_obj)
        lastbranch = nonusedloop_demandbranchlist_obj[f"Branch {num_current_branches} Name"]
        nonusedloop_demandbranchlist_obj[f"Branch {num_current_branches} Name"] = f"NonUsed_{self.idf_get_demandbranchname(zone)}"
        nonusedloop_demandbranchlist_obj[f"Branch {num_current_branches+1} Name"] = lastbranch
        
        postprocessors = [
            DemandBranchAppender(self, zone),
            ZoneAirNodeAppender(self, zone),
            EquipmentListAppender(self, zone),
        ]
        
        return curve_obj + component_obj + fcu_obj + branch_obj + nonusedloop_obj, postprocessors

    
class Radiator(SupplySystem):
    
    def __init__(self,
        name:str,
        capacity:int|float   ,
        source  :SourceSystem,
        *,
        radiant_fraction:int|float = 0
        ) -> None:
        
        # user property
        self.name = name
        
        # fundamental properties
        self.capacity = capacity
        self.source   = source
        
        # additional properties
        self.radiant_fraction = radiant_fraction
    
    @property
    def heatable(self) -> bool:
        return True
    
    @property
    def coolable(self) -> bool:
        return False
    
    """ idf-related
    """
    
    @property
    def idf_objtypename(self) -> str:
        return "ZoneHVAC:Baseboard:RadiantConvective:Water"
    
    def to_idf_object(self,
        zone       :Zone,
        for_heating:bool,
        for_cooling:bool,
        availability:None|Schedule=None,
        ) -> tuple[list[IdfObject], list[SupplySystemToIdfPostProcessor]]:
        
        if availability is None:
            availability = zone.profile.hvac_availability
        
        if (not self.heatable and for_heating) or (not self.coolable and for_cooling):
            raise ValueError(
                f"그런건 못해요..."
            )

        obj_radiator = [
            # radiator
            IdfObject("ZoneHVAC:Baseboard:RadiantConvective:Water:Design", {
                "Name": f"DesignOf_{self.idf_get_objname(zone)}",
                "Fraction Radiant": self.radiant_fraction,
            }, ignore_default=False),
            IdfObject(self.idf_objtypename,{
                "Name": self.idf_get_objname(zone),
                "Design Object": f"DesignOf_{self.idf_get_objname(zone)}",
                "Availability Schedule Name": availability.name,
                "Inlet Node Name" : f"{self.idf_get_objname(zone)} Water InletNode" ,
                "Outlet Node Name": f"{self.idf_get_objname(zone)} Water OutletNode",
                "Heating Design Capacity": self.capacity if self.capacity is not None else "autosize",
                "Maximum Water Flow Rate": "autosize",
            }),
        ]
        
        obj_branches = [
            IdfObject("Branch", {
                "Name": self.idf_get_demandbranchname(zone),
                "Component 1 Object Type": self.idf_objtypename,
                "Component 1 Name": self.idf_get_objname(zone),
                "Component 1 Inlet Node Name" : f"{self.idf_get_objname(zone)} Water InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_get_objname(zone)} Water OutletNode",
            })
        ]
        
        postprocessors = [
            DemandBranchAppender(self, zone),
            EquipmentListAppender(self, zone),
        ]

        return obj_radiator + obj_branches, postprocessors
    
    
class ElectricRadiator(SupplySystem):
    
    def __init__(self,
        name:str,
        capacity:int|float   ,
        *,
        efficiency:int|float=1.0,
        radiant_fraction:int|float = 0,
        ) -> None:
        
        # user property
        self.name = name
        
        # fundamental properties
        self.capacity = capacity
        
        # additional properties
        self.efficiency = efficiency
        self.radiant_fraction = radiant_fraction
    
    @property
    def source(self) -> None:
        return None
    
    @property
    def heatable(self) -> bool:
        return True
    
    @property
    def coolable(self) -> bool:
        return False
    
    """ idf-related
    """
    @property
    def idf_objtypename(self) -> str:
        return "ZoneHVAC:Baseboard:RadiantConvective:Electric"
    
    def to_idf_object(self,
        zone       :Zone,
        for_heating:bool,
        for_cooling:bool,
        availability:None|Schedule=None,
        ) -> tuple[list[IdfObject], list[SupplySystemToIdfPostProcessor]]:
        
        if availability is None:
            availability = zone.profile.hvac_availability
        
        if (not self.heatable and for_heating) or (not self.coolable and for_cooling):
            raise ValueError(
                f"그런건 못해요..."
            )

        obj_radiator = [
            # radiator
            IdfObject(self.idf_objtypename, {
                "Name": self.idf_get_objname(zone),
                "Availability Schedule Name": availability.name,
                "Heating Design Capacity": self.capacity if self.capacity is not None else "autosize",
                "Efficiency": self.efficiency,
                "Fraction Radiant": self.radiant_fraction,
            }, ignore_default=False),
        ]
        
        postprocessors = [
            EquipmentListAppender(self, zone),
        ]
        
        return obj_radiator, postprocessors

class RadiantFloor(SupplySystem):
    
    def __init__(self,
        name  :str,
        source:SourceSystem,
        *,
        throttling_range:int|float = 2,
        ) -> None:
        
        # user property
        self.name = name
        
        # fundamental properties
        self.source = source
        
        # additional properties
        self.throttling_range = throttling_range
    
    @property
    def heatable(self) -> bool:
        return True
    
    @property
    def coolable(self) -> bool:
        return False
    
    """ idf-related
    """

    @property
    def idf_objtypename(self) -> str:
        return "ZoneHVAC:LowTemperatureRadiant:VariableFlow"
    
    @staticmethod
    def _get_internal_heatsource_layer(construction:Construction):
        return max(len(construction.layers) - 1, 1)
    
    def to_idf_object(self,
        zone       :Zone,
        for_heating:bool,
        for_cooling:bool,
        availability:None|Schedule=None,
        ) -> tuple[list[IdfObject], list[SupplySystemToIdfPostProcessor]]:
        
        if availability is None:
            availability = zone.profile.hvac_availability
        
        if (not self.heatable and for_heating) or (not self.coolable and for_cooling):
            raise ValueError(
                f"그런건 못해요..."
            )
        
        obj_internal_heatsources = [
            IdfObject("ConstructionProperty:InternalHeatSource",{
                "Name": f"{surface.name} Internal Heat Source",
                "Construction Name": f"{surface.construction.name}:for:{surface.name}",
                "Thermal Source Present After Layer Number": self._get_internal_heatsource_layer(surface.construction),
                "Temperature Calculation Requested After Layer Number": self._get_internal_heatsource_layer(surface.construction),
                "Dimensions for the CTF Calculation": 1,
                "Tube Spacing": 0.3,
            }, ignore_default=False)
            for surface in zone.floor_surface
        ]
        
        flow_fractions = [surface.area/zone.floor_area for surface in zone.floor_surface]
        obj_radiant_floor = [
            # surface
            IdfObject("ZoneHVAC:LowTemperatureRadiant:SurfaceGroup",{
                "Name": f"RadiantFloorSurfaceGroup_for_{zone.name}",
                **{
                    f"Surface {idx+1} Name": surface.name                    
                    for idx, surface in enumerate(zone.floor_surface)
                },
                **{
                    f"Flow Fraction for Surface {idx+1}": fraction                    
                    for idx, fraction in enumerate(flow_fractions)
                },
                
            }),
            # radiant floor
            IdfObject("ZoneHVAC:LowTemperatureRadiant:VariableFlow:Design", {
                "Name": f"DesignOf_{self.idf_get_objname(zone)}",
                "Heating Control Temperature Schedule Name": zone.profile.heating_setpoint.name,
                "Heating Control Throttling Range": self.throttling_range,
                "Setpoint Control Type": "ZeroFlowPower",
            }, ignore_default=False),
            IdfObject(self.idf_objtypename,{
                "Name": self.idf_get_objname(zone),
                "Design Object":f"DesignOf_{self.idf_get_objname(zone)}",
                "Availability Schedule Name": availability.name,
                "Zone Name": zone.name,
                "Surface Name or Radiant Surface Group Name": f"RadiantFloorSurfaceGroup_for_{zone.name}",
                "Maximum Hot Water Flow": "autosize",
                "Heating Water Inlet Node Name" : f"{self.idf_get_objname(zone)} Water InletNode" ,
                "Heating Water Outlet Node Name": f"{self.idf_get_objname(zone)} Water OutletNode",
            }),
        ]
        
        obj_branches = [
            IdfObject("Branch", {
                "Name": self.idf_get_demandbranchname(zone),
                "Component 1 Object Type": self.idf_objtypename,
                "Component 1 Name": self.idf_get_objname(zone),
                "Component 1 Inlet Node Name" : f"{self.idf_get_objname(zone)} Water InletNode" ,
                "Component 1 Outlet Node Name": f"{self.idf_get_objname(zone)} Water OutletNode",
            })
        ]
        
        postprocessors = [
            DemandBranchAppender(self, zone),
            EquipmentListAppender(self, zone)
        ]
        
        return obj_internal_heatsources + obj_radiant_floor + obj_branches, postprocessors


class ElectricRadiantFloor(SupplySystem):
    
    def __init__(self,
        name:str,
        *,
        throttling_range:int|float = 2,
        ) -> None:
        
        # user property
        self.name = name
        
        # additional properties
        self.throttling_range = throttling_range
    
    @property
    def source(self) -> None:
        return None
    
    @property
    def heatable(self) -> bool:
        return True
    
    @property
    def coolable(self) -> bool:
        return False
    
    """ idf-related
    """
    @property
    def idf_objtypename(self) -> str:
        return "ZoneHVAC:LowTemperatureRadiant:Electric"
    
    @staticmethod
    def _get_internal_heatsource_layer(construction:Construction):    
        return max(len(construction.layers) - 1, 1)
    
    def to_idf_object(self,
        zone       :Zone,
        for_heating:bool,
        for_cooling:bool,
        availability:None|Schedule=None,
        ) -> tuple[list[IdfObject], list[SupplySystemToIdfPostProcessor]]:
        
        if availability is None:
            availability = zone.profile.hvac_availability
        
        if (not self.heatable and for_heating) or (not self.coolable and for_cooling):
            raise ValueError(
                f"그런건 못해요..."
            )

        obj_internal_heatsources = [
            IdfObject("ConstructionProperty:InternalHeatSource",{
                "Name": f"{surface.name} Internal Heat Source",
                "Construction Name": f"{surface.construction.name}:for:{surface.name}",
                "Thermal Source Present After Layer Number": self._get_internal_heatsource_layer(surface.construction),
                "Temperature Calculation Requested After Layer Number": self._get_internal_heatsource_layer(surface.construction),
                "Dimensions for the CTF Calculation": 1,
                "Tube Spacing": 0.3,
            }, ignore_default=False)
            for surface in zone.floor_surface
        ]
        
        flow_fractions = [surface.area/zone.floor_area for surface in zone.floor_surface]
        obj_radiant_floor = [
            # surface
            IdfObject("ZoneHVAC:LowTemperatureRadiant:SurfaceGroup",{
                "Name": f"RadiantFloorSurfaceGroup_for_{zone.name}",
                **{
                    f"Surface {idx+1} Name": surface.name                    
                    for idx, surface in enumerate(zone.floor_surface)
                },
                **{
                    f"Flow Fraction for Surface {idx+1}": fraction                    
                    for idx, fraction in enumerate(flow_fractions)
                },
                
            }),
            # radiant floor
            IdfObject(self.idf_objtypename,{
                "Name": self.idf_get_objname(zone),
                "Availability Schedule Name": availability.name,
                "Zone Name": zone.name,
                "Surface Name or Radiant Surface Group Name": f"RadiantFloorSurfaceGroup_for_{zone.name}",
                "Setpoint Control Type": "ZeroFlowPower",
                "Heating Throttling Range": self.throttling_range,
                "Heating Setpoint Temperature Schedule Name": zone.profile.heating_setpoint.name,
            }),
        ]
        
        postprocessors = [
            EquipmentListAppender(self, zone),
        ]
        
        return obj_internal_heatsources + obj_radiant_floor, postprocessors

# ---------------------------------------------------------------------------- #
#                                HOTWATER SYSTEM                               #
# ---------------------------------------------------------------------------- #

class DomesticHotWater:
    
    def __init__(self,
        name      :str,
        fuel      :Fuel,
        efficiency:int|float,
        ) -> None:
        
        # user property
        self.name = name
        
        # fundamental properties
        self.fuel       = fuel
        self.efficiency = efficiency
        
    """ fundamental properties
    """
    
    @property
    def fuel(self) -> str:
        return str(self.__fuel)
    
    @fuel.setter
    @validate_enum(Fuel)
    def fuel(self, value: str) -> None:
        self.__fuel = value
        
    @property
    def efficiency(self) -> int|float:
        return self.__efficiency
    
    @efficiency.setter
    @validate_range(min=math.nextafter(0, math.inf), max=1)
    @validate_type(int, float)
    def efficiency(self, value: int|float) -> None:
        self.__efficiency = value
        
    """ idf-related
    """
    
    def to_idf_object(self) -> list[IdfObject]:
        
        return []
    
    
    """ representation
    """
    
    def __str__(self) -> str:
        return f"DemesticHotWater {self.name} (fuel: {self.fuel}, eff.:{self.efficiency*Unit.NONE2PRC:.1f}%)"
    
    def __repr__(self) -> str:
        return f"<DomesticHotWater {self.name} at {hex(id(self))}>"
    
    

# ---------------------------------------------------------------------------- #
#                                 OTHER SYSTEMS                                #
# ---------------------------------------------------------------------------- #

class EnergyRecoveryVentilator:
    
    def __init__(self,
        name:str,
        heating_efficiency:int|float,
        cooling_efficiency:int|float,
        ) -> None:
        
        self.name = name
        self.heating_efficiency = heating_efficiency
        self.cooling_efficiency = cooling_efficiency
        
    def to_idf_object(self) -> list[IdfObject]:
        
        return []
    
    
class PhotoVoltaicPanel:
    
    def __init__(self,
        name:str,
        area      :int|float, # m2
        tilt      :int|float, # deg
        azimuth   :int|float, # deg
        efficiency:int|float, # -
        *,
        effective_area_ratio:int|float=0.7 # ECO2 밀착형 성능계수 (건기연 보고서 체크)
        ) -> None:
        
        # user property
        self.name = name
        
        # fundamental properties
        self.area       = area
        self.tilt       = tilt
        self.azimuth    = azimuth
        self.efficiency = efficiency
        
        # additional properties
        self.effective_area_ratio = effective_area_ratio
        
    """ fundamental properties
    """ 
    
    @property
    def area(self) -> int|float:
        return self.__area
    
    @area.setter
    @validate_range(min=math.nextafter(0, math.inf))
    @validate_type(int, float)
    def area(self, value: int|float) -> None:
        self.__area = value
        
    @property
    def tilt(self) -> int|float:
        return self.__tilt
    
    @tilt.setter
    @validate_range(min=0, max=90)
    @validate_type(int, float)
    def tilt(self, value: int|float) -> None:
        self.__tilt = value
        
    @property
    def azimuth(self) -> int|float:
        return self.__azimuth
    
    @azimuth.setter
    @validate_range(min=0, max=math.nextafter(360, -math.inf))
    def azimuth(self, value: int|float) -> None:
        self.__azimuth = value
        
    @property
    def efficiency(self) -> int|float:
        return self.__efficiency
    
    @efficiency.setter
    @validate_range(min=math.nextafter(0, math.inf), max=1)
    @validate_type(int, float)
    def efficiency(self, value: int|float) -> None:
        self.__efficiency = value
        
    @property
    def effective_area_ratio(self) -> int|float:
        return self.__effective_area_ratio
    
    @effective_area_ratio.setter
    @validate_range(min=math.nextafter(0, math.inf), max=1)
    @validate_type(int, float)
    def effective_area_ratio(self, value: int|float) -> None:
        self.__effective_area_ratio = value
    
    """ idf-related
    """
    
    def to_idf_object(self) -> list[IdfObject]:
        
        # PV panel related
        pv_objs = [
            # surface
            IdfObject("Shading:Site",[
                f"Shading4PVpanel:{self.name}",
                self.azimuth,
                self.tilt,
                0,0,10,
                math.sqrt(self.area),
                math.sqrt(self.area),
            ]),
            # spec
            IdfObject("PhotovoltaicPerformance:Simple",[
                f"Spec4PVpanel:{self.name}",
                self.effective_area_ratio,
                "Fixed", self.efficiency
            ]),
            # panel
            IdfObject("Generator:Photovoltaic",[
                f"PVpanel:{self.name}",
                f"Shading4PVpanel:{self.name}",
                "PhotovoltaicPerformance:Simple",
                f"Spec4PVpanel:{self.name}",
            ], ignore_default=False)
        ]
        
        # Demand related
        demand_objs = [
            IdfObject("ElectricLoadCenter:Generators",[
                f"Generator4PVpanel:{self.name}",
                f"PVpanel:{self.name}"         ,
                "Generator:Photovoltaic"       ,
                1_000_000                      ,
            ]),
            IdfObject("ElectricLoadCenter:Inverter:Simple",[
                f"Inverter4PVpanel:{self.name}",
                "ALLON",
                None    ,
                0       ,
                1       , 
            ]),
            IdfObject("ElectricLoadCenter:Distribution",[
                f"Distribution4PVpanel:{self.name}",
                f"Generator4PVpanel:{self.name}"   ,
                "Baseload",
                1_000_000,
                None, None,
                "DirectCurrentWithInverter",
                f"Inverter4PVpanel:{self.name}"
            ], ignore_default=False),
        ]
        
        return pv_objs + demand_objs
    
    """ representation
    """
    
    def __str__(self) -> str:
        return f"{self.area:.1f}m2 PhotovoltaicPanel {self.name} (tilt={self.tilt:.1f}°, azim.={self.azimuth:.1f}°, eff.={self.efficiency*Unit.NONE2PRC:.1f}%)" 
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
