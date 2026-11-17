
# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #

# built-in modules
from __future__ import annotations
import re
import math
import datetime
from typing import (
    Any     ,
    Callable,
)
from enum import Enum
from copy import deepcopy
from collections import UserList

# third-party modules

# local modules
from ..imugi import (
    IdfObject,
)
from ..utils import (
    validate_type ,
)
from ..common import (
    Setting,
)

# ---------------------------------------------------------------------------- #
#                                  EXCEPTIONS                                  #
# ---------------------------------------------------------------------------- #

class ScheduleOperationError(TypeError):
    pass

# ---------------------------------------------------------------------------- #
#                                    CLASSES                                   #
# ---------------------------------------------------------------------------- #

class ScheduleType(str, Enum):
    TEMPERATURE = "temperature"
    ONOFF       = "onoff"
    FRACTION    = "fraction"
    REAL        = "real"

    """ fundamental properties
    """

    @property
    def idf_objname(self) -> str:
        return f"ScheduleTypeLimits:{self.value.capitalize()}"

    @property
    def lower_limit(self) -> int|float|None:
        match self:
            case ScheduleType.TEMPERATURE: return -50
            case ScheduleType.ONOFF      : return 0
            case ScheduleType.FRACTION   : return 0
            case ScheduleType.REAL       : return None

    @property
    def upper_limit(self) -> int|float|None:
        match self:
            case ScheduleType.TEMPERATURE: return 200
            case ScheduleType.ONOFF      : return 1
            case ScheduleType.FRACTION   : return 1
            case ScheduleType.REAL       : return None

    @property
    def numeric_type(self) -> str:
        match self:
            case ScheduleType.ONOFF: return "Discrete"
            case _                 : return "Continuous"

    @property
    def unit_type(self) -> str:
        match self:
            case ScheduleType.TEMPERATURE: return "Temperature"
            case _                       : return "Dimensionless"

    """ core methods
    """

    def validate(self, value: int|float|bool) -> int|float:
        
        # check type and coerce bool to int
        if isinstance(value, bool):
            value = int(value)

        elif not isinstance(value, int|float):
            raise TypeError(
                f"{self.value} schedule value must be numeric or boolean, got {type(value).__name__}."
            )

        # check value range
        match self:
            case ScheduleType.TEMPERATURE:
                if not (self.lower_limit <= value <= self.upper_limit):
                    raise ValueError(
                        f"Temperature schedule value must be within [{self.lower_limit}, {self.upper_limit}], got {value}."
                    )
                return float(value)

            case ScheduleType.ONOFF:
                if value not in (0, 1):
                    raise ValueError(
                        f"ONOFF schedule value must be either 0 or 1, got {value}."
                    )
                return int(value)

            case ScheduleType.FRACTION:
                if not (0 <= value <= 1):
                    raise ValueError(
                        f"Fraction schedule value must be within [0, 1], got {value}."
                    )
                return float(value)

            case ScheduleType.REAL:
                return float(value)
    
    """ conversion and IO methods
    """
    
    def to_idf_object(self) -> IdfObject:
        return IdfObject(
            "ScheduleTypeLimits",
            [
                self.idf_objname ,
                self.lower_limit ,
                self.upper_limit ,
                self.numeric_type,
                self.unit_type   ,
            ],
        )
    
    """ representation
    """
    
    def __str__(self) -> str:
        return self.value

"""
NOTE: Schedule operation result type rules

- Rows are left operands and columns are right operands.
- "-" means the operation is not allowed and should raise an error.
- "value" means a scalar numeric value: int|float.
- If the result type is "onoff", calculated values must be exactly 0 or 1.
- If the result type is "temp", calculated values must satisfy the
  temperature schedule range.
- RuleSet and Schedule operations should simply propagate DaySchedule
  operations. Type validation is handled at the DaySchedule level.

MUL
          | onoff    | fraction | real     | temp     | value
----------+----------+----------+----------+----------+----------
onoff     | onoff    | fraction | real     | temp     | real
fraction  | fraction | fraction | real     | temp     | fraction
real      | real     | real     | real     | temp     | real
temp      | temp     | temp     | temp     | temp     | temp
value     | real     | fraction | real     | temp     | -

TRUEDIV
          | onoff    | fraction | real     | temp     | value
----------+----------+----------+----------+----------+----------
onoff     | -        | -        | -        | -        | real
fraction  | -        | -        | fraction | -        | fraction
real      | -        | -        | real     | -        | real
temp      | -        | -        | temp     | -        | temp
value     | -        | -        | real     | -        | -

ADD
          | onoff    | fraction | real     | temp     | value
----------+----------+----------+----------+----------+----------
onoff     | -        | -        | -        | -        | -
fraction  | -        | fraction | -        | -        | fraction
real      | -        | -        | real     | temp     | real
temp      | -        | -        | temp     | temp     | temp
value     | -        | -        | real     | temp     | -

SUB
          | onoff    | fraction | real     | temp     | value
----------+----------+----------+----------+----------+----------
onoff     | -        | -        | -        | -        | -
fraction  | -        | fraction | -        | -        | fraction
real      | -        | -        | real     | temp     | real
temp      | -        | -        | temp     | temp     | temp
value     | -        | fraction | real     | temp     | -

AND, OR
          | onoff    | fraction | real     | temp     | value
----------+----------+----------+----------+----------+----------
onoff     | onoff    | -        | -        | -        | -
fraction  | -        | -        | -        | -        | -
real      | -        | -        | -        | -        | -
temp      | -        | -        | -        | -        | -
value     | -        | -        | -        | -        | -

INVERT
          | result
----------+----------
onoff     | onoff
fraction  | -
real      | -
temp      | -

ELEMENT_EQ, ELEMENT_NE, LT, LE, GT, GE
          | onoff    | fraction | real     | temp     | value
----------+----------+----------+----------+----------+----------
onoff     | onoff    | onoff    | onoff    | onoff    | onoff
fraction  | onoff    | onoff    | onoff    | onoff    | onoff
real      | onoff    | onoff    | onoff    | onoff    | onoff
temp      | onoff    | onoff    | onoff    | onoff    | onoff
value     | onoff    | onoff    | onoff    | onoff    | -

ELEMENT_MIN, ELEMENT_MAX
          | onoff    | fraction | real     | temp     | value
----------+----------+----------+----------+----------+----------
onoff     | -        | -        | -        | -        | -
fraction  | -        | fraction | -        | -        | fraction
real      | -        | -        | real     | -        | real
temp      | -        | -        | -        | temp     | temp
value     | -        | fraction | real     | temp     | -
"""


