"""
electrical-power-dashboard.py - Electrical Power Monitor (Streamlit, mobile-first)
ดึงข้อมูลจาก Google Sheet "Electrical power check" (แท็บรายเดือน yyyy-MM)
แสดงผลแบบกระชับสำหรับมือถือ: การ์ดค่าล่าสุด + แท็บกราฟ

รันในเครื่อง:  streamlit run electrical-power-dashboard.py
"""

import io
from datetime import datetime, timedelta
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dateutil.relativedelta import relativedelta

# ===================== แก้ค่าตรงนี้ =====================
SPREADSHEET_ID = "1tQpqS3BGkWxzOiRel8xqEu_O1A9Ej7KOjnSNmGUur60"  # เฉพาะ ID ไม่ใช่ URL เต็ม
START_MONTH = "2026-09"  # เดือนแรกที่เริ่มเก็บข้อมูล (yyyy-MM)
# =========================================================

# (คอลัมน์ในชีต, ชื่อการ์ด, ชื่อแท็บ, หน่วย, สี, ทศนิยม)
METRICS = [
    ("Voltage(V)", "แรงดัน", "⚡ แรงดัน", "V", "#3B82F6", 1),
    ("Current(A)", "กระแส", "🔌 กระแส", "A", "#F59E0B", 2),
    ("Power(W)", "กำลังไฟ", "🔥 กำลัง", "W", "#EF4444", 1),
    ("Energy (kWh)", "พลังงานสะสม", "🔋 พลังงาน", "kWh", "#10B981", 3),
]

RANGES = ["1 ชม.", "วันนี้", "7 วัน", "ทั้งหมด"]

