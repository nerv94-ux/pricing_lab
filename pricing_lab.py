import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 1. [구조 유지] 페이지 설정 및 제목
st.set_page_config(page_title="유기농 통합 가격 관리 시스템 v4.5", layout="wide")
st.title("🥬 홍성유기농-유기농부 가격 협업 플랫폼 v4.5")

# 2. [복구] 구글 시트 보안 연결 설정
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    SHEET_NAME = st.secrets["connections"]["gsheets"]["spreadsheet"]
except Exception as e:
    st.error("⚠️ 관리자 설정(Secrets)의 spreadsheet 이름이나 인증키를 확인해주세요.")
    st.stop()

# 3. [구조 유지] 14개 전체 컬럼 규격 정의
ALL_COLUMNS = [
    "No", "역산모드", "상태", "품목명", "매입원가(원)", "목표마진(%)", 
    "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가", "업데이트시각", "수정자"
]

# 4. [구조 유지] 데이터 로드 함수
@st.cache_data(ttl=5)
def load_data():
    try:
        df = conn.read(spreadsheet=SHEET_NAME, worksheet=0)
        # 데이터가 아예 없을 경우 빈 틀 생성
        if df.empty or len(df.columns) < 2:
            df = pd.DataFrame(columns=ALL_COLUMNS)
        df = df.reindex(columns=ALL_COLUMNS)
        num_cols = ["No", "매입원가(원)", "목표마진(%)", "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가"]
        for col in num_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        df["역산모드"] = df["역산모드"].astype(bool)
        df["상태"] = df["상태"].astype(str).replace("0", "🟢 정상")
        df["품목명"] = df["품목명"].astype(str).replace("0", "")
        return df
    except Exception as e:
        return pd.DataFrame(columns=ALL_COLUMNS).fillna(0)

# 6. [구조 유지] 하이브리드 계산 엔진 (수식 및 아이콘 로직 100% 원본 유지)
def calculate_hybrid(df, act_mode, tgt_mode):
    if df.empty: return df
    temp_df = df.copy()
    for i in range(len(temp_df)):
        try:
            is_rev = bool(temp_df.at[i, "역산모드"])
            cost = float(pd.to_numeric(temp_df.at[i, "매입원가(원)"], errors='coerce') or 0)
            price = float(pd.to_numeric(temp_df.at[i, "판매가"], errors='coerce') or 0)
            t_rate = float(pd.to_numeric(temp_df.at[i, "목표마진(%)"], errors='coerce') or 0)
            f_rate = float(pd.to_numeric(temp_df.at[i, "수수료율(%)"], errors='coerce') or 0)
            
            clean_name = str(temp_df.at[i, "품목명"]).replace("🔄 ", "").replace("🚨 ", "").replace("🔻 ", "")
            if clean_name in ["nan", "None", "0"]: clean_name = ""

            # [핵심 수식 - 원본 보존]
            if is_rev:
                if tgt_mode == "판매가 기준": cost = round(price * (1 - (f_rate + t_rate) / 100))
                else: cost = round((price * (1 - f_rate/100)) / (1 + t_rate/100))
                temp_df.at[i, "매입원가(원)"] = int(cost)
                status_icon, name_prefix = "🟠", f"🔄 {clean_name}"
            else:
                if tgt_mode == "판매가 기준":
                    denom = 1 - (f_rate + t_rate) / 100
                    price = round(cost / denom) if denom > 0 else 0
                else: price = round(cost * (1 + (f_rate + t_rate) / 100))
                temp_df.at[i, "판매가"] = int(price)
                status_icon, name_prefix = "🟢", clean_name

            f_amt = round(price * (f_rate / 100))
            m_amt = int(price - cost - f_amt)
            m_rate = (m_amt / price * 100) if price > 0 and act_mode == "판매가 기준 마진" else (m_amt / cost * 100 if cost > 0 else 0)
            t_amt = round(price * (t_rate/100)) if tgt_mode == "판매가 기준" else round(cost * (t_rate/100))
            
            if price < (cost + f_amt) and price > 0:
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🚨 가격역전", f"🚨 {name_prefix}"
            elif m_amt < t_amt:
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = f"{status_icon} 목표미달", f"🔻 {name_prefix}"
            else:
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = f"{status_icon} 정상", name_prefix

            temp_df.at[i, "마진율(%)"], temp_df.at[i, "마진액(원)"] = round(m_rate, 2), int(m_amt)
            temp_df.at[i, "수수료액(원)"], temp_df.at[i, "목표대비(+/-)"] = int(f_amt), int(m_amt - t_amt)
        except: continue
    return temp_df

