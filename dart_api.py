
# version 0.0.4

# dart : http://dart.fss.or.kr/
# 오픈Dart: https://opendart.fss.or.kr/
# Dart-fss(라이브러리 문서): https://dart-fss.readthedocs.io/en/latest/
# 예제 쿼리 (2015년도 기준, 0 < 2013영업이익 < 2014영업이익 < 2015영업이익 종목
# ** 촬영 후 아래 쿼리 수정 하였습니다.
# select * from dart where fs_nm = '재무제표' and bsns_year = '2015' and account_nm ='영업이익' and 0 < bfefrmtrm_amount and bfefrmtrm_amount < frmtrm_amount and frmtrm_amount < thstrm_amount

# (별도, 개별)재무제표 vs 연결재무제표
# (별도, 개별)재무제표
#       - 지배기업의 재무정보만 표시 (종속기업이 있는 경우는 별도 재무제표, 없는 경우는 개별 재무제표)
#       - 종속기업과 내부거래가 많은 경우 별도재무제표 실적이 확대
# 연결재무제표 
#       - 지배기업과 종속기업의 재무정보를 하나로 합산
#       - 계열사를 여러개 거느리고 있고 지분구조도 복잡하게 얽히고 섥힌 기업일수록 연결재무제표가 별도재무제표보다 중요
#       - 종속기업, 모기업 간 내부거래를 제거한 재무제표
#       - 해당 기업이 외부 고객과 얼마나 거래를 했는지 효과적으로 구분하기 위해 만든 제도
#       - 종속기업이 없는 경우는 연결재무제표가 없다 (DB에도 저장 안됨)

import datetime
import warnings
warnings.simplefilter(action='ignore', category=UserWarning)

import dart_fss as dart
import pymysql
import sqlalchemy
from dart_fss.errors import NoDataReceived
from pandas import DataFrame
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL

from library import cf

pymysql.install_as_MySQLdb()


class DARTApi:
    def __init__(self):
        db_url = URL(
            drivername="mysql+mysqldb",
            username=cf.db_id,
            password=cf.db_passwd,
            host=cf.db_ip,
            port=cf.db_port,
            database='daily_buy_list'
        )
        self.db_engine = create_engine(db_url)
        # 자신의 Dart API 인증키 입력
        dart.set_api_key(cf.dart_api_key)
        # DART 공시된 회사 리스트 반환
        self.crp_list = dart.get_corp_list()
        # 모든 종목 코드 가져오기
        self._get_stock_item_all()

    def _get_stock_item_all(self):
        sql = """
           SELECT code, code_name
           FROM stock_item_all
           WHERE code not in (
               SELECT code FROM stock_konex
           ) ORDER BY code
           """  # Konex 제외 (기업공시 데이터 미제공)

        self.stock_item_all = self.db_engine.execute(sql).fetchall()

    # table 존재 여부 확인
    def is_table_exist(self, table_name):
        sql = """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'daily_buy_list' AND table_name = '{}'
        """.format(table_name)
        rows = self.db_engine.execute(sql).fetchall()
        if len(rows) == 1:
            return True
        elif len(rows) == 0:
            return False

    def is_exist_data(self, year, code):
        if self.is_table_exist('dart'):
            sql = "SELECT code FROM dart WHERE bsns_year = '{}' AND code = '{}'".format(year, code)
            rows = self.db_engine.execute(sql).fetchall()
            if rows:
                return True
            else:
                return False
        # table 자체가 없으면 False 반환
        else:
            return False

    # 이어 받아올 가장 최신의 데이터 위치를 가져오는 함수
    def _get_latest_index(self, year):
        if self.is_table_exist('dart'):
            try:
                latest_code = self.db_engine.execute(f"""
                    SELECT code
                    FROM dart
                    WHERE bsns_year = {year}
                    ORDER BY code DESC
                    LIMIT 1
                """).first()[0]
            except (IndexError, TypeError):
                return 0
            for i, (code, _) in enumerate(self.stock_item_all):
                if code == latest_code:
                    return i
        return 0

    def get_all_econ_info(self, year):
        print("{} start!".format(year))

        # 추가 된 코드
        # 크롤링 중간에 꺼졌을 때 이어받기 위해 설정
        latest_index = self._get_latest_index(year)

        num = len(self.stock_item_all)  # print 용 변수
        count = latest_index  # print 용 변수
        for stock_code in self.stock_item_all[latest_index:]:
            count += 1
            code = stock_code[0]
            code_name = stock_code[1]
            print("{} 년도 ++++++++++++++ {} ++++++++++++++ {} / {}".format(year, code_name, count, num))

            # 데이터가 있으면 넘어가는 로직
            if self.is_exist_data(year, code):
                print("{} 년도 {} 데이터는 이미 존재한다!".format(year, code_name))
                continue

            print("insert {} {}".format(year, code_name))
            corp_class = self.crp_list.find_by_stock_code(code)

            # corp_class 가 none값 인지 확인
            if corp_class:
                corp_code = corp_class.to_dict()['corp_code']
            else:
                print("{} 의 corp_class 데이터가 조회되지 않습니다.".format(code_name))
                continue
            try:
                """
                dart.api.finance.get_single_corp(corp_code: str, bsns_year: str, reprt_code: str)

                corp_code: corp_code(종목코드가 아님, 공시대상회사의 고유번호(8자리)),
                bsns_year: 연도를(사업연도(4자리))
                reprt_code:
                    1분기보고서 : 11013, 반기보고서 : 11012, 3분기보고서 : 11014, 사업보고서 : 11011
                """
                res = dart.api.finance.get_single_corp(corp_code, str(year), '11011')

            except NoDataReceived as e:
                print("{} 년도 {} ({}) 데이터는 조회되지 않습니다.".format(year, code_name, code))
                continue
            df = DataFrame(res['list'])

            # 콤마 제거
            # 당해 연도
            df['thstrm_amount'] = df['thstrm_amount'].str.replace(',', '')
            # 1년 전
            df['frmtrm_amount'] = df['frmtrm_amount'].str.replace(',', '')
            # 2년 전
            df['bfefrmtrm_amount'] = df['bfefrmtrm_amount'].str.replace(',', '')

            # - 가 있는 컬럼은 None으로 변경
            df.loc[df.thstrm_amount == '-', 'thstrm_amount'] = None
            df.loc[df.frmtrm_amount == '-', 'frmtrm_amount'] = None
            df.loc[df.bfefrmtrm_amount == '-', 'bfefrmtrm_amount'] = None

            # stock_code 라는 컬럼명을 code로 변경
            df = df.rename(columns={'stock_code': 'code'})

            # 데이터프레임에 코드명 컬럼이 없어서 새롭게 생성
            df['code_name'] = code_name
            df.to_sql('dart', self.db_engine, if_exists='append',
                      dtype={
                          'thstrm_amount': sqlalchemy.types.BIGINT,
                          'frmtrm_amount': sqlalchemy.types.BIGINT,
                          'bfefrmtrm_amount': sqlalchemy.types.BIGINT
                      }
                      )

    def get_recent_5y(self):
        # 최근 5년 조회 가능
        this_year = datetime.date.today().year
        for date in range(this_year - 5, this_year):
            self.get_all_econ_info(date)


if __name__ == "__main__":
    dartapi = DARTApi()
    dartapi.get_recent_5y()
    print("dart 크롤링을 성공적으로 마쳤습니다.")
