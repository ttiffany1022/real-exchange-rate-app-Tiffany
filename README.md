# Real Exchange Rate Explorer

A Streamlit app that downloads monthly CPI and exchange-rate data from the IMF and plots the bilateral real exchange rate between any two IMF countries (or the Euro area).

## Economics

| Symbol | Definition |
|---|---|
| S(t) | Units of Country 2 currency per 1 unit of Country 1 currency |
| P1(t), P2(t) | Monthly CPI of Country 1 and Country 2 |
| RER(t) | S(t) × P1(t) / P2(t) |
| RER* | Average of RER(t) over valid months in the selected sample |
| Real Index(t) | 100 × RER(t) / RER* |

IMF exchange rates are local currency units per USD, so the app converts them with

S(t) = FX2(t) / FX1(t)

where FX1 and FX2 are Country 1 and Country 2 currency per USD. Example: Country 1 = United Kingdom, Country 2 = United States gives S in USD per GBP.

RER* is recalculated every time the sample dates change, so the Real Index always averages 100 in the selected sample. Nominal S is plotted in actual currency units, not normalized.

## Features

- Choose Country 1 and Country 2 from the IMF country list, including the Euro area (G163)
- Monthly data from January 1976 where available
- Start and end month selector
- Real, Nominal, or Both chart views (Both uses two y-axes)
- CSV download of every observation and calculation in the selected sample
- Built-in manual check of one month's RER calculation

## Data source

IMF SDMX 3.0 API: `https://api.imf.org/external/sdmx/3.0`

| Series | Key |
|---|---|
| CPI | `{ISO3}.CPI._T.IX.M` (dataset CPI). Euro area falls back to `G163.HICP._T.IX.M` |
| Exchange rate | `{ISO3}.XDC_USD.PA_RT.M` (dataset ER), period average, local currency per USD |

No API key is required. Results are cached for 24 hours.

## Data notes

- IMF coverage varies by country. Months missing any of the four inputs are dropped.
- Euro area members such as Germany or France only have national-currency exchange rates up to December 1998. Use Euro Area (EA) for the euro period.
- Euro area exchange rate data begin in 1999, so Euro area samples start then.
- Live IMF downloads can occasionally fail. If so, wait a minute and reload.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Put `app.py`, `requirements.txt` and `README.md` at the top level of the GitHub repository.
2. At share.streamlit.io choose Create app, select the repository, branch `main`, file `app.py`.
3. In Advanced settings choose Python 3.12, leave Secrets empty, then Deploy.

## Files

- `app.py` Streamlit application
- `requirements.txt` Python dependencies (Python 3.12)
- `README.md` this file
