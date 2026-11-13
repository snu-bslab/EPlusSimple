# EPlusSimple

**EPlusSimple** is an open-source building energy simulation engine. It simplifies the complex EnergyPlus workflow by using a spreadsheet-centric data structure and graph-based spatial relationship visualization.

## Installation & Setup

This project is designed to be **portable**. You do not need to install Python or manage libraries manually.

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/Gonie-Gonie/EPlusSimple.git](https://github.com/Gonie-Gonie/EPlusSimple.git)
    cd EPlusSimple
    ```
2.  **Initialize Environment:**
    Run `setup.bat`. This will create a local portable Python environment (`venv`) and install all required dependencies from `requirements.txt` automatically.


## How to Run

There are two primary ways to interact with the engine:

### 1. CLI Mode (Simulation Engine)
Use `runEngine.bat` for direct simulation or format conversion via the command line.

* **Run Simulation:**
    ```bash
    runEngine.bat run -i your_model.grm -o your_output_destinaton.grr
    ```
* **Convert Formats (e.g., Excel to IDF):**
    ```bash
    runEngine.bat convert your_model.xlsx -s excel -d idf
    ```

### 2. Web GUI Mode (Excel Launcher)
Use `runExcelLauncher.bat` to launch a user-friendly web interface.

1.  Double-click `runExcelLauncher.bat`.
2.  A local Flask server will start, and the launcher will open a local web interface.
3.  Upload your "Before" and "After" Excel files to visualize energy performance differences and debug reports.

## REB Launcher weather years

The REB Launcher offers 2019 and 2025 weather for all 39 ASOS stations in
the existing district mapping. Selecting a year applies it to every
simulation in the comparison. The default uses the existing district and
simulation-stage mapping.

The EPWs combine hourly observations from the [KMA API Hub](https://apihub.kma.go.kr/apiList.do)
(ASOS period endpoint, KST) with the existing station's 2024 EPW. The
converter replaces valid observed temperature, dew point, humidity,
station pressure, wind, total sky cover and global horizontal radiation.
Missing and unobserved fields retain the base EPW values. Direct and
diffuse solar components are estimates based on the base EPW proportions.
See `src/reb/data/asos_coverage.csv` for station and year coverage. Files
for stations without an irradiance sensor may use base EPW irradiance
throughout. Consider these distinctions when comparing simulated energy
use across years.

To regenerate from monthly API response text files, run
`python scripts/build_reb_asos_epw.py PATH_TO_MONTHLY_RESPONSES`.
The API key is only needed to obtain the monthly responses.
