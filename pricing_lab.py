import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 1. 페이지 설정 및 제목 (원본 유지)
st.set_page_config(page_title="유기농 통합 가격 관리 시스템 v2.8", layout="wide")
st.title("🥬 홍성유기농-유기농부 가격 협업 플랫폼 v2.8")

# 2. 구글 시트 보안 연결 (v2.6 인증 방식 유지)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    SHEET_NAME = st.secrets["connections"]["gsheets"]["spreadsheet"]
except Exception as e:
    st.error("⚠️ 관리자 설정(Secrets)에 오류가 있습니다. 구글 시트 이름과 인증 정보를 확인해주세요.")
    st.stop()

# 3. 14개 전체 컬럼 정의 (v2.3 규격 100% 복원)
ALL_COLUMNS = [
    "No", "역산모드", "상태", "품목명", "매입원가(원)", "목표마진(%)", 
    "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가(원)", "업데이트시각", "수정자"
]

# 4. 데이터 로드 함수 (구조 보존)
@st.cache_data(ttl=60)
def load_data():
    try:
        df = conn.read(spreadsheet=SHEET_NAME, worksheet="0")
        if df.empty:
            return pd.DataFrame(columns=ALL_COLUMNS)
        # 14개 컬럼 순서 강제 고정 및 누락 데이터 0 처리
        return df.reindex(columns=ALL_COLUMNS).fillna(0)
    except:
        return pd.DataFrame([{"No": 1, "역산모드": False, "상태": "🟢 정상", "품목명": "신규 품목", "매입원가(원)": 0, "목표마진(%)": 0.0, "수수료율(%)": 5.6, "판매가(원)": 0}])

# 5. 사이드바 설정 (v2.3 기능 100% 복원)
st.sidebar.header("🏢 협업 센터")
user_role = st.sidebar.selectbox("접속 권한 선택", ["홍성유기농(공급사)", "유기농부(판매사)", "대표님(총괄)"])

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 마진 및 목표 설정")
actual_mode = st.sidebar.radio("마진율 계산 기준", ["판매가 기준 마진", "원가 기준 마진"], 
                             help="실제 마진율을 (마진액/판매가)로 할지 (마진액/원가)로 할지 결정합니다.")
target_mode = st.sidebar.radio("목표 산출 기준", ["판매가 기준", "원가 기준"], 
                             help="목표 마진율을 판매가에 곱할지, 원가에 곱할지 결정합니다.")

# 세션 상태 초기화
if 'df' not in st.session_state:
    st.session_state.df = load_data()

# 6. 하이브리드 프라이싱 엔진 (v2.3 수식 단 한 줄도 생략 없이 복원)
def calculate_engine(df, act_mode, tgt_mode):
    temp_df = df.copy()
    for i in range(len(temp_df)):
        try:
            # 기본 데이터 추출
            is_rev = bool(temp_df.at[i, "역산모드"])
            cost = float(temp_df.at[i, "매입원가(원)"])
            price = float(temp_df.at[i, "판매가(원)"])
            t_rate = float(temp_df.at[i, "목표마진(%)"])
            f_rate = float(temp_df.at[i, "수수료율(%)"])
            name = str(temp_df.at[i, "품목명"]).replace("🔄 ", "")

            # A. 가격 결정 로직 (역산 vs 정산)
            if is_rev: # 역산 모드: 시장가(판매가) 입력 시 매입원가 도출
                if tgt_mode == "판매가 기준":
                    cost = round(price * (1 - (f_rate + t_rate) / 100))
                else:
                    cost = round((price * (1 - f_rate/100)) / (1 + t_rate/100))
                temp_df.at[i, "매입원가(원)"] = int(cost)
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🟠 역산", f"🔄 {name}"
            else: # 정산 모드: 매입원가 입력 시 판매가 도출
                if tgt_mode == "판매가 기준":
                    denom = 1 - (f_rate + t_rate) / 100
                    price = round(cost / denom) if denom > 0 else 0
                else:
                    price = round(cost * (1 + (f_rate + t_rate) / 100))
                temp_df.at[i, "판매가(원)"] = int(price)
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🟢 정상", name

            # B. 상세 지표 계산 (마진, 수수료, 차액)
            f_amt = round(price * (f_rate / 100))
            m_amt = int(price - cost - f_amt)
            
            # 실제 마진율 산출
            if act_mode == "판매가 기준 마진":
                m_rate = (m_amt / price * 100) if price > 0 else 0
            else:
                m_rate = (m_amt / cost * 100) if cost > 0 else 0
            
            # 목표 마진액 산출
            t_amt = round(price * (t_rate/100)) if tgt_mode == "판매가 기준" else round(cost * (t_rate/100))
            
            # 데이터 프레임 업데이트
            temp_df.at[i, "마진율(%)"] = round(m_rate, 2)
            temp_df.at[i, "마진액(원)"] = m_amt
            temp_df.at[i, "수수료액(원)"] = f_amt
            temp_df.at[i, "목표대비(+/-)"] = int(m_amt - t_amt)
        except Exception:
            continue
            
    return temp_df

