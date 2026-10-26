"""
Real Exchange Rate (RER) Explorer
Streamlit app using IMF SDMX 3.0 monthly CPI and exchange-rate data.

Definitions
    S(t)   = units of Country 2 currency per 1 unit of Country 1 currency
    P1(t)  = Country 1 monthly CPI,  P2(t) = Country 2 monthly CPI
    RER(t) = S(t) * P1(t) / P2(t)
    RER*   = average of RER(t) over valid months in the selected sample
    Real Index(t) = 100 * RER(t) / RER*
"""

import time

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from plotly.subplots import make_subplots

# ----------------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------------
BASE_URL = "https://api.imf.org/external/sdmx/3.0"
DATA_URL = BASE_URL + "/data/dataflow/IMF.STA/{flow}/+/{key}"
CODELIST_URL = BASE_URL + "/structure/codelist/IMF/CL_COUNTRY/+"
START_PERIOD = pd.Period("1976-01", freq="M")
EURO_AREA = "G163"
HEADERS = {"Accept": "application/json", "User-Agent": "rer-streamlit-app/1.0"}

# Used only if the IMF country list cannot be downloaded
FALLBACK_COUNTRIES = {
    "AUS": "Australia", "BRA": "Brazil", "CAN": "Canada", "CHE": "Switzerland",
    "CHN": "China, People's Republic of", "G163": "Euro Area (EA)",
    "GBR": "United Kingdom", "HKG": "Hong Kong SAR, China", "IND": "India",
    "JPN": "Japan", "KOR": "Korea, Republic of", "MEX": "Mexico",
    "NOR": "Norway", "NZL": "New Zealand", "SGP": "Singapore",
    "SWE": "Sweden", "TWN": "Taiwan Province of China", "USA": "United States",
    "ZAF": "South Africa",
}

st.set_page_config(page_title="Real Exchange Rate Explorer", layout="wide")


# ----------------------------------------------------------------------------
# IMF data helpers
# ----------------------------------------------------------------------------
def fetch_json(url: str, retries: int = 3) -> dict | None:
    """GET a URL and return JSON. Returns None on 404 / no data. Raises on repeated failure."""
    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=60)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"IMF request failed after {retries} tries: {url}\n{last_error}")


def parse_sdmx_series(payload: dict | None) -> pd.Series:
    """Convert an SDMX-JSON 2.0 response with one series into a monthly pandas Series."""
    empty = pd.Series(dtype="float64")
    if not payload:
        return empty
    try:
        data = payload["data"]
        datasets = data.get("dataSets") or []
        if not datasets or not datasets[0].get("series"):
            return empty
        structure = data["structures"][0]
        time_values = structure["dimensions"]["observation"][0]["values"]
        series = next(iter(datasets[0]["series"].values()))
        observations = series.get("observations", {})
    except (KeyError, IndexError, StopIteration, TypeError):
        return empty

    records = {}
    for idx, obs in observations.items():
        try:
            label = time_values[int(idx)].get("value") or time_values[int(idx)].get("id")
            value = obs[0]
            if value is None or value == "" or str(value).upper() == "NAN":
                continue
            period = pd.Period(label.replace("-M", "-"), freq="M")  # "1976-M01" -> 1976-01
            records[period] = float(value)
        except (ValueError, TypeError, IndexError, AttributeError):
            continue

    if not records:
        return empty
    out = pd.Series(records, dtype="float64").sort_index()
    out.index = pd.PeriodIndex(out.index, freq="M")
    return out


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_countries() -> dict:
    """IMF country codelist: 3-letter ISO codes plus the Euro area (G163)."""
    try:
        payload = fetch_json(CODELIST_URL)
        codes = payload["data"]["codelists"][0]["codes"]
        countries = {
            c["id"]: c.get("name", c["id"])
            for c in codes
            if (len(c["id"]) == 3 and c["id"].isalpha()) or c["id"] == EURO_AREA
        }
        countries.setdefault(EURO_AREA, "Euro Area (EA)")
        return countries if len(countries) > 20 else FALLBACK_COUNTRIES
    except Exception:
        return FALLBACK_COUNTRIES


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_cpi(iso3: str) -> tuple[pd.Series, str]:
    """Monthly CPI index. Euro area headline index is published as HICP, so fall back to it."""
    for key in (f"{iso3}.CPI._T.IX.M", f"{iso3}.HICP._T.IX.M"):
        s = parse_sdmx_series(fetch_json(DATA_URL.format(flow="CPI", key=key)))
        if not s.empty:
            return s, key
    return pd.Series(dtype="float64"), ""


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def load_fx(iso3: str) -> tuple[pd.Series, str]:
    """Monthly average exchange rate, local currency units per USD."""
    key = f"{iso3}.XDC_USD.PA_RT.M"
    s = parse_sdmx_series(fetch_json(DATA_URL.format(flow="ER", key=key)))
    if s.empty and iso3 == "USA":
        # USD per USD is 1 by definition
        idx = pd.period_range(START_PERIOD, pd.Timestamp.today().to_period("M"), freq="M")
        s = pd.Series(1.0, index=idx)
    return s, key


