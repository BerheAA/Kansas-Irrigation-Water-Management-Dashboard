
import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import date, datetime, timedelta

# -------------------------
# CONFIG
# -------------------------

st.set_page_config(
    page_title="Kansas Irrigation Water Management Dashboard",
    layout="wide"
)

# Soft background theme similar to Nevada / New Mexico dashboard
st.markdown(
    """
    <style>
    html, body, [data-testid="stApp"] {
        background-color: #f5f5f5;
    }
    [data-testid="stSidebar"] {
        background-color: #ffffff;
    }
    .metric-card {
        padding: 0.75rem 1rem;
        border-radius: 0.75rem;
        background-color: #ffffff;
        box-shadow: 0 0 8px rgba(0,0,0,0.05);
        margin-bottom: 0.5rem;
    }
    .section-header {
        padding: 0.4rem 0.8rem;
        border-radius: 0.5rem;
        display: inline-block;
        font-weight: 600;
        background-color: #e3f2fd;
        margin-bottom: 0.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/era5"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
SSURGO_SDA_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"

# -------------------------
# REFERENCE DATA
# -------------------------

KS_EXAMPLE_LOCATIONS = {
    "Colby (NW Kansas irrigated corn/wheat)": (39.3953, -101.0524),
    "Garden City (SW Kansas High Plains)": (37.9717, -100.8727),
    "Dodge City": (37.7528, -100.0171),
    "Scott City": (38.4825, -100.9071),
    "Hays (Central KS)": (38.8792, -99.3268),
    "Great Bend": (38.3645, -98.7640),
    "Salina": (38.8403, -97.6114),
    "Manhattan (NE/Central research station)": (39.1836, -96.5717),
    "McPherson": (38.3708, -97.6648),
    "Wichita (South Central)": (37.6872, -97.3301),
    "Parsons (SE Kansas)": (37.3409, -95.2591),
    "User-defined": (39.1836, -96.5717),
}

CROP_PARAMS = {
    "Corn (grain)": {
        "kc": 1.15,
        "root_depth_m": 1.2,
        "yield_potential_mmy": 15000,
        "ky": 1.25,
        "season_length_days": 150,
    },
    "Corn (silage)": {
        "kc": 1.15,
        "root_depth_m": 1.2,
        "yield_potential_mmy": 25000,
        "ky": 1.1,
        "season_length_days": 145,
    },
    "Grain sorghum": {
        "kc": 1.0,
        "root_depth_m": 1.3,
        "yield_potential_mmy": 9000,
        "ky": 1.0,
        "season_length_days": 130,
    },
    "Soybean": {
        "kc": 1.05,
        "root_depth_m": 1.1,
        "yield_potential_mmy": 4500,
        "ky": 1.1,
        "season_length_days": 145,
    },
    "Winter wheat": {
        "kc": 1.05,
        "root_depth_m": 1.0,
        "yield_potential_mmy": 7000,
        "ky": 1.0,
        "season_length_days": 220,
    },
    "Alfalfa": {
        "kc": 1.1,
        "root_depth_m": 1.3,
        "yield_potential_mmy": 14000,
        "ky": 1.1,
        "season_length_days": 210,
    },
    "Pasture / Grass": {
        "kc": 0.95,
        "root_depth_m": 0.8,
        "yield_potential_mmy": 9000,
        "ky": 1.0,
        "season_length_days": 180,
    },
}

SOIL_TYPES = {
    "Sandy loam": {
        "description": "Lower water holding, common in parts of western KS",
        "TAW_mm_per_m": 110,
    },
    "Loam": {
        "description": "Balanced soil with moderate water storage",
        "TAW_mm_per_m": 140,
    },
    "Silt loam": {
        "description": "Typical of central and eastern KS, good water holding",
        "TAW_mm_per_m": 160,
    },
    "Clay loam": {
        "description": "Heavier soils with high water holding",
        "TAW_mm_per_m": 170,
    },
}

STRATEGIES = {
    "Full irrigation (no intentional stress)": 0.45,
    "Moderate deficit (light stress allowed)": 0.6,
    "Severe deficit (only critical irrigations)": 0.8,
}

IRRIGATION_SYSTEMS = {
    "Center pivot": 0.85,
    "Sprinkler (solid set/line)": 0.80,
    "Surface / Furrow": 0.65,
    "Drip": 0.90,
}

# -------------------------
# WEATHER FUNCTIONS
# -------------------------

def fetch_archive_weather(lat, lon, start_date, end_date):
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "daily": [
            "precipitation_sum",
            "et0_fao_evapotranspiration",
            "temperature_2m_max",
            "temperature_2m_min",
        ],
        "timezone": "America/Chicago",
    }
    try:
        r = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        st.warning(f"Could not retrieve historical weather data: {e}")
        return pd.DataFrame()

    if "daily" not in data:
        return pd.DataFrame()

    daily = data["daily"]
    df = pd.DataFrame(daily)
    df["time"] = pd.to_datetime(df["time"])
    df.rename(
        columns={
            "precipitation_sum": "precip_mm",
            "et0_fao_evapotranspiration": "et0_mm",
            "temperature_2m_max": "tmax_c",
            "temperature_2m_min": "tmin_c",
        },
        inplace=True,
    )
    return df


def fetch_forecast_weather(lat, lon, start_date, end_date):
    from datetime import date as _date
    days_ahead = (end_date - _date.today()).days
    if days_ahead <= 0:
        return pd.DataFrame()

    days_ahead = min(days_ahead, 16)

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": [
            "precipitation_sum",
            "et0_fao_evapotranspiration",
            "temperature_2m_max",
            "temperature_2m_min",
        ],
        "timezone": "America/Chicago",
        "forecast_days": days_ahead,
        "past_days": 0,
    }

    try:
        r = requests.get(OPEN_METEO_FORECAST_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        st.warning(f"Could not retrieve forecast weather data: {e}")
        return pd.DataFrame()

    if "daily" not in data:
        return pd.DataFrame()

    daily = data["daily"]
    df = pd.DataFrame(daily)
    df["time"] = pd.to_datetime(df["time"])
    df.rename(
        columns={
            "precipitation_sum": "precip_mm",
            "et0_fao_evapotranspiration": "et0_mm",
            "temperature_2m_max": "tmax_c",
            "temperature_2m_min": "tmin_c",
        },
        inplace=True,
    )
    df = df[df["time"].dt.date >= start_date]
    df = df[df["time"].dt.date <= end_date]
    return df


def get_season_weather(lat, lon, planting_date, season_length):
    start_date = planting_date
    end_date = planting_date + timedelta(days=season_length)

    today = date.today()
    hist_end = min(end_date, today - timedelta(days=1))
    hist_df = pd.DataFrame()
    if hist_end >= start_date:
        hist_df = fetch_archive_weather(lat, lon, start_date, hist_end)

    fc_df = pd.DataFrame()
    if end_date >= today:
        fc_df = fetch_forecast_weather(lat, lon, max(start_date, today), end_date)

    if not hist_df.empty and not fc_df.empty:
        df = pd.concat([hist_df, fc_df], ignore_index=True)
    elif not hist_df.empty:
        df = hist_df
    else:
        df = fc_df

    if df is None or df.empty:
        return pd.DataFrame()

    df = df.sort_values("time")
    df = df[df["time"].dt.date >= start_date]
    df = df[df["time"].dt.date <= end_date]
    df.reset_index(drop=True, inplace=True)
    return df


def generate_simple_eto_weather(
    planting_date,
    season_length,
    base_eto_mm=5.0,
    seasonal_amp_mm=1.0,
    mean_precip_mm=2.0,
    rain_probability=0.30,
):
    """Generate a simple synthetic ET0 and rainfall pattern for demonstration."""
    dates = [planting_date + timedelta(days=i) for i in range(season_length)]
    doy = np.array([d.timetuple().tm_yday for d in dates])

    et0 = base_eto_mm + seasonal_amp_mm * np.sin(2 * np.pi * (doy - 190) / 365.0)
    et0 = np.maximum(et0, 0.0)

    rng = np.random.default_rng(42)
    rain_flag = rng.uniform(size=len(dates)) < rain_probability
    precip = np.where(rain_flag, rng.gamma(shape=1.5, scale=mean_precip_mm / 1.5), 0.0)

    tmean = 23 + 7 * np.sin(2 * np.pi * (doy - 200) / 365.0)
    tmax = tmean + 6
    tmin = tmean - 6

    df = pd.DataFrame(
        {
            "time": pd.to_datetime(dates),
            "precip_mm": precip,
            "et0_mm": et0,
            "tmax_c": tmax,
            "tmin_c": tmin,
        }
    )
    return df


def load_climate_from_csv(uploaded_file, planting_date, season_length):
    try:
        df = pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"Could not read CSV file: {e}")
        return pd.DataFrame()

    required_cols = ["date", "precip_mm", "et0_mm", "tmax_c", "tmin_c"]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"CSV is missing required columns: {missing}")
        return pd.DataFrame()

    try:
        df["time"] = pd.to_datetime(df["date"])
    except Exception as e:
        st.error(f"Could not parse 'date' column: {e}")
        return pd.DataFrame()

    df = df.sort_values("time")
    start_date = planting_date
    end_date = planting_date + timedelta(days=season_length)
    df = df[(df["time"].dt.date >= start_date) & (df["time"].dt.date <= end_date)]

    if df.empty:
        st.error("No climate data in CSV covers the requested season.")
        return pd.DataFrame()

    return df[["time", "precip_mm", "et0_mm", "tmax_c", "tmin_c"]].copy()


# -------------------------
# SSURGO SOIL LOOKUP (BETA)
# -------------------------

def lookup_ssurgo_soil(lat, lon):
    """
    Very simple SSURGO lookup using NRCS SDA Tabular service (beta).
    Returns dominant component name and taxonomic order, if available.
    """
    sql = f"""
        SELECT TOP 1 c.compname, c.taxorder
        FROM mapunit AS mu
        INNER JOIN component AS c ON c.mukey = mu.mukey
        WHERE mu.mukey IN (
            SELECT TOP 1 mukey
            FROM SDA_Get_Mukey_from_intersection_with_WktWgs84(
                'POINT({lon} {lat})'
            )
        )
        ORDER BY c.comppct_r DESC
    """
    payload = {"format": "JSON+COLUMNS", "query": sql}
    try:
        r = requests.post(SSURGO_SDA_URL, data=payload, timeout=25)
        r.raise_for_status()
        data = r.json()
        if "Table" in data and len(data["Table"]) > 0:
            row = data["Table"][0]
            return {
                "compname": row.get("compname", None),
                "taxorder": row.get("taxorder", None),
            }
        else:
            return None
    except Exception as e:
        st.warning(f"SSURGO lookup failed: {e}")
        return None


# -------------------------
# IRRIGATION ENGINE
# -------------------------

def simulate_irrigation(
    df_weather,
    crop_name,
    soil_name,
    strategy_label,
    irrigation_efficiency=0.85,
    rainfall_efficiency=0.8,
):
    if df_weather is None or df_weather.empty:
        return None, None

    crop = CROP_PARAMS[crop_name]
    soil = SOIL_TYPES[soil_name]

    kc = crop["kc"]
    root_depth = crop["root_depth_m"]
    taw_per_m = soil["TAW_mm_per_m"]
    taw = taw_per_m * root_depth

    raw_fraction = STRATEGIES[strategy_label]
    readily_available = taw * (1 - raw_fraction)

    df = df_weather.copy()
    df["date"] = df["time"].dt.date

    df["etc_mm"] = df["et0_mm"] * kc
    df["eff_precip_mm"] = df["precip_mm"] * rainfall_efficiency

    water_storage = taw
    cum_deficit = 0.0
    irrigations = []
    storage_list = []
    deficit_list = []
    etc_cum = 0.0
    etc_met_cum = 0.0

    for idx, row in df.iterrows():
        etc = max(row["etc_mm"], 0)
        p_eff = max(row["eff_precip_mm"], 0)

        water_storage = max(0.0, min(taw, water_storage + p_eff - etc))

        deficit = taw - water_storage
        irrigation_mm = 0.0

        if deficit > readily_available:
            target_refill = taw - water_storage
            irrigation_mm = target_refill / irrigation_efficiency
            water_storage = taw
            irrigations.append(
                {
                    "date": row["date"],
                    "irrigation_mm": irrigation_mm,
                    "deficit_before_mm": deficit,
                }
            )

        storage_list.append(water_storage)
        deficit_list.append(taw - water_storage)

        etc_cum += etc
        supplied_today = p_eff + irrigation_mm * irrigation_efficiency
        etc_met_cum += min(etc, supplied_today)

        cum_deficit += max(0.0, etc - supplied_today)

    df["soil_storage_mm"] = storage_list
    df["deficit_mm"] = deficit_list

    irrigation_df = pd.DataFrame(irrigations)

    if etc_cum > 0:
        yield_index = etc_met_cum / etc_cum
    else:
        yield_index = 1.0

    yield_index = float(np.clip(yield_index, 0.3, 1.05))
    rel_yield = yield_index

    return irrigation_df, {
        "taw_mm": taw,
        "readily_available_mm": readily_available,
        "total_etc_mm": etc_cum,
        "total_deficit_mm": cum_deficit,
        "yield_index": rel_yield,
        "n_irrigations": 0 if irrigation_df is None or irrigation_df.empty else len(irrigation_df),
        "total_irrigation_mm": 0.0 if irrigation_df is None or irrigation_df.empty else float(irrigation_df["irrigation_mm"].sum()),
    }


# -------------------------
# MAIN APP LAYOUT
# -------------------------

st.title("Kansas Irrigation Water Management Dashboard")
st.caption(
    "Prototype decision support tool for ET-based irrigation scheduling and water planning "
    "across Kansas (for demonstration and Extension use)."
)

st.markdown("---")

# SIDEBAR: LOCATION, CROP, CLIMATE, IRRIGATION
with st.sidebar:
    st.header("1. Location & Crop Setup")

    loc_name = st.selectbox(
        "Select location",
        options=list(KS_EXAMPLE_LOCATIONS.keys()),
        index=1,
        help="Choose a representative location or 'User-defined' and adjust coordinates.",
    )

    base_lat, base_lon = KS_EXAMPLE_LOCATIONS[loc_name]
    lat = st.number_input("Latitude (°N)", value=float(base_lat), format="%.4f")
    lon = st.number_input("Longitude (°E)", value=float(base_lon), format="%.4f")

    today = date.today()
    default_planting = date(today.year, 4, 15)
    planting_date = st.date_input(
        "Planting / emergence date",
        value=default_planting,
        help="Approximate start of main irrigation season.",
    )

    crop_name = st.selectbox("Crop", options=list(CROP_PARAMS.keys()), index=0)

    st.header("2. Soil & SSURGO (beta)")
    soil_name = st.selectbox(
        "Dominant soil type (manual)",
        options=list(SOIL_TYPES.keys()),
        index=1,
        help="Generic texture class used to estimate soil water holding capacity.",
    )

    use_ssurgo = st.checkbox(
        "Try SSURGO soil lookup from GPS (beta)",
        value=False,
        help="Queries NRCS Soil Data Access by coordinates and reports dominant soil component.",
    )
    if use_ssurgo:
        if st.button("Lookup SSURGO soil at this point"):
            ssurgo_info = lookup_ssurgo_soil(lat, lon)
            if ssurgo_info:
                st.success(
                    f"SSURGO dominant component: {ssurgo_info.get('compname', 'N/A')} "
                    f"(Taxorder: {ssurgo_info.get('taxorder', 'N/A')})"
                )
            else:
                st.warning("No SSURGO component found for this point (or request failed).")

    st.header("3. Climate Data / ETo options")

    climate_source = st.radio(
        "Climate / ET₀ source",
        options=[
            "Open-Meteo (automatic)",
            "Simple ET₀ pattern (demo)",
            "Upload daily climate CSV",
        ],
        index=0,
        help="Choose how to provide daily ET₀ and rainfall to the irrigation engine.",
    )

    uploaded_csv = None
    if climate_source == "Upload daily climate CSV":
        st.markdown(
            """
            **CSV format requirements**  
            - Columns: `date`, `precip_mm`, `et0_mm`, `tmax_c`, `tmin_c`  
            - `date` in a format recognized by pandas (e.g., YYYY-MM-DD)
            """
        )
        uploaded_csv = st.file_uploader(
            "Upload daily climate CSV",
            type=["csv"],
        )

    if climate_source == "Simple ET₀ pattern (demo)":
        st.markdown("Simple sinusoidal ET₀ pattern with random rainfall for teaching / demos.")
        base_eto = st.slider("Base ET₀ (mm/day)", 3.0, 7.0, 5.0, 0.1)
        seasonal_amp = st.slider("Seasonal ET₀ amplitude (mm/day)", 0.0, 3.0, 1.0, 0.1)
        rain_prob = st.slider("Daily rainfall probability", 0.0, 0.7, 0.30, 0.05)
        mean_rain = st.slider("Mean rainfall on rainy days (mm)", 2.0, 25.0, 10.0, 0.5)
    else:
        base_eto = 5.0
        seasonal_amp = 1.0
        rain_prob = 0.30
        mean_rain = 10.0

    st.header("4. Irrigation system & strategy")

    irrigation_system = st.selectbox(
        "Irrigation system",
        options=list(IRRIGATION_SYSTEMS.keys()),
        index=0,
    )
    default_eff = IRRIGATION_SYSTEMS[irrigation_system]

    strategy_label = st.selectbox(
        "Irrigation strategy",
        options=list(STRATEGIES.keys()),
        index=0,
        help="Full irrigation keeps soil water high; deficit irrigation allows more stress.",
    )

    irrigation_eff = st.slider(
        "Irrigation application efficiency",
        min_value=0.6,
        max_value=0.95,
        value=float(default_eff),
        step=0.01,
        help="Can be adjusted around typical values for the selected system.",
    )
    rainfall_eff = st.slider(
        "Rainfall effectiveness",
        min_value=0.5,
        max_value=1.0,
        value=0.8,
        step=0.05,
    )

    run_button = st.button("Run irrigation simulation", type="primary")

# TOP SECTION: MAP & SUMMARY CARDS
st.markdown('<span class="section-header">1. Kansas overview & field location</span>', unsafe_allow_html=True)

col_map, col_desc = st.columns([1.3, 1.2])

with col_map:
    df_map = pd.DataFrame({"lat": [lat], "lon": [lon]})
    st.map(df_map, zoom=6)

with col_desc:
    st.markdown(
        f"""
        <div class="metric-card">
        <b>Selected location:</b> {loc_name}<br>
        <b>Coordinates:</b> {lat:.3f}°N, {lon:.3f}°E<br>
        <b>Crop:</b> {crop_name}<br>
        <b>Soil (manual):</b> {soil_name}<br>
        <b>Irrigation system:</b> {irrigation_system}<br>
        <b>Strategy:</b> {strategy_label}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if use_ssurgo:
        st.markdown(
            """
            <div class="metric-card">
            <b>SSURGO soil (beta):</b><br>
            If lookup was successful, dominant component and taxorder are shown in the sidebar.
            Use this info to refine your soil texture selection.
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        This prototype focuses on **ET-based irrigation scheduling** for key crops in Kansas.  
        Use it to explore how **location, climate source, soil, irrigation system, and strategy** affect water use and yield.
        """
    )

st.markdown("---")

tabs = st.tabs(
    [
        "2. Weather & ET summary",
        "3. Scenario results: irrigation, ET, yield index",
        "4. Detailed irrigation schedule & time series",
    ]
)

if run_button:
    crop = CROP_PARAMS[crop_name]
    season_len = crop["season_length_days"]

    with st.spinner("Preparing climate data and running irrigation simulation..."):
        if climate_source == "Open-Meteo (automatic)":
            df_weather = get_season_weather(lat, lon, planting_date, season_len)
        elif climate_source == "Simple ET₀ pattern (demo)":
            df_weather = generate_simple_eto_weather(
                planting_date,
                season_length=season_len,
                base_eto_mm=base_eto,
                seasonal_amp_mm=seasonal_amp,
                mean_precip_mm=mean_rain,
                rain_probability=rain_prob,
            )
        else:  # Upload daily climate CSV
            if uploaded_csv is None:
                st.error("Please upload a climate CSV file or choose another climate option.")
                df_weather = pd.DataFrame()
            else:
                df_weather = load_climate_from_csv(uploaded_csv, planting_date, season_len)

        if df_weather is None or df_weather.empty:
            st.error("No weather / climate data available for this configuration.")
        else:
            irr_df, summary = simulate_irrigation(
                df_weather,
                crop_name,
                soil_name,
                strategy_label,
                irrigation_efficiency=irrigation_eff,
                rainfall_efficiency=rainfall_eff,
            )

            # TAB 1: Weather & ET summary
            with tabs[0]:
                st.markdown('<span class="section-header">2. Weather and reference ET₀ for the season</span>', unsafe_allow_html=True)

                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric(
                        "Season length (days)",
                        f"{len(df_weather):.0f}",
                    )
                with c2:
                    st.metric(
                        "Total precipitation (mm)",
                        f"{df_weather['precip_mm'].sum():.1f}",
                    )
                with c3:
                    st.metric(
                        "Total reference ET₀ (mm)",
                        f"{df_weather['et0_mm'].sum():.1f}",
                    )
                with c4:
                    st.metric(
                        "Mean Tmax / Tmin (°C)",
                        f"{df_weather['tmax_c'].mean():.1f} / {df_weather['tmin_c'].mean():.1f}",
                    )

                chart_df = df_weather[["time", "precip_mm", "et0_mm"]].copy()
                chart_df = chart_df.rename(
                    columns={
                        "time": "Date",
                        "precip_mm": "Rain (mm)",
                        "et0_mm": "ET₀ (mm)",
                    }
                )
                chart_df = chart_df.melt("Date", var_name="Variable", value_name="mm")

                st.line_chart(chart_df, x="Date", y="mm", color="Variable")

                st.caption(
                    "Reference ET₀ can come from Open-Meteo, a simple ET pattern, or an uploaded CSV. "
                    "Actual crop water use (ETc) is ET₀ × crop coefficient (Kc)."
                )

            # TAB 2: Scenario results summary
            with tabs[1]:
                st.markdown('<span class="section-header">3. Irrigation water use and yield index</span>', unsafe_allow_html=True)

                if irr_df is None or irr_df.empty:
                    st.info(
                        "No irrigations were triggered with the current assumptions. "
                        "This may occur if rainfall and ET are low, or if the season is very short."
                    )

                colA, colB, colC = st.columns(3)
                with colA:
                    st.metric(
                        "Total irrigation (mm)",
                        f"{summary['total_irrigation_mm']:.1f}",
                    )
                with colB:
                    st.metric(
                        "Number of irrigation events",
                        f"{summary['n_irrigations']}",
                    )
                with colC:
                    st.metric(
                        "Yield index (0–1)",
                        f"{summary['yield_index']:.2f}",
                        help="Relative yield index based on how much of crop water demand is satisfied.",
                    )

                col1, col2 = st.columns(2)
                with col1:
                    st.metric(
                        "Total crop ETc (mm)",
                        f"{summary['total_etc_mm']:.1f}",
                    )
                with col2:
                    st.metric(
                        "Cumulative ET deficit (mm)",
                        f"{summary['total_deficit_mm']:.1f}",
                    )

                summary_table = pd.DataFrame(
                    {
                        "Crop": [crop_name],
                        "Soil (manual)": [soil_name],
                        "Irrigation system": [irrigation_system],
                        "Strategy": [strategy_label],
                        "TAW (mm)": [summary["taw_mm"]],
                        "Total irrigation (mm)": [summary["total_irrigation_mm"]],
                        "Irrigation events (#)": [summary["n_irrigations"]],
                        "Total ETc (mm)": [summary["total_etc_mm"]],
                        "Cum. deficit (mm)": [summary["total_deficit_mm"]],
                        "Yield index (0–1)": [summary["yield_index"]],
                    }
                )
                st.markdown("#### Scenario summary table")
                st.dataframe(summary_table, use_container_width=True)

                st.markdown(
                    """
                    - **TAW** = Total Available Water in the root zone, based on soil texture and rooting depth.  
                    - **Yield index** approximates relative yield compared to a fully irrigated scenario.  
                    - Use this tab to compare strategies, irrigation systems, and climate scenarios.
                    """
                )

            # TAB 3: Detailed schedule & time series
            with tabs[2]:
                st.markdown('<span class="section-header">4. Daily soil water balance and irrigation schedule</span>', unsafe_allow_html=True)

                if irr_df is not None and not irr_df.empty:
                    st.markdown("##### Irrigation events")
                    st.dataframe(irr_df, use_container_width=True)
                else:
                    st.info("No irrigation events were triggered in this simulation.")

                ts = df_weather[["time", "soil_storage_mm", "deficit_mm"]].copy()
                ts = ts.rename(
                    columns={
                        "time": "Date",
                        "soil_storage_mm": "Soil storage (mm)",
                        "deficit_mm": "Deficit (mm)",
                    }
                )
                st.markdown("##### Soil water storage & deficit")
                st.line_chart(ts.set_index("Date"))

                st.caption(
                    "Values are conceptual and for demonstration only. For operational scheduling, "
                    "this framework should be calibrated with local soil and crop data from Kansas fields."
                )

else:
    with tabs[0]:
        st.info("Set your location, crop, climate option, soil, and irrigation system in the sidebar, then click **Run irrigation simulation**.")
    with tabs[1]:
        st.info("Scenario results will appear here after running a simulation.")
    with tabs[2]:
        st.info("Daily irrigation schedule and time series will be shown after running a simulation.")