# 7. [수정] 무한 루프 방지 및 즉각 계산 콜백
def on_data_change():
    change_info = st.session_state["pricing_editor"]
    # 현재 세션 데이터가 비어있으면 ALL_COLUMNS 구조로 초기화
    if st.session_state.df is None or st.session_state.df.empty:
        df = pd.DataFrame(columns=ALL_COLUMNS)
    else:
        df = st.session_state.df.copy()
    
    # 1. 수정된 값 반영
    for row_idx, edit_values in change_info["edited_rows"].items():
        for col, val in edit_values.items():
            df.at[row_idx, col] = val
            
    # 2. 추가된 행 처리 (번호 및 기본값 강제 주입)
    for added_row in change_info["added_rows"]:
        new_row_data = {col: 0 for col in ALL_COLUMNS}
        new_row_data.update(added_row)
        new_row_data["역산모드"] = bool(new_row_data.get("역산모드", False))
        new_row_data["상태"] = "🟢 정상"
        
        # 번호 부여
        last_no = df["No"].max() if not df.empty else 0
        new_row_data["No"] = int(last_no) + 1
        
        df = pd.concat([df, pd.DataFrame([new_row_data])], ignore_index=True)
        
    # 3. 삭제된 행 처리
    if change_info["deleted_rows"]:
        df = df.drop(change_info["deleted_rows"]).reset_index(drop=True)

    # 4. 즉시 계산 엔진 가동 (데이터 타입 강제 고정)
    st.session_state.df = calculate_hybrid(df, st.session_state.actual_mode, st.session_state.target_mode)

# 5. [구조 유지] 세션 상태 초기화 및 사이드바
if 'df' not in st.session_state:
    st.session_state.df = load_data()

st.sidebar.header("🏢 실무 협업 센터")
search_term = st.sidebar.text_input("🔍 품목명 검색", placeholder="검색어를 입력하세요...")
user_role = st.sidebar.selectbox("접속 권한 선택", ["홍성유기농(공급사)", "유기농부(판매사)", "대표님(총괄)"])

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 마진 및 목표 설정")
st.session_state.actual_mode = st.sidebar.radio("마진율 계산 기준", ["판매가 기준 마진", "원가 기준 마진"])
st.session_state.target_mode = st.sidebar.radio("목표 산출 기준", ["판매가 기준", "원가 기준"])

# 8. [교체] 반응형 라이브 에디터 (st.rerun 없이 콜백 사용)
st.info(f"💡 접속: **[{user_role}]** | 시트가 비어있어도 '+' 버튼으로 품목을 추가하면 즉시 계산됩니다.")

display_df = st.session_state.df.copy()
if search_term:
    display_df = display_df[display_df["품목명"].str.contains(search_term, na=False, case=False)]

st.data_editor(
    display_df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "No": st.column_config.NumberColumn(width="small"),
        "역산모드": st.column_config.CheckboxColumn("시세역산"),
        "상태": st.column_config.TextColumn(disabled=True),
        "품목명": st.column_config.TextColumn("품목명", width="medium"),
        "매입원가(원)": st.column_config.NumberColumn("매입원가", format="%d"),
        "목표마진(%)": st.column_config.NumberColumn("목표마진(%)", format="%.1f%%"),
        "마진율(%)": st.column_config.NumberColumn("실제마진율(%)", format="%.2f%%", disabled=True),
        "마진액(원)": st.column_config.NumberColumn("마진금액", format="%d", disabled=True),
        "목표대비(+/-)": st.column_config.NumberColumn("목표대비", format="%+d", disabled=True),
        "수수료율(%)": st.column_config.NumberColumn("수수료율(%)", format="%.1f%%"),
        "수수료액(원)": st.column_config.NumberColumn("수수료금액", format="%d", disabled=True),
        "판매가": st.column_config.NumberColumn("판매가", format="%d"),
        "업데이트시각": st.column_config.TextColumn(disabled=True),
        "수정자": st.column_config.TextColumn(disabled=True)
    },
    hide_index=True,
    key="pricing_editor",
    on_change=on_data_change 
)

# 9. [구조 유지] 저장/불러오기 버튼
st.sidebar.markdown("---")
if st.sidebar.button("🚀 클라우드 전송 (저장/공유)", use_container_width=True):
    with st.spinner('구글 시트에 데이터 동기화 중...'):
        final_df = calculate_hybrid(st.session_state.df, st.session_state.actual_mode, st.session_state.target_mode)
        final_df['업데이트시각'] = datetime.now().strftime("%m/%d %H:%M")
        final_df['수정자'] = user_role
        conn.update(spreadsheet=SHEET_NAME, worksheet=0, data=final_df)
        st.cache_data.clear()
        st.session_state.df = final_df
        st.sidebar.success("✅ 저장 완료!")
        st.rerun()

if st.sidebar.button("🔄 최신 데이터 불러오기", use_container_width=True):
    st.cache_data.clear()
    st.session_state.df = load_data()
    st.rerun()

st.sidebar.caption(f"v4.5 Robust Engine | {datetime.now().strftime('%H:%M:%S')}")