def build_panel(c1: str, c2: str) -> tuple[pd.DataFrame, dict]:
    cpi1, k_cpi1 = load_cpi(c1)
    cpi2, k_cpi2 = load_cpi(c2)
    fx1, k_fx1 = load_fx(c1)
    fx2, k_fx2 = load_fx(c2)

    df = pd.DataFrame(
        {
            "FX1_LCU_per_USD": fx1,
            "FX2_LCU_per_USD": fx2,
            "P1_CPI": cpi1,
            "P2_CPI": cpi2,
        }
    )
    df = df[df.index >= START_PERIOD]
    # S(t) = Country 2 currency per 1 unit of Country 1 currency
    df["S"] = df["FX2_LCU_per_USD"] / df["FX1_LCU_per_USD"]
    df["RER"] = df["S"] * df["P1_CPI"] / df["P2_CPI"]

    keys = {"cpi1": k_cpi1, "cpi2": k_cpi2, "fx1": k_fx1, "fx2": k_fx2}
    lengths = {"cpi1": len(cpi1), "cpi2": len(cpi2), "fx1": len(fx1), "fx2": len(fx2)}
    return df, {"keys": keys, "lengths": lengths}


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
st.title("Real Exchange Rate Explorer")
st.caption(
    "Data: IMF SDMX 3.0 API (CPI and ER datasets), monthly, from January 1976 where available. "
    "S(t) = Country 2 currency per 1 unit of Country 1 currency. RER(t) = S(t) × P1(t) / P2(t)."
)

countries = load_countries()
codes_sorted = sorted(countries, key=lambda c: countries[c])
fmt = lambda c: f"{countries.get(c, c)} ({c})"

col1, col2 = st.columns(2)
with col1:
    c1 = st.selectbox(
        "Country 1 (base currency)", codes_sorted,
        index=codes_sorted.index("GBR") if "GBR" in codes_sorted else 0, format_func=fmt,
    )
with col2:
    c2 = st.selectbox(
        "Country 2 (quote currency)", codes_sorted,
        index=codes_sorted.index("USA") if "USA" in codes_sorted else 0, format_func=fmt,
    )

if c1 == c2:
    st.warning("Please choose two different countries.")
    st.stop()

with st.spinner("Downloading IMF data..."):
    try:
        panel, meta = build_panel(c1, c2)
    except RuntimeError as exc:
        st.error(f"Could not download IMF data. Please try again in a minute.\n\n{exc}")
        st.stop()

missing = [name for name, n in meta["lengths"].items() if n == 0]
if missing:
    labels = {
        "cpi1": f"CPI for {fmt(c1)}", "cpi2": f"CPI for {fmt(c2)}",
        "fx1": f"exchange rate for {fmt(c1)}", "fx2": f"exchange rate for {fmt(c2)}",
    }
    st.error("The IMF returned no monthly data for: " + "; ".join(labels[m] for m in missing))
    st.info(
        "Tip: euro area members (for example DEU, FRA) only have national-currency exchange rates "
        "up to December 1998. Choose 'Euro Area (EA)' for the euro period."
    )
    st.stop()

valid = panel.dropna(subset=["S", "P1_CPI", "P2_CPI", "RER"])
valid = valid[(valid["S"] > 0) & (valid["P1_CPI"] > 0) & (valid["P2_CPI"] > 0)]
if valid.empty:
    st.error("No overlapping months with valid exchange-rate and CPI data for both countries.")
    st.stop()

months = [str(p) for p in valid.index]
st.markdown(
    f"**Available overlapping data:** {months[0]} to {months[-1]} "
    f"({len(valid)} valid months). Gaps in IMF data are dropped."
)

start_m, end_m = st.select_slider(
    "Sample period (start and end month)", options=months, value=(months[0], months[-1])
)
start_p, end_p = pd.Period(start_m, freq="M"), pd.Period(end_m, freq="M")
sample = valid[(valid.index >= start_p) & (valid.index <= end_p)].copy()

