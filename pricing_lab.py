import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 1. 페이지 및 보안 설정
st.set_page_config(page_title="유기농 통합 가격 관리 시스템 v2.5", layout="wide")
st.title("🥬 홍성유기농-유기농부 협업 플랫폼 v2.5")

# 1-1. 구글 시트 보안 연결 (Secrets 연동)
try:
    SHEET_URL = st.secrets["connections"]["gsheets"]["spreadsheet"]
    conn = st.connection("gsheets", type=GSheetsConnection)
except Exception:
    st.error("⚠️ 관리자 설정(Secrets)에 구글 시트 주소가 등록되지 않았습니다.")
    st.info("Streamlit Cloud 설정에서 [connections.gsheets] spreadsheet='주소'를 입력해주세요.")
    st.stop()

# 2. 컬럼 및 데이터 구조 정의
ALL_COLUMNS = [
    "No", "역산모드", "상태", "품목명", "매입원가(원)", "목표마진(%)", 
    "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가(원)", "업데이트시각", "수정자"
]

@st.cache_data(ttl=300) 
def load_data():
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet="0")
        # 기존 데이터가 있으면 구조에 맞게 재정렬, 없으면 초기화
        if df.empty:
            return pd.DataFrame(columns=ALL_COLUMNS)
        return df.reindex(columns=ALL_COLUMNS).fillna(0)
    except:
        return pd.DataFrame([{"No": 1, "역산모드": False, "상태": "🟢 정상", "품목명": "신규 품목", "매입원가(원)": 0, "목표마진(%)": 0.0, "수수료율(%)": 5.6, "판매가(원)": 0}])

# 3. 사이드바 - 실무자 최적화 설정
st.sidebar.header("🏢 협업 센터")
user_role = st.sidebar.selectbox("접속 권한", ["홍성유기농(공급사)", "유기농부(판매사)", "대표님(총괄)"])

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 계산 기준 설정")
actual_mode = st.sidebar.radio("마진율 계산 기준", ["판매가 기준", "원가 기준"], help="실제 마진율을 무엇으로 나눌지 결정합니다.")
target_mode = st.sidebar.radio("목표가 산출 기준", ["판매가 기준", "원가 기준"], help="목표 마진율을 적용할 때의 기준입니다.")

if 'df' not in st.session_state:
    st.session_state.df = load_data()

# 4. 핵심 하이브리드 계산 로직 (v2.3 원본 로직 복원)
def calculate_all(df, act_mode, tgt_mode):
    temp_df = df.copy()
    for i in range(len(temp_df)):
        try:
            is_rev = bool(temp_df.at[i, "역산모드"])
            cost = float(temp_df.at[i, "매입원가(원)"])
            price = float(temp_df.at[i, "판매가(원)"])
            t_rate = float(temp_df.at[i, "목표마진(%)"])
            f_rate = float(temp_df.at[i, "수수료율(%)"])
            name = str(temp_df.at[i, "품목명"]).replace("🔄 ", "")

            # A. 판매가/매입가 결정 로직
            if is_rev: # 역산 모드: 시장가(판매가)에 맞춰 원가 계산
                if tgt_mode == "판매가 기준":
                    cost = round(price * (1 - (f_rate + t_rate) / 100))
                else:
                    cost = round((price * (1 - f_rate/100)) / (1 + t_rate/100))
                temp_df.at[i, "매입원가(원)"] = int(cost)
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🟠 역산", f"🔄 {name}"
            else: # 정산 모드: 원가에 마진 붙여 판매가 계산
                if tgt_mode == "판매가 기준":
                    denom = 1 - (f_rate + t_rate) / 100
                    price = round(cost / denom) if denom > 0 else 0
                else:
                    price = round(cost * (1 + (f_rate + t_rate) / 100))
                temp_df.at[i, "판매가(원)"] = int(price)
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🟢 정상", name

            # B. 결과 지표 계산
            f_amt = round(price * (f_rate / 100))
            m_amt = int(price - cost - f_amt)
            
            # 실제 마진율 계산
            if act_mode == "판매가 기준":
                m_rate = (m_amt / price * 100) if price > 0 else 0
            else:
                m_rate = (m_amt / cost * 100) if cost > 0 else 0
            
            # 목표 대비 차액 계산
            t_amt = round(price * (t_rate/100)) if tgt_mode == "판매가 기준" else round(cost * (t_rate/100))
            
            temp_df.at[i, "마진율(%)"] = round(m_rate, 2)
            temp_df.at[i, "마진액(원)"] = m_amt
            temp_df.at[i, "수수료액(원)"] = f_amt
            temp_df.at[i, "목표대비(+/-)"] = int(m_amt - t_amt)
        except Exception as e:
            continue
            
    return temp_df

# 5. 메인 화면 구성
st.info(f"현재 **[{user_role}]** 권한으로 데이터를 편집 중입니다. 수정 후 '클라우드 전송'을 누르세요.")

# 편집기 설정 (자동 계산 결과는 수정 불가 처리)
edited_df = st.data_editor(
    st.session_state.df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "No": st.column_config.NumberColumn(width="small"),
        "역산모드": st.column_config.CheckboxColumn("역산"),
        "상태": st.column_config.TextColumn(disabled=True),
        "마진율(%)": st.column_config.NumberColumn(format="%.2f%%", disabled=True),
        "마진액(원)": st.column_config.NumberColumn(format="%d", disabled=True),
        "수수료액(원)": st.column_config.NumberColumn(format="%d", disabled=True),
        "목표대비(+/-)": st.column_config.NumberColumn(format="%+d", disabled=True),
        "업데이트시각": st.column_config.TextColumn(disabled=True),
        "수정자": st.column_config.TextColumn(disabled=True)
    },
    hide_index=True
)

# 6. 제어 버튼
col1, col2, col3 = st.sidebar.columns(3)

if st.sidebar.button("🚀 클라우드 전송 (저장/공유)", use_container_width=True):
    with st.spinner('양사 데이터 동기화 중...'):
        final_df = calculate_all(edited_df, actual_mode, target_mode)
        final_df['업데이트시각'] = datetime.now().strftime("%m/%d %H:%M")
        final_df['수정자'] = user_role
        conn.update(spreadsheet=SHEET_URL, data=final_df)
        st.cache_data.clear()
        st.session_state.df = final_df
        st.sidebar.success("✅ 저장 완료!")
        st.rerun()

if st.sidebar.button("🔄 새로고침 (불러오기)", use_container_width=True):
    st.cache_data.clear()
    st.session_state.df = load_data()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption(f"최종 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}")