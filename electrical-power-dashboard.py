"""
electrical-power-dashboard.py - Electrical Power Monitor (Streamlit, mobile-first)
ดึงข้อมูลจาก Google Sheet "Electrical power check" (แท็บรายเดือน yyyy-MM)
แสดงผลแบบกระชับสำหรับมือถือ: การ์ดค่าล่าสุด + แท็บกราฟ

รันในเครื่อง:  streamlit run electrical-power-dashboard.py
"""

import io
import time
from datetime import datetime, timedelta, timezone
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

RANGES = ["1 ชม.", "วันนี้", "7 วัน", "30 วัน", "เลือกวันที่", "ทั้งหมด"]

st.set_page_config(
    page_title="Power Monitor",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
.block-container{padding:4rem 1rem 3rem;max-width:720px;}
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
@media (max-width:480px){
.block-container{padding:3.6rem .8rem 2.5rem;}
.ttl{font-size:1.6rem;}
.sub{font-size:.9rem;}
.grid{gap:10px;}
.card{padding:12px 14px;}
.card .lbl{font-size:.9rem;}
.card .val{font-size:2.1rem;}
.card .val small{font-size:1rem;}
.mini{padding:10px 4px;}
.mini .lbl{font-size:.8rem;}
.mini .val{font-size:1.05rem;white-space:nowrap;}
div[data-testid="stRadio"] div[role="radiogroup"]{display:grid !important;grid-template-columns:repeat(3,1fr);gap:8px 6px;}
div[data-testid="stRadio"] label p{font-size:1.05rem;}
div[data-testid="stTabs"] button{padding:8px 8px;}
div[data-testid="stTabs"] button p{font-size:1.02rem;}
div[data-testid="stHorizontalBlock"]:has(.hdr) button{padding:.4rem .9rem;font-size:1.2rem;}
}
</style>
""",
    unsafe_allow_html=True,
)


# ----------------------------- ดึงข้อมูล -----------------------------
TH_TZ = timezone(timedelta(hours=7))


def now_th():
    return datetime.now(TH_TZ).replace(tzinfo=None)


def get_month_list(start_month: str):
    cursor = datetime.strptime(start_month, "%Y-%m")
    now = now_th()
    months = []
    while cursor <= now:
        months.append(cursor.strftime("%Y-%m"))
        cursor += relativedelta(months=1)
    return months


def fetch_sheet(spreadsheet_id: str, sheet_name: str):
    url = (
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        f"/gviz/tq?tqx=out:csv&sheet={quote(sheet_name)}&_={int(time.time())}"
    )
    try:
        r = requests.get(url, timeout=15, headers={"Cache-Control": "no-cache"})
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


@st.cache_data(ttl=120, show_spinner=False)
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
        return None, loaded, skipped, now_th()
    data = pd.concat(frames, ignore_index=True)
    data["Timestamp"] = pd.to_datetime(data["Timestamp"], dayfirst=True, errors="coerce")
    for col, *_ in METRICS:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["Timestamp"]).sort_values("Timestamp")
    data = data.drop_duplicates(subset="Timestamp")  # กันข้อมูลซ้ำข้ามแท็บ
    return data, loaded, skipped, now_th()


# ----------------------------- ตัวช่วยแสดงผล -----------------------------
def fmt(value, decimals):
    return "-" if pd.isna(value) else f"{value:,.{decimals}f}"


def hex_to_rgba(hex_color: str, alpha: float):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def filter_range(data: pd.DataFrame, choice: str, custom=None):
    latest = data["Timestamp"].max()
    if choice == "1 ชม.":
        out = data[data["Timestamp"] >= latest - timedelta(hours=1)]
    elif choice == "วันนี้":
        out = data[data["Timestamp"].dt.date == latest.date()]
    elif choice == "7 วัน":
        out = data[data["Timestamp"] >= latest - timedelta(days=7)]
    elif choice == "30 วัน":
        out = data[data["Timestamp"] >= latest - timedelta(days=30)]
    elif choice == "เลือกวันที่" and custom:
        d = data["Timestamp"].dt.date
        out = data[(d >= custom[0]) & (d <= custom[1])]
    else:
        out = data
    return out if not out.empty else data


def downsample(df: pd.DataFrame, max_points: int = 500):
    """ถ้าจุดข้อมูลเยอะเกิน ให้เฉลี่ยเป็นช่วงเวลา (พลังงานสะสมใช้ค่าท้ายช่วง)
    คืนค่า (dataframe, นาทีต่อจุด หรือ None ถ้าไม่ได้ย่อ)"""
    if len(df) <= max_points:
        return df, None
    span = df["Timestamp"].max() - df["Timestamp"].min()
    minutes = max(1, int(span.total_seconds() / 60 / max_points) + 1)
    cols = [c for c, *_ in METRICS if c in df.columns]
    grouped = df.set_index("Timestamp")[cols].resample(f"{minutes}min")
    out = grouped.mean()
    if "Energy (kWh)" in cols:
        out["Energy (kWh)"] = grouped["Energy (kWh)"].last()
    return out.dropna(how="all").reset_index(), minutes


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
        height=340,
        margin=dict(l=4, r=8, t=8, b=8),
        showlegend=False,
        hovermode="x",
        dragmode=False,  # ไม่ให้นิ้วลากซูมกราฟ เลื่อนหน้าจอได้ปกติ
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=13),
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
        st.session_state["just_refreshed"] = True
        st.rerun()

@st.fragment(run_every=300)  # รีรันส่วนนี้อัตโนมัติทุก 5 นาที (300 วินาที)
def dashboard():
    data, loaded, skipped, fetched_at = load_data(SPREADSHEET_ID, START_MONTH)

    if data is None or data.empty:
        st.error(
            "ไม่พบข้อมูล ตรวจสอบว่า SPREADSHEET_ID ถูกต้อง, ชื่อแท็บเป็น yyyy-MM "
            "และตั้งค่าแชร์เป็น 'Anyone with the link – Viewer'"
        )
        return

    latest = data.iloc[-1]
    if st.session_state.pop("just_refreshed", False):
        st.toast(f"รีเฟรชแล้ว · ข้อมูลล่าสุด {latest['Timestamp']:%H:%M:%S}", icon="✅")
    st.markdown(
        f'<p class="sub">ข้อมูลล่าสุด {latest["Timestamp"]:%d/%m %H:%M:%S}'
        f' · โหลด {fetched_at:%H:%M:%S}</p>',
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
    custom = None
    if choice == "เลือกวันที่":
        d_min, d_max = data["Timestamp"].min().date(), data["Timestamp"].max().date()
        picked = st.date_input(
            "เลือกช่วงวันที่", (d_min, d_max), min_value=d_min, max_value=d_max,
            format="DD/MM/YYYY",
        )
        if isinstance(picked, (tuple, list)) and len(picked) == 2:
            custom = (picked[0], picked[1])
        else:
            st.caption("เลือกวันสิ้นสุดอีกหนึ่งวัน")
    view = filter_range(data, choice, custom)
    plot_df, step_min = downsample(view)
    if step_min:
        st.caption(
            f"ช่วงนี้มี {len(view):,} จุด กราฟแสดงค่าเฉลี่ยทุก {step_min} นาทีเพื่อความลื่น "
            "ส่วนค่าต่ำสุด/เฉลี่ย/สูงสุดคำนวณจากข้อมูลจริงทั้งหมด"
        )

    # แท็บกราฟ (1 แท็บ = 1 กราฟ)
    tabs = st.tabs([m[2] for m in METRICS])
    for tab, (col, _label, _tab, unit, color, dec) in zip(tabs, METRICS):
        with tab:
            if col not in view.columns or view[col].dropna().empty:
                st.info("ไม่มีข้อมูลในช่วงนี้")
                continue
            is_energy = col == "Energy (kWh)"
            st.plotly_chart(
                make_chart(plot_df, col, color, unit, dec, fill=is_energy),
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
        st.caption("รีเฟรชอัตโนมัติทุก 5 นาที (ขณะเปิดหน้านี้ค้างไว้)")
        st.write("**เดือนที่ดึงได้:**", ", ".join(loaded) if loaded else "-")
        if skipped:
            st.write("**เดือนที่ข้าม:**", ", ".join(skipped))
        if len(view) > 500:
            st.caption(f"แสดง 500 แถวล่าสุด จากทั้งหมด {len(view):,} แถวในช่วงนี้")
        st.dataframe(
            view.sort_values("Timestamp", ascending=False).head(500),
            width="stretch", hide_index=True,
        )


dashboard()