class DaySchedule(UserList):
    
    DATA_INTERVAL = 6 # per hour
    
    def __init__(self,
        name         :str|None            =None,
        value        :list[int|float]|None=None,
        *,
        type:ScheduleType=ScheduleType.REAL,
        unit:str|None    =None             ,
        ) -> None:
        
        # fundamental properties
        if name is None:
            name = hex(id(self))
        self.name = name
        
        self.type = type
        self.unit = unit
        
        # default value is 0
        if value is None:
            value = [0]*self.fixed_length
        
        # value length check
        if len(value) != self.fixed_length:
            raise ValueError(
                f"DaySchedule requires exactly {self.fixed_length} values, got {len(value)}."
            )
        
        # allocate data list and validate values
        self.data = [0] * self.fixed_length
        for idx, item in enumerate(value):
            self[idx] = item
        
    """ fundamental properties
    """
    
    @property
    def type(self) -> ScheduleType:
        return self.__schedule_type
    
    @type.setter
    def type(self, value: ScheduleType|str) -> None:
        self.__schedule_type = ScheduleType(value)
        
    def astype(self,
        newtype:ScheduleType|str,
        inplace:bool=False      ,
        ) -> DaySchedule|None:
        
        if inplace:
            newtype = ScheduleType(newtype)
            new_values = [newtype.validate(value) for value in self.data]
            self.__schedule_type = newtype
            self.data = new_values
            return None
        else:
            return DaySchedule(self.name, self.data, type=newtype, unit=self.unit)
    
    @property
    def fixed_length(self) -> int:
        return DaySchedule.DATA_INTERVAL * 24
    
    def __setitem__(self, index:int, item:int|float) -> None:
        
        item = self.type.validate(item)
        super().__setitem__(index, item)
    
    """ algebraic operations
    """
        
    def __mul__(self, other:int|float|DaySchedule) -> DaySchedule:
    
        if isinstance(other, DaySchedule):
            
            # type validation and calculation
            match self.type:
                case ScheduleType.ONOFF:
                                                       output_type = other.type
                case ScheduleType.FRACTION:
                    match other.type:
                        case ScheduleType.ONOFF      : output_type = self.type
                        case _                       : output_type = other.type
                case ScheduleType.REAL:
                    match other.type:
                        case ScheduleType.TEMPERATURE: output_type = other.type
                        case _                       : output_type = self.type
                case ScheduleType.TEMPERATURE:
                                                       output_type = self.type
            
            # element calculation
            return DaySchedule(
                f"{self.name}:MUL:{other.name}",
                [a * b for a,b in zip(self.data, other.data)],
                type=output_type
                )
        
        elif isinstance(other, int|float):
            
            # type validation and calculation
            match self.type:
                case ScheduleType.ONOFF: output_type = ScheduleType.REAL
                case _                 : output_type = self.type
            
            # element calculation
            return DaySchedule(
                self.name,
                [item * other for item in self.data],
                type=output_type
                )
        
        # unsupported type
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule multiplication: {self.type} * {type(other).__name__}. Right operand must be int, float, or DaySchedule."
            )
        
    def __rmul__(self, other:int|float) -> DaySchedule:
        return self.__mul__(other)
    
    def __truediv__(self, other:int|float|DaySchedule) -> DaySchedule:
        
        if isinstance(other, DaySchedule):
            
            # type validation and calculation
            if self.type is ScheduleType.ONOFF:
                raise ScheduleOperationError(
                    f"Unsupported DaySchedule division: {self.type} / {other.type} ({self.name!r}, {other.name!r}). ONOFF schedules cannot be divided."
                )
            if other.type is not ScheduleType.REAL:
                raise ScheduleOperationError(
                    f"Unsupported DaySchedule division: {self.type} / {other.type} ({self.name!r}, {other.name!r}). The right-hand DaySchedule divisor must be REAL."
                )
            output_type = self.type
            
            # element calculation
            if any(v == 0 for v in other.data):
                raise ZeroDivisionError(
                    f"Cannot divide DaySchedule {self.name!r} by {other.name!r}: divisor contains zero."
                )
            
            return DaySchedule(
                f"{self.name}:DIV:{other.name}",
                [a / b for a,b in zip(self.data, other.data)],
                type=output_type
                )
        
        elif isinstance(other, int|float):
            
            # type calculation
            match self.type:
                case ScheduleType.ONOFF: output_type = ScheduleType.REAL
                case _                 : output_type = self.type
            
            # element calculation
            if other == 0:
                raise ZeroDivisionError(
                    f"Cannot divide DaySchedule {self.name!r} by scalar zero."
                )
            return DaySchedule(
                self.name,
                [item / other for item in self.data],
                type=output_type
                )

        # unsupported type
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule division: {self.type} / {type(other).__name__}. Right operand must be int, float, or DaySchedule."
            )
            
    def __rtruediv__(self, other:int|float) -> DaySchedule:
        
        # type validation and calculation
        if self.type is not ScheduleType.REAL:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule reverse division: value / {self.type} ({self.name!r}). Scalar divided by DaySchedule is only supported for REAL schedules."
            )
        if not isinstance(other, int|float):
            raise ScheduleOperationError(
                f"Unsupported DaySchedule reverse division: {type(other).__name__} / {self.type}. Left operand must be int or float."
            )
        
        # element calculation
        if any(v == 0 for v in self.data):
            raise ZeroDivisionError(
                f"Cannot divide scalar {other!r} by DaySchedule {self.name!r}: divisor contains zero."
            )
                
        return DaySchedule(
            self.name,
            [other / item for item in self.data],
            type=self.type
            )
    
    def __add__(self, other:DaySchedule) -> DaySchedule:
        
        if isinstance(other, DaySchedule):
            
            # type validation and calculation
            match self.type:
                case ScheduleType.ONOFF:
                    raise ScheduleOperationError(
                        f"Unsupported DaySchedule addition: ONOFF + {other.type} ({self.name!r}, {other.name!r}). ONOFF schedules cannot be added."

                    )
                case ScheduleType.FRACTION:
                    match other.type:
                        case ScheduleType.FRACTION   : output_type = self.type
                        case _                       : 
                            raise ScheduleOperationError(
                                f"Unsupported DaySchedule addition: FRACTION + {other.type} ({self.name!r}, {other.name!r}). FRACTION schedules can only be added to FRACTION schedules."
                            )
                case ScheduleType.REAL:
                    match other.type:
                        case ScheduleType.REAL       : output_type = other.type
                        case ScheduleType.TEMPERATURE: output_type = other.type
                        case _                       :
                            raise ScheduleOperationError(
                                f"Unsupported DaySchedule addition: REAL + {other.type} ({self.name!r}, {other.name!r}). REAL schedules can only be added to REAL or TEMPERATURE schedules."
                            )
                case ScheduleType.TEMPERATURE:
                    match other.type:
                        case ScheduleType.REAL       : output_type = self.type
                        case ScheduleType.TEMPERATURE: output_type = self.type
                        case _                       :
                            raise ScheduleOperationError(
                                f"Unsupported DaySchedule addition: TEMPERATURE + {other.type} ({self.name!r}, {other.name!r}). TEMPERATURE schedules can only be added to REAL or TEMPERATURE schedules."
                            )
            
            # element calculation
            return DaySchedule(
                f"{self.name}:ADD:{other.name}",
                [self_item+other_item for self_item, other_item in zip(self.data, other.data)],
                type=output_type
            )
        
        elif isinstance(other, int|float):
            
            # type validation and calculation
            if self.type is ScheduleType.ONOFF:
                raise ScheduleOperationError(
                    f"Unsupported DaySchedule addition: ONOFF + value ({self.name!r}, {other!r}). ONOFF schedules cannot be added to scalar values."
                )
            output_type = self.type
            
            # element calculation
            return DaySchedule(
                f"{self.name}:ADD:{other}",
                [self_item+other for self_item in self.data],
                type=output_type
            )
            
        # unsupported type
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule addition: {self.type} + {type(other).__name__}. Right operand must be int, float, or DaySchedule."
            )
        
    def __radd__(self, other:int|float) -> DaySchedule:
        return self.__add__(other)
    
    def __sub__(self, other:int|float|DaySchedule) -> DaySchedule:
        
        if isinstance(other, DaySchedule):
            
            # type validation and calculation
            match self.type:
                case ScheduleType.ONOFF:
                    raise ScheduleOperationError(
                        f"Unsupported DaySchedule subtraction: ONOFF - {other.type} ({self.name!r}, {other.name!r}). ONOFF schedules cannot be subtracted."
                    )
                case ScheduleType.FRACTION:
                    match other.type:
                        case ScheduleType.FRACTION   : output_type = self.type
                        case _                       : 
                            raise ScheduleOperationError(
                                f"Unsupported DaySchedule subtraction: FRACTION - {other.type} ({self.name!r}, {other.name!r}). FRACTION schedules can only be subtracted by FRACTION schedules."
                            )
                case ScheduleType.REAL:
                    match other.type:
                        case ScheduleType.REAL       : output_type = other.type
                        case ScheduleType.TEMPERATURE: output_type = other.type
                        case _                       :
                            raise ScheduleOperationError(
                                f"Unsupported DaySchedule subtraction: REAL - {other.type} ({self.name!r}, {other.name!r}). REAL schedules can only be subtracted by REAL or TEMPERATURE schedules."
                            )
                case ScheduleType.TEMPERATURE:
                    match other.type:
                        case ScheduleType.REAL       : output_type = self.type
                        case ScheduleType.TEMPERATURE: output_type = self.type
                        case _                       :
                            raise ScheduleOperationError(
                                f"Unsupported DaySchedule subtraction: TEMPERATURE - {other.type} ({self.name!r}, {other.name!r}). TEMPERATURE schedules can only be subtracted by REAL or TEMPERATURE schedules."
                            )
            
            # element calculation
            return DaySchedule(
                f"{self.name}:SUB:{other.name}",
                [self_item-other_item for self_item, other_item in zip(self.data, other.data)],
                type=output_type
            )
        
        elif isinstance(other, int|float):
            
            # type validation and calculation
            if self.type is ScheduleType.ONOFF:
                raise ScheduleOperationError(
                    f"Unsupported DaySchedule subtraction: ONOFF - value ({self.name!r}, {other!r}). ONOFF schedules cannot be subtracted by scalar values."

                )
            output_type = self.type
            
            # element calculation
            return DaySchedule(
                f"{self.name}:SUB:{other}",
                [self_item-other for self_item in self.data],
                type=output_type
            )
            
        # unsupported type
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule subtraction: {self.type} - {type(other).__name__}. Right operand must be int, float, or DaySchedule."
            )
    
    def __rsub__(self, other:int|float) -> DaySchedule:
        
        # type validation and calculation
        if self.type is ScheduleType.ONOFF:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule reverse subtraction: value - ONOFF ({other!r}, {self.name!r}). ONOFF schedules cannot be used in scalar reverse subtraction."
            )
        output_type = self.type
        
        # element calculation
        return DaySchedule(
            f"{self.name}:SUB:{other}",
            [other-self_item for self_item in self.data],
            type=output_type
        )
        
    def __and__(self, other:DaySchedule) -> DaySchedule:
        
        if (self.type is not ScheduleType.ONOFF) or (other.type is not ScheduleType.ONOFF):
            raise ScheduleOperationError(
                f"Unsupported DaySchedule logical AND: {self.type} & {other.type} ({self.name!r}, {other.name!r}). Logical operations require both operands to be ONOFF schedules."
            )
            
        return DaySchedule(
            f"{self.name}:AND:{other.name}",
            [int(bool(a) and bool(b)) for a,b in zip(self.data, other.data)],
            type=ScheduleType.ONOFF
        )
        
    def __or__(self, other:DaySchedule) -> DaySchedule:
        
        if (self.type is not ScheduleType.ONOFF) or (other.type is not ScheduleType.ONOFF):
            raise ScheduleOperationError(
                f"Unsupported DaySchedule logical OR: {self.type} | {other.type} ({self.name!r}, {other.name!r}). Logical operations require both operands to be ONOFF schedules."
            )
            
        return DaySchedule(
            f"{self.name}:OR:{other.name}",
            [int(bool(a) or bool(b)) for a,b in zip(self.data, other.data)],
            type=ScheduleType.ONOFF
        )
        
    def __invert__(self) -> DaySchedule:
        
        if self.type is not ScheduleType.ONOFF:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule inversion: ~{self.type} ({self.name!r}). Inversion is only supported for ONOFF schedules."
            )
            
        return DaySchedule(
            f"{self.name}:INVERTED",
            [int(not bool(value)) for value in self.data],
            type = ScheduleType.ONOFF
        )
        
    def element_eq(self, other:int|float|DaySchedule) -> DaySchedule:
        
        if isinstance(other, DaySchedule):
            
            return DaySchedule(
                f"{self.name}:EQ:{other.name}",
                [int(a == b) for a,b in zip(self.data, other.data)],
                type=ScheduleType.ONOFF
            )
            
        elif isinstance(other, int|float):
            
            return DaySchedule(
                f"{self.name}:EQ:{other}",
                [int(v == other) for v in self.data],
                type=ScheduleType.ONOFF
            )
        
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule equality comparison: {self.type} == {type(other).__name__}. Right operand must be int, float, or DaySchedule."
            )
    
    def element_ne(self, other:int|float|DaySchedule) -> DaySchedule:
        
        if isinstance(other, DaySchedule):
            
            return DaySchedule(
                f"{self.name}:NE:{other.name}",
                [int(a != b) for a,b in zip(self.data, other.data)],
                type=ScheduleType.ONOFF
            )
            
        elif isinstance(other, int|float):
            
            return DaySchedule(
                f"{self.name}:NE:{other}",
                [int(v != other) for v in self.data],
                type=ScheduleType.ONOFF
            )
        
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule inequality comparison: {self.type} != {type(other).__name__}. Right operand must be int, float, or DaySchedule."
            )
    
    def __lt__(self, other:int|float|DaySchedule) -> DaySchedule:
        
        if isinstance(other, DaySchedule):
            
            return DaySchedule(
                f"{self.name}:LT:{other.name}",
                [int(a < b) for a,b in zip(self.data, other.data)],
                type=ScheduleType.ONOFF
            )
            
        elif isinstance(other, int|float):
            
            return DaySchedule(
                f"{self.name}:LT:{other}",
                [int(v < other) for v in self.data],
                type=ScheduleType.ONOFF
            )
        
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule less-than comparison: {self.type} < {type(other).__name__}. Right operand must be int, float, or DaySchedule."

            )
        
    def __le__(self, other:int|float|DaySchedule) -> DaySchedule:
        
        if isinstance(other, DaySchedule):
            
            return DaySchedule(
                f"{self.name}:LE:{other.name}",
                [int(a <= b) for a,b in zip(self.data, other.data)],
                type=ScheduleType.ONOFF
            )
            
        elif isinstance(other, int|float):
            
            return DaySchedule(
                f"{self.name}:LE:{other}",
                [int(v <= other) for v in self.data],
                type=ScheduleType.ONOFF
            )
        
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule less-than-or-equal comparison: {self.type} <= {type(other).__name__}. Right operand must be int, float, or DaySchedule."
            )
       
    def __gt__(self, other:int|float|DaySchedule) -> DaySchedule:
        
        if isinstance(other, DaySchedule):
            
            return DaySchedule(
                f"{self.name}:GT:{other.name}",
                [int(a > b) for a,b in zip(self.data, other.data)],
                type=ScheduleType.ONOFF
            )
            
        elif isinstance(other, int|float):
            
            return DaySchedule(
                f"{self.name}:GT:{other}",
                [int(v > other) for v in self.data],
                type=ScheduleType.ONOFF
            )
        
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule greater-than comparison: {self.type} > {type(other).__name__}. Right operand must be int, float, or DaySchedule."
            )
    
    def __ge__(self, other:int|float|DaySchedule) -> DaySchedule:
        
        if isinstance(other, DaySchedule):
            
            return DaySchedule(
                f"{self.name}:GE:{other.name}",
                [int(a >= b) for a,b in zip(self.data, other.data)],
                type=ScheduleType.ONOFF
            )
            
        elif isinstance(other, int|float):
            
            return DaySchedule(
                f"{self.name}:GE:{other}",
                [int(v >= other) for v in self.data],
                type=ScheduleType.ONOFF
            )
        
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule greater-than-or-equal comparison: {self.type} >= {type(other).__name__}. Right operand must be int, float, or DaySchedule."
            )
    
    def element_min(self, other:int|float|DaySchedule) -> DaySchedule:
        
        if isinstance(other, DaySchedule):
            
            # type validation and calculation
            if self.type is not other.type:
                raise ScheduleOperationError(
                    f"Unsupported DaySchedule element_min: {self.type} with {other.type} ({self.name!r}, {other.name!r}). element_min requires operands of the same non-ONOFF schedule type."
                )
            if self.type is ScheduleType.ONOFF:
                raise ScheduleOperationError(
                    f"Unsupported DaySchedule element_min: ONOFF ({self.name!r}). element_min is not defined for ONOFF schedules; use logical AND for ONOFF schedules."
                )
            output_type = self.type    
            
            # element calculation
            return DaySchedule(
                f"{self.name}:MIN:{other.name}",
                [min(a,b) for a,b in zip(self.data, other.data)],
                type=output_type
            )
            
        elif isinstance(other, int|float):
            
            # type validation and calculation
            if self.type is ScheduleType.ONOFF:
                raise ScheduleOperationError(
                    f"Unsupported DaySchedule element_min: ONOFF with scalar ({self.name!r}, {other!r}). element_min is not defined for ONOFF schedules."
                )
            output_type = self.type
                
            # element calculation
            return DaySchedule(
                f"{self.name}:MIN:{other}",
                [min(a,other) for a in self.data],
                type=output_type
            )
        
        # unsupported type
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule element_min: {self.type} with {type(other).__name__}. Right operand must be int, float, or DaySchedule."
            )
        
    def element_max(self, other:int|float|DaySchedule) -> DaySchedule:
        
        if isinstance(other, DaySchedule):
            
            # type validation and calculation
            if self.type is not other.type:
                raise ScheduleOperationError(
                    f"Unsupported DaySchedule element_max: {self.type} with {other.type} ({self.name!r}, {other.name!r}). element_max requires operands of the same non-ONOFF schedule type."
                )
            if self.type is ScheduleType.ONOFF:
                raise ScheduleOperationError(
                    f"Unsupported DaySchedule element_max: ONOFF ({self.name!r}). element_max is not defined for ONOFF schedules; use logical OR for ONOFF schedules."
                )
            output_type = self.type    
            
            # element calculation
            return DaySchedule(
                f"{self.name}:MAX:{other.name}",
                [max(a,b) for a,b in zip(self.data, other.data)],
                type=output_type
            )
            
        elif isinstance(other, int|float):
            
            # type validation and calculation
            if self.type is ScheduleType.ONOFF:
                raise ScheduleOperationError(
                    f"Unsupported DaySchedule element_max: ONOFF with scalar ({self.name!r}, {other!r}). element_max is not defined for ONOFF schedules."
                )
            output_type = self.type
                
            # element calculation
            return DaySchedule(
                f"{self.name}:MAX:{other}",
                [max(a,other) for a in self.data],
                type=output_type
            )
        
        # unsupported type
        else:
            raise ScheduleOperationError(
                f"Unsupported DaySchedule element_max: {self.type} with {type(other).__name__}. Right operand must be int, float, or DaySchedule."
            )
    
    @property
    def min(self) -> int|float:
        return min(self.data)
    
    @property
    def max(self) -> int|float:
        return max(self.data)
    
    def normalize_by_max(self, inplace:bool=False, *, new_name:str=None):
        
        if self.max == 0:
            scaler = 1
        else:
            scaler = self.max
        
        if inplace:
            self.data = [item/scaler for item in self.data]
            return
        
        else:
            
            if new_name is None:
                new_name = self.name + "_normalized"
            
            normalized_schedule = self / scaler
            normalized_schedule.name = new_name
            
            return normalized_schedule
    
    def is_on(self) -> DaySchedule:
        return self.element_eq(1)

    def is_off(self) -> DaySchedule:
        return self.element_eq(0)

    def is_positive(self) -> DaySchedule:
        return self > 0

    def is_negative(self) -> DaySchedule:
        return self < 0

    def is_zero(self) -> DaySchedule:
        return self.element_eq(0)

    def is_nonzero(self) -> DaySchedule:
        return self.element_ne(0)

    def is_between(
        self,
        min_value: int|float,
        max_value: int|float,
        *,
        include_min: bool = True,
        include_max: bool = True,
    ) -> DaySchedule:
        
        lower = self >= min_value if include_min else self > min_value
        upper = self <= max_value if include_max else self < max_value

        return lower & upper    
    
    @property
    def step_in_hours(self) -> float:
        return 1/DaySchedule.DATA_INTERVAL
    
    @property
    def integral(self) -> float:
        return sum(self.data) * self.step_in_hours
    
    @property
    def positive_hours(self) -> float:
        return sum(v > 0 for v in self.data) * self.step_in_hours
    
    @property
    def nonzero_hours(self) -> float:
        return sum(v != 0 for v in self.data) * self.step_in_hours
    
    @property
    def has_positive(self) -> bool:
        return any(v>0 for v in self.data)
    
    @property
    def has_nonzero(self) -> bool:
        return any(v!=0 for v in self.data)
    
    @property
    def is_constant(self) -> bool:
        return all(v == self.data[0] for v in self.data)
    
    @property
    def average(self) -> float:
        return sum(self.data) / self.fixed_length
    
    @property
    def positive_average(self) -> float:
        positive_values = [v for v in self.data if v > 0]
        if not positive_values:
            return 0.0
        return sum(positive_values) / len(positive_values)
    
    """ prohibited methods
    """
    
    def __delitem__(self, index:int) -> None:
        raise AttributeError(
            f"Cannot delete items from fixed-length DaySchedule {self.name!r} with length {self.fixed_length}."
        )
        
    def append(self, item:Any) -> None:
        raise AttributeError(
            f"Cannot append items to fixed-length DaySchedule {self.name!r} with length {self.fixed_length}."
        )

    def extend(self, items: list) -> None:
        raise AttributeError(
            f"Cannot extend fixed-length DaySchedule {self.name!r} with length {self.fixed_length}."
        )
        
    def pop(self, index:int= -1) -> None:
        raise AttributeError(
            f"Cannot pop items from fixed-length DaySchedule {self.name!r} with length {self.fixed_length}."
        )
        
    def clear(self) -> None:
        raise AttributeError(
            f"Cannot clear fixed-length DaySchedule {self.name!r} with length {self.fixed_length}."
        )
        
    def insert(self, index:int, item:Any) -> None:
        raise AttributeError(
            f"Cannot insert items into fixed-length DaySchedule {self.name!r} with length {self.fixed_length}."
        )
    
    """ time-related operations
    """
    
    @staticmethod
    def time_tuple() -> list[tuple[int]]:
        return [
            (hh + (1 if math.isclose(mm,60) else 0), (0 if math.isclose(mm, 60) else mm)) 
            for hh in range(24)
            for mm in [int(n*60/DaySchedule.DATA_INTERVAL) for n in range(1,DaySchedule.DATA_INTERVAL+1)]
            ]
    
    def compactize(self) -> list[tuple[int, int, int|float]]:
        
        time_tuple = DaySchedule.time_tuple()
        
        compact_tuples = []
        for idx, value in enumerate(self.data):
            
            new_tuple = (*time_tuple[idx], value)
            
            if (idx == 0) or (value != self.data[idx-1]):
                compact_tuples.append(new_tuple)
            else:
                compact_tuples[-1] = new_tuple           
        
        return compact_tuples
    
    def clip(
        self,
        min_value:int|float|None = None,
        max_value:int|float|None = None,
        *,
        name   :str|None=None ,
        inplace:bool    =False,
    ) -> DaySchedule|None:
        
        if (min_value is None) and (max_value is None):
            values = list(self.data)
        else:
            values = []
            for value in self.data:
                clipped_value = value

                if min_value is not None:
                    clipped_value = max(min_value, clipped_value)

                if max_value is not None:
                    clipped_value = min(max_value, clipped_value)

                values.append(clipped_value)

        if inplace:
            for idx, value in enumerate(values):
                self[idx] = value
            return None

        return DaySchedule(
            name or f"{self.name}:CLIP",
            values,
            type=self.type,
            unit=self.unit,
        )
    
    @classmethod
    def where(
        cls,
        condition: DaySchedule,
        if_true  : int|float|DaySchedule,
        if_false : int|float|DaySchedule,
        *,
        name: str|None=None,
        type: ScheduleType|None=None,
    ) -> DaySchedule:
        
        if condition.type is not ScheduleType.ONOFF:
            raise ScheduleOperationError(
                f"DaySchedule.where requires an ONOFF condition schedule, got {condition.type}."
            )

        # infer result type
        given_types = [
            value.type
            for value in [if_true, if_false]
            if isinstance(value, DaySchedule)
        ]

        if type is None:
            if given_types:
                if len(set(given_types)) > 1:
                    raise ScheduleOperationError(
                        f"DaySchedule.where got mixed result schedule types: {set(given_types)}."
                    )
                type = given_types[0]
            else:
                type = ScheduleType.REAL
        else:
            type = ScheduleType(type)

        def get_values(value: int|float|DaySchedule) -> list[int|float]:
            if isinstance(value, DaySchedule):
                if value.type is not type:
                    raise ScheduleOperationError(
                        f"DaySchedule.where expected {type} result schedule, got {value.type}."
                    )
                return list(value.data)

            if isinstance(value, int|float):
                return [value] * condition.fixed_length

            raise TypeError(
                f"DaySchedule.where expects int, float, or DaySchedule, got {type(value).__name__}."
            )

        true_values = get_values(if_true)
        false_values = get_values(if_false)

        return cls(
            name,
            [
                true_value if bool(condition_value) else false_value
                for condition_value, true_value, false_value
                in zip(condition.data, true_values, false_values)
            ],
            type=type,
        )
    
    @classmethod
    def from_compact(cls,
        name  :str|None,
        values:list[tuple[int,int, int|float]],
        type  :ScheduleType=ScheduleType.REAL
        ) -> DaySchedule:
        
        """
        Create a day schedule from EnergyPlus-like compact "Until" tuples.

        Each tuple has the form:

            (until_hour, until_minute, value)

        The time in each tuple represents the end time of the interval to
        which the value is applied. Therefore, this method follows the same
        interpretation as EnergyPlus Schedule:Compact "Until" fields.

        For example:

            [
                (9, 0, 0),
                (18, 0, 1),
                (24, 0, 0),
            ]

        means:

            00:00 < time <= 09:00  -> 0
            09:00 < time <= 18:00  -> 1
            18:00 < time <= 24:00  -> 0

        Since DaySchedule uses 10-minute intervals by default, the internal
        time points are interpreted as interval end times:

            00:10, 00:20, ..., 23:50, 24:00

        Thus, the example above produces:

            00:10 ~ 09:00  -> 0
            09:10 ~ 18:00  -> 1
            18:10 ~ 24:00  -> 0

        The final tuple must end at 24:00.

        Parameters
        ----------
        name:
            Name of the day schedule.
        values:
            Compact schedule definition as a list of
            (until_hour, until_minute, value) tuples.
        type:
            Schedule type used for value validation.

        Returns
        -------
        DaySchedule
            A fixed-length day schedule with 24 * DATA_INTERVAL values.

        Examples
        --------
        Constant OFF schedule:

            DaySchedule.from_compact(
                "always_off",
                [(24, 0, 0)],
                type=ScheduleType.ONOFF,
            )

        Office-hour ON/OFF schedule:

            DaySchedule.from_compact(
                "office_hours",
                [
                    (9, 0, 0),
                    (18, 0, 1),
                    (24, 0, 0),
                ],
                type=ScheduleType.ONOFF,
            )

        Temperature setpoint schedule:

            DaySchedule.from_compact(
                "heating_setpoint",
                [
                    (7, 0, 16),
                    (18, 0, 20),
                    (24, 0, 16),
                ],
                type=ScheduleType.TEMPERATURE,
            )

        Notes
        -----
        This method mutates a local copy of `values`, not the user-provided
        list.
        """
        
        # prevent mutation
        values = list(values)
        if not values:
            raise ValueError(
                f"Compact DaySchedule {name!r} must contain at least one (hour, minute, value) tuple."
            )
            
        if values[-1][:2] != (24,0):
            raise ValueError(
                f"Compact DaySchedule must end at 24:00, got {values[-1][:2]}"
            )
            
        schedule_values = []
        for time_tuple in DaySchedule.time_tuple():
            
            hh, mm, value = values[0]
            
            if time_tuple <= (hh, mm):
                schedule_values.append(value)
            else:
                values.pop(0)
                schedule_values.append(values[0][2])
         
        return cls(name, schedule_values, type=type)
    
    @classmethod
    def from_windows(
        cls,
        name    : str|None,
        default: int|float,
        windows: list[tuple[tuple[int,int], tuple[int,int], int|float]],
        type   : ScheduleType=ScheduleType.REAL,
        ) -> DaySchedule:
        
        """
        Create a day schedule from explicit time windows.

        Each window has the form:

            ((start_hour, start_minute), (end_hour, end_minute), value)

        Unlike `from_compact()`, this method uses start-inclusive and
        end-exclusive intervals:

            start <= interval_start < end

        Values outside all windows are filled with `default`.

        If multiple windows overlap, the first matching window is used.

        Parameters
        ----------
        name:
            Name of the day schedule.
        default:
            Value applied outside all windows.
        windows:
            List of time windows. Each item is
            ((start_hour, start_minute), (end_hour, end_minute), value).
        type:
            Schedule type used for value validation.

        Returns
        -------
        DaySchedule
            A fixed-length day schedule with 24 * DATA_INTERVAL values.

        Examples
        --------
        Office-hour ON/OFF schedule:

            DaySchedule.from_windows(
                "office_hours",
                default=0,
                windows=[
                    ((9, 0), (18, 0), 1),
                ],
                type=ScheduleType.ONOFF,
            )

        This means:

            09:00 <= interval_start < 18:00  -> 1
            otherwise                        -> 0

        Lunch-break lighting schedule:

            DaySchedule.from_windows(
                "lighting",
                default=0,
                windows=[
                    ((10, 0), (12, 0), 1),
                    ((13, 0), (18, 0), 1),
                ],
                type=ScheduleType.ONOFF,
            )

        Fraction schedule:

            DaySchedule.from_windows(
                "partial_availability",
                default=0.0,
                windows=[
                    ((8, 0), (12, 0), 0.5),
                    ((13, 0), (17, 0), 0.8),
                ],
                type=ScheduleType.FRACTION,
            )

        Temperature schedule with night setback:

            DaySchedule.from_windows(
                "heating_setpoint",
                default=16,
                windows=[
                    ((7, 0), (18, 0), 20),
                ],
                type=ScheduleType.TEMPERATURE,
            )

        Notes
        -----
        This method is usually more intuitive than `from_compact()` when the
        user wants to express that something is active "from A to B".
        """

        step_minutes = int(60 / cls.DATA_INTERVAL)

        def to_minutes(time_tuple: tuple[int, int]) -> int:
            hh, mm = time_tuple
            return hh * 60 + mm

        schedule_values = []

        for hh, mm in cls.time_tuple():
            interval_end = hh * 60 + mm
            interval_start = interval_end - step_minutes

            value = default

            for start, end, window_value in windows:
                if to_minutes(start) <= interval_start < to_minutes(end):
                    value = window_value
                    break

            schedule_values.append(value)

        return cls(name, schedule_values, type=type)
    
    @classmethod
    def from_constant(cls,
        name :str|None ,
        value:int|float,
        type :ScheduleType=ScheduleType.REAL
        ) -> DaySchedule:
        
        """
        Create a constant day schedule.

        This is a convenience wrapper around `from_compact()` using a single
        24:00 tuple.

        Parameters
        ----------
        name:
            Name of the day schedule.
        value:
            Constant value applied to the whole day.
        type:
            Schedule type used for value validation.

        Returns
        -------
        DaySchedule
            A fixed-length day schedule whose values are all equal to `value`.

        Examples
        --------
        Always OFF:

            DaySchedule.from_constant(
                "always_off",
                0,
                type=ScheduleType.ONOFF,
            )

        Always ON:

            DaySchedule.from_constant(
                "always_on",
                1,
                type=ScheduleType.ONOFF,
            )

        Constant heating setpoint:

            DaySchedule.from_constant(
                "heating_setpoint",
                20,
                type=ScheduleType.TEMPERATURE,
            )

        Constant real-valued schedule:

            DaySchedule.from_constant(
                "equipment_density",
                4.7,
                type=ScheduleType.REAL,
            )
        """
        
        return cls.from_compact(
            name,
            [(24, 0, value)],
            type=type
        )
    
    """ representation
    """
    
    def __deepcopy__(self, memo:dict):
        
        if id(self) in memo:
            return memo[id(self)]
        
        return DaySchedule(
            f"{self.name}:COPY",
            self.data,
            type = self.type,
            unit = self.unit,
        )
    
    def _format_value(self, value: int | float) -> str:
        if isinstance(value, float):
            return f"{value:.4g}"
        return str(value)


    def summary(self, *, max_segments: int = 6) -> str:
        compact = self.compactize()
        is_constant = len(compact) == 1

        unit_text = f", unit={self.unit}" if self.unit is not None else ""
        header = (
            f"DaySchedule {self.name!r} "
            f"[type={self.type}{unit_text}, steps={self.fixed_length}, "
            f"interval={int(60 / self.DATA_INTERVAL)} min]"
        )

        stats = (
            f"  range: min={self._format_value(self.min)}, "
            f"max={self._format_value(self.max)}, "
            f"constant={is_constant}, segments={len(compact)}"
        )

        preview_items = compact[:max_segments]
        preview = [
            f"  Until {hh:02d}:{mm:02d} -> {self._format_value(value)}"
            for hh, mm, value in preview_items
        ]

        if len(compact) > max_segments:
            preview.append(f"  ... ({len(compact) - max_segments} more segments)")

        return "\n".join([header, stats, *preview])

    def __str__(self) -> str:
        return self.summary()
    
    def __repr__(self) -> str:
        return f"<DaySchedule {self.name} at {hex(id(self))}>"

    def to_idf_compactexpr(self) -> list[str]:
        return sum([
            [f"Until: {hh:02d}:{mm:02d}", str(v)]
            for hh, mm, v in self.compactize()
        ], start=[])
    