st.set_page_config(
    page_title="Power Monitor",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
.block-container{padding:1.2rem 1rem 3rem;max-width:720px;}
header[data-testid="stHeader"]{background:transparent;}
#MainMenu, footer{visibility:hidden;}
.ttl{font-size:1.35rem;font-weight:700;margin:0;}
.sub{font-size:.78rem;opacity:.65;margin:2px 0 12px;}
.grid{display:grid;gap:10px;margin-bottom:10px;}
.g2{grid-template-columns:1fr 1fr;}
.g3{grid-template-columns:1fr 1fr 1fr;}
.card{background:rgba(128,128,128,.10);border-radius:14px;padding:10px 14px;border-left:4px solid var(--c);}
.card .lbl{font-size:.72rem;opacity:.7;}
.card .val{font-size:1.65rem;font-weight:700;line-height:1.25;}
.card .val small{font-size:.8rem;font-weight:500;opacity:.7;margin-left:3px;}
.mini{background:rgba(128,128,128,.08);border-radius:12px;padding:8px 10px;text-align:center;}
.mini .lbl{font-size:.68rem;opacity:.65;}
.mini .val{font-size:1rem;font-weight:600;}
div[data-testid="stTabs"] button{padding:6px 10px;}
div[data-testid="stHorizontalBlock"]:has(.hdr){flex-wrap:nowrap !important;align-items:center;gap:.5rem;margin-bottom:2px;}
div[data-testid="stHorizontalBlock"]:has(.hdr) > div{min-width:0 !important;}
div[data-testid="stHorizontalBlock"]:has(.hdr) > div:first-child{flex:1 1 auto !important;width:auto !important;}
div[data-testid="stHorizontalBlock"]:has(.hdr) > div:last-child{flex:0 0 auto !important;width:auto !important;}
div[data-testid="stHorizontalBlock"]:has(.hdr) button{padding:.2rem .7rem;min-height:0;}
</style>
""",
    unsafe_allow_html=True,
)


# ----------------------------- ดึงข้อมูล -----------------------------
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


@st.cache_data(ttl=300, show_spinner="กำลังโหลดข้อมูล...")
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
    for col, *_ in METRICS:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["Timestamp"]).sort_values("Timestamp")
    return data, loaded, skipped


# ----------------------------- ตัวช่วยแสดงผล -----------------------------
def fmt(value, decimals):
    return "-" if pd.isna(value) else f"{value:,.{decimals}f}"


def hex_to_rgba(hex_color: str, alpha: float):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def filter_range(data: pd.DataFrame, choice: str):
    latest = data["Timestamp"].max()
    if choice == "1 ชม.":
        out = data[data["Timestamp"] >= latest - timedelta(hours=1)]
    elif choice == "วันนี้":
        out = data[data["Timestamp"].dt.date == latest.date()]
    elif choice == "7 วัน":
        out = data[data["Timestamp"] >= latest - timedelta(days=7)]
    else:
        out = data
    return out if not out.empty else data


def make_chart(df, col, color, unit, decimals, fill=False):
    y = df[col]
    span = df["Timestamp"].max() - df["Timestamp"].min()
    tick_fmt = "%H:%M" if span <= timedelta(days=2) else "%d/%m"

    fig = go.Figure(
        go.Scatter(
            x=df["Timestamp"], y=y, mode="lines",
            line=dict(color=color, width=2.5),
            fill="tozeroy" if fill else None,
            fillcolor=hex_to_rgba(color, 0.25) if fill else None,
            hovertemplate=f"%{{y:.{decimals}f}} {unit}<br>%{{x|%d/%m %H:%M}}<extra></extra>",
        )
    )
    if fill:
        yrange = [0, max(y.max() * 1.05, 0.001)]
    else:
        pad = (y.max() - y.min()) * 0.2 or max(abs(y.max()) * 0.02, 0.1)
        yrange = [y.min() - pad, y.max() + pad]

    fig.update_layout(
        height=300,
        margin=dict(l=4, r=8, t=8, b=8),
        showlegend=False,
        hovermode="x",
        dragmode=False,  # ไม่ให้นิ้วลากซูมกราฟ เลื่อนหน้าจอได้ปกติ
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=11),
    )
    fig.update_xaxes(showgrid=False, tickformat=tick_fmt, nticks=5, fixedrange=True)
    fig.update_yaxes(
        range=yrange, gridcolor="rgba(128,128,128,0.2)", zeroline=False,
        automargin=True, fixedrange=True,
    )
    return fig


def mini_cards(items):
    cells = "".join(
        f'<div class="mini"><div class="lbl">{label}</div><div class="val">{value}</div></div>'
        for label, value in items
    )
    return f'<div class="grid g3">{cells}</div>'


# ----------------------------- หน้าจอหลัก -----------------------------
h_left, h_right = st.columns([5, 1], vertical_alignment="center")
with h_left:
    st.markdown('<span class="hdr"></span><p class="ttl">⚡ Power Monitor</p>', unsafe_allow_html=True)
with h_right:
    if st.button("🔄", key="refresh", help="รีเฟรชข้อมูล"):
        st.cache_data.clear()
        st.rerun()

data, loaded, skipped = load_data(SPREADSHEET_ID, START_MONTH)

if data is None or data.empty:
    st.error(
        "ไม่พบข้อมูล ตรวจสอบว่า SPREADSHEET_ID ถูกต้อง, ชื่อแท็บเป็น yyyy-MM "
        "และตั้งค่าแชร์เป็น 'Anyone with the link – Viewer'"
    )
    st.stop()

latest = data.iloc[-1]
st.markdown(
    f'<p class="sub">อัปเดตล่าสุด {latest["Timestamp"]:%d/%m/%Y %H:%M:%S}</p>',
    unsafe_allow_html=True,
)

# การ์ดค่าล่าสุด 2x2
cards = ""
for col, label, _tab, unit, color, dec in METRICS:
    v = latest[col] if col in data.columns else float("nan")
    cards += (
        f'<div class="card" style="--c:{color}"><div class="lbl">{label}</div>'
        f'<div class="val">{fmt(v, dec)}<small>{unit}</small></div></div>'
    )
st.markdown(f'<div class="grid g2">{cards}</div>', unsafe_allow_html=True)

# เลือกช่วงเวลา
choice = st.radio("ช่วงเวลา", RANGES, index=1, horizontal=True, label_visibility="collapsed")
view = filter_range(data, choice)

# แท็บกราฟ (1 แท็บ = 1 กราฟ)
tabs = st.tabs([m[2] for m in METRICS])
for tab, (col, _label, _tab, unit, color, dec) in zip(tabs, METRICS):
    with tab:
        if col not in view.columns or view[col].dropna().empty:
            st.info("ไม่มีข้อมูลในช่วงนี้")
            continue
        is_energy = col == "Energy (kWh)"
        st.plotly_chart(
            make_chart(view, col, color, unit, dec, fill=is_energy),
            width="stretch",
            config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False},
        )
        s = view[col].dropna()
        if is_energy:
            items = [
                ("เริ่มช่วงนี้", f"{fmt(s.iloc[0], dec)} {unit}"),
                ("ล่าสุด", f"{fmt(s.iloc[-1], dec)} {unit}"),
                ("ใช้ไป", f"+{fmt(s.iloc[-1] - s.iloc[0], dec)} {unit}"),
            ]
        else:
            items = [
                ("ต่ำสุด", f"{fmt(s.min(), dec)} {unit}"),
                ("เฉลี่ย", f"{fmt(s.mean(), dec)} {unit}"),
                ("สูงสุด", f"{fmt(s.max(), dec)} {unit}"),
            ]
        st.markdown(mini_cards(items), unsafe_allow_html=True)

# ส่วนเพิ่มเติม
with st.expander("เพิ่มเติม"):
    st.caption("ข้อมูลอัปเดตอัตโนมัติทุก 5 นาที")
    st.write("**เดือนที่ดึงได้:**", ", ".join(loaded) if loaded else "-")
    if skipped:
        st.write("**เดือนที่ข้าม:**", ", ".join(skipped))
    st.dataframe(view.sort_values("Timestamp", ascending=False), width="stretch")
