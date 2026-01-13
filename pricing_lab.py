import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 1. [구조 유지] 페이지 설정 및 제목
st.set_page_config(page_title="유기농 통합 가격 관리 시스템 v3.2", layout="wide")
st.title("🥬 홍성유기농-유기농부 가격 협업 플랫폼 v3.2")

# 2. [교체] 구글 시트 보안 연결 설정 (v2.6 서비스 계정 방식)
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    SHEET_NAME = st.secrets["connections"]["gsheets"]["spreadsheet"]
except Exception as e:
    st.error("⚠️ 관리자 설정(Secrets)의 spreadsheet 이름이나 인증키를 확인해주세요.")
    st.stop()

# 3. [구조 유지] 14개 전체 컬럼 규격 정의 (단 한 글자도 생략 없음)
ALL_COLUMNS = [
    "No", "역산모드", "상태", "품목명", "매입원가(원)", "목표마진(%)", 
    "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가(원)", "업데이트시각", "수정자"
]

# 4. [수정] 데이터 로드 함수 (14개 컬럼 강제 고정 및 데이터 형식 무결성 확보)
@st.cache_data(ttl=10)
def load_data():
    try:
        # worksheet=0으로 첫 번째 탭을 강제 지정하여 읽어옵니다.
        df = conn.read(spreadsheet=SHEET_NAME, worksheet=0)
        
        # 14개 컬럼 순서 강제 고정 (시트에 없으면 빈 칸으로 생성)
        df = df.reindex(columns=ALL_COLUMNS)
        
        # [에러방지] 숫자형 컬럼들의 데이터 형식을 강제하여 API 오류를 차단합니다.
        num_cols = ["No", "매입원가(원)", "목표마진(%)", "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가(원)"]
        df[num_cols] = df[num_cols].fillna(0).apply(pd.to_numeric, errors='coerce').fillna(0)
        
        return df.fillna("")
    except Exception as e:
        # 로드 실패 시에도 시스템이 멈추지 않도록 14칸 빈 틀을 제공합니다.
        return pd.DataFrame(columns=ALL_COLUMNS).fillna("")

# 5. [구조 유지] 사이드바 메뉴 및 권한 설정 (v2.3 100% 복원)
st.sidebar.header("🏢 실무 협업 센터")
user_role = st.sidebar.selectbox("접속 권한 선택", ["홍성유기농(공급사)", "유기농부(판매사)", "대표님(총괄)"])

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 마진 및 목표 설정")
actual_mode = st.sidebar.radio("마진율 계산 기준", ["판매가 기준 마진", "원가 기준 마진"], 
                             help="실제 마진율을 (마진액/판매가)로 할지 (마진액/원가)로 할지 결정합니다.")
target_mode = st.sidebar.radio("목표 산출 기준", ["판매가 기준", "원가 기준"], 
                             help="목표 마진율을 판매가에 곱할지, 원가에 곱할지 결정합니다.")

if 'df' not in st.session_state:
    st.session_state.df = load_data()

