"""Finite-capacity startup hotfix for baseline EPlusSimple 0a958165 (not a refactor).
Install once BEFORE constructing any IDF/IdfObject. Do not overwrite vendor pickle.
Always check_idf() before write/run. This does not repair legacy DataFrame/tuple APIs.
"""
from copy import deepcopy
from pathlib import Path
import pickle
import re
from idragon.imugi import IDD, IddObject

HOTFIX_REVISION = 'rooms1000-equipment18-preliminary-r1'

DEFAULT_CAPACITIES = {
    'ZoneTerminalUnitList': 1200,
    'BranchList': 1200,
    'Connector:Splitter': 1200,
    'Connector:Mixer': 1200,
    'ZoneHVAC:EquipmentList': 18,
    'ZoneHVAC:LowTemperatureRadiant:SurfaceGroup': 600,
    'NodeList': 600,
    'OutdoorAir:NodeList': 600,
    'Schedule:Compact': 600,
}
class CapacityError(ValueError):
    pass

def _expand_object(obj, total_groups):
    width = int(obj.extensible or 0)
    if not width:
        raise CapacityError(f'{obj.name}: non-extensible; expansion prohibited')
    if isinstance(total_groups, bool) or not isinstance(total_groups, int) or not 1 <= total_groups <= 10000:
        raise CapacityError('Capacity must be an integer group count in 1..10000')
    entries = []; blank_seen = False
    for name, code in zip(obj.allowed_keys, obj.idd_index):
        if not name:
            blank_seen = True
            continue
        if blank_seen:
            raise CapacityError(f'{obj.name}: unnamed middle slot requires a real layout parser')
        entries.append((name, code, obj[name]))
    names = [n for n, _, _ in entries]
    if len(names) != len(set(names)):
        raise CapacityError(f'{obj.name}: duplicate names cannot safely be reconstructed from legacy pickle')
    starts = [i for i, (_, _, f) in enumerate(entries) if f.is_extensible]
    if len(starts) != 1:
        raise CapacityError(f'{obj.name}: missing/ambiguous begin-extensible marker')
    start = starts[0]
    if (len(entries) - start) % width:
        raise CapacityError(f'{obj.name}: incomplete named group')
    existing = (len(entries) - start) // width
    total_groups = max(existing, total_groups)
    if start + width * total_groups > 100000:
        raise CapacityError('Schema expansion exceeds 100000 fields per object')
    patterns = []
    for offset in range(width):
        parts = re.split(r'(\d+)', names[start + offset]); candidates = []
        for part in range(1, len(parts), 2):
            if all(re.split(r'(\d+)', names[start + g*width + offset]) ==
                   parts[:part] + [str(int(parts[part]) + g)] + parts[part+1:]
                   for g in range(existing)):
                candidates.append(part)
        if len(candidates) != 1:
            raise CapacityError(f'{obj.name}: cannot infer a unique numbered field template')
        part = candidates[0]
        patterns.append((''.join(parts[:part]), int(parts[part]), ''.join(parts[part+1:])))
    fields = [deepcopy(f) for _, _, f in entries]
    codes = [code for _, code, _ in entries]
    counters = {kind: max((int(c[1:]) for c in codes if c.startswith(kind)), default=0) for kind in 'AN'}
    for group in range(existing, total_groups):
        for offset, (before, first, after) in enumerate(patterns):
            field = deepcopy(entries[start + (existing-1)*width + offset][2])
            field._IddField__name = f'{before}{first+group}{after}'
            # Added schema capacity must not add real defaults/required groups to IDF output.
            field._IddField__default = None
            field._IddField__is_required = False
            field._IddField__is_extensible = False
            fields.append(field)
            kind = entries[start + (existing-1)*width + offset][1][0]
            counters[kind] += 1; codes.append(f'{kind}{counters[kind]}')
    attrs = {k: getattr(obj,k) for k in ['name','memo','is_unique','is_required','is_obsolete','min_fields','extensible','begin_extensible','format','reference']}
    result = IddObject(*fields, index=codes, **attrs)
    return result, {'start':start, 'width':width, 'original_groups':existing, 'capacity_groups':total_groups,
                    'fields':len(fields), 'anonymous_padding_removed':len(obj.allowed_keys)-len(entries)}

