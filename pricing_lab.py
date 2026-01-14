import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# 1. [구조 유지] 페이지 설정 및 제목
st.set_page_config(page_title="유기농 통합 가격 관리 시스템 v3.7", layout="wide")
st.title("🥬 홍성유기농-유기농부 가격 협업 플랫폼 v3.7")

# 2. [구조 유지] 구글 시트 보안 연결 설정
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    SHEET_NAME = st.secrets["connections"]["gsheets"]["spreadsheet"]
except Exception as e:
    st.error("⚠️ 관리자 설정(Secrets)의 spreadsheet 이름이나 인증키를 확인해주세요.")
    st.stop()

# 3. [구조 유지] 14개 전체 컬럼 규격 정의 ("판매가" 명칭 반영 완료)
ALL_COLUMNS = [
    "No", "역산모드", "상태", "품목명", "매입원가(원)", "목표마진(%)", 
    "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가", "업데이트시각", "수정자"
]

# 4. [구조 유지] 데이터 로드 함수 (형식 강제 및 무결성 유지)
@st.cache_data(ttl=5)
def load_data():
    try:
        # worksheet=0으로 첫 번째 탭을 읽어옵니다.
        df = conn.read(spreadsheet=SHEET_NAME, worksheet=0)
        
        # 1. 컬럼 순서 및 존재 여부 강제 고정
        df = df.reindex(columns=ALL_COLUMNS)
        
        # 2. 숫자형 데이터 정제 (입력 오류 방지)
        num_cols = ["No", "매입원가(원)", "목표마진(%)", "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가"]
        for col in num_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        # 3. 불리언 및 문자열 형식 강제
        df["역산모드"] = df["역산모드"].astype(bool)
        df["상태"] = df["상태"].astype(str).replace("0", "🟢 정상")
        df["품목명"] = df["품목명"].astype(str).replace("0", "")
        df["업데이트시각"] = df["업데이트시각"].astype(str).replace("0", "-")
        df["수정자"] = df["수정자"].astype(str).replace("0", "-")
        
        return df
    except Exception as e:
        empty_df = pd.DataFrame(columns=ALL_COLUMNS)
        num_cols = ["No", "매입원가(원)", "목표마진(%)", "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가"]
        for col in num_cols:
            empty_df[col] = 0
        empty_df["역산모드"] = False
        return empty_df

# 5. [구조 유지] 사이드바 메뉴 및 품목 검색
st.sidebar.header("🏢 실무 협업 센터")

# [유지] 품목 검색 필터
search_term = st.sidebar.text_input("🔍 품목명 검색", placeholder="검색어를 입력하세요...")

user_role = st.sidebar.selectbox("접속 권한 선택", ["홍성유기농(공급사)", "유기농부(판매사)", "대표님(총괄)"])

st.sidebar.markdown("---")
st.sidebar.subheader("⚙️ 마진 및 목표 설정")
actual_mode = st.sidebar.radio("마진율 계산 기준", ["판매가 기준 마진", "원가 기준 마진"], 
                             help="실제 마진율을 (마진액/판매가)로 할지 (마진액/원가)로 할지 결정합니다.")
target_mode = st.sidebar.radio("목표 산출 기준", ["판매가 기준", "원가 기준"], 
                             help="목표 마진율을 판매가에 곱할지, 원가에 곱할지 결정합니다.")

# 세션 상태 데이터 로드
if 'df' not in st.session_state:
    st.session_state.df = load_data()

