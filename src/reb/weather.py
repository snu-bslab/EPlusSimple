# ------------------------------------------------------------------------ #
#                                  MODULES                                 #
# ------------------------------------------------------------------------ #
"""
건물정보 탭의 주소, 기상데이터옵션, 기준년도로 기상파일(epw)을 정한다.

  표준기상(TMY): 070 코어와 같은 runtime/Weather/TMY 파일
  실제기상(AMY): runtime/Weather/AMY/{기상청 지점}_{기준년도}.epw
                 없으면 기상청 API허브(https://apihub.kma.go.kr)에서 시간자료를 받아
                 TMY 파일을 틀로 만든다. 인증키는 환경변수 KMA_API_KEY 또는 authkey 인자.

관리건축물대장 PK 코드('30170-30467')가 있으면 앞 5자리(시군구 법정동코드)로 주소의
시군구를 교차검증한다. 둘이 다르면 오류로 멈춘다.
PK 는 건물정보 탭 PK코드를 먼저 보고, 형식이 아니면 파일명(reb/filename.py)에서 읽는다.
"""

# built-in modules
import os
import math
import datetime
import calendar
import time
import urllib.error
import urllib.request
import urllib.parse

# third-party modules
import pandas as pd

# local modules
from epsimple.core.model import address_to_weather, ADDR_WEATHER_TABLE
from .auxiliary import WEATHERDATA_MAPPER, WEATHTERDATA_DIR, MAPPING_DIR
from .filename import read_filename


# ---------------------------------------------------------------------------- #
#                                   VARIABLES                                  #
# ---------------------------------------------------------------------------- #

AMY_DIR = WEATHTERDATA_DIR   # runtime/Weather/AMY

# 기상청 ASOS 지점표 (API허브 stn_inf.php 에서 받은 지점번호, 한글 지점명, 소재지)
STATIONS = pd.read_csv(os.path.join(MAPPING_DIR, "kma_asos_stations.csv"), encoding="utf-8-sig").set_index("지점번호")

API_URL = "https://apihub.kma.go.kr/api/typ01/url/kma_sfctm3.php"

# API허브 지상관측 시간자료(kma_sfctm3) 응답의 열 순서
ASOS_COLUMNS = [
    "TM", "STN", "WD", "WS", "GST_WD", "GST_WS", "GST_TM", "PA", "PS", "PT", "PR",
    "TA", "TD", "HM", "PV", "RN", "RN_DAY", "RN_JUN", "RN_INT", "SD_HR3", "SD_DAY", "SD_TOT",
    "WC", "WP", "WW", "CA_TOT", "CA_MID", "CH_MIN", "CT", "CT_TOP", "CT_MID", "CT_LOW",
    "VS", "SS", "SI", "ST_GD", "TS", "TE_005", "TE_01", "TE_02", "TE_03", "ST_SEA",
    "WH", "BF", "IR", "IX",
]

# epw 데이터 행의 열 이름 (35개)
EPW_COLUMNS = [
    "year", "month", "day", "hour", "minute", "flags",
    "drybulb", "dewpoint", "relhum", "pressure",
    "exthorrad", "extdirrad", "horirsky", "glohorrad", "dirnorrad", "difhorrad",
    "glohorillum", "dirnorillum", "difhorillum", "zenlum",
    "winddir", "windspd", "totskycvr", "opaqskycvr", "visibility", "ceiling",
    "presweathobs", "presweathcodes", "precipwtr", "aerosol", "snowdepth", "dayslastsnow",
    "albedo", "liqprecip", "liqprecipqty",
]

MJ_TO_WH       = 1E6 / 3600   # 1시간 누적 MJ/m2 -> 평균 W/m2
SOLAR_CONSTANT = 1367         # W/m2
KST_MERIDIAN   = 135          # 한국 표준시 기준 경도


# ---------------------------------------------------------------------------- #
#                                   MAIN FUNC                                  #
# ---------------------------------------------------------------------------- #

def get_weatherdata(address:str, option:str, year:int|float|None, pk:str|None=None, authkey:str|None=None) -> str:
    """건물정보 탭 값으로 epw 경로를 정한다. option 은 '표준기상(TMY)' 또는 '실제기상(AMY)'"""

    address = check_pk_address(pk, address)

    if pd.isna(option) or "AMY" not in str(option):
        return tmy_filepath(address)

    if pd.isna(year):
        raise ValueError("기상데이터옵션이 실제기상(AMY)이면 기준년도를 입력해야 합니다.")
    return get_amy_weatherdata(address, int(year), authkey)


