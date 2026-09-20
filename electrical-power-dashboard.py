"""
app.py - Electrical Power Monitoring Dashboard (Streamlit)
ดึงข้อมูลจาก Google Sheet "Electrical power check" (แท็บรายเดือน yyyy-MM)
แล้วแสดงกราฟ Voltage / Current / Power / Energy บนเว็บ

รันในเครื่อง:  streamlit run app.py
"""

import io
from datetime import datetime
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dateutil.relativedelta import relativedelta
from plotly.subplots import make_subplots

# ===================== แก้ค่าตรงนี้ =====================
SPREADSHEET_ID = "1tQpqS3BGkWxzOiRel8xqEu_O1A9Ej7KOjnSNmGUur60"  # เฉพาะ ID ไม่ใช่ URL เต็ม
START_MONTH = "2026-09"  # เดือนแรกที่เริ่มเก็บข้อมูล (yyyy-MM)
# =========================================================

st.set_page_config(page_title="Electrical Power Dashboard", layout="wide")


def get_month_list(start_month: str):
    cursor = datetime.strptime(start_month, "%Y-%m")
    now = datetime.now()
    months = []
    while cursor <= now:
        months.append(cursor.strftime("%Y-%m"))
        cursor += relativedelta(months=1)
    return months


def fetch_sheet(spreadsheet_id: str, sheet_name: str):
    url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        f"/gviz/tq?tqx=out:csv&sheet={quote(sheet_name)}"
    )
    try:
        r = requests.get(url, timeout=15)
    except requests.RequestException:
        return None
    if r.status_code != 200 or "html" in r.headers.get("Content-Type", ""):
        return None
    try:
        df = pd.read_csv(io.StringIO(r.text))
    except Exception:
        return None
    if df.empty or "Timestamp" not in df.columns:
        return None
    return df


@st.cache_data(ttl=300, show_spinner="กำลังดึงข้อมูลจาก Google Sheet...")
def load_data(spreadsheet_id: str, start_month: str):
    frames, loaded, skipped = [], [], []
    for month in get_month_list(start_month):
        df = fetch_sheet(spreadsheet_id, month)
        if df is None:
            skipped.append(month)
        else:
            frames.append(df)
            loaded.append(f"{month} ({len(df)} แถว)")
    if not frames:
        return None, loaded, skipped
    data = pd.concat(frames, ignore_index=True)
    data["Timestamp"] = pd.to_datetime(data["Timestamp"], dayfirst=True, errors="coerce")
    data = data.dropna(subset=["Timestamp"]).sort_values("Timestamp")
    return data, loaded, skipped


def build_figure(data: pd.DataFrame):
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        subplot_titles=(
            "แรงดันไฟฟ้า (Voltage, V)",
            "กระแสไฟฟ้า (Current, A)",
            "กำลังไฟฟ้า (Power, W)",
            "พลังงานไฟฟ้าสะสม (Energy, kWh)",
        ),
    )
    specs = [
        ("Voltage(V)", "Voltage (V)", "#3B82F6", None),
        ("Current(A)", "Current (A)", "#F59E0B", None),
        ("Power(W)", "Power (W)", "#EF4444", None),
        ("Energy (kWh)", "Energy (kWh)", "#10B981", "tozeroy"),
    ]
    for i, (col, name, color, fill) in enumerate(specs, start=1):
        if col in data.columns:
            fig.add_trace(
                go.Scatter(x=data["Timestamp"], y=data[col], name=name,
                           line=dict(color=color), fill=fill),
                row=i, col=1,
            )
    fig.update_layout(height=1000, showlegend=False, hovermode="x unified",
                      margin=dict(t=60, b=20))
    fig.update_xaxes(rangeslider_visible=True, row=4, col=1)
    return fig


st.title("Electrical Power Monitoring Dashboard")

data, loaded, skipped = load_data(SPREADSHEET_ID, START_MONTH)

with st.sidebar:
    st.header("ตั้งค่า")
    if st.button("รีเฟรชข้อมูล"):
        st.cache_data.clear()
        st.rerun()
    st.caption("ข้อมูลอัปเดตอัตโนมัติทุก 5 นาที")
    st.write("**เดือนที่ดึงได้:**", ", ".join(loaded) if loaded else "-")
    if skipped:
        st.write("**เดือนที่ข้าม:**", ", ".join(skipped))

if data is None or data.empty:
    st.error(
        "ไม่พบข้อมูล ตรวจสอบว่า SPREADSHEET_ID ถูกต้อง, ชื่อแท็บเป็น yyyy-MM "
        "และตั้งค่าแชร์เป็น 'Anyone with the link – Viewer'"
    )
    st.stop()

# ตัวกรองช่วงวันที่
min_d, max_d = data["Timestamp"].min().date(), data["Timestamp"].max().date()
with st.sidebar:
    date_range = st.date_input("ช่วงวันที่", (min_d, max_d), min_value=min_d, max_value=max_d)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start, end = date_range
    mask = (data["Timestamp"].dt.date >= start) & (data["Timestamp"].dt.date <= end)
    data = data[mask]

# ตัวเลขสรุป
latest = data.iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Voltage (V)", f"{latest.get('Voltage(V)', float('nan')):.1f}")
c2.metric("Current (A)", f"{latest.get('Current(A)', float('nan')):.3f}")
c3.metric("Power (W)", f"{latest.get('Power(W)', float('nan')):.1f}")
c4.metric("Energy (kWh)", f"{latest.get('Energy (kWh)', float('nan')):.3f}")
st.caption(f"ค่าล่าสุด ณ {latest['Timestamp']:%d/%m/%Y %H:%M:%S} — รวม {len(data):,} แถว")

st.plotly_chart(build_figure(data), use_container_width=True)

with st.expander("ดูตารางข้อมูล"):
    st.dataframe(data, use_container_width=True)
