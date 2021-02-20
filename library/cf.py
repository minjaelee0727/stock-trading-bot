
# db 계정
db_id='root' # [mysql ID를 넣어주세요]
# db ip
db_ip='localhost'
# db 패스워드
db_passwd='Ehsahdmwk2580' # [mysql password 를 넣어주세요]

# db port가 3306이 아닌 다른 port를 사용 하시는 분은 아래 변수에 포트에 맞게 수정하셔야합니다.
db_port='3306'

# 모의 투자 계좌번호를 넣는다. 모의 투자 계좌는 3개월에 한번씩 만료 되기 때문에 3개월 이용 후 재신청 하게 되면 계좌 번호가 변경된다.
# 이때 계정이 존재 하지 않는다!!! 는 에러가 뜰텐데 그때 변경 된 계좌번호를 다시 아래 imi1_account 변수에 넣으면 된다.
# 계좌 번호 쉽게 알아보는법:  콘솔창에 보면 상단 부분에 로그로 "계좌번호 :  " 옆에 출력이 된다
imi1_accout="8151209911" # [모의투자 계좌번호를 넣어주세요. 주의! 10자리 계좌번호입니다. 모의투자는 8자리 계좌번호 뒤에 11, 실전은 10이 붙어 있음]

# imi1_simul_num은 알고리즘의 번호이다. 새로운 알고리즘으로 새롭게 database를 구축해서 운영하고 싶을 경우 번호를 2, 3, 4 ... 순차적으로 올려 주면 된다.
imi1_simul_num=1
imi1_db_name = "JackBot"+str(imi1_simul_num)+"_imi1"


# 아래는 실전 투자 계좌번호를 넣는다.
real_account=""
real_simul_num=1
real_db_name="JackBot"+str(real_simul_num)


real_daily_craw_db_name = "daily_craw"
real_daily_buy_list_db_name = "daily_buy_list"

# daily_buy_list database의 날짜 테이블을 과거 어떤 시점 부터 만들 것인지 설정 하는 변수
start_daily_buy_list='20190102'

# openapi 1회 조회 시 대기 시간(0.2 보다-> 0.3이 안정적)
TR_REQ_TIME_INTERVAL = 0.3

# n회 조회를 1번 발생시킨 경우 대기 시간
TR_REQ_TIME_INTERVAL_LONG = 1

# api를 최대 몇 번까지 호출 하고 봇을 끌지 설정 하는 옵션
max_api_call = 999

# dart api key (고급클래스에서 소개)
dart_api_key = ''

# etf 사용 여부 (고급클래스에서 소개)
use_etf = False
