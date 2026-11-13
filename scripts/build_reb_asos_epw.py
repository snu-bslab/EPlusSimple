"""Build REB hourly EPWs from monthly KMA sfctm3 period responses.

Supply unmodified YYYYMM.txt responses for all stations. Query KST from
01:00 on the first of each month through 00:00 on the first of the next.
"""
import argparse
import calendar
import csv
from datetime import datetime, timedelta
from pathlib import Path


DATA = Path(__file__).resolve().parents[1] / "src" / "reb" / "data"
# EPW column, ASOS column, valid range, conversion factor.
FIELDS = [
    (6, 11, -90, 70, 1), (7, 12, -90, 70, 1),
    (8, 13, 0, 100, 1), (9, 7, 310, 1200, 100),
    (20, 2, 0, 36, 10), (21, 3, 0, 100, 1),
    (22, 25, 0, 10, 1),
]


def observations(source, year, stations):
    result = {station: {} for station in stations}
    for month in range(1, 13):
        path = source / f"{year}{month:02}.txt"
        with path.open(encoding="utf-8-sig") as file:
            for line in file:
                fields = line.split()
                if not fields or fields[0].startswith("#"):
                    continue
                if len(fields) < 35 or len(fields[0]) != 12:
                    raise ValueError(f"Unexpected ASOS row in {path.name}")
                station = int(fields[1])
                if station in result:
                    key = fields[0]
                    if key in result[station]:
                        raise ValueError(f"Duplicate observation: {station} {key}")
                    result[station][key] = fields
    return result


def build(station, year, records):
    template = DATA / f"{station}_2024.epw"
    with template.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        headers = [next(reader) for _ in range(8)]
        rows = {
            (int(row[1]), int(row[2]), int(row[3])): row
            for row in reader if row
        }
    headers[5] = ["COMMENTS 1", f"KMA ASOS {station}, {year}; base: {template.name}"]
    headers[6] = [
        "COMMENTS 2",
        "Missing or unobserved fields use the base EPW; observed GHI uses base solar proportions where available",
    ]
    headers[7][4] = calendar.day_name[datetime(year, 1, 1).weekday()]
    start = datetime(year, 1, 1)
    coverage = {"temperature": 0, "ghi": 0}
    output = []
    for offset in range(8760):
        beginning = start + timedelta(hours=offset)
        hour = beginning.hour + 1
        row = rows[beginning.month, beginning.day, hour]
        row[0] = str(year)
        row[4] = "60"
        fields = records.get((beginning + timedelta(hours=1)).strftime("%Y%m%d%H%M"))
        if fields:
            for target, source, low, high, scale in FIELDS:
                value = float(fields[source])
                if low <= value <= high:
                    row[target] = f"{value * scale:g}"
                    if target == 6:
                        coverage["temperature"] += 1
            solar = float(fields[34])
            if solar >= 0:
                ghi = solar * 1000 / 3.6
                base_ghi = float(row[13])
                row[13] = f"{ghi:.2f}"
                if ghi == 0 or base_ghi <= 0:
                    row[14], row[15] = "0", row[13]
                else:
                    ratio = ghi / base_ghi
                    row[14] = f"{min(1415, ratio * float(row[14])):.2f}"
                    row[15] = f"{min(ghi, ratio * float(row[15])):.2f}"
                coverage["ghi"] += 1
        output.append(row)
    if coverage["temperature"] < 8760 * 0.95:
        raise ValueError(f"Incomplete temperature coverage for {station} {year}: {coverage}")
    target = DATA / f"{station}_{year}.epw"
    with target.open("w", encoding="utf-8", newline="") as file:
        csv.writer(file, lineterminator="\n").writerows(headers + output)
    return [station, year, len(records), *coverage.values()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    with (DATA / "weatherdata_mapping.csv").open(encoding="cp949", newline="") as file:
        stations = sorted({int(row["Station_num"]) for row in csv.DictReader(file)})
    with (DATA / "asos_coverage.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(["station", "year", "observations", "temperature_hours", "observed_ghi_hours"])
        for year in (2019, 2025):
            data = observations(args.source, year, stations)
            for station in stations:
                writer.writerow(build(station, year, data[station]))


if __name__ == "__main__":
    main()