def describe_weatherdata(address:str, option:str, year:int|float|None) -> str:
    """get_weatherdata 가 쓸 파일을 실행 전에 글로 보여준다. 파일은 만들지 않는다"""

    if pd.isna(option) or "AMY" not in str(option):
        return "표준기상(TMY) " + os.path.basename(tmy_filepath(address))

    if pd.isna(year):
        raise ValueError("기상데이터옵션이 실제기상(AMY)이면 기준년도를 입력해야 합니다.")

    station  = find_station(address)
    filename = f"{station['Station_num']}_{int(year)}.epw"
    text     = f"실제기상(AMY) {int(year)}년 기상청 {station_name(station['Station_num'])}({station['Station_num']}) 지점"

    if os.path.exists(os.path.join(AMY_DIR, filename)):
        return text
    if not os.environ.get("KMA_API_KEY"):
        raise ValueError(f"{filename} 이 없고 기상청 API 키(런처의 키 입력칸 또는 환경변수 KMA_API_KEY)도 없어 만들 수 없습니다.")
    return text + " - 실행 시 기상청 자료로 생성"


def station_name(number:int) -> str:
    """기상청 지점번호 -> 한글 지점명 (143 -> 대구). 표에 없으면 번호 그대로"""

    number = int(number)
    if number in STATIONS.index:
        return STATIONS.at[number, "지점명"]
    return str(number)


def tmy_filepath(address:str) -> str:
    """070 코어의 주소 매칭으로 TMY epw 경로"""

    terrain, climate, location, filepath = address_to_weather(address, datetime.datetime.today())
    return str(filepath)


def get_amy_weatherdata(address:str, year:int, authkey:str|None=None) -> str:
    """주소와 연도에 맞는 AMY epw 경로. 파일이 없으면 만든다"""

    station  = find_station(address)
    filepath = os.path.join(AMY_DIR, f"{station['Station_num']}_{year}.epw")

    if os.path.exists(filepath):
        return filepath

    print(f"기상청 자료 수집 중: {station_name(station['Station_num'])}({station['Station_num']}) {year}년") # v-070 수정사항
    asos = download_asos(station["Station_num"], year, authkey)
    asos_to_epw(asos, station, year, filepath, template=tmy_filepath(address))
    return filepath


def check_pk_address(pk:str|None, address:str) -> str:
    """PK 코드의 시군구와 주소의 시군구를 비교한다. PK 가 없거나 형식이 아니면 주소를 그대로 쓴다"""

    sigungu = sigungu_from_pk(pk)
    if sigungu is None:
        return address

    if sigungu not in address:
        raise ValueError(f"PK 코드 '{pk}' 의 시군구는 '{sigungu}' 인데 주소는 '{address}' 입니다. 건물정보 탭을 확인하세요.")

    return address


def sigungu_from_pk(pk:str|None) -> str|None:
    """관리건축물대장 PK ('30170-30467') 의 앞 5자리 = 시군구 법정동코드 -> 시군구 이름"""

    if pk is None or pd.isna(pk):
        return None

    code = str(pk).split("-")[0]
    if not (code.isdigit() and len(code) == 5):
        return None

    for sigungu, row in ADDR_WEATHER_TABLE.iterrows():
        if str(row["법정동코드"])[:5] == code:
            return sigungu

    return None


def choose_pk(sheet_pk, filepath:str) -> str|None:
    """건물정보 탭의 PK코드가 형식에 맞으면 그것을, 아니면 파일명의 PK 를 쓴다"""

    if sigungu_from_pk(sheet_pk) is not None:
        return str(sheet_pk)
    return read_filename(filepath)["PK"]


def find_station(address:str) -> pd.Series:
    """주소에 포함된 시군구로 매핑표 행을 찾는다 (지점번호, 위경도)"""

    for _, row in WEATHERDATA_MAPPER.iterrows():
        if row["시·군·구"] in address:
            return row

    raise ValueError(f"주소 '{address}' 에서 시군구를 찾지 못했습니다.")


# ---------------------------------------------------------------------------- #
#                                 KMA API HUB                                  #
# ---------------------------------------------------------------------------- #

def download_asos(station:int, year:int, authkey:str|None=None) -> pd.DataFrame:
    """한 지점의 1년치 시간자료를 월별로 받아 하나의 표로 합친다"""

    if authkey is None:
        authkey = os.environ.get("KMA_API_KEY")
    if not authkey:
        raise ValueError("기상청 API허브 인증키가 없습니다. 환경변수 KMA_API_KEY 또는 authkey 인자로 전달하세요.")

    tables = []
    for month in range(1, 13):
        last_day = calendar.monthrange(year, month)[1]
        params = {
            "tm1"    : f"{year}{month:02d}010000",
            "tm2"    : f"{year}{month:02d}{last_day:02d}2359",
            "stn"    : station,
            "help"   : 0,
            "authKey": authkey,
        }
        url  = API_URL + "?" + urllib.parse.urlencode(params)
        text = request_text(url)

        table = parse_asos_text(text)
        print(f"  {year}-{month:02d} 수집 완료 ({len(table)}행)") # v-070 수정사항
        tables.append(table)

    return pd.concat(tables, ignore_index=True)