class RuleSet:
    
    _WEEKDAY_KEYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
    _WEEKEND_KEYS = ["saturday", "sunday"]
    _DAY_KEYS     = _WEEKDAY_KEYS + _WEEKEND_KEYS + ["holiday"]
    
    def __init__(
        self,
        name: str|None,
        weekdays: DaySchedule|None = None,
        weekends: DaySchedule|None = None,
        *,
        monday   : DaySchedule|None = None,
        tuesday  : DaySchedule|None = None,
        wednesday: DaySchedule|None = None,
        thursday : DaySchedule|None = None,
        friday   : DaySchedule|None = None,
        saturday : DaySchedule|None = None,
        sunday   : DaySchedule|None = None,
        holiday  : DaySchedule|None = None,
        type: ScheduleType|str|None = None,
    ) -> None:

        given_days = [
            day for day in [
                weekdays, weekends,
                monday, tuesday, wednesday, thursday, friday,
                saturday, sunday, holiday,
            ]
            if day is not None
        ]

        if type is None:
            inferred_type = given_days[0].type if given_days else ScheduleType.REAL
        else:
            inferred_type = ScheduleType(type)

        mismatched_days = [
            day for day in given_days
            if day.type != inferred_type
        ]

        if mismatched_days:
            raise ValueError(
                f"RuleSet {name!r} contains mixed DaySchedule types. "
                f"Expected {inferred_type}, got {[day.type for day in mismatched_days]}."
            )

        if weekdays is None:
            weekdays = DaySchedule.from_constant(None, 0, type=inferred_type)

        if weekends is None:
            weekends = DaySchedule.from_constant(None, 0, type=inferred_type)

        if name is None:
            name = hex(id(self))

        self.name = name
        self.__type = inferred_type

        self.__weekdays = weekdays
        self.__weekends = weekends
        self.__monday = monday
        self.__tuesday = tuesday
        self.__wednesday = wednesday
        self.__thursday = thursday
        self.__friday = friday
        self.__saturday = saturday
        self.__sunday = sunday
        self.__holiday = holiday
    
    """ fundamental properties
    """
    
    @property
    def type(self) -> ScheduleType|str:
        return self.__type
    
    def astype(self,
        newtype:ScheduleType|str,
        inplace:bool=False      ,
        ) -> RuleSet|None:
        
        if inplace:
            self.weekdays.astype(newtype, inplace=True)
            self.weekends.astype(newtype, inplace=True)
            if self.monday    is not None: self.monday   .astype(newtype, inplace=True)
            if self.tuesday   is not None: self.tuesday  .astype(newtype, inplace=True)
            if self.wednesday is not None: self.wednesday.astype(newtype, inplace=True)
            if self.thursday  is not None: self.thursday .astype(newtype, inplace=True)
            if self.friday    is not None: self.friday   .astype(newtype, inplace=True)
            if self.saturday  is not None: self.saturday .astype(newtype, inplace=True)
            if self.sunday    is not None: self.sunday   .astype(newtype, inplace=True)
            if self.holiday   is not None: self.holiday  .astype(newtype, inplace=True)
            return None
        
        else:
            dayscheduledict = {
                k: v.astype(newtype) if v is not None else v
                for k, v in self.to_dict().items()
            }
            return RuleSet(
                self.name,
                **dayscheduledict
            )            
    
    @property
    def weekdays(self) -> DaySchedule:
        return self.__weekdays
    
    @weekdays.setter
    @validate_type(DaySchedule)
    def weekdays(self, value) -> None:
        self.__weekdays = value
        
    @property
    def weekends(self) -> DaySchedule:
        return self.__weekends
    
    @weekends.setter
    @validate_type(DaySchedule)
    def weekends(self, value) -> None:
        self.__weekends = value
    
    @property
    def monday(self) -> DaySchedule:
        return self.__monday
    
    @monday.setter
    @validate_type(DaySchedule, allow_none=True)
    def monday(self, value: DaySchedule|None) -> None:
        self.__monday = value
    
    @property
    def tuesday(self) -> DaySchedule:
        return self.__tuesday
    
    @tuesday.setter
    @validate_type(DaySchedule, allow_none=True)
    def tuesday(self, value: DaySchedule|None) -> None:
        self.__tuesday = value
        
    @property
    def wednesday(self) -> DaySchedule:
        return self.__wednesday
    
    @wednesday.setter
    @validate_type(DaySchedule, allow_none=True)
    def wednesday(self, value: DaySchedule|None) -> None:
        self.__wednesday = value
        
    @property
    def thursday(self) -> DaySchedule:
        return self.__thursday
    
    @thursday.setter
    @validate_type(DaySchedule, allow_none=True)
    def thursday(self, value: DaySchedule|None) -> None:
        self.__thursday = value
    
    @property
    def friday(self) -> DaySchedule:
        return self.__friday
    
    @friday.setter
    @validate_type(DaySchedule, allow_none=True)
    def friday(self, value: DaySchedule|None) -> None:
        self.__friday = value
    
    @property
    def saturday(self) -> DaySchedule:
        return self.__saturday
    
    @saturday.setter
    @validate_type(DaySchedule, allow_none=True)
    def saturday(self, value: DaySchedule|None) -> None:
        self.__saturday = value
    
    @property
    def sunday(self) -> DaySchedule:
        return self.__sunday
    
    @sunday.setter
    @validate_type(DaySchedule, allow_none=True)
    def sunday(self, value: DaySchedule|None) -> None:
        self.__sunday = value
    
    @property
    def holiday(self) -> DaySchedule:
        return self.__holiday
    
    @holiday.setter
    @validate_type(DaySchedule, allow_none=True)
    def holiday(self, value: DaySchedule|None) -> None:
        self.__holiday = value
    
    """ algebraic methods
    """
    
    @staticmethod
    def __default_day_for_key(
        ruleset: RuleSet,
        key    : str    ,
        ) -> DaySchedule:
        if key in ["weekdays", "monday", "tuesday", "wednesday", "thursday", "friday"]:
            return ruleset.weekdays

        if key in ["weekends", "saturday", "sunday", "holiday"]:
            return ruleset.weekends

        raise KeyError(f"Unknown RuleSet day key: {key}")
        
    @staticmethod
    def __operate_with_default(
        newname             : str,
        dayschedule_operator: Callable,
        self_ruleset        : RuleSet,
        other               : RuleSet|int|float,
        ) -> RuleSet:

        self_dict = self_ruleset.to_dict()

        # scalar case: keep scalar as scalar
        if isinstance(other, int|float):
            result = {}

            for key, self_day in self_dict.items():
                if key in ["weekdays", "weekends"]:
                    result[key] = dayschedule_operator(self_day, other)
                    continue

                # Preserve missing overrides.
                # If monday is None, keep it None and let IDF export fall back to weekdays.
                if self_day is None:
                    result[key] = None
                else:
                    result[key] = dayschedule_operator(self_day, other)

            return RuleSet(newname, **result)

        # RuleSet case
        if isinstance(other, RuleSet):
            other_dict = other.to_dict()
            result = {}

            for key in self_dict.keys():
                self_day = self_dict[key]
                other_day = other_dict[key]

                if key in ["weekdays", "weekends"]:
                    result[key] = dayschedule_operator(self_day, other_day)
                    continue

                if self_day is None and other_day is None:
                    result[key] = None
                    continue

                if self_day is None:
                    self_day = RuleSet.__default_day_for_key(self_ruleset, key)

                if other_day is None:
                    other_day = RuleSet.__default_day_for_key(other, key)

                result[key] = dayschedule_operator(self_day, other_day)

            return RuleSet(newname, **result)

        raise ScheduleOperationError(
            f"Unsupported RuleSet operation with {type(other).__name__}. "
            f"Right operand must be int, float, or RuleSet."
        )
    
    def __mul__(self, value:int|float|RuleSet) -> RuleSet:
        
        return RuleSet.__operate_with_default(
            f"{self.name}:MUL:{value.name if isinstance(value, RuleSet) else str(value)}",
            lambda a, b: a.__mul__(b),
            self, value
        )
        
    def __rmul__(self, value:int|float) -> RuleSet:
        return self.__mul__(value)
    
    def __truediv__(self, value:int|float|RuleSet) -> RuleSet:
        
        return RuleSet.__operate_with_default(
            f"{self.name}:DIV:{value.name if isinstance(value, RuleSet) else str(value)}",
            lambda a, b: a.__truediv__(b),
            self, value
        )
        
    def __rtruediv__(self, value: int|float) -> RuleSet:
        return RuleSet.__operate_with_default(
            f"{value}:DIV:{self.name}",
            lambda a, b: a.__rtruediv__(b),
            self,
            value,
        )
        
    def __add__(self, other: int|float|RuleSet) -> RuleSet:
        return RuleSet.__operate_with_default(
            f"{self.name}:ADD:{other.name if isinstance(other, RuleSet) else str(other)}",
            lambda a, b: a + b,
            self,
            other,
        )
    
    def __radd__(self, other: int|float) -> RuleSet:
        return RuleSet.__operate_with_default(
            f"{other}:ADD:{self.name}",
            lambda a, b: a.__radd__(b),
            self,
            other,
        )
    
    def __sub__(self, other:int|float|RuleSet) -> RuleSet:
        return RuleSet.__operate_with_default(
            f"{self.name}:SUB:{other.name if isinstance(other, RuleSet) else str(other)}",
            lambda a, b: a - b,
            self, other,
        )
    
    def __rsub__(self, other: int|float) -> RuleSet:
        return RuleSet.__operate_with_default(
            f"{other}:SUB:{self.name}",
            lambda a, b: a.__rsub__(b),
            self,
            other,
        )
    
    def __and__(self, other:RuleSet) -> RuleSet:
        return RuleSet.__operate_with_default(
            f"{self.name}:AND:{other.name}",
            lambda a, b: a.__and__(b),
            self, other
        )
        
    def __or__(self, other:RuleSet) -> RuleSet:
        return RuleSet.__operate_with_default(
            f"{self.name}:OR:{other.name}",
            lambda a, b: a.__or__(b),
            self, other
        )
        
    def __invert__(self) -> RuleSet:            
        return RuleSet(
            self.name,
            **{
                k: dayschedule.__invert__()
                for k,dayschedule in self.to_dict().items()
                if isinstance(dayschedule, DaySchedule)
            }
        )
    
    def element_eq(self, other:int|float|RuleSet) -> RuleSet:
            
        return RuleSet.__operate_with_default(
            f"{self.name}:EQ:{other.name if isinstance(other, RuleSet) else str(other)}",
            lambda a, b: a.element_eq(b),
            self, other
        )
        
    def element_ne(self, other:int|float|RuleSet) -> RuleSet:
            
        return RuleSet.__operate_with_default(
            f"{self.name}:NE:{other.name if isinstance(other, RuleSet) else str(other)}",
            lambda a, b: a.element_ne(b),
            self, other
        )
            
    def __lt__(self, other:int|float|RuleSet) -> RuleSet:
            
        return RuleSet.__operate_with_default(
            f"{self.name}:LT:{other.name if isinstance(other, RuleSet) else str(other)}",
            lambda a, b: a.__lt__(b),
            self, other
        )
        
    def __le__(self, other:int|float|RuleSet) -> RuleSet:
            
        return RuleSet.__operate_with_default(
            f"{self.name}:LE:{other.name if isinstance(other, RuleSet) else str(other)}",
            lambda a, b: a.__le__(b),
            self, other
        )
        
    def __gt__(self, other:int|float|RuleSet) -> RuleSet:
            
        return RuleSet.__operate_with_default(
            f"{self.name}:GT:{other.name if isinstance(other, RuleSet) else str(other)}",
            lambda a, b: a.__gt__(b),
            self, other
        )
        
    def __ge__(self, other:int|float|RuleSet) -> RuleSet:
            
        return RuleSet.__operate_with_default(
            f"{self.name}:GE:{other.name if isinstance(other, RuleSet) else str(other)}",
            lambda a, b: a.__ge__(b),
            self, other
        )     
        
    def element_min(self, other:int|float|RuleSet) -> RuleSet:
        
        return RuleSet.__operate_with_default(
            f"{self.name}:MIN:{other.name}",
            lambda a, b: a.element_min(b),
            self, other
        )
        
    def element_max(self, other:int|float|RuleSet) -> RuleSet:
        
        return RuleSet.__operate_with_default(
            f"{self.name}:MAX:{other.name}",
            lambda a, b: a.element_max(b),
            self, other
        )
    
    @property
    def min(self) -> int|float:
        return min([
            day_schedule.min
            for day_schedule in self.to_dict().values()
            if day_schedule is not None
        ])
    
    @property
    def max(self) -> int|float:
        return max([
            day_schedule.max
            for day_schedule in self.to_dict().values()
            if day_schedule is not None
        ])
        
    def normalize_by_max(self, *, new_name:str=None):
        
        if new_name is None:
            new_name = self.name + "_normalized"
        
        return RuleSet(
            new_name,
            self.weekdays.normalize_by_max() if self.weekdays is not None else None,
            self.weekends.normalize_by_max() if self.weekends is not None else None,
            monday    = self.monday   .normalize_by_max() if self.monday    is not None else None,
            tuesday   = self.tuesday  .normalize_by_max() if self.tuesday   is not None else None,
            wednesday = self.wednesday.normalize_by_max() if self.wednesday is not None else None,
            thursday  = self.thursday .normalize_by_max() if self.thursday  is not None else None,
            friday    = self.friday   .normalize_by_max() if self.friday    is not None else None,
            saturday  = self.saturday .normalize_by_max() if self.saturday  is not None else None,
            sunday    = self.sunday   .normalize_by_max() if self.sunday    is not None else None,
            holiday   = self.holiday  .normalize_by_max() if self.holiday   is not None else None,
        )
    
    def is_on(self) -> RuleSet:
        return self.element_eq(1)

    def is_off(self) -> RuleSet:
        return self.element_eq(0)

    def is_positive(self) -> RuleSet:
        return self > 0

    def is_negative(self) -> RuleSet:
        return self < 0

    def is_zero(self) -> RuleSet:
        return self.element_eq(0)

    def is_nonzero(self) -> RuleSet:
        return self.element_ne(0)

    def is_between(
        self,
        min_value: int|float,
        max_value: int|float,
        *,
        include_min: bool = True,
        include_max: bool = True,
    ) -> RuleSet:
        
        lower = self >= min_value if include_min else self > min_value
        upper = self <= max_value if include_max else self < max_value

        return lower & upper
    
    def clip(
        self,
        min_value: int|float|None = None,
        max_value: int|float|None = None,
        *,
        name   : str|None = None ,
        inplace: bool     = False,
    ) -> RuleSet|None:
        
        if inplace:
            self.weekdays.clip(min_value, max_value, inplace=True)
            self.weekends.clip(min_value, max_value, inplace=True)

            if self.monday    is not None: self.monday   .clip(min_value, max_value, inplace=True)
            if self.tuesday   is not None: self.tuesday  .clip(min_value, max_value, inplace=True)
            if self.wednesday is not None: self.wednesday.clip(min_value, max_value, inplace=True)
            if self.thursday  is not None: self.thursday .clip(min_value, max_value, inplace=True)
            if self.friday    is not None: self.friday   .clip(min_value, max_value, inplace=True)
            if self.saturday  is not None: self.saturday .clip(min_value, max_value, inplace=True)
            if self.sunday    is not None: self.sunday   .clip(min_value, max_value, inplace=True)
            if self.holiday   is not None: self.holiday  .clip(min_value, max_value, inplace=True)

            return None

        return RuleSet(
            name or f"{self.name}:CLIP",
            weekdays =self.weekdays .clip(min_value, max_value),
            weekends =self.weekends .clip(min_value, max_value),
            monday   =self.monday   .clip(min_value, max_value) if self.monday    is not None else None,
            tuesday  =self.tuesday  .clip(min_value, max_value) if self.tuesday   is not None else None,
            wednesday=self.wednesday.clip(min_value, max_value) if self.wednesday is not None else None,
            thursday =self.thursday .clip(min_value, max_value) if self.thursday  is not None else None,
            friday   =self.friday   .clip(min_value, max_value) if self.friday    is not None else None,
            saturday =self.saturday .clip(min_value, max_value) if self.saturday  is not None else None,
            sunday   =self.sunday   .clip(min_value, max_value) if self.sunday    is not None else None,
            holiday  =self.holiday  .clip(min_value, max_value) if self.holiday   is not None else None,
        )
    
    @staticmethod
    def _coerce_dayschedule(
        value: int|float|DaySchedule,
        *,
        type: ScheduleType,
    ) -> DaySchedule:
        if isinstance(value, DaySchedule):
            if value.type != type:
                raise ValueError(
                    f"DaySchedule type mismatch: expected {type}, got {value.type}."
                )
            return value

        if isinstance(value, int|float):
            return DaySchedule.from_constant(None, value, type=type)

        raise TypeError(
            f"Cannot convert {type(value).__name__} to DaySchedule."
        )
    
    @classmethod
    def where(
        cls,
        condition: RuleSet,
        if_true  : int|float|DaySchedule|RuleSet,
        if_false : int|float|DaySchedule|RuleSet,
        *,
        name: str|None          = None,
        type: ScheduleType|None = None,
    ) -> RuleSet:
        
        if condition.type is not ScheduleType.ONOFF:
            raise ScheduleOperationError(
                f"RuleSet.where requires an ONOFF condition RuleSet, got {condition.type}."
            )

        def to_ruleset(value: int|float|DaySchedule|RuleSet) -> RuleSet:
            if isinstance(value, RuleSet):
                return value

            return RuleSet.from_constant(None, value, type=type)

        true_ruleset = to_ruleset(if_true)
        false_ruleset = to_ruleset(if_false)

        def needs_day_override(key: str) -> bool:
            return (
                getattr(condition, key) is not None
                or getattr(true_ruleset, key) is not None
                or getattr(false_ruleset, key) is not None
            )
        
        return cls(
            name or "WHERE",
            weekdays=DaySchedule.where(
                condition.weekdays,
                true_ruleset.weekdays,
                false_ruleset.weekdays,
                type=type,
            ),
            weekends=DaySchedule.where(
                condition.weekends,
                true_ruleset.weekends,
                false_ruleset.weekends,
                type=type,
            ),
            monday=DaySchedule.where(
                condition.monday     or condition.weekdays,
                true_ruleset.monday  or true_ruleset.weekdays,
                false_ruleset.monday or false_ruleset.weekdays,
                type=type,
            ) if needs_day_override("monday") else None,
            tuesday=DaySchedule.where(
                condition.tuesday     or condition.weekdays,
                true_ruleset.tuesday  or true_ruleset.weekdays,
                false_ruleset.tuesday or false_ruleset.weekdays,
                type=type,
            ) if needs_day_override("tuesday") else None,
            wednesday=DaySchedule.where(
                condition.wednesday     or condition.weekdays,
                true_ruleset.wednesday  or true_ruleset.weekdays,
                false_ruleset.wednesday or false_ruleset.weekdays,
                type=type,
            ) if needs_day_override("wednesday") else None,
            thursday=DaySchedule.where(
                condition.thursday     or condition.weekdays,
                true_ruleset.thursday  or true_ruleset.weekdays,
                false_ruleset.thursday or false_ruleset.weekdays,
                type=type,
            ) if needs_day_override("thursday") else None,
            friday=DaySchedule.where(
                condition.friday     or condition.weekdays,
                true_ruleset.friday  or true_ruleset.weekdays,
                false_ruleset.friday or false_ruleset.weekdays,
                type=type,
            ) if needs_day_override("friday") else None,
            saturday=DaySchedule.where(
                condition.saturday     or condition.weekends,
                true_ruleset.saturday  or true_ruleset.weekends,
                false_ruleset.saturday or false_ruleset.weekends,
                type=type,
            ) if needs_day_override("saturday") else None,
            sunday=DaySchedule.where(
                condition.sunday     or condition.weekends,
                true_ruleset.sunday  or true_ruleset.weekends,
                false_ruleset.sunday or false_ruleset.weekends,
                type=type,
            ) if needs_day_override("sunday") else None,
            holiday=DaySchedule.where(
                condition.holiday     or condition.weekends,
                true_ruleset.holiday  or true_ruleset.weekends,
                false_ruleset.holiday or false_ruleset.weekends,
                type=type,
            ) if needs_day_override("holiday") else None,
        )
    
    @classmethod
    def from_days(
        cls,
        name: str|None,
        default: int|float|DaySchedule,
        *,
        monday   : int|float|DaySchedule|None = None,
        tuesday  : int|float|DaySchedule|None = None,
        wednesday: int|float|DaySchedule|None = None,
        thursday : int|float|DaySchedule|None = None,
        friday   : int|float|DaySchedule|None = None,
        saturday : int|float|DaySchedule|None = None,
        sunday   : int|float|DaySchedule|None = None,
        holiday  : int|float|DaySchedule|None = None,
        type: ScheduleType|None = None,
        ) -> RuleSet:
        
        """
        Create a RuleSet from explicit day-of-week overrides.

        `default` is used as both the weekday and weekend fallback. Individual
        days can be overridden by passing values to `monday`, `tuesday`, ...,
        `holiday`.

        Parameters
        ----------
        name:
            Name of the RuleSet.
        default:
            Default value used for weekdays and weekends.
        monday, tuesday, wednesday, thursday, friday, saturday, sunday, holiday:
            Optional day-specific override values.
        type:
            Schedule type used when scalar values are given. If omitted and
            `default` is a scalar, REAL is used.

        Returns
        -------
        RuleSet
            A RuleSet with day-specific overrides.

        Examples
        --------
        Monday-only ON schedule:

            monday_day = DaySchedule.from_windows(
                "monday_day",
                default=0,
                windows=[
                    ((9, 0), (18, 0), 1),
                ],
                type=ScheduleType.ONOFF,
            )

            RuleSet.from_days(
                "monday_only",
                default=0,
                monday=monday_day,
                type=ScheduleType.ONOFF,
            )

        Weekday/weekend style schedule with a Friday override:

            workday = DaySchedule.from_windows(
                "workday",
                default=0,
                windows=[
                    ((9, 0), (18, 0), 1),
                ],
                type=ScheduleType.ONOFF,
            )

            short_friday = DaySchedule.from_windows(
                "short_friday",
                default=0,
                windows=[
                    ((9, 0), (15, 0), 1),
                ],
                type=ScheduleType.ONOFF,
            )

            RuleSet.from_days(
                "workweek_with_short_friday",
                default=workday,
                friday=short_friday,
            )

        Temperature setpoint with weekend override:

            RuleSet.from_days(
                "heating_setpoint",
                default=20,
                saturday=16,
                sunday=16,
                holiday=16,
                type=ScheduleType.TEMPERATURE,
            )
        """
        
        if isinstance(default, DaySchedule):
            inferred_type = default.type
        else:
            inferred_type = ScheduleType.REAL if type is None else ScheduleType(type)

        default_day = cls._coerce_dayschedule(default, type=inferred_type)

        def day_or_default(value):
            if value is None:
                return None
            return cls._coerce_dayschedule(value, type=inferred_type)

        return cls(
            name,
            weekdays=default_day,
            weekends=default_day,
            monday   =day_or_default(monday),
            tuesday  =day_or_default(tuesday),
            wednesday=day_or_default(wednesday),
            thursday =day_or_default(thursday),
            friday   =day_or_default(friday),
            saturday =day_or_default(saturday),
            sunday   =day_or_default(sunday),
            holiday  =day_or_default(holiday),
        )
    
    @classmethod
    def from_constant(cls,
        name :str      ,
        value:int|float|DaySchedule,
        type :ScheduleType|None=None
        ) -> RuleSet:
        
        """
        Create a RuleSet from a constant value or a DaySchedule.

        If `value` is numeric, both weekdays and weekends are filled with
        constant DaySchedules created from the value.

        If `value` is a DaySchedule, the same DaySchedule is assigned to both
        weekdays and weekends.

        Parameters
        ----------
        name:
            Name of the RuleSet.
        value:
            Constant scalar value or DaySchedule.
        type:
            Schedule type used when `value` is numeric. If omitted, REAL is used.

        Returns
        -------
        RuleSet
            A RuleSet whose weekdays and weekends share the same value pattern.

        Examples
        --------
        Always OFF RuleSet:

            RuleSet.from_constant(
                "always_off",
                0,
                type=ScheduleType.ONOFF,
            )

        Constant heating setpoint RuleSet:

            RuleSet.from_constant(
                "heating_setpoint_20",
                20,
                type=ScheduleType.TEMPERATURE,
            )

        RuleSet from an existing DaySchedule:

            workday = DaySchedule.from_windows(
                "workday",
                default=0,
                windows=[
                    ((9, 0), (18, 0), 1),
                ],
                type=ScheduleType.ONOFF,
            )

            RuleSet.from_constant(
                "workday_all_week",
                workday,
            )

        Notes
        -----
        If weekdays and weekends should differ, use the RuleSet constructor
        directly or use `RuleSet.from_days()`.
        """
        
        if isinstance(value, DaySchedule):
            return RuleSet(name, value, value)
        
        else:
            if type is None:
                type = ScheduleType.REAL
            return RuleSet(
                name,
                DaySchedule.from_constant(None, value, type=type),
                DaySchedule.from_constant(None, value, type=type),
            )
    
    """ representation
    """
    
    def to_dict(self) -> dict[str, DaySchedule]:
        return {
            "weekdays" : self.weekdays ,
            "weekends" : self.weekends ,
            "monday"   : self.monday   ,
            "tuesday"  : self.tuesday  ,
            "wednesday": self.wednesday,
            "thursday" : self.thursday ,
            "friday"   : self.friday   ,
            "saturday" : self.saturday ,
            "sunday"   : self.sunday   ,
            "holiday"  : self.holiday  ,
        }
    
    def __deepcopy__(self, memo:dict):
        
        if id(self) in memo:
            return memo[id(self)]
        
        return RuleSet(
            f"{self.name}:COPY",
            **{k: deepcopy(dayschedule) for k, dayschedule in self.to_dict().items()}
        )
    
    def _fallback_day_for_key(self, key: str) -> DaySchedule:
        if key in self._WEEKDAY_KEYS:
            return self.weekdays

        if key in self._WEEKEND_KEYS or key == "holiday":
            return self.weekends

        raise KeyError(f"Unknown RuleSet day key: {key!r}")


    def get_dayschedule(
        self,
        key: str|int,
        *,
        fallback: bool = True,
    ) -> DaySchedule | None:
        if isinstance(key, int):
            key = self._DAY_KEYS[key]

        day = getattr(self, key)

        if day is not None:
            return day

        if fallback:
            return self._fallback_day_for_key(key)

        return None
    
    def summary(self, *, include_days: bool = True) -> str:
        override_keys = [
            key for key in self._DAY_KEYS
            if getattr(self, key) is not None
        ]

        header = f"RuleSet {self.name!r} [type={self.type}]"
        stats = f"  range: min={self.min:.4g}, max={self.max:.4g}"
        defaults = (
            f"  defaults: weekdays={self.weekdays.name!r}, "
            f"weekends={self.weekends.name!r}"
        )
        overrides = (
            "  overrides: "
            + (", ".join(override_keys) if override_keys else "none")
        )

        lines = [header, stats, defaults, overrides]

        if include_days:
            for key in self._DAY_KEYS:
                explicit = getattr(self, key)
                effective = self.get_dayschedule(key, fallback=True)

                source = "override" if explicit is not None else "fallback"
                lines.append(
                    f"  {key:9s}: {effective.name!r} "
                    f"({source}, min={effective.min:.4g}, max={effective.max:.4g})"
                )

        return "\n".join(lines)

    def __str__(self) -> str:
        return self.summary(include_days=True)
    
    def __repr__(self) -> str:
        return f"<RuleSet {self.name} at {hex(id(self))}>"
    
    def to_idf_compactexpr(self) -> list[str]:
        result = []

        # 평일: override 여부 확인
        weekday_keys = ["monday", "tuesday", "wednesday", "thursday", "friday"]
        if any(getattr(self, k) for k in weekday_keys):
            for k in weekday_keys:
                day = getattr(self, k)
                if day:
                    result.append(f"For: {k.capitalize()}")
                    result += day.to_idf_compactexpr()
                else:
                    result.append(f"For: {k.capitalize()}")
                    result += self.weekdays.to_idf_compactexpr()
        else:
            result.append("For: Weekdays")
            result += self.weekdays.to_idf_compactexpr()

        # 주말: override 여부 확인
        weekend_keys = ["saturday", "sunday"]
        if any(getattr(self, k) for k in weekend_keys):
            for k in weekend_keys:
                day = getattr(self, k)
                if day:
                    result.append(f"For: {k.capitalize()}")
                    result += day.to_idf_compactexpr()
                else:
                    result.append(f"For: {k.capitalize()}")
                    result += self.weekends.to_idf_compactexpr()
        else:
            result.append("For: Weekends")
            result += self.weekends.to_idf_compactexpr()

        # 휴일
        if self.holiday:
            result.append("For: Holiday")
            result += self.holiday.to_idf_compactexpr()

        # fallback (AllOtherDays → weekends 스케줄 사용)
        result.append("For: AllOtherDays")
        result += self.weekends.to_idf_compactexpr()
        
        return result
    
