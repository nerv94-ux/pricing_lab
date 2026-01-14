@ -4,10 +4,10 @@ import pandas as pd
from datetime import datetime

# 1. [구조 유지] 페이지 설정 및 제목
st.set_page_config(page_title="유기농 통합 가격 관리 시스템 v3.2", layout="wide")
st.title("🥬 가격 협업 플랫폼 v3.2")
st.set_page_config(page_title="유기농 통합 가격 관리 시스템 v3.3", layout="wide")
st.title("🥬 가격 협업 플랫폼 v3.3")

# 2. [교체] 구글 시트 보안 연결 설정 (v2.6 서비스 계정 방식)
# 2. [구조 유지] 구글 시트 보안 연결 설정
try:
    conn = st.connection("gsheets", type=GSheetsConnection)
    SHEET_NAME = st.secrets["connections"]["gsheets"]["spreadsheet"]
@ -15,32 +15,44 @@ except Exception as e:
    st.error("⚠️ 관리자 설정(Secrets)의 spreadsheet 이름이나 인증키를 확인해주세요.")
    st.stop()

# 3. [구조 유지] 14개 전체 컬럼 규격 정의 (단 한 글자도 생략 없음)
# 3. [구조 유지] 14개 전체 컬럼 규격 정의 (생략 없음)
ALL_COLUMNS = [
    "No", "역산모드", "상태", "품목명", "매입원가(원)", "목표마진(%)", 
    "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가(원)", "업데이트시각", "수정자"
]

# 4. [수정] 데이터 로드 함수 (14개 컬럼 강제 고정 및 데이터 형식 무결성 확보)
# 4. [수정/교체] 데이터 로드 함수 (데이터 형식 충돌 원천 차단)
@st.cache_data(ttl=10)
def load_data():
    try:
        # worksheet=0으로 첫 번째 탭을 강제 지정하여 읽어옵니다.
        # worksheet=0으로 첫 번째 탭을 읽어옵니다.
        df = conn.read(spreadsheet=SHEET_NAME, worksheet=0)
        
        # 14개 컬럼 순서 강제 고정 (시트에 없으면 빈 칸으로 생성)
        # 1. 컬럼 순서 및 존재 여부 강제 고정
        df = df.reindex(columns=ALL_COLUMNS)
        
        # [에러방지] 숫자형 컬럼들의 데이터 형식을 강제하여 API 오류를 차단합니다.
        # 2. [핵심 교체] 숫자형 컬럼 강제 변환 (StreamlitAPIException 방지)
        # 빈 값은 NaN이 아닌 0으로 처리하며, 명확히 숫자 타입으로 정의합니다.
        num_cols = ["No", "매입원가(원)", "목표마진(%)", "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가(원)"]
        df[num_cols] = df[num_cols].fillna(0).apply(pd.to_numeric, errors='coerce').fillna(0)
        for col in num_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        return df.fillna("")
        # 3. 불리언(체크박스) 및 문자열 형식 강제
        df["역산모드"] = df["역산모드"].astype(bool)
        df["상태"] = df["상태"].astype(str).replace("0", "🟢 정상")
        df["품목명"] = df["품목명"].astype(str).replace("0", "")
        
        return df
    except Exception as e:
        # 로드 실패 시에도 시스템이 멈추지 않도록 14칸 빈 틀을 제공합니다.
        return pd.DataFrame(columns=ALL_COLUMNS).fillna("")
        # 실패 시 구조에 맞는 빈 데이터프레임 생성
        empty_df = pd.DataFrame(columns=ALL_COLUMNS)
        num_cols = ["No", "매입원가(원)", "목표마진(%)", "마진율(%)", "마진액(원)", "목표대비(+/-)", "수수료율(%)", "수수료액(원)", "판매가(원)"]
        for col in num_cols:
            empty_df[col] = 0
        empty_df["역산모드"] = False
        return empty_df

# 5. [구조 유지] 사이드바 메뉴 및 권한 설정 (v2.3 100% 복원)
# 5. [구조 유지] 사이드바 메뉴 및 권한 설정
st.sidebar.header("🏢 실무 협업 센터")
user_role = st.sidebar.selectbox("접속 권한 선택", ["홍성유기농(공급사)", "유기농부(판매사)", "대표님(총괄)"])

