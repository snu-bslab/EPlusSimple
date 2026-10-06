

# ---------------------------------------------------------------------------- #
#                                    MODULES                                   #
# ---------------------------------------------------------------------------- #

# built-in modules
from enum    import Enum
from pathlib import Path

# third-party modules

# local modules

# ---------------------------------------------------------------------------- #
#                           PACKAGE-RELATED VARIABLES                          #
# ---------------------------------------------------------------------------- #

class Directory:
    
    # root directories
    _MODULE_ROOT  = Path(__file__).resolve().parent
    _PACKAGE_ROOT = Path(__file__).resolve().parents[2]
    
    # subdirectories
    _DATA_DIR    = _MODULE_ROOT / "_data"
    
    # data directories
    WEATHER_META_DIR = _DATA_DIR / "weather"
    WEATHER_DATA_DIR = _PACKAGE_ROOT / "runtime" / "Weather" / "TMY"
    PROFILE_DIR      = _DATA_DIR / "profile"
    CONSTRUCTION_DIR = _DATA_DIR / "construction"


class PackageInfo:
    
    NAME    = "epsimple"
    VERSION = (0,6,6)
    REQUIRED_PYTHON = (3,12)
    
    
    
# ---------------------------------------------------------------------------- #
#                           COEFFICIENTS: ENGINEERING                          #
# ---------------------------------------------------------------------------- #

class Unit(float, Enum):
    
    # length
    MM_TO_M = 1/1000
    M_TO_MM = 1000
    
    # ratio
    FRACTION_TO_PERCENT = 100
    PERCENT_TO_FRACTION = 1/100
    
    # power
    W_TO_KW = 1/1000
    
    # infiltration
    ACH50_TO_ACH = 0.07    
    
class ConvectionHeatTransfer(float, Enum):
    
    IN  = 1/0.110 # 거실의 실내표면열전달저항 (건축물의 에너지절약설계기준 [별표 5])
    OUT = 1/0.043 # 거실의 실외(직접외기)표면열전달저항 (건축물의 에너지절약설계기준 [별표 5])
    
# ---------------------------------------------------------------------------- #
#           COEFFICIENT: REGULATIONS, STANDARDS, DOMESTIC STATISTICS           #
# ---------------------------------------------------------------------------- #
    
class Site2Source(float, Enum): # kWh -> kWh
    
    ELECTRICITY     = 2.75
    NATURALGAS      = 1.1
    OIL             = 1.1 
    DISTRICTHEATING = 0.728 
    
    
class Site2CO2(float, Enum): # kWh -> kgCO2eq
    
    ELECTRICITY     = 0.4541
    NATURALGAS      = 0.2024
    OIL             = 0.2603
    DISTRICTHEATING = 0.1358
    
    
class Site2Cost(float, Enum): # kWh -> won
    
    ELECTRICITY     = 162.92
    NATURALGAS      =  78.12
    OIL             = 141.92
    DISTRICTHEATING =  94.98
    
    

# ---------------------------------------------------------------------------- #
#                                  CONVENTIONS                                 #
# ---------------------------------------------------------------------------- #

class SpecialTag(str, Enum):
    
    """
    Special tags (to be precise, prefix) are used to indicate special instances,
    by being attached as a prefix to the instance's ID
    """
    
    # general
    SPECIAL = "SPECIAL"
    
    # data source
    DB      = "FROM_DB"
    
    # copy
    CLONE    = "CLONE_OF"
    FLIP     = "REVERSED"
    
    # surface & construction
    COOLROOF = "FOR_COOLROOF"
    
    """ representation
    
    Examples
    --------
    >>> f"{SpecialTag.CLONE}"
    $CLONE_OF$:
    
    >>> f"{SpecialTag.CLONE:SURFACE}
    $CLONE_OF:SURFACE$:
    
    >>> SpecialTag.CLONE
    CLONE_OF
    """
    
    def __format__(self, format_spec:str) -> str:
        suffix = f":{format_spec}" if format_spec else ""
        return f"${self.value}{suffix}$:"
    
    def __str__(self) -> str:
        return self.__format__("")
    
    def __repr__(self) -> str:
        return self.value


class AUTOID_PREFIX(str, Enum):
    
    # construction
    MATERIAL                  = "MTRL"
    SURFACE_CONSTRUCTION      = "CTSF"
    FENESTRATION_CONSTRUCTION = "CTFN"
    
    # hvac
    SOURCE_SYSTEM  = "SRCE"
    SUPPLY_SYSTEM  = "SUPL"
    HEAT_EXCHANGER = "ERVT"
    PV_PANEL       = "PVPN"
    
    # shape
    SURFACE      = "SURF"
    FENESTRATION = "FNST"
    ZONE         = "ZONE"
    
    # profile
    DAY_SCHEDULE = "DYSC"
    RULESET     = "RLST"
    SCHEDULE    = "SCHE"
    PROFILE     = "PRFL"
    
    def __format__(self, format_spec:str) -> str:
        suffix = f":{format_spec}" if format_spec else ""
        return f"{self.value}{suffix}-"
    
    def __str__(self) -> str:
        return self.__format__("")
    
    def __repr__(self) -> str:
        return self.value
    
    
    
    
    
    
    