# 7. 메인 화면 구성 및 실시간 동기화
st.info(f"💡 현재 권한: **[{user_role}]** | 수정 후 '중간 계산' 또는 '클라우드 전송'을 누르세요.")

# 데이터 편집기 (14개 컬럼 세부 설정 100% 복원)
edited_df = st.data_editor(
    st.session_state.df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "No": st.column_config.NumberColumn(width="small"),
        "역산모드": st.column_config.CheckboxColumn("시세역산"),
        "품목명": st.column_config.TextColumn("품목명", width="medium"),
        "매입원가(원)": st.column_config.NumberColumn("매입원가"),
        "목표마진(%)": st.column_config.NumberColumn("목표마진", format="%.1f%%"),
        "마진율(%)": st.column_config.NumberColumn("실제마진율", format="%.2f%%", disabled=True),
        "마진액(원)": st.column_config.NumberColumn("마진액", disabled=True),
        "목표대비(+/-)": st.column_config.NumberColumn("목표대비", format="%+d", disabled=True),
        "수수료율(%)": st.column_config.NumberColumn("수수료율", format="%.1f%%"),
        "수수료액(원)": st.column_config.NumberColumn("수수료액", disabled=True),
        "판매가(원)": st.column_config.NumberColumn("판매가(시세)"),
        "상태": st.column_config.TextColumn(disabled=True),
        "업데이트시각": st.column_config.TextColumn(disabled=True),
        "수정자": st.column_config.TextColumn(disabled=True)
    },
    hide_index=True
)

# 8. 컨트롤 버튼 로직
st.sidebar.markdown("---")
if st.sidebar.button("🔢 중간 계산하기 (화면 반영)", use_container_width=True):
    # 전송 전 화면에서 미리 계산 결과를 보여주는 기능
    st.session_state.df = calculate_engine(edited_df, actual_mode, target_mode)
    st.rerun()

if st.sidebar.button("🚀 클라우드 전송 (최종 저장)", use_container_width=True):
    with st.spinner('구글 시트에 14개 컬럼 데이터를 저장 중...'):
        # 최종 계산 수행
        final_df = calculate_engine(edited_df, actual_mode, target_mode)
        final_df['업데이트시각'] = datetime.now().strftime("%m/%d %H:%M")
        final_df['수정자'] = user_role
        
        # 클라우드 전송
        conn.update(spreadsheet=SHEET_NAME, worksheet="0", data=final_df)
        
        st.cache_data.clear()
        st.session_state.df = final_df
        st.sidebar.success("✅ 클라우드 동기화 완료!")
        st.rerun()

if st.sidebar.button("🔄 최신 데이터 불러오기", use_container_width=True):
    st.cache_data.clear()
    st.session_state.df = load_data()
    st.rerun()

# 하단 정보
st.sidebar.caption(f"v2.8 완전체 버전 | 접속: {datetime.now().strftime('%H:%M:%S')}")