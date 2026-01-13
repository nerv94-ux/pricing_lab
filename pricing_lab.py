import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 1. 시스템 초기 설정 및 레이아웃
st.set_page_config(page_title="유기농 통합 가격 관리 시스템 v3.0", layout="wide")
st.title("🥬 홍성유기농-유기농부 가격 협업 플랫폼 v3.0")

# 2. 구글 시트 보안 연결 (Secrets 데이터 활용)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    SHEET_NAME = st.secrets["connections"]["gsheets"]["spreadsheet"]
except Exception as e:
    st.error("⚠️ 관리자 설정(Secrets)의 spreadsheet 이름이나 인증키가 올바르지 않습니다.")
    st.stop()

# 3. [생략 없음] 14개 전체 컬럼 표준 규격 정의
ALL_COLUMNS = [
    "No", "역산모드", "상태", "품목명", "매입원가(원)", "목표마진(%)", 
    "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가(원)", "업데이트시각", "수정자"
]

# 4. 데이터 로드 함수 (14개 컬럼 강제 고정 로직 포함)
@st.cache_data(ttl=10)
def load_data():
    try:
        # worksheet=0은 첫 번째 탭을 의미합니다. (문자열 "0"이 아닌 정수 0 사용)
        df = conn.read(spreadsheet=SHEET_NAME, worksheet=0)
        
        # 구글 시트에 데이터가 있든 없든 14개 컬럼을 강제로 생성하고 정렬합니다.
        df = df.reindex(columns=ALL_COLUMNS)
        return df.fillna(0)
    except Exception as e:
        # 오류 발생 시 빈 14개 컬럼의 틀을 반환합니다.
        return pd.DataFrame(columns=ALL_COLUMNS)

# 5. 사이드바 제어 센터 (v2.3 UI 100% 유지)
st.sidebar.header("🏢 실무 협업 센터")
user_role = st.sidebar.selectbox("현재 접속 권한", ["홍성유기농(공급사)", "유기농부(판매사)", "대표님(총괄)"])

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 가격 산출 로직 설정")
actual_mode = st.sidebar.radio("실제 마진율 산출 기준", ["판매가 기준 마진", "원가 기준 마진"])
target_mode = st.sidebar.radio("목표 가격 산출 기준", ["판매가 기준", "원가 기준"])

if 'df' not in st.session_state:
    st.session_state.df = load_data()

# 6. [생략 없음] 하이브리드 프라이싱 엔진 (v2.3 수식 100% 복원)
def run_full_pricing_engine(df, act_mode, tgt_mode):
    temp_df = df.copy()
    for i in range(len(temp_df)):
        try:
            # 1. 기본 변수 할당
            is_rev = bool(temp_df.at[i, "역산모드"])
            cost = float(temp_df.at[i, "매입원가(원)"])
            price = float(temp_df.at[i, "판매가(원)"])
            t_rate = float(temp_df.at[i, "목표마진(%)"])
            f_rate = float(temp_df.at[i, "수수료율(%)"])
            name = str(temp_df.at[i, "품목명"]).replace("🔄 ", "")

            # 2. 가격 결정 (역산 vs 정산)
            if is_rev: # [역산모드] 판매가(시세)를 기준으로 원가를 도출
                if tgt_mode == "판매가 기준":
                    # 원가 = 판매가 * (1 - (수수료율 + 목표마진율) / 100)
                    cost = round(price * (1 - (f_rate + t_rate) / 100))
                else:
                    # 원가 = (판매가 * (1 - 수수료율/100)) / (1 + 목표마진율/100)
                    cost = round((price * (1 - f_rate/100)) / (1 + t_rate/100))
                temp_df.at[i, "매입원가(원)"] = int(cost)
                temp_df.at[i, "상태"] = "🟠 역산"
                temp_df.at[i, "품목명"] = f"🔄 {name}"
            else: # [정산모드] 매입원가를 기준으로 판매가를 도출
                if tgt_mode == "판매가 기준":
                    denom = 1 - (f_rate + t_rate) / 100
                    price = round(cost / denom) if denom > 0 else 0
                else:
                    price = round(cost * (1 + (f_rate + t_rate) / 100))
                temp_df.at[i, "판매가(원)"] = int(price)
                temp_df.at[i, "상태"] = "🟢 정상"
                temp_df.at[i, "품목명"] = name

            # 3. 상세 지표 산출
            # 수수료액 = 판매가 * 수수료율
            f_amt = round(price * (f_rate / 100))
            # 마진액 = 판매가 - 원가 - 수수료액
            m_amt = int(price - cost - f_amt)
            
            # 실제 마진율 산출
            if act_mode == "판매가 기준 마진":
                m_rate = (m_amt / price * 100) if price > 0 else 0
            else:
                m_rate = (m_amt / cost * 100) if cost > 0 else 0
            
            # 목표 마진액 산출 (차액 계산용)
            if tgt_mode == "판매가 기준":
                t_amt = round(price * (t_rate/100))
            else:
                t_amt = round(cost * (t_rate/100))
            
            # 4. 데이터 프레임에 최종 결과값 반영
            temp_df.at[i, "마진율(%)"] = round(m_rate, 2)
            temp_df.at[i, "마진액(원)"] = int(m_amt)
            temp_df.at[i, "수수료액(원)"] = int(f_amt)
            temp_df.at[i, "목표대비(+/-)"] = int(m_amt - t_amt)
            
        except Exception:
            continue
            
    return temp_df

