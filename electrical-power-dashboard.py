"""
electrical-power-dashboard.py - Electrical Power Monitor (Streamlit, mobile-first)
ดึงข้อมูลจาก Google Sheet "Electrical power check" (แท็บรายเดือน yyyy-MM)
แสดงผลแบบกระชับสำหรับมือถือ: การ์ดค่าล่าสุด + แท็บกราฟ

รันในเครื่อง:  streamlit run electrical-power-dashboard.py
"""

import io
import time
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from dateutil.relativedelta import relativedelta

# ===================== แก้ค่าตรงนี้ =====================
SPREADSHEET_ID = "1tQpqS3BGkWxzOiRel8xqEu_O1A9Ej7KOjnSNmGUur60"  # เฉพาะ ID ไม่ใช่ URL เต็ม
START_MONTH = "2026-09"  # เดือนแรกที่เริ่มเก็บข้อมูล (yyyy-MM)
DEFAULT_RATE = 4.52      # ค่าไฟ บาท/หน่วย ไม่รวม VAT (4.3583 + Ft 0.1623 ตามบิล 10/2569) ปรับได้ในแท็บ "ค่าไฟ"
DEFAULT_VAT = 7.0        # VAT % (ใส่ 0 ถ้าไม่ต้องการรวม)
COST_COL = "Cost (฿)"
COST_COLOR = "#F59E0B"
# --- ปรับหน้าตาเส้นกราฟ ---
AVG_LINE_WIDTH = 1.5     # ความหนาเส้นหลักของทุกกราฟ (แรงดัน กระแส กำลัง พลังงาน ค่าไฟ)
PEAK_LINE_WIDTH = 1.0    # ความหนาเส้นพีค (เฉพาะกราฟกระแสและกำลัง)
PEAK_DOT_SIZE = 2.0      # ขนาดจุดบนเส้นพีค (แสดงเมื่อมีข้อมูลพีคไม่เกิน 40 จุด ตั้ง 0 = ไม่มีจุด)
# =========================================================

# (คอลัมน์ในชีต, ชื่อการ์ด, ชื่อแท็บ, หน่วย, สี, ทศนิยม)
METRICS = [
    ("Voltage(V)", "แรงดัน", "⚡ แรงดัน", "V", "#3B82F6", 1),
    ("Current(A)", "กระแส", "🔌 กระแส", "A", "#F59E0B", 2),
    ("Power(W)", "กำลังไฟ", "🔥 กำลัง", "W", "#EF4444", 1),
    ("Energy (kWh)", "พลังงานสะสม", "🔋 พลังงาน", "kWh", "#10B981", 3),
]

# คอลัมน์ "ค่าสูงสุดต่อรอบ" ที่ ESP ส่งมาพร้อมค่าเฉลี่ย (แถวเก่าที่ไม่มีจะเว้นว่าง)
PEAK_COLS = {"Current(A)": "Peak Current(A)", "Power(W)": "Peak Power(W)"}

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
.card{background:rgba(128,128,128,.10);border-radius:14px;padding:10px 14px;border-left:4px solid var(--c);display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;column-gap:8px;}
.card .pk{margin-left:auto;text-align:right;line-height:1.2;padding-bottom:4px;}
.card .pk .pl{font-size:.68rem;opacity:.7;}
.card .pk .pv{font-size:.95rem;font-weight:600;color:var(--pc);white-space:nowrap;}
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
.card .pk .pl{font-size:.8rem;}
.card .pk .pv{font-size:1.05rem;}
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
    for col in [m[0] for m in METRICS] + list(PEAK_COLS.values()):
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