class Schedule(UserList):
    
    FIXED_LENGTH = 365
    TIME_TUPLE   = [datetime.date(Setting.DEFAULT_YEAR,1,1)+datetime.timedelta(days=days) for days in range(365)]
    
    def __init__(
        self,
        name: str|None,
        rulesets: list[RuleSet]|None = None,
        *,
        type: ScheduleType|str|None = None,
        ) -> None:

        if name is None:
            name = hex(id(self))
        self.name = name

        if rulesets is None:
            inferred_type = ScheduleType.REAL if type is None else ScheduleType(type)
            rulesets = [
                RuleSet.from_constant(None, 0, type=inferred_type)
                for _ in range(Schedule.FIXED_LENGTH)
            ]
        else:
            if len(rulesets) != Schedule.FIXED_LENGTH:
                raise ValueError(
                    f"Schedule {name!r} requires exactly {self.FIXED_LENGTH} RuleSet values, got {len(rulesets)}."
                )

            if any(not isinstance(item, RuleSet) for item in rulesets):
                raise TypeError(
                    f"Schedule {name!r} requires RuleSet items only."
                )

            inferred_type = rulesets[0].type if type is None else ScheduleType(type)

            if any(ruleset.type != inferred_type for ruleset in rulesets):
                raise ValueError(
                    f"Schedule {name!r} contains mixed RuleSet types. "
                    f"Expected {inferred_type}, got inconsistent RuleSet types."
                )

        self.__type = inferred_type
        self.data = rulesets
    
    def apply(self,
        ruleset:RuleSet,
        *,
        start:datetime.date|str,
        end  :datetime.date|str,
        inplace:bool=True
        ) -> None:
        
        def datetime_parser(datestr:str) -> datetime.date:
            
            if re.match(r"\d{8}$", datestr):
                datetuple = (int(datestr[:4]), int(datestr[4:6]), int(datestr[6:8]))
            elif re.match(r"\d{4}$", datestr):
                datetuple = (Setting.DEFAULT_YEAR, int(datestr[:2]), int(datestr[2:4]))
            else:
                datetuple = tuple(map(lambda v: int(v), re.findall(r"\d+", datestr)))
                if len(datetuple) == 2:
                    datetuple = (Setting.DEFAULT_YEAR, *datetuple)
            
            date = datetime.date(*datetuple)
            return date
        
        if isinstance(start, str):
            start = datetime_parser(start)

        if isinstance(end, str):
            end = datetime_parser(end)
        
        if inplace:
            target = self
        else:
            target = deepcopy(self)
            
        for idx in range(Schedule.FIXED_LENGTH):
            if start <= Schedule.TIME_TUPLE[idx] <= end:
                target.data[idx] = ruleset
                
        if not inplace:
            return target
    
    """ algebraic operation
    """
    
    @staticmethod
    def __operate_with_unified_schedule(
        newname: str,
        ruleset_operator: Callable,
        self_schedule   : Schedule,
        other: Schedule|int|float,
    ) -> Schedule:

        # scalar case: keep scalar as scalar and let RuleSet/DaySchedule handle it
        if isinstance(other, int|float):
            return Schedule.from_compact(
                newname,
                [
                    (
                        start_date,
                        end_date,
                        ruleset_operator(ruleset_self, other),
                    )
                    for start_date, end_date, ruleset_self
                    in self_schedule.compactize()
                ],
            )

        # Schedule case
        if isinstance(other, Schedule):
            unified_self, unified_other = Schedule.unify_compactized_schedules(
                self_schedule.compactize(),
                other.compactize(),
            )

            return Schedule.from_compact(
                newname,
                [
                    (
                        start_date,
                        end_date,
                        ruleset_operator(ruleset_self, ruleset_other),
                    )
                    for (
                        start_date,
                        end_date,
                        ruleset_self,
                    ), (
                        _,
                        _,
                        ruleset_other,
                    )
                    in zip(unified_self, unified_other)
                ],
            )

        raise ScheduleOperationError(
            f"Unsupported Schedule operation with {type(other).__name__}. "
            f"Right operand must be int, float, or Schedule."
        )
    
    @staticmethod
    def unify_compactized_schedules_many(
        *compactized_schedules: list[tuple[datetime.date, datetime.date, RuleSet]]
        ) -> list[list[tuple[datetime.date, datetime.date, RuleSet]]]:
        boundaries = set()

        for compactized in compactized_schedules:
            for start_date, end_date, _ in compactized:
                boundaries.add(start_date)
                boundaries.add(end_date + datetime.timedelta(days=1))

        boundaries = sorted(boundaries)

        def find_ruleset(compactized, date):
            for start, end, ruleset in compactized:
                if start <= date <= end:
                    return ruleset
            raise ValueError(f"Cannot find RuleSet for date {date}.")

        unified = [[] for _ in compactized_schedules]

        for idx in range(len(boundaries) - 1):
            start = boundaries[idx]
            end = boundaries[idx + 1] - datetime.timedelta(days=1)

            for out, compactized in zip(unified, compactized_schedules):
                out.append((start, end, find_ruleset(compactized, start)))

        return unified
    
    def __mul__(self, value:int|float|Schedule) -> Schedule:
            
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:MUL:{value.name if isinstance(value, Schedule) else str(value)}",
            lambda a,b: a.__mul__(b),
            self, value
        )
        
    def __rmul__(self, value:int|float) -> Schedule:
        return self.__mul__(value)
    
    def __truediv__(self, value:int|float|Schedule) -> Schedule:
        
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:DIV:{value.name if isinstance(value, Schedule) else str(value)}",
            lambda a,b: a.__truediv__(b),
            self, value
        )
    
    def __rtruediv__(self, value:int|float) -> Schedule:
        
        return Schedule.__operate_with_unified_schedule(
            f"{value}:DIV:{self.name}",
            lambda a,b: a.__rtruediv__(b),
            self, value
        )
    
    def __add__(self, other:int|float|Schedule) -> Schedule:
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:ADD:{other.name if isinstance(other, Schedule) else str(other)}",
            lambda a, b: a+b,
            self, other
        )
    
    def __radd__(self, other: int|float) -> Schedule:
        return Schedule.__operate_with_unified_schedule(
            f"{other}:ADD:{self.name}",
            lambda a, b: a.__radd__(b),
            self,
            other,
        )
    
    def __sub__(self, other:int|float|Schedule) -> Schedule:
            
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:SUB:{other.name if isinstance(other, Schedule) else str(other)}",
            lambda a, b: a-b,
            self, other
        )
    
    def __rsub__(self, other: int|float) -> Schedule:
        return Schedule.__operate_with_unified_schedule(
            f"{other}:SUB:{self.name}",
            lambda a, b: a.__rsub__(b),
            self,
            other,
        )
        
    def __and__(self, other:Schedule) -> Schedule:
            
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:AND:{other.name}",
            lambda a, b: a.__and__(b),
            self, other
        )
    
    def __or__(self, other:Schedule) -> Schedule:
            
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:OR:{other.name}",
            lambda a, b: a.__or__(b),
            self, other
        )
        
    def __invert__(self) -> Schedule:
            
        return Schedule.from_compact(
            f"{self.name}:INVERTED",
            [
                (start_date, end_date, ruleset.__invert__())
                for start_date, end_date, ruleset in self.compactize()
            ]
        )
        
    def element_eq(self, other:int|float|Schedule) -> Schedule:
        
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:EQ:{other.name if isinstance(other, Schedule) else str(other)}",
            lambda a,b: a.element_eq(b),
            self, other
        )
    
    def element_ne(self, other:int|float|Schedule) -> Schedule:
        
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:NE:{other.name if isinstance(other, Schedule) else str(other)}",
            lambda a,b: a.element_ne(b),
            self, other
        )
        
    def __lt__(self, other:int|float|Schedule) -> Schedule:
        
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:LT:{other.name if isinstance(other, Schedule) else str(other)}",
            lambda a,b: a.__lt__(b),
            self, other
        )
    
    def __le__(self, other:int|float|Schedule) -> Schedule:
        
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:LE:{other.name if isinstance(other, Schedule) else str(other)}",
            lambda a,b: a.__le__(b),
            self, other
        )
        
    def __gt__(self, other:int|float|Schedule) -> Schedule:
        
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:GT:{other.name if isinstance(other, Schedule) else str(other)}",
            lambda a,b: a.__gt__(b),
            self, other
        )
        
    def __ge__(self, other:int|float|Schedule) -> Schedule:
        
        return Schedule.__operate_with_unified_schedule(
            f"{self.name}:GE:{other.name if isinstance(other, Schedule) else str(other)}",
            lambda a,b: a.__ge__(b),
            self, other
        )    
        
    def element_min(self, other:Schedule) -> Schedule:
        
        unified_compactized_self, unified_compactized_other = Schedule.unify_compactized_schedules(
            self.compactize(), other.compactize(),
        )

        return Schedule.from_compact(
            f"{self.name}:MIN:{other.name}",
            [
                (start_date, end_date, ruleset_self.element_min(ruleset_other))
                for (start_date, end_date, ruleset_self), (start_date, end_date, ruleset_other) in zip(unified_compactized_self, unified_compactized_other)
            ]
        )
    
    def element_max(self, other:Schedule) -> Schedule:
        
        unified_compactized_self, unified_compactized_other = Schedule.unify_compactized_schedules(
            self.compactize(), other.compactize(),
        )

        return Schedule.from_compact(
            f"{self.name}:MAX:{other.name}",
            [
                (start_date, end_date, ruleset_self.element_max(ruleset_other))
                for (start_date, end_date, ruleset_self), (start_date, end_date, ruleset_other) in zip(unified_compactized_self, unified_compactized_other)
            ]
        )
    
    @property
    def min(self) -> int|float:
        return min([ruleset.min for ruleset in self.data])
    
    @property
    def max(self) -> int|float:
        return max([ruleset.max for ruleset in self.data])
    
    def normalize_by_max(self, *, new_name:str=None):
        
        if new_name is None:
            new_name = self.name + "_normalized"
        
        return Schedule.from_compact(
            new_name                       ,
            [
                (start_date, end_date, ruleset.normalize_by_max())
                for start_date, end_date, ruleset in self.compactize()
            ]
        )
        
    def is_on(self) -> Schedule:
        return self.element_eq(1)

    def is_off(self) -> Schedule:
        return self.element_eq(0)

    def is_positive(self) -> Schedule:
        return self > 0

    def is_negative(self) -> Schedule:
        return self < 0

    def is_zero(self) -> Schedule:
        return self.element_eq(0)

    def is_nonzero(self) -> Schedule:
        return self.element_ne(0)

    def is_between(
        self,
        min_value: int|float,
        max_value: int|float,
        *,
        include_min: bool = True,
        include_max: bool = True,
    ) -> Schedule:
        
        lower = self >= min_value if include_min else self > min_value
        upper = self <= max_value if include_max else self < max_value

        return lower & upper
    
    @property
    def dayschedules(self) -> list[DaySchedule]:
        return [
            ruleset.get_dayschedule(time.weekday()) 
            for time, ruleset in zip(Schedule.TIME_TUPLE, self.data)
        ]
        
    @property
    def integral(self) -> float:
        return sum(dayschedule.integral for dayschedule in self.dayschedules)
    
    @property
    def average(self) -> float:
        return self.integral / Schedule.FIXED_LENGTH
    
    @property
    def positive_average(self) -> float:
        positive_values = [v for ds in self.dayschedules for v in ds.data if v > 0]
        return sum(positive_values) / len(positive_values) if positive_values else 0.0
        
    def clip(
        self,
        min_value: int|float|None = None,
        max_value: int|float|None = None,
        *,
        name: str|None = None,
        inplace: bool = False,
    ) -> Schedule|None:
        
        if inplace:
            for idx, ruleset in enumerate(self.data):
                self.data[idx] = ruleset.clip(min_value, max_value)
            return None

        return Schedule.from_compact(
            name or f"{self.name}:CLIP",
            [
                (
                    start,
                    end,
                    ruleset.clip(min_value, max_value),
                )
                for start, end, ruleset in self.compactize()
            ],
        )
    
    """ prohibited methods
    """
    
    def __delitem__(self, index:int) -> None:
        raise AttributeError(
            f"Cannot delete item from the fixed-length ({self.fixed_length}) Schedule"
        )
        
    def append(self, item:Any) -> None:
        raise AttributeError(
            f"Cannot append to the fixed-length ({self.fixed_length}) Schedule"
        )

    def extend(self, items: list) -> None:
        raise AttributeError(
            f"Cannot extend the fixed-length ({self.fixed_length}) Schedule"
        )
        
    def pop(self, index:int= -1) -> None:
        raise AttributeError(
            f"Cannot pop from the fixed-length ({self.fixed_length}) Schedule"
        )
        
    def clear(self) -> None:
        raise AttributeError(
            f"Cannot clear the fixed-length ({self.fixed_length}) Schedule"
        )
        
    def insert(self, index:int, item:Any) -> None:
        raise AttributeError(
            f"Cannot insert into the fixed-length ({self.fixed_length}) Schedule"
        )
    
    @property
    def type(self) -> ScheduleType:
        return self.__type
    
    def astype(self,
        newtype:ScheduleType,
        inplace:bool=False,
        ) -> Schedule|None:
        
        if inplace:
            for ruleset in self.data:
                ruleset.astype(newtype, inplace=True)
            
        else:
            return Schedule.from_compact(
                self.name,
                [
                    (start, end, deepcopy(ruleset).astype(newtype))
                    for start, end, ruleset in self.compactize()
                ]
            )
    
    """ time-related operations
    """
    
    def compactize(self) -> list[tuple[datetime.date, datetime.date, RuleSet]]:
        
        compact_tuples = []
        for time, ruleset in zip(Schedule.TIME_TUPLE, self.data):
            
            if (len(compact_tuples) == 0) or (compact_tuples[-1][2] != ruleset):
                compact_tuples.append((time, time, ruleset))
            else:
                compact_tuples[-1] = (compact_tuples[-1][0], time, compact_tuples[-1][2])
        
        return compact_tuples
    
    @staticmethod
    def _coerce_ruleset(
        value: int|float|DaySchedule|RuleSet,
        *,
        type: ScheduleType|None = None,
    ) -> RuleSet:
        if isinstance(value, RuleSet):
            if type is not None and value.type != ScheduleType(type):
                raise ValueError(
                    f"RuleSet type mismatch: expected {ScheduleType(type)}, got {value.type}."
                )
            return value

        if isinstance(value, DaySchedule):
            if type is not None and value.type != ScheduleType(type):
                raise ValueError(
                    f"DaySchedule type mismatch: expected {ScheduleType(type)}, got {value.type}."
                )
            return RuleSet.from_constant(None, value)

        if isinstance(value, int|float):
            if type is None:
                type = ScheduleType.REAL
            return RuleSet.from_constant(None, value, type=type)

        raise TypeError(
            f"Cannot convert {type(value).__name__} to RuleSet."
        )
        
    @classmethod
    def where(
        cls,
        condition: Schedule,
        if_true  : int|float|DaySchedule|RuleSet|Schedule,
        if_false : int|float|DaySchedule|RuleSet|Schedule,
        *,
        name: str|None = None,
        type: ScheduleType|None = None,
    ) -> Schedule:
        
        if condition.type is not ScheduleType.ONOFF:
            raise ScheduleOperationError(
                f"Schedule.where requires an ONOFF condition Schedule, got {condition.type}."
            )

        def to_schedule(value: int|float|DaySchedule|RuleSet|Schedule) -> Schedule:
            if isinstance(value, Schedule):
                return value

            return Schedule.from_constant(None, value, type=type)

        true_schedule = to_schedule(if_true)
        false_schedule = to_schedule(if_false)

        condition_compact, true_compact, false_compact = Schedule.unify_compactized_schedules_many(
            condition.compactize(),
            true_schedule.compactize(),
            false_schedule.compactize(),
        )

        return Schedule.from_compact(
            name or "WHERE",
            [
                (
                    start,
                    end,
                    RuleSet.where(
                        condition_ruleset,
                        true_ruleset,
                        false_ruleset,
                        type=type,
                    ),
                )
                for (
                    (start, end, condition_ruleset),
                    (_, _, true_ruleset),
                    (_, _, false_ruleset),
                )
                in zip(condition_compact, true_compact, false_compact)
            ],
        )
    
    @classmethod
    def from_compact(cls,
        name    :str,
        rulesets:list[tuple[datetime.date, datetime.date, RuleSet]],
        ) -> Schedule:
        
        """
        Create a yearly Schedule from compact period definitions.

        Each tuple has the form:

            (start_date, end_date, ruleset)

        The date range is inclusive:

            start_date <= date <= end_date

        Dates may be datetime.date objects or strings accepted by Schedule.apply(),
        such as "0101", "0831", "20250101", "1/1", or "8/31".

        Parameters
        ----------
        name:
            Name of the yearly schedule.
        rulesets:
            List of compact period definitions.

        Returns
        -------
        Schedule
            A fixed-length 365-day Schedule.

        Examples
        --------
        Annual ON/OFF work schedule with summer vacation:

            workday = DaySchedule.from_windows(
                "workday",
                default=0,
                windows=[
                    ((9, 0), (18, 0), 1),
                ],
                type=ScheduleType.ONOFF,
            )

            work_ruleset = RuleSet(
                "work",
                weekdays=workday,
                weekends=DaySchedule.from_constant(None, 0, type=ScheduleType.ONOFF),
            )

            off_ruleset = RuleSet.from_constant(
                "off",
                0,
                type=ScheduleType.ONOFF,
            )

            Schedule.from_compact(
                "school_schedule",
                [
                    ("0101", "0731", work_ruleset),
                    ("0801", "0831", off_ruleset),
                    ("0901", "1231", work_ruleset),
                ],
            )

        Constant heating setpoint by season:

            heating_20 = RuleSet.from_constant(
                "heating_20",
                20,
                type=ScheduleType.TEMPERATURE,
            )

            heating_16 = RuleSet.from_constant(
                "heating_16",
                16,
                type=ScheduleType.TEMPERATURE,
            )

            Schedule.from_compact(
                "seasonal_heating_setpoint",
                [
                    ("0101", "0430", heating_20),
                    ("0501", "0930", heating_16),
                    ("1001", "1231", heating_20),
                ],
            )

        Notes
        -----
        If some dates are not covered, they are filled with a zero-valued RuleSet of the inferred ScheduleType.
        """
        
        if not rulesets:
            raise ValueError(
                f"Compact Schedule {name!r} must contain at least one (start, end, ruleset) tuple."
            )

        given_types = [ruleset.type for _, _, ruleset in rulesets]
        if len(set(given_types)) > 1:
            raise ValueError(
                f"Cannot create Schedule {name!r} from compact rulesets with mixed ScheduleTypes: {set(given_types)}."
            )

        inferred_type = rulesets[0][2].type
        
        if (len(rulesets) == 1 and rulesets[0][0] in ("0101", cls.TIME_TUPLE[0])
            and rulesets[0][1] in ("1231", cls.TIME_TUPLE[-1])):
            return cls(name, [rulesets[0][2]] * cls.FIXED_LENGTH)

        else:
            # Create default zero RuleSets with the same inferred type.
            schedule = cls(name, type=inferred_type)

            for start, end, ruleset in rulesets:
                schedule.apply(ruleset, start=start, end=end)

            return schedule
    
    @classmethod
    def from_windows(
        cls,
        name: str|None,
        default: int|float|DaySchedule|RuleSet,
        windows: list[
            tuple[
                datetime.date|str,
                datetime.date|str,
                int|float|DaySchedule|RuleSet,
            ]
        ],
        *,
        type: ScheduleType|None = None,
    ) -> Schedule:
        """
        Create a yearly Schedule from date windows.

        Each window has the form:

            (start_date, end_date, value)

        The date range is inclusive:

            start_date <= date <= end_date

        `default` is applied to the full year first. Then each window is applied
        in the given order. Later windows overwrite earlier windows if ranges
        overlap.

        Parameters
        ----------
        name:
            Name of the yearly schedule.
        default:
            Default scalar value, DaySchedule, or RuleSet used for the whole year.
        windows:
            List of date windows. Each item is
            (start_date, end_date, value).
        type:
            Schedule type used when scalar values are given. If omitted and
            `default` is scalar, REAL is used.

        Returns
        -------
        Schedule
            A yearly Schedule with date-window overrides.

        Examples
        --------
        Work schedule with a summer vacation:

            workday = DaySchedule.from_windows(
                "workday",
                default=0,
                windows=[
                    ((9, 0), (18, 0), 1),
                ],
                type=ScheduleType.ONOFF,
            )

            work_ruleset = RuleSet(
                "work",
                weekdays=workday,
                weekends=DaySchedule.from_constant(None, 0, type=ScheduleType.ONOFF),
            )

            off_ruleset = RuleSet.from_constant(
                "off",
                0,
                type=ScheduleType.ONOFF,
            )

            Schedule.from_windows(
                "school_schedule",
                default=work_ruleset,
                windows=[
                    ("0801", "0831", off_ruleset),
                ],
            )

        Temperature setpoint with seasonal setback:

            Schedule.from_windows(
                "heating_setpoint",
                default=20,
                windows=[
                    ("0501", "0930", 16),
                ],
                type=ScheduleType.TEMPERATURE,
            )

        Fraction schedule with seasonal reduction:

            Schedule.from_windows(
                "availability",
                default=1.0,
                windows=[
                    ("0701", "0831", 0.5),
                ],
                type=ScheduleType.FRACTION,
            )

        Notes
        -----
        This method is more convenient than `from_compact()` when the schedule has
        a clear default value and a small number of exception periods.
        """

        schedule = cls.from_constant(name, default, type=type)
        inferred_type = schedule.type

        for start, end, value in windows:
            ruleset = cls._coerce_ruleset(value, type=inferred_type)
            schedule.apply(ruleset, start=start, end=end, inplace=True)

        return schedule

    @classmethod
    def from_constant(cls,
        name :str      ,
        value:int|float|DaySchedule|RuleSet,
        type:ScheduleType|None=None,
        ) -> Schedule:
        
        """
        Create a yearly Schedule from a constant scalar, DaySchedule, or RuleSet.

        If `value` is numeric, a constant RuleSet is created for the whole year.

        If `value` is a DaySchedule, it is converted to a RuleSet and applied to
        the whole year.

        If `value` is a RuleSet, it is directly applied to the whole year.

        Parameters
        ----------
        name:
            Name of the yearly schedule.
        value:
            Scalar value, DaySchedule, or RuleSet.
        type:
            Schedule type used when `value` is numeric. If omitted, REAL is used.

        Returns
        -------
        Schedule
            A yearly Schedule covering 01/01 through 12/31.

        Examples
        --------
        Annual always-OFF schedule:

            Schedule.from_constant(
                "always_off",
                0,
                type=ScheduleType.ONOFF,
            )

        Annual constant heating setpoint:

            Schedule.from_constant(
                "heating_setpoint_20",
                20,
                type=ScheduleType.TEMPERATURE,
            )

        Annual schedule from a DaySchedule:

            workday = DaySchedule.from_windows(
                "workday",
                default=0,
                windows=[
                    ((9, 0), (18, 0), 1),
                ],
                type=ScheduleType.ONOFF,
            )

            Schedule.from_constant(
                "same_day_all_year",
                workday,
            )

        Annual schedule from a RuleSet:

            work_ruleset = RuleSet(
                "work",
                weekdays=workday,
                weekends=DaySchedule.from_constant(None, 0, type=ScheduleType.ONOFF),
            )

            Schedule.from_constant(
                "work_schedule",
                work_ruleset,
            )
        """
    
        if isinstance(value, RuleSet):
            return cls.from_compact(
                name, [("0101","1231", value)]
            )
        
        elif isinstance(value, DaySchedule):
            return cls.from_compact(
                name, [("0101","1231", RuleSet.from_constant(None, value))]
            )
        
        else:
            if type is None:
                type = ScheduleType.REAL
            
            return cls.from_compact(
                name,
                [
                    ("0101","1231",RuleSet.from_constant(None, value, type=type))
                ]
            )
    
    @staticmethod
    def unify_compactized_schedules(
        compactized1:list[tuple[datetime.date, datetime.date, RuleSet]],
        compactized2:list[tuple[datetime.date, datetime.date, RuleSet]],
        ) -> tuple[
            list[tuple[datetime.date, datetime.date, RuleSet]],
            list[tuple[datetime.date, datetime.date, RuleSet]],
        ]:
            
        boundaries = set()
        for start_date, end_date, _ in compactized1 + compactized2:
            boundaries.add(start_date)
            boundaries.add(end_date + datetime.timedelta(days=1))
        boundaries = sorted(boundaries)
        
        def find_ruleset(compact_list, d):
            for s, e, rs in compact_list:
                if s <= d <= e:
                    return rs
        
        new_list1, new_list2 = [], []
        for i in range(len(boundaries) - 1):
            seg_start = boundaries[i]
            seg_end_excl = boundaries[i + 1]
            seg_end_incl = seg_end_excl - datetime.timedelta(days=1)

            r1 = find_ruleset(compactized1, seg_start)
            r2 = find_ruleset(compactized2, seg_start)

            new_list1.append((seg_start, seg_end_incl, r1))
            new_list2.append((seg_start, seg_end_incl, r2))
        
        return new_list1, new_list2
    
    def to_idf_object(self) -> IdfObject:
        
        return IdfObject("Schedule:Compact",[
            f"{self.name}",
            self.type.idf_objname,
            *sum([
                [
                    f"Through: {end_date.month}/{end_date.day}",
                    *ruleset.to_idf_compactexpr()
                ]
                for start_date, end_date, ruleset in self.compactize()  
            ],start=[])
        ])

    """ representation
    """
    
    def __deepcopy__(self, memo:dict):
        
        if id(self) in memo:
            return memo[id(self)]
        
        return Schedule.from_compact(
            f"{self.name}:COPY",
            [
                (start, end, deepcopy(ruleset))
                for start, end, ruleset in self.compactize()
            ]
        )
    
    def summary(self, *, max_periods: int = 8) -> str:
        compact = self.compactize()

        unique_rulesets = {}
        for ruleset in self.data:
            unique_rulesets[ruleset.name] = ruleset

        header = (
            f"Schedule {self.name!r} "
            f"[type={self.type}, days={self.FIXED_LENGTH}]"
        )
        stats = (
            f"  range: min={self.min:.4g}, max={self.max:.4g}, "
            f"periods={len(compact)}, unique_rulesets={len(unique_rulesets)}"
        )

        lines = [header, stats]

        for start, end, ruleset in compact[:max_periods]:
            lines.append(
                f"  {start.month:02d}/{start.day:02d} ~ "
                f"{end.month:02d}/{end.day:02d}: "
                f"{ruleset.name!r} "
                f"(min={ruleset.min:.4g}, max={ruleset.max:.4g})"
            )

        if len(compact) > max_periods:
            lines.append(f"  ... ({len(compact) - max_periods} more periods)")

        return "\n".join(lines)


    def __str__(self) -> str:
        return self.summary()
    
    def __repr__(self) -> str:
        return f"<Schedule {self.name} at {hex(id(self))}>"
    
class Profile:
    
    def __init__(self,
        name:str,
        heating_setpoint :Schedule|None=None, # °C
        cooling_setpoint :Schedule|None=None, # °C
        hvac_availability:Schedule|None=None, # onoff
        occupant         :Schedule|None=None, # W/m2
        lighting         :Schedule|None=None, # onoff
        equipment        :Schedule|None=None, # W/m2
        hotwater         :Schedule|None=None, # L/m2
        ) -> None:
        
        self.name = name
        self.heating_setpoint  =heating_setpoint
        self.cooling_setpoint  =cooling_setpoint
        self.hvac_availability =hvac_availability
        self.occupant          =occupant
        self.lighting          =lighting
        self.equipment         =equipment
        self.hotwater          =hotwater
    
    def to_idf_object(self) -> list[IdfObject]:
        
        return [
            schedule.to_idf_object()
            for schedule in [
                self.heating_setpoint ,
                self.cooling_setpoint ,
                self.hvac_availability,
                self.occupant ,
                self.lighting ,
                self.equipment,
                self.hotwater ,
            ]
            if isinstance(schedule, Schedule)
        ]