# 7. [생략 없음] 메인 에디터 및 14개 컬럼 세부 설정 (v2.3 UI 설정 100% 복원)
st.info(f"💡 현재 **[{user_role}]** 권한으로 작업 중입니다. 수치 변경 후 '중간 계산' 또는 '클라우드 전송'을 누르세요.")

edited_df = st.data_editor(
    st.session_state.df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "No": st.column_config.NumberColumn(width="small"),
        "역산모드": st.column_config.CheckboxColumn("시세역산", help="체크 시 판매가(시세)를 기준으로 매입원가를 도출합니다."),
        "상태": st.column_config.TextColumn(disabled=True),
        "품목명": st.column_config.TextColumn("품목명", width="medium"),
        "매입원가(원)": st.column_config.NumberColumn("매입원가"),
        "목표마진(%)": st.column_config.NumberColumn("목표마진(%)", format="%.1f%%"),
        "마진율(%)": st.column_config.NumberColumn("실제마진율(%)", format="%.2f%%", disabled=True),
        "마진액(원)": st.column_config.NumberColumn("마진금액", disabled=True),
        "목표대비(+/-)": st.column_config.NumberColumn("목표대비", format="%+d", disabled=True),
        "수수료율(%)": st.column_config.NumberColumn("수수료율(%)", format="%.1f%%"),
        "수수료액(원)": st.column_config.NumberColumn("수수료금액", disabled=True),
        "판매가(원)": st.column_config.NumberColumn("판매가(시세)"),
        "업데이트시각": st.column_config.TextColumn(disabled=True),
        "수정자": st.column_config.TextColumn(disabled=True)
    },
    hide_index=True
)

# 8. 컨트롤 버튼 및 동기화 로직
st.sidebar.markdown("---")
if st.sidebar.button("🔢 중간 계산하기 (화면 반영)", use_container_width=True):
    # 전송 전 화면에 계산 결과만 먼저 보여줍니다.
    st.session_state.df = run_full_pricing_engine(edited_df, actual_mode, target_mode)
    st.rerun()

if st.sidebar.button("🚀 클라우드 전송 (최종 저장)", use_container_width=True):
    with st.spinner('구글 시트 서버에 14개 컬럼 데이터를 기록 중...'):
        # 최종 계산 수행
        final_df = run_full_pricing_engine(edited_df, actual_mode, target_mode)
        final_df['업데이트시각'] = datetime.now().strftime("%m/%d %H:%M")
        final_df['수정자'] = user_role
        
        # [수정] worksheet=0으로 명시하여 '첫 번째 탭'에 강제 저장
        conn.update(spreadsheet=SHEET_NAME, worksheet=0, data=final_df)
        
        st.cache_data.clear()
        st.session_state.df = final_df
        st.sidebar.success("✅ 클라우드 동기화가 완료되었습니다!")
        st.rerun()

if st.sidebar.button("🔄 최신 데이터 불러오기", use_container_width=True):
    st.cache_data.clear()
    st.session_state.df = load_data()
    st.rerun()

st.sidebar.caption(f"Pricing Lab v3.0 | {datetime.now().year} Hongseong Organic")