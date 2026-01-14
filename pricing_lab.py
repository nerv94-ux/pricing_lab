import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 1. [구조 유지] 페이지 설정
st.set_page_config(page_title="유기농 통합 가격 관리 시스템 v5.0", layout="wide")
st.title("🥬 홍성유기농-유기농부 가격 협업 플랫폼 v5.0")

# 2. [구조 유지] 보안 연결 (절대 경로 고정)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    SHEET_NAME = st.secrets["connections"]["gsheets"]["spreadsheet"]
except Exception:
    st.error("⚠️ Secrets 설정에서 spreadsheet 이름을 확인해주세요.")
    st.stop()

# 3. [구조 유지] 14개 컬럼 규격
ALL_COLUMNS = [
    "No", "역산모드", "상태", "품목명", "매입원가(원)", "목표마진(%)", 
    "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가", "업데이트시각", "수정자"
]

# 4. [혁신] 캐시 없는 실시간 로드 (데이터 고임 현상 해결)
def load_data_direct():
    try:
        df = conn.read(spreadsheet=SHEET_NAME, worksheet=0)
        if df is None or df.empty or len(df.columns) < 2:
            df = pd.DataFrame(columns=ALL_COLUMNS)
        df = df.reindex(columns=ALL_COLUMNS)
        # 숫자형 강제 변환 및 결측치 0 채움
        num_cols = ["No", "매입원가(원)", "목표마진(%)", "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가"]
        for col in num_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df["역산모드"] = df["역산모드"].astype(bool)
        df["상태"] = df["상태"].astype(str).replace("0", "🟢 정상")
        return df
    except:
        return pd.DataFrame(columns=ALL_COLUMNS).fillna(0)

# 6. [구조 유지] 하이브리드 계산 엔진 (v3.5 수식 100% 보존)
def run_calculation_engine(df, act_mode, tgt_mode):
    if df is None or df.empty: return df
    t_df = df.copy()
    for i in range(len(t_df)):
        try:
            is_rev = bool(t_df.at[i, "역산모드"])
            cost = float(t_df.at[i, "매입원가(원)"])
            price = float(t_df.at[i, "판매가"])
            t_rate = float(t_df.at[i, "목표마진(%)"])
            f_rate = float(t_df.at[i, "수수료율(%)"])
            name = str(t_df.at[i, "품목명"]).replace("🔄 ", "").replace("🚨 ", "").replace("🔻 ", "")

            if is_rev: # 역산 모드
                if tgt_mode == "판매가 기준": cost = round(price * (1 - (f_rate + t_rate) / 100))
                else: cost = round((price * (1 - f_rate/100)) / (1 + t_rate/100))
                t_df.at[i, "매입원가(원)"] = int(cost)
                status_icon, prefix = "🟠", f"🔄 {name}"
            else: # 정산 모드
                if tgt_mode == "판매가 기준":
                    denom = 1 - (f_rate + t_rate) / 100
                    price = round(cost / denom) if denom > 0 else 0
                else: price = round(cost * (1 + (f_rate + t_rate) / 100))
                t_df.at[i, "판매가"] = int(price)
                status_icon, prefix = "🟢", name

            f_amt = round(price * (f_rate / 100))
            m_amt = int(price - cost - f_amt)
            m_rate = (m_amt / price * 100) if price > 0 and act_mode == "판매가 기준 마진" else (m_amt / cost * 100 if cost > 0 else 0)
            t_amt = round(price * (t_rate/100)) if tgt_mode == "판매가 기준" else round(cost * (t_rate/100))
            
            if price < (cost + f_amt) and price > 0:
                t_df.at[i, "상태"], t_df.at[i, "품목명"] = "🚨 가격역전", f"🚨 {prefix}"
            elif m_amt < t_amt:
                t_df.at[i, "상태"], t_df.at[i, "품목명"] = f"{status_icon} 목표미달", f"🔻 {prefix}"
            else:
                t_df.at[i, "상태"], t_df.at[i, "품목명"] = f"{status_icon} 정상", prefix

            t_df.at[i, "마진율(%)"], t_df.at[i, "마진액(원)"] = round(m_rate, 2), int(m_amt)
            t_df.at[i, "수수료액(원)"], t_df.at[i, "목표대비(+/-)"] = int(f_amt), int(m_amt - t_amt)
        except: continue
    return t_df