def install(capacities=None, version=(24,2,0), save_as=None, patch_equipment_helpers=True):
    capacities = DEFAULT_CAPACITIES if capacities is None else dict(capacities)
    # Isolated copy: no in-place changes to an IDD already shared by an existing model.
    base = pickle.loads(pickle.dumps(IDD.load(version)))
    objects=[]; receipt={}
    for name, obj in base.items():
        if name in capacities:
            obj, receipt[name] = _expand_object(obj, capacities[name])
        objects.append(obj)
    missing=set(capacities)-set(base.keys())
    if missing:
        raise CapacityError(f'Unknown objects: {sorted(missing)}')
    # Rebuild reverse-reference maps; legacy pickle used __referencible spelling.
    # Reset, rather than append onto old maps, to avoid duplicates.
    for obj in objects:
        for field in obj.values():
            field._IddField__referenceable = []
    schema=IDD(base.version,*objects)
    schema._capacity_hotfix_profile = dict(capacities)
    schema._capacity_hotfix_revision = HOTFIX_REVISION
    if save_as is not None:
        destination=Path(save_as)
        if destination.exists():
            raise FileExistsError('Refuse to overwrite any existing pickle')
        with destination.open('xb') as stream:
            pickle.dump(schema,stream)
    if patch_equipment_helpers:
        patch_appenders()
    # Atomic cache replacement after the entire schema was prepared successfully.
    IDD.loaded[tuple(base.version)] = schema
    return schema,receipt

def patch_appenders():
    from idragon.dragon.hvac import EquipmentListAppender, SequentialLoadFractionController, DemandBranchAppender
    def count(equipment):
        capacity=(len(equipment.allowed_keys)-2)//6
        for idx in range(1,capacity+1):
            if equipment[f'Zone Equipment {idx} Name'] is None:
                return idx-1
        return capacity
    def find(equipment,name):
        capacity=(len(equipment.allowed_keys)-2)//6
        for idx in range(1,capacity+1):
            current=equipment[f'Zone Equipment {idx} Name']
            if current==name:return idx
            if current is None:break
        raise ValueError(f'Cannot find {name!r} within {capacity} allocated equipment groups')
    # The original branch appender mutates splitter/mixer and moves the
    # outlet before discovering a full BranchList. Check all three first.
    original_branch_run = getattr(DemandBranchAppender.run, "_capacity_original_run", DemandBranchAppender.run)
    def guarded_branch_run(self, idf):
        targets = [
            ('BranchList', self.source.idf_demandbranchlistname,
             'Branch {} Name', 1),
            ('Connector:Splitter', self.source.idf_demandsplittername,
             'Outlet Branch {} Name', 2),
            ('Connector:Mixer', self.source.idf_demandmixername,
             'Inlet Branch {} Name', 2),
        ]
        for typ, name, pattern, fixed in targets:
            target=idf[typ][name]
            count_now=sum(v is not None for v in target.values())-fixed
            key=pattern.format(count_now+1)
            if key not in target.allowed_keys:
                raise CapacityError(f'{typ} needs {key}; increase startup capacity and regenerate')
        return original_branch_run(self,idf)
    guarded_branch_run._capacity_original_run=original_branch_run
    DemandBranchAppender.run=guarded_branch_run
    EquipmentListAppender.count_current_equipments=staticmethod(count)
    SequentialLoadFractionController.find_target_equipment_number=staticmethod(find)

def load_saved(path, patch_equipment_helpers=True):
    """Only trust locally generated pickles; install before creating any model."""
    with Path(path).open("rb") as stream:
        schema=pickle.load(stream)
    if not isinstance(schema,IDD) or getattr(schema,"_capacity_hotfix_revision",None) != HOTFIX_REVISION:
        raise CapacityError("Not a locally generated capacity-hotfix IDD pickle")
    if patch_equipment_helpers:
        patch_appenders()
    IDD.loaded[tuple(schema.version)] = schema
    return schema


def ensure_installed(capacities=None, version=(24,2,0)):
    """Install before creation; a bare repeat keeps this revision's active caps."""
    active = IDD.loaded.get(tuple(version))
    if getattr(active, '_capacity_hotfix_revision', None) == HOTFIX_REVISION:
        if capacities is None or active._capacity_hotfix_profile == dict(capacities):
            return active
    capacities = dict(DEFAULT_CAPACITIES if capacities is None else capacities)
    return install(capacities, version)[0]


def check_idf(idf):
    active=IDD.load(idf.version)
    if idf.idd is not active:
        raise CapacityError('IDF predates schema installation: start fresh and regenerate, do not reuse old objects')
    for typ, objects in idf.items():
        for number,obj in enumerate(objects):
            if obj.idd is not active[typ]:
                raise CapacityError(f'{typ}[{number}] uses an old/different schema')
            tail=getattr(obj,'_IdfObject__extended_input',None)
            if tail is None:
                raise CapacityError(f'{typ}[{number}] has unsupported legacy tuple/ndarray state; construct with list/dict')
            if tail:
                raise CapacityError(f'{typ}[{number}] exceeds named capacity: {len(tail)} hidden tail fields; increase startup capacity, or fix a non-extensible object')
            if len(obj.data)!=len(obj.allowed_keys) or tuple(obj.data)!=tuple(obj.allowed_keys):
                raise CapacityError(f'{typ}[{number}] data/key layout mismatch')
            if '' in obj.data and obj.data[''] is not None:
                raise CapacityError(f'{typ}[{number}] populated anonymous slot requires explicit named-schema expansion')
    return True