@ -54,7 +66,7 @@ target_mode = st.sidebar.radio("목표 산출 기준", ["판매가 기준", "원
if 'df' not in st.session_state:
    st.session_state.df = load_data()

# 6. [구조 유지] 하이브리드 계산 엔진 (v2.3 원본 수식 100% 복원)
# 6. [구조 유지] 하이브리드 계산 엔진 (v2.3 원본 로직 100% 보존)
def calculate_hybrid(df, act_mode, tgt_mode):
    temp_df = df.copy()
    for i in range(len(temp_df)):
@ -68,7 +80,7 @@ def calculate_hybrid(df, act_mode, tgt_mode):
            name = str(temp_df.at[i, "품목명"]).replace("🔄 ", "")

            # A. 판매가/매입가 결정 로직 (역산 vs 정산)
            if is_rev: # [역산 모드] 판매가(시세) 기준으로 매입원가 산출
            if is_rev: # [역산 모드] 판매가 기준으로 매입원가 도출
                if tgt_mode == "판매가 기준":
                    cost = round(price * (1 - (f_rate + t_rate) / 100))
                else:
@ -84,7 +96,7 @@ def calculate_hybrid(df, act_mode, tgt_mode):
                temp_df.at[i, "판매가(원)"] = int(price)
                temp_df.at[i, "상태"], temp_df.at[i, "품목명"] = "🟢 정상", name

            # B. 결과값 상세 계산 (마진액, 마진율, 수수료, 목표대비 차액)
            # B. 결과값 상세 계산
            f_amt = round(price * (f_rate / 100))
            m_amt = int(price - cost - f_amt)
            
@ -106,11 +118,11 @@ def calculate_hybrid(df, act_mode, tgt_mode):
            
    return temp_df

# 7. [구조 유지] 메인 데이터 편집 화면 (14개 컬럼 세부 설정 100% 복원)
# 7. [구조 유지] 메인 데이터 편집 화면 (v2.3 컬럼 설정 100% 유지)
st.info(f"💡 현재 **[{user_role}]** 권한으로 작업 중입니다. 수정 후 '중간 계산' 또는 '클라우드 전송'을 누르세요.")

# 에디터 호출 전, 현재 세션 데이터에 ALL_COLUMNS가 모두 있는지 한 번 더 보증합니다.
st.session_state.df = st.session_state.df.reindex(columns=ALL_COLUMNS).fillna(0)
# 에디터 호출 전 최종 타입 검증 (교체 지점)
st.session_state.df["역산모드"] = st.session_state.df["역산모드"].astype(bool)

edited_df = st.data_editor(
    st.session_state.df,
@ -118,7 +130,7 @@ edited_df = st.data_editor(
    use_container_width=True,
    column_config={
        "No": st.column_config.NumberColumn(width="small"),
        "역산모드": st.column_config.CheckboxColumn("시세역산", help="체크 시 판매가(시세)를 기준으로 매입원가를 산출합니다."),
        "역산모드": st.column_config.CheckboxColumn("시세역산"),
        "상태": st.column_config.TextColumn(disabled=True),
        "품목명": st.column_config.TextColumn("품목명", width="medium"),
        "매입원가(원)": st.column_config.NumberColumn("매입원가"),
@ -135,22 +147,20 @@ edited_df = st.data_editor(
    hide_index=True
)

# 8. [수정/유지] 컨트롤 버튼 로직 (중간 계산 추가 및 클라우드 전송 최적화)
# 8. [구조 유지] 컨트롤 버튼 로직
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
        # 클라우드 업데이트
        conn.update(spreadsheet=SHEET_NAME, worksheet=0, data=final_df)
        
        st.cache_data.clear()
@ -165,4 +175,4 @@ if st.sidebar.button("🔄 최신 데이터 불러오기", use_container_width=T

# 9. [구조 유지] 하단 상태 정보 표기
st.sidebar.markdown("---")
st.sidebar.caption(f"Pricing Lab v3.2 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.sidebar.caption(f"Pricing Lab v3.3 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")