# 7. [혁신] 상태 격리 업데이트 콜백
def silent_sync():
    # 화면 깜빡임 없이 메모리 데이터만 즉시 교체
    changes = st.session_state["editor_v5"]
    current_df = st.session_state.df.copy()

    for idx, vals in changes["edited_rows"].items():
        for col, val in vals.items():
            current_df.at[idx, col] = val

    for added in changes["added_rows"]:
        new_row = {c: 0 for c in ALL_COLUMNS}
        new_row.update(added)
        last_no = current_df["No"].max() if not current_df.empty else 0
        new_row["No"] = int(last_no) + 1
        new_row["역산모드"] = bool(new_row.get("역산모드", False))
        current_df = pd.concat([current_df, pd.DataFrame([new_row])], ignore_index=True)

    if changes["deleted_rows"]:
        current_df = current_df.drop(changes["deleted_rows"]).reset_index(drop=True)

    # 계산 엔진 가동 후 저장
    st.session_state.df = run_calculation_engine(current_df, st.session_state.a_mode, st.session_state.t_mode)

# 5. 초기화
if 'df' not in st.session_state:
    st.session_state.df = load_data_direct()

# 사이드바 설정
st.sidebar.header("🏢 실무 협업 센터 v5.0")
search = st.sidebar.text_input("🔍 품목명 검색", placeholder="품목명을 입력하세요...")
user = st.sidebar.selectbox("접속 권한", ["홍성유기농(공급사)", "유기농부(판매사)", "대표님(총괄)"])
st.session_state.a_mode = st.sidebar.radio("마진율 기준", ["판매가 기준 마진", "원가 기준 마진"])
st.session_state.t_mode = st.sidebar.radio("목표 산출 기준", ["판매가 기준", "원가 기준"])

# 8. 에디터 출력
st.info(f"💡 현재: **[{user}]** | 무한 루프가 해결된 5.0 엔진입니다. 입력 즉시 계산됩니다.")

# 화면 표시 전 최종 동기화
st.session_state.df = run_calculation_engine(st.session_state.df, st.session_state.a_mode, st.session_state.t_mode)

view_df = st.session_state.df.copy()
if search:
    view_df = view_df[view_df["품목명"].str.contains(search, na=False, case=False)]

st.data_editor(
    view_df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "No": st.column_config.NumberColumn(width="small"),
        "역산모드": st.column_config.CheckboxColumn("시세역산"),
        "상태": st.column_config.TextColumn(disabled=True),
        "매입원가(원)": st.column_config.NumberColumn("매입원가", format="%d"),
        "판매가": st.column_config.NumberColumn("판매가", format="%d"),
        "마진율(%)": st.column_config.NumberColumn("마진율", format="%.2f%%", disabled=True),
        "마진액(원)": st.column_config.NumberColumn("마진액", format="%d", disabled=True),
    },
    hide_index=True,
    key="editor_v5",
    on_change=silent_sync # 루프 방지 핵심
)

# 9. 버튼부
st.sidebar.markdown("---")
if st.sidebar.button("🚀 클라우드 저장 (시트 전송)", use_container_width=True):
    with st.spinner('전송 중...'):
        final = run_calculation_engine(st.session_state.df, st.session_state.a_mode, st.session_state.t_mode)
        final['업데이트시각'] = datetime.now().strftime("%m/%d %H:%M")
        final['수정자'] = user
        conn.update(spreadsheet=SHEET_NAME, worksheet=0, data=final)
        st.sidebar.success("✅ 저장 성공!")

if st.sidebar.button("🔄 시트에서 다시 불러오기", use_container_width=True):
    st.session_state.df = load_data_direct()
    st.rerun()

st.sidebar.caption(f"v5.0 Architecture | {datetime.now().strftime('%H:%M:%S')}")