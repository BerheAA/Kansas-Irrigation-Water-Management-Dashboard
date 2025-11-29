# Kansas Irrigation Water Management Dashboard

This is a Streamlit-based prototype dashboard for **ET-based irrigation scheduling** and water planning across Kansas.

The structure and functionality mirror the New Mexico irrigation dashboard, but with **Kansas-specific locations, crops, soils, and time zone.**

## Features

- Kansas locations:
  - Colby, Garden City, Dodge City, Scott City, Hays, Great Bend, Salina, Manhattan, McPherson, Wichita, Parsons, and a user-defined GPS point.
- Key irrigated and rainfed crops:
  - Corn (grain and silage), grain sorghum, soybean, winter wheat, alfalfa, pasture/grass.
- **Climate / ET₀ options:**
  - Open-Meteo archive + forecast (automatic ET₀ and rainfall; timezone = America/Chicago).
  - Simple synthetic ET₀ pattern (demo mode for teaching, reflecting Kansas seasonal patterns).
  - Uploaded daily climate CSV (`date`, `precip_mm`, `et0_mm`, `tmax_c`, `tmin_c`).
- **Irrigation systems:** Center pivot, sprinkler (solid set/line), surface/furrow, drip (each with typical application efficiency, adjustable).
- **Irrigation strategies:** Full irrigation, moderate deficit, severe deficit.
- Soil types (Sandy loam, Loam, Silt loam, Clay loam) with total available water (TAW) estimates.
- Optional **SSURGO soil lookup (beta)** by GPS using NRCS Soil Data Access.
- Tabs for:
  - Weather & ET₀ summary
  - Scenario results (irrigation, ETc, yield index)
  - Detailed daily soil-water balance and irrigation schedule

## Installation

1. Create and activate a Python environment (optional but recommended).

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the dashboard:

```bash
streamlit run app.py
```

The app will open in your browser (typically at `http://localhost:8501`).

## Climate CSV Format

If you choose **"Upload daily climate CSV"**, your file must contain at least these columns:

- `date` – parsable by pandas (e.g., `YYYY-MM-DD`)
- `precip_mm` – daily rainfall (mm)
- `et0_mm` – daily reference ET₀ (mm)
- `tmax_c` – daily maximum temperature (°C)
- `tmin_c` – daily minimum temperature (°C)

The app will filter the CSV to match your selected planting date and crop season length.

## SSURGO Soil Lookup (beta)

- Enable the checkbox **"Try SSURGO soil lookup from GPS (beta)"** in the sidebar.
- Click **"Lookup SSURGO soil at this point"**.
- If successful, the app reports the dominant soil component name and taxonomic order.
- Use this information to refine your manual soil texture selection.

> **Note:** SSURGO lookup requires internet access to the NRCS SDA service. If it fails, you can still use the manual soil types.

## Notes

- This is a **prototype for research and Extension demos**. For operational use, the model parameters (Kc, rooting depth, TAW, yield response, etc.) should be calibrated with local field data from Kansas.
- The simple ET₀ pattern mode is ideal for presentations when live web APIs are not reliable.