def request_text(url:str, retries:int=3) -> str:
    """URL 응답 본문. 서버 오류(504 등)면 잠시 기다렸다 다시 시도한다"""
    
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read().decode("euc-kr", errors="replace")
        except urllib.error.HTTPError as error:
            if attempt == retries:
                raise
            print(f"  서버 응답 오류 {error.code}, 재시도 {attempt}/{retries}") # v-070 수정사항
            time.sleep(5)


def parse_asos_text(text:str) -> pd.DataFrame:
    """API 응답 본문(# 주석, 공백 구분)을 표로 바꾼다"""

    rows = []
    for line in text.splitlines():
        if line.startswith("#") or line.strip() == "":
            continue
        values = line.split()
        if len(values) < len(ASOS_COLUMNS):
            raise ValueError(f"열 개수가 {len(values)}개 ({len(ASOS_COLUMNS)}개 기대): {line[:100]}")
        # 가운데 WW(일기 문자열)에 공백이 있을 수 있으므로 앞 24개, 뒤 21개를 자리로 읽고 나머지를 WW 로 합친다
        front = values[:24]
        back  = values[-21:]
        ww    = " ".join(values[24:-21])
        rows.append(front + [ww] + back)

    table = pd.DataFrame(rows, columns=ASOS_COLUMNS)
    table["TM"] = pd.to_datetime(table["TM"], format="%Y%m%d%H%M")
    for column in ASOS_COLUMNS[1:]:
        table[column] = pd.to_numeric(table[column], errors="coerce")
    return table


def is_missing(value, column:str) -> bool:
    """결측 판정. 기온(TA, TD)은 -99, 나머지는 -9/-99/-999 가 결측"""

    if pd.isna(value):
        return True
    if column in ("TA", "TD"):
        return value <= -90
    return value in (-9, -99, -999)


# ---------------------------------------------------------------------------- #
#                                  EPW FILE                                    #
# ---------------------------------------------------------------------------- #

