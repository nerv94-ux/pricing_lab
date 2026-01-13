import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# [구조 유지] 1. 페이지 설정 및 제목
st.set_page_config(page_title="유기농 통합 가격 관리 시스템 v2.7", layout="wide")
st.title("🥬 홍성유기농-유기농부 가격 협업 플랫폼 v2.7")

# [교체/수정] 2. 구글 시트 보안 연결 설정 (v2.6 방식 적용)
# Secrets에서 시트 이름과 인증 정보를 자동으로 읽어옵니다.
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    SHEET_NAME = st.secrets["connections"]["gsheets"]["spreadsheet"]
except Exception as e:
    st.error("⚠️ 관리자 설정(Secrets)에 오류가 있거나 인증 정보가 부족합니다.")
    st.stop()

# [구조 유지] 3. 컬럼 정의 (v2.3의 모든 컬럼 100% 복원)
ALL_COLUMNS = [
    "No", "역산모드", "상태", "품목명", "매입원가(원)", "목표마진(%)", 
    "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가(원)", "업데이트시각", "수정자"
]

# [수정] 4. 데이터 불러오기 함수 (구조는 유지하되 클라우드 읽기 방식으로 교체)
@st.cache_data(ttl=60)
def load_data():
    try:
        # worksheet="0"은 첫 번째 탭을 의미합니다.
        df = conn.read(spreadsheet=SHEET_NAME, worksheet="0")
        if df.empty:
            return pd.DataFrame(columns=ALL_COLUMNS)
        return df.reindex(columns=ALL_COLUMNS).fillna(0)
    except:
        # 데이터가 없을 경우를 대비한 샘플 구조
        return pd.DataFrame([{"No": 1, "역산모드": False, "상태": "🟢 정상", "품목명": "신규 품목", "매입원가(원)": 0, "목표마진(%)": 0.0, "수수료율(%)": 5.6, "판매가(원)": 0}])

# [구조 유지] 5. 사이드바 메뉴 및 권한 설정
st.sidebar.header("🏢 협업 센터")
user_role = st.sidebar.selectbox("접속 권한 선택", ["홍성유기농(공급사)", "유기농부(판매사)", "대표님(총괄)"])

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 마진 및 목표 설정")
actual_mode = st.sidebar.radio("마진율 계산 기준", ["판매가 기준 마진", "원가 기준 마진"], 
                             help="실제 마진율을 (마진액/판매가)로 할지 (마진액/원가)로 할지 결정합니다.")
target_mode = st.sidebar.radio("목표 산출 기준", ["판매가 기준", "원가 기준"], 
                             help="목표 마진율을 판매가에 곱할지, 원가에 곱할지 결정합니다.")

if 'df' not in st.session_state:
    st.session_state.df = load_data()

# [구조 유지] 6. 하이브리드 계산 함수 (v2.3의 모든 수식과 로직 100% 보존)
def calculate_hybrid(df, act_mode, tgt_mode):
    temp_df = df.copy()
    for i in range(len(temp_df)):
        try:
            is_rev = bool(temp_df.at[i, "역산모드"])
            cost = float(temp_df.at[i, "매입원가(원)"])
            price = float(temp_df.at[i, "판매가(원)"])
            t_rate = float(temp_df.at[i, "목표마진(%)"])
            f_rate = float(temp_df.at[i, "수수료율(%)"])
            name = str(temp_df.at[i, "품목명"]).replace("🔄 ", "")

            # A. 판매가/매입가 결정 (역산 vs 정산)
            if is_rev: # 역산 모드: 판매가 기준으로 매입원가 산출
                if tgt_mode == "판매가 기준":
                    cost = round(price * (1 - (f_rate + t_rate) / 100))
                else:
                    cost = round((price * (1 - f_rate/100)) / (1 + t_rate/100))
                temp_df.at[i, "매입원가(원)"] = int(cost)
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🟠 역산", f"🔄 {name}"
            else: # 정산 모드: 매입원가 기준으로 판매가 산출
                if tgt_mode == "판매가 기준":
                    denom = 1 - (f_rate + t_rate) / 100
                    price = round(cost / denom) if denom > 0 else 0
                else:
                    price = round(cost * (1 + (f_rate + t_rate) / 100))
                temp_df.at[i, "판매가(원)"] = int(price)
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🟢 정상", name

            # B. 결과값 상세 계산
            f_amt = round(price * (f_rate / 100))
            m_amt = int(price - cost - f_amt)
            
            # 마진율 계산
            if act_mode == "판매가 기준 마진":
                m_rate = (m_amt / price * 100) if price > 0 else 0
            else:
                m_rate = (m_amt / cost * 100) if cost > 0 else 0
            
            # 목표 대비 차액 계산
            t_amt = round(price * (t_rate/100)) if tgt_mode == "판매가 기준" else round(cost * (t_rate/100))
            
            temp_df.at[i, "마진율(%)"] = round(m_rate, 2)
            temp_df.at[i, "마진액(원)"] = m_amt
            temp_df.at[i, "수수료액(원)"] = f_amt
            temp_df.at[i, "목표대비(+/-)"] = int(m_amt - t_amt)
        except:
            continue
            
    return temp_df

# [구조 유지] 7. 메인 데이터 편집 화면 (v2.3 UI 설정 100% 복원)
st.info(f"💡 현재 **[{user_role}]** 권한으로 작업 중입니다. 전송 시 상대 회사와 데이터가 즉시 공유됩니다.")

edited_df = st.data_editor(
    st.session_state.df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "No": st.column_config.NumberColumn(width="small"),
        "역산모드": st.column_config.CheckboxColumn("시세역산", help="체크 시 판매가(시세)를 기준으로 매입원가를 산출합니다."),
        "매입원가(원)": st.column_config.NumberColumn("매입원가(목표)"),
        "마진율(%)": st.column_config.NumberColumn(format="%.2f%%", disabled=True),
        "마진액(원)": st.column_config.NumberColumn(disabled=True),
        "수수료율(%)": st.column_config.NumberColumn(format="%.1f%%"),
        "수수료액(원)": st.column_config.NumberColumn(disabled=True),
        "목표대비(+/-)": st.column_config.NumberColumn(format="%+d", disabled=True),
        "상태": st.column_config.TextColumn(disabled=True),
        "업데이트시각": st.column_config.TextColumn(disabled=True),
        "수정자": st.column_config.TextColumn(disabled=True)
    },
    hide_index=True
)

# [수정] 8. 저장 및 불러오기 버튼 (v2.6 클라우드 업데이트 로직 반영)
col1, col2 = st.sidebar.columns(2)

if col1.button("🚀 클라우드 전송"):
    with st.spinner('구글 시트에 데이터를 반영 중...'):
        # 계산 수행
        final_df = calculate_hybrid(edited_df, actual_mode, target_mode)
        # 이력 기록
        final_df['업데이트시각'] = datetime.now().strftime("%m/%d %H:%M")
        final_df['수정자'] = user_role
        # [교체] 구글 시트 업데이트 로직
        conn.update(spreadsheet=SHEET_NAME, worksheet="0", data=final_df)
        
        st.cache_data.clear()
        st.session_state.df = final_df
        st.sidebar.success("✅ 클라우드 저장 완료!")
        st.rerun()

if col2.button("🔄 최신 데이터"):
    st.cache_data.clear()
    st.session_state.df = load_data()
    st.rerun()

# [구조 유지] 9. 하단 정보 표기
st.sidebar.markdown("---")
st.sidebar.caption(f"최종 접속 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")