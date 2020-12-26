
from pandas import DataFrame
import sys

import datetime
from sqlalchemy import create_engine
import library.cf
import pymysql
import pymysql.cursors


pymysql.install_as_MySQLdb()
import MySQLdb



# jango_data 테이블 이외 추가 컬럼 설명
# account : 시뮬레이션 번호
# total_date_count : 총 매수한 일자 수
# total_profitcut_rate : 익절률 ( 총익절종목수 / 총매수종목수 ) * 100
# total_buy_count : 총 매수 종목수


class simul_scraper():
    def __init__(self):
        self.cf = library.cf
        if len(sys.argv) == 1:
            self.start_db_num = int(input("start_db_num: "))
        # db_setting
        self.db_setting()
        # simul_scrap db생성
        if not self.is_database_exist('simul_scrap'):
            self.create_database('simul_scrap')

        # 몇 번째 db까지 정렬할지 설정
        self.simul_db_range = 1000

        # simul_scrap db에 ranking 테이블이 있는지 확인 후 있으면 삭제
        if self.is_scrap_table_exist("ranking"):
            self.drop_table('ranking')

        # 데이터프레임을 만들 때 사용할 컬럼 리스트 설정
        self.set_jango_list()

        # simulator db의 최종 수익률을 (jango_data의 가장 최신 row) ranking table에 넣는다
        self.set_scraped_db()

        # ranking 테이블을 수익률 순 재정렬
        self.set_orderby_scraped_db()


    # 데이터 베이스를 만드는 함수
    def create_database(self,db_name):
        print("create_database!!! {}".format(db_name))
        sql = 'CREATE DATABASE {}'
        self.db_conn.cursor().execute(sql.format(db_name))

    # 봇 데이터 베이스 존재 여부 확인 함수
    def is_database_exist(self,db_name):
        sql = "SELECT 1 FROM Information_schema.SCHEMATA WHERE SCHEMA_NAME = '{}'"
        rows = self.db_conn.cursor().execute(sql.format(db_name))
        if rows:
            print(f"{db_name} 데이터 베이스가 존재한다! ")
            return True
        else:
            print(f"{db_name} 데이터 베이스가 존재하지 않는다! ")
            return False

    # 스크랩 시작하는 simulator의 가장 최종 jango_data일자를 가져온다
    def get_jango_data_last_date(self):
        self.engine_start_db = create_engine(
            "mysql+mysqldb://" + self.cf.db_id + ":" + self.cf.db_passwd + "@" + self.cf.db_ip + ":" + self.cf.db_port + "/" + "simulator" + str(
                self.start_db_num),
            encoding='utf-8')
        sql = "SELECT date from jango_data order by date desc limit 1"
        return self.engine_start_db.execute(sql).fetchall()[0][0]



    # simul_scrap에 jango_data 테이블이 있는지 확인
    def is_scrap_table_exist(self, table_name):
        sql = "select 1 from information_schema.tables where table_schema = '%s' and table_name = '%s'"
        rows = self.engine_simul_scrap.execute(sql % ('simul_scrap', table_name)).fetchall()

        if len(rows) == 1:
            return True
        else:
            return False

    # 각 simulator db에 jango_data 테이블이 있는지 확인
    def is_simul_table_exist(self, db_name, table_name):
        sql = "select 1 from information_schema.tables where table_schema = '%s' and table_name = '%s'"
        rows = self.engine_simulator.execute(sql % (db_name, table_name)).fetchall()

        if len(rows) == 1:
            return True
        else:
            return False
    # 데이터프레임을 만들 때 사용할 컬럼 리스트 설정
    def set_jango_list(self):
        self.jango_list = ['account', 'date', 'today_earning_rate', 'sum_valuation_profit', 'total_profit',
                           'today_profit',
                           'today_profitcut_count', 'today_losscut_count', 'today_profitcut', 'today_losscut',
                           'd2_deposit', 'total_possess_count', 'today_buy_count', 'today_buy_list_count',
                           'today_reinvest_count',
                           'today_cant_reinvest_count'
                            , 'total_asset',
                           'total_invest',
                           'sum_item_total_purchase', 'total_evaluation', 'today_rate',
                           'today_invest_price', 'today_reinvest_price',
                           'today_sell_price', 'volume_limit', 'reinvest_point', 'sell_point',
                           'max_reinvest_count', 'invest_limit_rate', 'invest_unit',
                           'rate_std_sell_point', 'limit_money', 'total_profitcut', 'total_losscut',
                           'total_profitcut_count',
                           'total_losscut_count', 'loan_money', 'start_kospi_point',
                           'start_kosdaq_point', 'end_kospi_point', 'end_kosdaq_point',
                           'today_buy_total_sell_count',
                           'today_buy_total_possess_count', 'today_buy_today_profitcut_count',
                           'today_buy_today_profitcut_rate', 'today_buy_today_losscut_count',
                           'today_buy_today_losscut_rate',
                           'today_buy_total_profitcut_count', 'today_buy_total_profitcut_rate',
                           'today_buy_total_losscut_count', 'today_buy_total_losscut_rate',
                           'today_buy_reinvest_count0_sell_count',
                           'today_buy_reinvest_count1_sell_count', 'today_buy_reinvest_count2_sell_count',
                           'today_buy_reinvest_count3_sell_count', 'today_buy_reinvest_count4_sell_count',
                           'today_buy_reinvest_count4_sell_profitcut_count',
                           'today_buy_reinvest_count4_sell_losscut_count',
                           'today_buy_reinvest_count5_sell_count',
                           'today_buy_reinvest_count5_sell_profitcut_count',
                           'today_buy_reinvest_count5_sell_losscut_count',
                           'today_buy_reinvest_count0_remain_count',
                           'today_buy_reinvest_count1_remain_count', 'today_buy_reinvest_count2_remain_count',
                           'today_buy_reinvest_count3_remain_count', 'today_buy_reinvest_count4_remain_count',
                           'today_buy_reinvest_count5_remain_count']

        self.jango_list_temp = ['account', 'date', 'today_earning_rate', 'sum_valuation_profit', 'total_profit',
                                'today_profit',
                                'today_profitcut_count', 'today_losscut_count', 'today_profitcut', 'today_losscut',
                                'd2_deposit', 'total_possess_count', 'today_buy_count', 'today_buy_list_count',
                                'today_reinvest_count',
                                'today_cant_reinvest_count'
                                , 'total_asset',
                                'total_invest',
                                'sum_item_total_purchase', 'total_evaluation', 'today_rate',
                                'today_invest_price', 'today_reinvest_price',
                                'today_sell_price', 'volume_limit', 'reinvest_point', 'sell_point',
                                'max_reinvest_count', 'invest_limit_rate', 'invest_unit',
                                'rate_std_sell_point', 'limit_money', 'total_profitcut', 'total_losscut',
                                'total_profitcut_count',
                                'total_losscut_count', 'loan_money', 'start_kospi_point',
                                'start_kosdaq_point', 'end_kospi_point', 'end_kosdaq_point',
                                'today_buy_total_sell_count',
                                'today_buy_total_possess_count', 'today_buy_today_profitcut_count',
                                'today_buy_today_profitcut_rate', 'today_buy_today_losscut_count',
                                'today_buy_today_losscut_rate',
                                'today_buy_total_profitcut_count', 'today_buy_total_profitcut_rate',
                                'today_buy_total_losscut_count', 'today_buy_total_losscut_rate',
                                'today_buy_reinvest_count0_sell_count',
                                'today_buy_reinvest_count1_sell_count', 'today_buy_reinvest_count2_sell_count',
                                'today_buy_reinvest_count3_sell_count', 'today_buy_reinvest_count4_sell_count',
                                'today_buy_reinvest_count4_sell_profitcut_count',
                                'today_buy_reinvest_count4_sell_losscut_count',
                                'today_buy_reinvest_count5_sell_count',
                                'today_buy_reinvest_count5_sell_profitcut_count',
                                'today_buy_reinvest_count5_sell_losscut_count',
                                'today_buy_reinvest_count0_remain_count',
                                'today_buy_reinvest_count1_remain_count', 'today_buy_reinvest_count2_remain_count',
                                'today_buy_reinvest_count3_remain_count', 'today_buy_reinvest_count4_remain_count',
                                'today_buy_reinvest_count5_remain_count', 'total_date_count', 'total_profitcut_rate',
                                'total_buy_count']


    def set_jango_df(self, rows):
        jango_df = DataFrame(rows, columns=self.jango_list)

        sql = "SELECT count(*) FROM `" + self.simul_db_name + "`.jango_data"
        rows = self.engine_simulator.execute(sql).fetchall()

        # 그냥 이게 추가하는방식  self.jango[0]['total_date_count'] 이거아님, loc도 넣는거 아님
        # 총 매수한 일자 수
        jango_df['total_date_count'] = rows[0][0]

        if len(jango_df):
            total_profitcut_count = jango_df.loc[0, 'total_profitcut_count']
            total_buy_count = total_profitcut_count + jango_df.loc[0, 'total_losscut_count']
            # 익절률 ( 익절종목수 / 총매수종목수 ) * 100
            jango_df['total_profitcut_rate'] = round(
                total_profitcut_count / (total_buy_count) * 100, 2)
            # 총매수종목수
            jango_df['total_buy_count'] = total_buy_count

        # astype(str) str all
        jango_df = jango_df.astype(str)
        return jango_df

    def db_setting(self):
        self.db_conn = pymysql.connect(host=self.cf.db_ip, port=int(self.cf.db_port), user=self.cf.db_id, password=self.cf.db_passwd,
                                       charset='utf8')


        self.engine_simul_scrap = create_engine(
            "mysql+mysqldb://" + self.cf.db_id + ":" + self.cf.db_passwd + "@" + self.cf.db_ip + ":" + self.cf.db_port + "/" + "simul_scrap",
            encoding='utf-8')

    # 매일 새롭게 받아야 하기 때문에 매번 삭제해준다.
    def drop_table(self, table):
        print("drop ranking 테이블!")
        sql = f"drop table {table}"
        self.engine_simul_scrap.execute(sql)

    def is_simul_database_exist(self, db_name):

        sql = "SHOW DATABASES LIKE '%s'"

        rows = self.db_conn.cursor().execute(sql % (db_name))

        if rows == 1:
            return True
        else:
            return False

    # sum_valuation_profit 순으로 정렬 (수익이 높은 순서)
    def set_orderby_scraped_db(self):
        sql = "select * from ranking order by cast(sum_valuation_profit as signed INTEGER) desc"
        rows = self.engine_simul_scrap.execute(sql).fetchall()
        # print(rows)
        if len(rows) == 0:
            print("scrap_date 가 존재하지 않는다!! ")

        else:
            jango_temp = DataFrame(rows, columns=self.jango_list_temp)

            # 컬럼 순서 변경
            cols = jango_temp.columns.tolist()
            # print("cols", cols)
            # [start : end] , -1 이면 가장 끝, 비어있으면 가장 처음
            # cols[-1:] 는 가장 마지막 부터 시작해서 끝까지 니까 마지막 하나임
            # cols[:-1] 는 처음부터 가장 끝에서 하나 빼고 다 가져오는거
            # cols[:1] account 하나
            cols = cols[:1] + cols[-3:] + cols[1:-3]
            # print("cols", cols)
            # 순서변경
            jango_temp = jango_temp[cols]

            jango_temp.to_sql('ranking', self.engine_simul_scrap, if_exists='replace')
            print("simul scrap success!")

    # 각각의 simulator db의 최종 jango_data row를 simul_scrap db의 ranking 테이블에 넣는다
    def set_scraped_db(self):
        print("set_scraped_db!!")
        # 스크랩 시작하는 simulator db 기준으로 jango_data의 가장 마지막 날을 가져온다
        scrap_date = self.get_jango_data_last_date()

        print("scrap_date!!!: " + scrap_date)
        print(datetime.datetime.today().strftime("start  ******* %H : %M : %S *******"))
        # 스크랩 시작하는 simulator 부터 모든 simulator의 최종 jango_data row를 가져온다
        for i in range(self.start_db_num, self.simul_db_range):
            db_num = str(i)
            print(db_num)
            # 스크랩할 시뮬레이터 번호
            self.simul_db_name = "simulator" + str(db_num)

            if self.is_simul_database_exist(self.simul_db_name) == False:
                print(self.simul_db_name + " not exist !!! ")
                continue;

            self.engine_simulator = create_engine(
                "mysql+mysqldb://" + self.cf.db_id + ":" + self.cf.db_passwd + "@" + self.cf.db_ip + ":" + self.cf.db_port + "/" + str(
                    self.simul_db_name),
                encoding='utf-8')

            if self.is_simul_table_exist(self.simul_db_name, "jango_data") == False:
                print("jango_data 존재하지 않는다!!!")

            else:
                sql = "select * from jango_data where date='%s' group by date"
                rows = self.engine_simulator.execute(sql % (scrap_date)).fetchall()
                jango_df = self.set_jango_df(rows)

                # account 컬럼 추가 (simulator number)
                jango_df.loc[0, 'account'] = int(db_num)
                jango_df = jango_df.set_index("account")
                # ranking table에 넣는다
                jango_df.to_sql('ranking', self.engine_simul_scrap, if_exists='append')

        print(datetime.datetime.today().strftime("end  ******* %H : %M : %S *******"))


if __name__ == "__main__":
    simul_scraper()