# RER* recalculated on every change of dates
rer_star = sample["RER"].mean()
sample["RER_star"] = rer_star
sample["Real_Index"] = 100 * sample["RER"] / rer_star

m1, m2, m3 = st.columns(3)
m1.metric("RER* (sample average)", f"{rer_star:,.6f}")
m2.metric("Average Real Index", f"{sample['Real_Index'].mean():.4f}")
m3.metric("Months in sample", f"{len(sample)}")

view = st.radio("Chart", ["Real", "Nominal", "Both"], horizontal=True)

x = sample.index.to_timestamp()
real_name = "Real Index (RER*/100 = sample average)"
nom_name = f"Nominal S: {c2} currency per 1 {c1} currency"

if view == "Real":
    fig = go.Figure(go.Scatter(x=x, y=sample["Real_Index"], name="Real Index", mode="lines"))
    fig.add_hline(y=100, line_dash="dot", line_color="gray")
    fig.update_yaxes(title_text="Real Index (sample average = 100)")
elif view == "Nominal":
    fig = go.Figure(go.Scatter(x=x, y=sample["S"], name="Nominal S", mode="lines",
                               line=dict(color="#d62728")))
    fig.update_yaxes(title_text=nom_name)
else:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=x, y=sample["Real_Index"], name="Real Index", mode="lines"),
                  secondary_y=False)
    fig.add_trace(go.Scatter(x=x, y=sample["S"], name="Nominal S", mode="lines",
                             line=dict(color="#d62728")), secondary_y=True)
    fig.add_hline(y=100, line_dash="dot", line_color="gray", secondary_y=False)
    fig.update_yaxes(title_text="Real Index (sample average = 100)", secondary_y=False)
    fig.update_yaxes(title_text=nom_name, secondary_y=True)

fig.update_layout(
    title=f"{countries.get(c1, c1)} vs {countries.get(c2, c2)}: {start_m} to {end_m}",
    hovermode="x unified", height=520, legend=dict(orientation="h", y=-0.15),
)
fig.update_xaxes(title_text="Month")
st.plotly_chart(fig, width="stretch")

# ----------------------------------------------------------------------------
# Table and CSV
# ----------------------------------------------------------------------------
export = sample.reset_index().rename(columns={"index": "Month"})
export["Month"] = export["Month"].astype(str)
export.insert(1, "Country1", c1)
export.insert(2, "Country2", c2)
export = export.rename(
    columns={
        "FX1_LCU_per_USD": f"FX1_{c1}_LCU_per_USD",
        "FX2_LCU_per_USD": f"FX2_{c2}_LCU_per_USD",
        "S": f"S_{c2}_per_{c1}",
        "P1_CPI": f"P1_CPI_{c1}",
        "P2_CPI": f"P2_CPI_{c2}",
    }
)

st.download_button(
    "Download CSV (selected sample)",
    data=export.to_csv(index=False).encode("utf-8"),
    file_name=f"RER_{c1}_{c2}_{start_m}_{end_m}.csv",
    mime="text/csv",
)

with st.expander("Show data table"):
    st.dataframe(export, width="stretch", hide_index=True)

with st.expander("Manual check of one month"):
    row = sample.iloc[-1]
    st.markdown(
        f"""
**Month {sample.index[-1]}**

- FX1 = {row['FX1_LCU_per_USD']:.6f} {c1} currency per USD
- FX2 = {row['FX2_LCU_per_USD']:.6f} {c2} currency per USD
- S = FX2 / FX1 = {row['S']:.6f} {c2} currency per 1 {c1} currency
- P1 = {row['P1_CPI']:.6f}, P2 = {row['P2_CPI']:.6f}
- RER = S × P1 / P2 = {row['RER']:.6f}
- Real Index = 100 × RER / RER* = 100 × {row['RER']:.6f} / {rer_star:.6f} = {row['Real_Index']:.4f}
"""
    )

with st.expander("IMF series used"):
    st.write(
        {
            f"CPI {c1}": meta["keys"]["cpi1"],
            f"CPI {c2}": meta["keys"]["cpi2"],
            f"FX {c1}": meta["keys"]["fx1"],
            f"FX {c2}": meta["keys"]["fx2"],
        }
    )
    st.caption(
        "IMF exchange rates are local currency per USD (period average). "
        "S is converted as FX2 / FX1. Euro area CPI uses the HICP headline index when CPI is not published."
    )
