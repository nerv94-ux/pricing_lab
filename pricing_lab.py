import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 페이지 설정 및 제목 (한글화)
st.set_page_config(page_title="유기농 통합 가격 관리 시스템 v2.5", layout="wide")
st.title("🥬 홍성유기농-유기농부 가격 협업 플랫폼 v2.5")

# 1. 구글 시트 연결 설정 (Secrets 연동)
# 코드에 주소를 직접 적지 않고, 스트림릿 관리자 페이지의 Secrets에서 읽어옵니다.
try:
    SHEET_URL = st.secrets["connections"]["gsheets"]["spreadsheet"]
except Exception:
    st.error("⚠️ 스트림릿 관리자 설정(Secrets)에서 구글 시트 URL을 먼저 등록해주세요!")
    st.info("설정 방법: App Settings -> Secrets -> [connections.gsheets] spreadsheet='주소' 입력")
    st.stop()

conn = st.connection("gsheets", type=GSheetsConnection)

# 컬럼 정의 (수정 이력 포함)
ALL_COLUMNS = [
    "No", "역산모드", "상태", "품목명", "매입원가(원)", "목표마진(%)", 
    "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가(원)", "업데이트시각", "수정자"
]

# 2. 데이터 불러오기 (캐싱 적용)
@st.cache_data(ttl=300) 
def load_data():
    try:
        df = conn.read(spreadsheet=SHEET_URL, worksheet="0")
        return df.reindex(columns=ALL_COLUMNS).fillna(0)
    except:
        # 데이터가 없을 때의 초기 샘플
        return pd.DataFrame([{"No": 1, "역산모드": False, "상태": "🟢 정상", "품목명": "유기농 당근", "매입원가(원)": 15000, "목표마진(%)": 20.0, "수수료율(%)": 5.6, "판매가(원)": 23000, "수정자": "초기세팅"}])

# 3. 사이드바 메뉴 (CDO님의 권한 관리)
st.sidebar.header("🏢 협업 센터")
user_role = st.sidebar.selectbox("접속 권한 선택", ["홍성유기농(공급사)", "유기농부(판매사)", "대표님(총괄)"])
actual_mode = st.sidebar.radio("마진 계산 기준", ["판매가 기준 마진", "원가 기준 마진"])
target_mode = st.sidebar.radio("목표 산출 기준", ["판매가 기준", "원가 기준"])

if 'df' not in st.session_state:
    st.session_state.df = load_data()

# 4. 하이브리드 계산 로직 (품목별 개별 역산 적용)
def calculate_hybrid(df, act_mode, tgt_mode):
    temp_df = df.copy()
    for i in range(len(temp_df)):
        is_rev = temp_df.at[i, "역산모드"]
        cost = int(temp_df.at[i, "매입원가(원)"])
        price = int(temp_df.at[i, "판매가(원)"])
        t_rate = float(temp_df.at[i, "목표마진(%)"])
        f_rate = float(temp_df.at[i, "수수료율(%)"])
        name = str(temp_df.at[i, "품목명"]).replace("🔄 ", "")

        if is_rev: # 역산 모드: 판매가(시세) 기반으로 매입원가 산출
            if tgt_mode == "판매가 기준":
                cost = round(price * (1 - (f_rate + t_rate) / 100))
            else:
                cost = round((price * (1 - f_rate/100)) / (1 + t_rate/100))
            temp_df.at[i, "매입원가(원)"] = int(cost)
            temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🟠 역산", f"🔄 {name}"
        else: # 정상 모드: 매입원가 기반으로 판매가 산출
            if tgt_mode == "판매가 기준":
                denom = 1 - (f_rate + t_rate) / 100
                price = round(cost / denom) if denom > 0 else 0
            else:
                price = round(cost * (1 + (f_rate + t_rate) / 100))
            temp_df.at[i, "판매가(원)"] = int(price)
            temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🟢 정상", name

        # 공통 마진 지표 계산
        f_amt = round(int(temp_df.at[i, "판매가(원)"]) * (f_rate / 100))
        m_amt = int(temp_df.at[i, "판매가(원)"]) - int(temp_df.at[i, "매입원가(원)"]) - f_amt
        m_rate = (m_amt / int(temp_df.at[i, "판매가(원)"]) * 100) if act_mode == "판매가 기준 마진" else (m_amt / int(temp_df.at[i, "매입원가(원)"]) * 100)
        
        temp_df.at[i, "마진율(%)"], temp_df.at[i, "마진액(원)"], temp_df.at[i, "수수료액(원)"] = round(m_rate, 2), int(m_amt), int(f_amt)
        t_amt = round(int(temp_df.at[i, "판매가(원)"]) * (t_rate/100)) if tgt_mode == "판매가 기준" else round(int(temp_df.at[i, "매입원가(원)"]) * (t_rate/100))
        temp_df.at[i, "목표대비(+/-)"] = int(m_amt - t_amt)
    return temp_df

# 5. 메인 데이터 편집 화면
st.info(f"💡 현재 **[{user_role}]** 권한으로 작업 중입니다. 전송 시 양사 데이터가 동기화됩니다.")

edited_df = st.data_editor(
    st.session_state.df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "No": st.column_config.NumberColumn(width="small"),
        "역산모드": st.column_config.CheckboxColumn("시세조정", help="체크 시 판매가(시세)를 입력하면 매입원가가 역산됩니다."),
        "매입원가(원)": st.column_config.NumberColumn("매입원가(목표)"),
        "마진율(%)": st.column_config.NumberColumn(disabled=True),
        "상태": st.column_config.TextColumn(disabled=True),
        "수정자": st.column_config.TextColumn(disabled=True)
    },
    hide_index=True
)

# 6. 전송 및 업데이트 컨트롤
col1, col2 = st.sidebar.columns(2)
if col1.button("🚀 데이터 전송"):
    with st.spinner('클라우드 서버에 반영 중...'):
        final_df = calculate_hybrid(edited_df, actual_mode, target_mode)
        final_df['업데이트시각'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_df['수정자'] = user_role
        conn.update(spreadsheet=SHEET_URL, data=final_df)
        st.cache_data.clear()
        st.sidebar.success("✅ 구글 시트 저장 완료!")
        st.rerun()

if col2.button("🔄 최신화"):
    st.cache_data.clear()
    st.session_state.df = load_data()
    st.rerun()