# 6. [구조 유지] 하이브리드 계산 엔진 (v2.3 원본 수식 100% 복원)
def calculate_hybrid(df, act_mode, tgt_mode):
    temp_df = df.copy()
    for i in range(len(temp_df)):
        try:
            # 기본 변수 추출
            is_rev = bool(temp_df.at[i, "역산모드"])
            cost = float(temp_df.at[i, "매입원가(원)"])
            price = float(temp_df.at[i, "판매가(원)"])
            t_rate = float(temp_df.at[i, "목표마진(%)"])
            f_rate = float(temp_df.at[i, "수수료율(%)"])
            name = str(temp_df.at[i, "품목명"]).replace("🔄 ", "")

            # A. 판매가/매입가 결정 로직 (역산 vs 정산)
            if is_rev: # [역산 모드] 판매가(시세) 기준으로 매입원가 산출
                if tgt_mode == "판매가 기준":
                    cost = round(price * (1 - (f_rate + t_rate) / 100))
                else:
                    cost = round((price * (1 - f_rate/100)) / (1 + t_rate/100))
                temp_df.at[i, "매입원가(원)"] = int(cost)
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🟠 역산", f"🔄 {name}"
            else: # [정산 모드] 매입원가 기준으로 판매가 산출
                if tgt_mode == "판매가 기준":
                    denom = 1 - (f_rate + t_rate) / 100
                    price = round(cost / denom) if denom > 0 else 0
                else:
                    price = round(cost * (1 + (f_rate + t_rate) / 100))
                temp_df.at[i, "판매가(원)"] = int(price)
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🟢 정상", name

            # B. 결과값 상세 계산 (마진액, 마진율, 수수료, 목표대비 차액)
            f_amt = round(price * (f_rate / 100))
            m_amt = int(price - cost - f_amt)
            
            # 마진율 계산
            if act_mode == "판매가 기준 마진":
                m_rate = (m_amt / price * 100) if price > 0 else 0
            else:
                m_rate = (m_amt / cost * 100) if cost > 0 else 0
            
            # 목표 마진액 계산 (차액 비교용)
            t_amt = round(price * (t_rate/100)) if tgt_mode == "판매가 기준" else round(cost * (t_rate/100))
            
            temp_df.at[i, "마진율(%)"] = round(m_rate, 2)
            temp_df.at[i, "마진액(원)"] = int(m_amt)
            temp_df.at[i, "수수료액(원)"] = int(f_amt)
            temp_df.at[i, "목표대비(+/-)"] = int(m_amt - t_amt)
        except Exception:
            continue
            
    return temp_df

# 7. [구조 유지] 메인 데이터 편집 화면 (14개 컬럼 세부 설정 100% 복원)
st.info(f"💡 현재 **[{user_role}]** 권한으로 작업 중입니다. 수정 후 '중간 계산' 또는 '클라우드 전송'을 누르세요.")

# 에디터 호출 전, 현재 세션 데이터에 ALL_COLUMNS가 모두 있는지 한 번 더 보증합니다.
st.session_state.df = st.session_state.df.reindex(columns=ALL_COLUMNS).fillna(0)

edited_df = st.data_editor(
    st.session_state.df,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "No": st.column_config.NumberColumn(width="small"),
        "역산모드": st.column_config.CheckboxColumn("시세역산", help="체크 시 판매가(시세)를 기준으로 매입원가를 산출합니다."),
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

# 8. [수정/유지] 컨트롤 버튼 로직 (중간 계산 추가 및 클라우드 전송 최적화)
st.sidebar.markdown("---")

if st.sidebar.button("🔢 중간 계산하기 (화면 반영)", use_container_width=True):
    # 전송 전에 화면상에서 수식을 즉시 계산하여 세션에 반영합니다.
    st.session_state.df = calculate_hybrid(edited_df, actual_mode, target_mode)
    st.rerun()

if st.sidebar.button("🚀 클라우드 전송 (저장/공유)", use_container_width=True):
    with st.spinner('구글 시트에 14개 컬럼 데이터를 기록 중...'):
        # 최종 계산 수행 후 이력 추가
        final_df = calculate_hybrid(edited_df, actual_mode, target_mode)
        final_df['업데이트시각'] = datetime.now().strftime("%m/%d %H:%M")
        final_df['수정자'] = user_role
        
        # [교체] 구글 시트 업데이트 로직 (worksheet=0 사용)
        conn.update(spreadsheet=SHEET_NAME, worksheet=0, data=final_df)
        
        st.cache_data.clear()
        st.session_state.df = final_df
        st.sidebar.success("✅ 클라우드 동기화 완료!")
        st.rerun()

if st.sidebar.button("🔄 최신 데이터 불러오기", use_container_width=True):
    st.cache_data.clear()
    st.session_state.df = load_data()
    st.rerun()

# 9. [구조 유지] 하단 상태 정보 표기
st.sidebar.markdown("---")
st.sidebar.caption(f"Pricing Lab v3.2 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")