def read_epw(filepath:str) -> tuple[list[str], pd.DataFrame]:
    """epw -> (헤더 8줄, 데이터 표)"""

    with open(filepath, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    header = lines[:8]
    rows   = [line.split(",") for line in lines[8:] if line.strip()]
    return header, pd.DataFrame(rows, columns=EPW_COLUMNS)


def write_epw(filepath:str, header:list[str], data:pd.DataFrame) -> None:

    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        for line in header:
            f.write(line + "\n")
        for row in data.itertuples(index=False):
            f.write(",".join(str(v) for v in row) + "\n")


def asos_to_epw(asos:pd.DataFrame, station:pd.Series, year:int, out_filepath:str, template:str) -> None:
    """ASOS 시간자료를 TMY 파일(template) 틀에 채워 epw 로 저장한다"""

    if not os.path.exists(template):
        raise FileNotFoundError(f"틀로 쓸 TMY 파일이 없습니다: {template}")

    header, epw = read_epw(template)
    lat  = float(station["기상지점 위도"])
    lon  = float(station["기상지점 경도"])
    asos = asos.set_index("TM")

    missing_radiation = 0
    for i in epw.index:
        month = int(epw.at[i, "month"])
        day   = int(epw.at[i, "day"])
        hour  = int(epw.at[i, "hour"])

        # epw 의 h시 행 = h-1시~h시 값 = ASOS h시 관측
        tm = datetime.datetime(year, month, day) + datetime.timedelta(hours=hour)
        epw.at[i, "year"] = str(year)
        if tm not in asos.index:
            continue
        obs = asos.loc[tm]

        if not is_missing(obs["TA"], "TA"):
            epw.at[i, "drybulb"] = f"{obs['TA']:.1f}"
        if not is_missing(obs["HM"], "HM"):
            epw.at[i, "relhum"] = f"{obs['HM']:.0f}"
        if not is_missing(obs["TD"], "TD"):
            epw.at[i, "dewpoint"] = f"{obs['TD']:.1f}"
        if not is_missing(obs["PA"], "PA"):
            epw.at[i, "pressure"] = f"{obs['PA'] * 100:.0f}"       # hPa -> Pa
        if not is_missing(obs["WD"], "WD"):
            epw.at[i, "winddir"] = f"{obs['WD'] * 10:.0f}"         # 16방위 코드 -> 도
        if not is_missing(obs["WS"], "WS"):
            epw.at[i, "windspd"] = f"{obs['WS']:.1f}"
        if not is_missing(obs["CA_TOT"], "CA_TOT"):
            epw.at[i, "totskycvr"]  = f"{obs['CA_TOT']:.0f}"
            epw.at[i, "opaqskycvr"] = f"{obs['CA_TOT']:.0f}"
        if not is_missing(obs["VS"], "VS"):
            epw.at[i, "visibility"] = f"{obs['VS'] / 100:.1f}"     # 10m 단위 -> km
        if not is_missing(obs["RN"], "RN"):
            epw.at[i, "liqprecip"] = f"{obs['RN']:.1f}"

        # 일사: 밤에는 결측(-9)으로 오므로 0 으로 쓰고, 낮 결측만 TMY 값을 남긴다
        zenith = solar_zenith(lat, lon, month, day, hour - 0.5)
        if is_missing(obs["SI"], "SI") and zenith < 90:
            missing_radiation += 1
            continue
        if is_missing(obs["SI"], "SI"):
            ghi = 0.0
        else:
            ghi = obs["SI"] * MJ_TO_WH
        dni, dhi = split_radiation(ghi, zenith, tm.timetuple().tm_yday)
        epw.at[i, "glohorrad"] = f"{ghi:.0f}"
        epw.at[i, "dirnorrad"] = f"{dni:.0f}"
        epw.at[i, "difhorrad"] = f"{dhi:.0f}"

    if missing_radiation > 0:
        print(f"  일사 결측 {missing_radiation}시간, TMY 값 유지") # v-070 수정사항

    weekday   = calendar.day_name[datetime.date(year, 1, 1).weekday()]
    header[5] = f'COMMENTS 1, "Based on {os.path.basename(template)}"'
    header[6] = f'COMMENTS 2, "KMA ASOS station {station["Station_num"]}, {year}"'
    header[7] = f"DATA PERIODS,1,1,Data,{weekday},1/ 1,12/31"

    write_epw(out_filepath, header, epw)
    print(f"기상청 자료 수집 완료: {os.path.basename(out_filepath)}") # v-070 수정사항


# ---------------------------------------------------------------------------- #
#                                SOLAR RADIATION                               #
# ---------------------------------------------------------------------------- #

def solar_zenith(lat:float, lon:float, month:int, day:int, hour:float) -> float:
    """태양 천정각 [도]. hour 는 KST (12.5 = 12시 30분). NOAA 근사식"""

    n     = datetime.date(2001, month, day).timetuple().tm_yday
    gamma = 2 * math.pi / 365 * (n - 1 + (hour - 12) / 24)

    # 균시차 [분]
    eqtime = 229.18 * (0.000075
                       + 0.001868 * math.cos(gamma)     - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma) - 0.040849 * math.sin(2 * gamma))
    # 적위 [rad]
    decl = (0.006918
            - 0.399912 * math.cos(gamma)     + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.001480 * math.sin(3 * gamma))

    solar_minutes = hour * 60 + eqtime + 4 * (lon - KST_MERIDIAN)
    hour_angle    = math.radians(solar_minutes / 4 - 180)
    lat_rad       = math.radians(lat)

    cos_zenith = math.sin(lat_rad) * math.sin(decl) + math.cos(lat_rad) * math.cos(decl) * math.cos(hour_angle)
    cos_zenith = max(-1, min(1, cos_zenith))
    return math.degrees(math.acos(cos_zenith))


def split_radiation(ghi:float, zenith:float, day_of_year:int) -> tuple[float, float]:
    """전천일사 GHI [W/m2] -> (법선면 직달 DNI, 수평면 확산 DHI). Erbs 모델"""

    if ghi <= 0 or zenith >= 88:
        return 0.0, max(ghi, 0.0)

    cos_zenith = math.cos(math.radians(zenith))
    ext_normal = SOLAR_CONSTANT * (1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365))

    # 청명도 kt
    kt = ghi / (ext_normal * cos_zenith)
    kt = min(kt, 1.0)

    if kt <= 0.22:
        diffuse_fraction = 1 - 0.09 * kt
    elif kt <= 0.8:
        diffuse_fraction = 0.9511 - 0.1604 * kt + 4.388 * kt**2 - 16.638 * kt**3 + 12.336 * kt**4
    else:
        diffuse_fraction = 0.165

    dhi = ghi * diffuse_fraction
    dni = (ghi - dhi) / cos_zenith
    dni = min(dni, ext_normal)
    return dni, dhi