# 6. [구조 유지] 하이브리드 계산 엔진 (판매가 명칭 매칭 수정 완료)
def calculate_hybrid(df, act_mode, tgt_mode):
    temp_df = df.copy()
    for i in range(len(temp_df)):
        try:
            # 변수 추출 시 "판매가" 컬럼명 정확히 매칭
            is_rev = bool(temp_df.at[i, "역산모드"])
            cost = float(temp_df.at[i, "매입원가(원)"])
            price = float(temp_df.at[i, "판매가"])
            t_rate = float(temp_df.at[i, "목표마진(%)"])
            f_rate = float(temp_df.at[i, "수수료율(%)"])
            
            # 아이콘 중복 방지를 위해 기존 아이콘 제거 후 재설정
            clean_name = str(temp_df.at[i, "품목명"]).replace("🔄 ", "").replace("🚨 ", "").replace("🔻 ", "")

            # A. 가격 결정 로직
            if is_rev:
                if tgt_mode == "판매가 기준":
                    cost = round(price * (1 - (f_rate + t_rate) / 100))
                else:
                    cost = round((price * (1 - f_rate/100)) / (1 + t_rate/100))
                temp_df.at[i, "매입원가(원)"] = int(cost)
                status_icon, name_prefix = "🟠", f"🔄 {clean_name}"
            else:
                if tgt_mode == "판매가 기준":
                    denom = 1 - (f_rate + t_rate) / 100
                    price = round(cost / denom) if denom > 0 else 0
                else:
                    price = round(cost * (1 + (f_rate + t_rate) / 100))
                temp_df.at[i, "판매가"] = int(price)
                status_icon, name_prefix = "🟢", clean_name

            # B. 상세 수식 계산
            f_amt = round(price * (f_rate / 100))
            m_amt = int(price - cost - f_amt)
            
            if act_mode == "판매가 기준 마진":
                m_rate = (m_amt / price * 100) if price > 0 else 0
            else:
                m_rate = (m_amt / cost * 100) if cost > 0 else 0
            
            t_amt = round(price * (t_rate/100)) if tgt_mode == "판매가 기준" else round(cost * (t_rate/100))
            
            # [유지] 조건부 알림 및 경고 로직
            if price < (cost + f_amt) and price > 0:
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🚨 가격역전", f"🚨 {name_prefix}"
            elif m_amt < t_amt:
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = f"{status_icon} 목표미달", f"🔻 {name_prefix}"
            else:
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = f"{status_icon} 정상", name_prefix

            temp_df.at[i, "마진율(%)"], temp_df.at[i, "마진액(원)"] = round(m_rate, 2), int(m_amt)
            temp_df.at[i, "수수료액(원)"], temp_df.at[i, "목표대비(+/-)"] = int(f_amt), int(m_amt - t_amt)
        except Exception:
            continue
    return temp_df

# 7. [교체] 포커스 유지형 라이브 에디터 (st.rerun 제거 및 직접 동기화)
st.info(f"💡 접속: **[{user_role}]** | 값 입력 후 엔터나 탭을 치면 배경에서 자동 계산됩니다.")

# 필터링 적용 (화면 표시용)
display_df = st.session_state.df.copy()
if search_term:
    display_df = display_df[display_df["품목명"].str.contains(search_term, na=False, case=False)]

# [수정] 렌더링 직전에 항상 계산 엔진을 돌려 실시간성을 확보합니다.
st.session_state.df = calculate_hybrid(st.session_state.df, actual_mode, target_mode)

# 데이터 편집기 (포커스 유지를 위해 key 설정 및 rerun 배제)
edited_df = st.data_editor(
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
    key="main_pricing_editor" # 고유 키 유지
)

# [교체 핵심] 변경 사항을 세션에 반영하되, 화면을 강제로 새로고침(rerun)하지 않아 포커스를 유지합니다.
if not display_df.equals(edited_df):
    st.session_state.df.update(edited_df)
    # 별도의 rerun 없이 다음 상호작용 시 calculate_hybrid가 자동 적용됨

# 8. [구조 유지] 컨트롤 버튼 로직
st.sidebar.markdown("---")

if st.sidebar.button("🚀 클라우드 전송 (저장/공유)", use_container_width=True):
    with st.spinner('구글 시트에 14개 컬럼 데이터 동기화 중...'):
        # 전송 직전 최종 계산
        final_df = calculate_hybrid(st.session_state.df, actual_mode, target_mode)
        final_df['업데이트시각'] = datetime.now().strftime("%m/%d %H:%M")
        final_df['수정자'] = user_role
        
        conn.update(spreadsheet=SHEET_NAME, worksheet=0, data=final_df)
        
        st.cache_data.clear()
        st.session_state.df = final_df
        st.sidebar.success("✅ 클라우드 저장 완료!")
        st.rerun()

if st.sidebar.button("🔄 최신 데이터 불러오기", use_container_width=True):
    st.cache_data.clear()
    st.session_state.df = load_data()
    st.rerun()

# 9. [구조 유지] 하단 상태 정보 표기
st.sidebar.markdown("---")
st.sidebar.caption(f"Pricing Lab v3.7 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")