def lighten(hex_color: str, amount: float = 0.45):
    """ผสมสีกับสีขาว ให้เส้นพีคสว่างและแยกจากเส้นค่าเฉลี่ยได้ชัดบนพื้นมืด"""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    r, g, b = (round(c + (255 - c) * amount) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def filter_range(data: pd.DataFrame, choice: str, custom=None, start_hour=0, end_hour=24):
    """คืนค่า (ข้อมูลในช่วงที่เลือก, True ถ้าช่วงที่เลือกไม่มีข้อมูลจึงใช้ข้อมูลทั้งหมดแทน)
    วันนี้: เริ่มที่ start_hour ของวันที่ตรงกับข้อมูลล่าสุด จนถึงข้อมูลล่าสุด
    เลือกวันที่: เริ่ม start_hour ของวันเริ่มต้น จนถึง end_hour ของวันสิ้นสุด (24 = สิ้นวัน)"""
    latest = data["Timestamp"].max()
    ts = data["Timestamp"]
    if choice == "1 ชม.":
        out = data[data["Timestamp"] >= latest - timedelta(hours=1)]
    elif choice == "วันนี้":
        start = datetime.combine(latest.date(), dtime(start_hour))
        out = data[(ts >= start) & (ts.dt.date == latest.date())]
    elif choice == "7 วัน":
        out = data[data["Timestamp"] >= latest - timedelta(days=7)]
    elif choice == "30 วัน":
        out = data[data["Timestamp"] >= latest - timedelta(days=30)]
    elif choice == "เลือกวันที่" and custom:
        start = datetime.combine(custom[0], dtime(start_hour))
        end = datetime.combine(custom[1], dtime(0)) + timedelta(hours=end_hour)
        out = data[(ts >= start) & (ts < end)]
    else:
        out = data
    if out.empty:
        return data, True
    return out, False


def add_cost(df: pd.DataFrame, rate: float, vat_pct: float):
    """หน่วยที่ใช้ + ค่าไฟสะสมนับจากต้นช่วงที่เลือก
    ใช้ส่วนต่างของ Energy และตัดค่าติดลบทิ้ง (กรณี PZEM ถูกรีเซ็ตค่า)"""
    if "Energy (kWh)" not in df.columns:
        return df
    out = df.copy()
    out["kWh_used"] = out["Energy (kWh)"].diff().clip(lower=0).fillna(0)
    out[COST_COL] = out["kWh_used"].cumsum() * rate * (1 + vat_pct / 100)
    return out


def downsample(df: pd.DataFrame, max_points: int = 500):
    """ถ้าจุดข้อมูลเยอะเกิน ให้เฉลี่ยเป็นช่วงเวลา (พลังงานสะสมใช้ค่าท้ายช่วง)
    คืนค่า (dataframe, นาทีต่อจุด หรือ None ถ้าไม่ได้ย่อ)"""
    if len(df) <= max_points:
        return df, None
    span = df["Timestamp"].max() - df["Timestamp"].min()
    minutes = max(1, int(span.total_seconds() / 60 / max_points) + 1)
    cols = [c for c, *_ in METRICS if c in df.columns]
    if COST_COL in df.columns:
        cols.append(COST_COL)
    peak_cols = [p for p in PEAK_COLS.values() if p in df.columns]
    grouped = df.set_index("Timestamp")[cols + peak_cols].resample(f"{minutes}min")
    out = grouped.mean()
    for p in peak_cols:  # ค่าพีคใช้ค่าสูงสุดของช่วง ไม่ใช่ค่าเฉลี่ย
        out[p] = grouped[p].max()
    for cum_col in ("Energy (kWh)", COST_COL):  # ค่าสะสมใช้ค่าท้ายช่วง
        if cum_col in cols:
            out[cum_col] = grouped[cum_col].last()
    return out.dropna(how="all").reset_index(), minutes


def make_chart(df, col, color, unit, decimals, fill=False, peak_col=None):
    y = df[col]
    span = df["Timestamp"].max() - df["Timestamp"].min()
    tick_fmt = "%H:%M" if span <= timedelta(days=2) else "%d/%m"

    fig = go.Figure(
        go.Scatter(
            x=df["Timestamp"], y=y, mode="lines",
            line=dict(color=color, width=AVG_LINE_WIDTH),
            fill="tozeroy" if fill else None,
            fillcolor=hex_to_rgba(color, 0.25) if fill else None,
            hovertemplate=f"%{{y:.{decimals}f}} {unit}<br>%{{x|%d/%m %H:%M}}<extra></extra>",
        )
    )
    has_peak = peak_col is not None and peak_col in df.columns and df[peak_col].notna().any()
    if has_peak:  # เส้นสีอ่อน = ค่าสูงสุดในแต่ละรอบ
        peak_color = lighten(color)
        few = int(df[peak_col].notna().sum()) <= 40  # ข้อมูลน้อย ใส่จุดกลมให้เห็นชัด
        fig.add_trace(
            go.Scatter(
                x=df["Timestamp"], y=df[peak_col],
                mode="lines+markers" if few else "lines",
                line=dict(color=peak_color, width=PEAK_LINE_WIDTH),
                marker=dict(size=PEAK_DOT_SIZE, color=peak_color),
                hovertemplate=f"พีค %{{y:.{decimals}f}} {unit}<br>%{{x|%d/%m %H:%M}}<extra></extra>",
            )
        )
    if has_peak:  # วาดเส้นพีคก่อน ให้เส้นค่าเฉลี่ยอยู่ด้านบนและไม่ถูกบัง
        fig.data = (fig.data[1], fig.data[0])
    top = max(y.max(), df[peak_col].max()) if has_peak else y.max()
    if fill:
        yrange = [0, max(top * 1.05, 0.001)]
    else:
        pad = (top - y.min()) * 0.2 or max(abs(top) * 0.02, 0.1)
        yrange = [y.min() - pad, top + pad]

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


# ----------------------------- จำค่าที่เลือกไว้ -----------------------------
# เก็บใน session_state (ไม่หายตอนสลับตัวเลือก/รีเฟรชอัตโนมัติ) และเขียนลง URL ด้วย
# เพื่อให้เบราว์เซอร์จำค่าไว้เมื่อโหลดหน้าซ้ำ (เช่น สลับแอปไปมาแล้วหน้าถูกโหลดใหม่)
def init_saved():
    if "saved" in st.session_state:
        return
    qp = st.query_params

    def to_int(key, lo, hi, default):
        try:
            v = int(qp.get(key))
            return v if lo <= v <= hi else default
        except (TypeError, ValueError):
            return default

    saved = {
        "range": RANGES[to_int("r", 0, len(RANGES) - 1, 1)],
        "today_start": to_int("ts", 0, 23, 0),
        "custom_start": to_int("cs", 0, 23, 0),
        "custom_end": to_int("ce", 1, 24, 24),
        "d1": None,
        "d2": None,
    }
    try:
        saved["d1"] = datetime.strptime(qp.get("d1"), "%Y-%m-%d").date()
        saved["d2"] = datetime.strptime(qp.get("d2"), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        saved["d1"] = saved["d2"] = None
    st.session_state["saved"] = saved


def sync_query_params():
    sv = st.session_state["saved"]
    params = {
        "r": str(RANGES.index(sv["range"])),
        "ts": str(sv["today_start"]),
        "cs": str(sv["custom_start"]),
        "ce": str(sv["custom_end"]),
    }
    if sv["d1"] and sv["d2"]:
        params["d1"], params["d2"] = sv["d1"].isoformat(), sv["d2"].isoformat()
    st.query_params.update(params)


def remember(name, widget_key):
    st.session_state["saved"][name] = st.session_state[widget_key]
    sync_query_params()


def remember_dates():
    v = st.session_state.get("w_dates")
    if isinstance(v, (tuple, list)) and len(v) == 2:  # เลือกครบทั้งวันเริ่มและวันสิ้นสุดแล้ว
        st.session_state["saved"]["d1"], st.session_state["saved"]["d2"] = v
        sync_query_params()


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
        peak_html = ""
        pcol = PEAK_COLS.get(col)
        if pcol and pcol in data.columns and pd.notna(latest[pcol]):  # ค่าพีคของรอบล่าสุด
            peak_html = (
                f'<div class="pk" title="ค่าสูงสุดในรอบ 5 นาทีล่าสุด">'
                f'<div class="pl">พีค</div>'
                f'<div class="pv">{fmt(latest[pcol], dec)} {unit}</div></div>'
            )
        cards += (
            f'<div class="card" style="--c:{color};--pc:{lighten(color)}">'
            f'<div class="cl"><div class="lbl">{label}</div>'
            f'<div class="val">{fmt(v, dec)}<small>{unit}</small></div></div>{peak_html}</div>'
        )
    st.markdown(f'<div class="grid g2">{cards}</div>', unsafe_allow_html=True)

    # เลือกช่วงเวลา (จำค่าที่เลือกไว้ ทั้งตอนสลับตัวเลือกและตอนโหลดหน้าซ้ำ)
    init_saved()
    saved = st.session_state["saved"]
    choice = st.radio(
        "ช่วงเวลา", RANGES, index=RANGES.index(saved["range"]), horizontal=True,
        label_visibility="collapsed", key="w_range",
        on_change=remember, args=("range", "w_range"),
    )
    custom = None
    start_hour, end_hour = 0, 24
    hour_label = lambda h: f"{h:02d}:00"
    if choice == "วันนี้":
        c_start, _ = st.columns(2)
        with c_start:
            start_hour = st.selectbox(
                "เริ่มตั้งแต่เวลา", list(range(24)), index=saved["today_start"],
                format_func=hour_label, key="w_today_start",
                on_change=remember, args=("today_start", "w_today_start"),
            )
    if choice == "เลือกวันที่":
        d_min, d_max = data["Timestamp"].min().date(), data["Timestamp"].max().date()
        d1, d2 = saved["d1"], saved["d2"]
        if d1 and d2:  # ปรับให้อยู่ในช่วงที่มีข้อมูลจริง
            d1, d2 = max(d1, d_min), min(d2, d_max)
        if not (d1 and d2 and d1 <= d2):
            d1, d2 = d_min, d_max
        picked = st.date_input(
            "เลือกช่วงวันที่", (d1, d2), min_value=d_min, max_value=d_max,
            format="DD/MM/YYYY", key="w_dates", on_change=remember_dates,
        )
        if isinstance(picked, (tuple, list)) and len(picked) == 2:
            custom = (picked[0], picked[1])
        else:
            st.caption("เลือกวันสิ้นสุดอีกหนึ่งวัน")
        c_start, c_end = st.columns(2)
        with c_start:
            start_hour = st.selectbox(
                "เริ่มเวลา (วันแรก)", list(range(24)), index=saved["custom_start"],
                format_func=hour_label, key="w_custom_start",
                on_change=remember, args=("custom_start", "w_custom_start"),
            )
        with c_end:
            end_hour = st.selectbox(
                "ถึงเวลา (วันสุดท้าย)", list(range(1, 25)), index=saved["custom_end"] - 1,
                format_func=lambda h: "24:00 (สิ้นวัน)" if h == 24 else hour_label(h),
                key="w_custom_end",
                on_change=remember, args=("custom_end", "w_custom_end"),
            )
    view, fell_back = filter_range(data, choice, custom, start_hour, end_hour)
    if fell_back:
        st.warning("ไม่มีข้อมูลในช่วงที่เลือก (ตรวจสอบเวลาเริ่ม/สิ้นสุด) จึงแสดงข้อมูลทั้งหมดแทน")
    elif choice in ("วันนี้", "เลือกวันที่"):
        st.caption(
            f"ช่วงที่แสดง: {view['Timestamp'].min():%d/%m %H:%M} – "
            f"{view['Timestamp'].max():%d/%m %H:%M} · {len(view):,} จุด"
        )
    rate = st.session_state.get("rate", DEFAULT_RATE)
    vat_pct = st.session_state.get("vat", DEFAULT_VAT)
    view = add_cost(view, rate, vat_pct)
    plot_df, step_min = downsample(view)
    if step_min:
        st.caption(
            f"ช่วงนี้มี {len(view):,} จุด กราฟแสดงค่าเฉลี่ยทุก {step_min} นาทีเพื่อความลื่น "
            "ส่วนค่าต่ำสุด/เฉลี่ย/สูงสุดคำนวณจากข้อมูลจริงทั้งหมด"
        )

    # แท็บกราฟ (1 แท็บ = 1 กราฟ)
    # ลำดับแท็บ: กำลัง → กระแส → แรงดัน → พลังงาน (ค่าไฟต่อท้าย) การ์ดด้านบนยังเรียงตาม METRICS เดิม
    TAB_ORDER = ["Power(W)", "Current(A)", "Voltage(V)", "Energy (kWh)"]
    tab_metrics = sorted(METRICS, key=lambda m: TAB_ORDER.index(m[0]))
    tabs = st.tabs([m[2] for m in tab_metrics] + ["💰 ค่าไฟ"])
    for tab, (col, _label, _tab, unit, color, dec) in zip(tabs, tab_metrics):
        with tab:
            if col not in view.columns or view[col].dropna().empty:
                st.info("ไม่มีข้อมูลในช่วงนี้")
                continue
            is_energy = col == "Energy (kWh)"
            peak_col = PEAK_COLS.get(col)
            has_peak = peak_col in view.columns and view[peak_col].notna().any()
            st.plotly_chart(
                make_chart(plot_df, col, color, unit, dec, fill=is_energy, peak_col=peak_col),
                width="stretch",
                config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False},
            )
            if has_peak:
                st.caption("เส้นสีเข้ม = ค่าเฉลี่ย · เส้นสีอ่อน = ค่าสูงสุดที่อ่านได้ในแต่ละช่วงเวลา")
            s = view[col].dropna()
            if is_energy:
                items = [
                    ("เริ่มช่วงนี้", f"{fmt(s.iloc[0], dec)} {unit}"),
                    ("ล่าสุด", f"{fmt(s.iloc[-1], dec)} {unit}"),
                    ("ใช้ไป", f"+{fmt(s.iloc[-1] - s.iloc[0], dec)} {unit}"),
                ]
            else:
                top, top_label = s.max(), "สูงสุด"
                if has_peak:  # มีค่าพีคจริง ใช้ค่านี้แทนค่าสูงสุดของค่าเฉลี่ย
                    top, top_label = max(top, view[peak_col].max()), "พีคสูงสุด"
                items = [
                    ("ต่ำสุด", f"{fmt(s.min(), dec)} {unit}"),
                    ("เฉลี่ย", f"{fmt(s.mean(), dec)} {unit}"),
                    (top_label, f"{fmt(top, dec)} {unit}"),
                ]
            st.markdown(mini_cards(items), unsafe_allow_html=True)

    # แท็บค่าไฟ (ต่อจากแท็บพลังงาน)
    with tabs[-1]:
        if COST_COL not in view.columns or view[COST_COL].dropna().empty:
            st.info("ไม่มีข้อมูลในช่วงนี้")
        else:
            st.plotly_chart(
                make_chart(plot_df, COST_COL, COST_COLOR, "฿", 1, fill=True),
                width="stretch",
                config={"displayModeBar": False, "scrollZoom": False, "doubleClick": False},
            )
            st.markdown(
                mini_cards([
                    ("หน่วยที่ใช้", f"{fmt(view['kWh_used'].sum(), 3)} kWh"),
                    ("ค่าไฟช่วงนี้", f"{fmt(view[COST_COL].iloc[-1], 1)} ฿"),
                    ("อัตรารวม VAT", f"{fmt(rate * (1 + vat_pct / 100), 2)} ฿/หน่วย"),
                ]),
                unsafe_allow_html=True,
            )
        with st.expander("ตั้งค่าอัตราค่าไฟ"):
            st.number_input("อัตรา (บาท/หน่วย)", min_value=0.0, value=DEFAULT_RATE,
                            step=0.1, key="rate")
            st.number_input("VAT (%)", min_value=0.0, value=DEFAULT_VAT,
                            step=1.0, key="vat")
            st.caption(
                "ค่าประมาณจากอัตราเดียว ค่าไฟตามบิลจริงอาจต่างเพราะคิดแบบขั้นบันได "
                "บวกค่า Ft และค่าบริการ"
            )

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
            column_config={COST_COL: st.column_config.NumberColumn(COST_COL, format="%.1f")},
        )


dashboard()
