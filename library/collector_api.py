from collections import OrderedDict

from sqlalchemy import Integer, Text

ver = "#version 1.3.13"
print(f"collector_api Version: {ver}")

import numpy
import pathlib
from library.open_api import *
import os
import time
from PyQt5.QtWidgets import *
from library.daily_buy_list import *
from pandas import DataFrame
# from kind_crawling import *

MARKET_KOSPI = 0
MARKET_KOSDAQ = 10


# 콜렉팅에 사용되는 메서드를 모아 놓은 클래스
class collector_api():
    def __init__(self):
        self.open_api = open_api()
        self.engine_JB = self.open_api.engine_JB
        self.variable_setting()
        # self.kind = KINDCrawler()

    def variable_setting(self):
        self.open_api.py_gubun = "collector"
        self.dc = daily_crawler(self.open_api.cf.real_db_name, self.open_api.cf.real_daily_craw_db_name,
                                self.open_api.cf.real_daily_buy_list_db_name)
        self.dbl = daily_buy_list()

    # 콜렉팅을 실행하는 함수
    def code_update_check(self):
        logger.debug("code_update_check 함수에 들어왔습니다.")
        sql = "select code_update,jango_data_db_check, possessed_item, today_profit, final_chegyul_check, db_to_buy_list,today_buy_list, daily_crawler , min_crawler, daily_buy_list from setting_data limit 1"

        rows = self.engine_JB.execute(sql).fetchall()

        # stock_item_all(kospi,kosdaq,konex)
        # kospi(stock_kospi), kosdaq(stock_kosdaq), konex(stock_konex)
        # 관리종목(stock_managing), 불성실법인종목(stock_insincerity) 업데이트
        if rows[0][0] != self.open_api.today:
            self.open_api.check_balance()
            self.get_code_list()

        # 잔고 및 보유종목 현황 db setting   &  # sql % setting
        if rows[0][1] != self.open_api.today or rows[0][2] != self.open_api.today:
            self.py_check_balance()
            self.open_api.set_invest_unit()

        # possessed_item(현재 보유종목) 테이블 업데이트
        if rows[0][2] != self.open_api.today:
            self.open_api.db_to_possesed_item()
            self.open_api.setting_data_possesed_item()

        # 당일 종목별 실현 손익 db
        if rows[0][3] != self.open_api.today:
            self.db_to_today_profit_list()

        # daily_craw db 업데이트
        if rows[0][7] != self.open_api.today:
            self.daily_crawler_check()

        # daily_buy_list db 업데이트
        if rows[0][9] != self.open_api.today:
            self.daily_buy_list_check()

        # daily_buy_list db업데이트 이 후에 들어가야함
        if rows[0][4] != self.open_api.today:
            # 매수했는데 all_item_db에 없는 종목들 넣어준다.
            self.open_api.chegyul_check()
            # 매도 했는데 bot이 꺼져있을때 매도해서 all_item_db에 sell_date에 오늘 일자가 안 찍힌 종목들에 date 값을 넣어 준다. (이때 sell_rate는 0.0으로 찍힌다.)
            self.open_api.final_chegyul_check()

        # 내일 매수 종목 업데이트 (realtime_daily_buy_list)
        if rows[0][6] != self.open_api.today:
            self.realtime_daily_buy_list_check()

        # min_craw db (분별 데이터) 업데이트
        if rows[0][8] != self.open_api.today:
            self.min_crawler_check()

        # self.kind.craw()

        logger.debug("collecting 작업을 모두 정상적으로 마쳤습니다.")

        # cmd 콘솔창 종료
        os.system("@taskkill /f /im cmd.exe")

        # # AI 알고리즘 적용
        # if self.open_api.sf.use_ai:
        #     path = pathlib.Path(__file__).parent.parent.absolute() / 'bat' / 'ai_filter.bat'
        #     os.system(f"start {path} {self.open_api.db_name} {self.open_api.simul_num}")

    # 실전 봇, 모의 봇 매수 종목 세팅 + all_item_db 업데이트 함수
    def realtime_daily_buy_list_check(self):
        if self.open_api.sf.is_date_exist(self.open_api.today):
            logger.debug("daily_buy_list DB에 {} 테이블이 있습니다. jackbot DB에 realtime_daily_buy_list 테이블을 생성합니다".format(self.open_api.today))

            self.open_api.sf.get_date_for_simul()
            # 첫 번째 파라미터는 여기서는 의미가 없다.
            # 두 번째 파라미터에 오늘 일자를 넣는 이유는 매수를 하는 시점인 내일 기준으로 date_rows_yesterday가 오늘 이기 때문
            self.open_api.sf.db_to_realtime_daily_buy_list(self.open_api.today, self.open_api.today, len(self.open_api.sf.date_rows))


            # all_item_db에서 open, clo5~120, volume 등을 오늘 일자 데이터로 업데이트 한다.
            self.open_api.sf.update_all_db_by_date(self.open_api.today)
            self.open_api.rate_check()
            # realtime_daily_buy_list(매수 리스트) 테이블 세팅을 완료 했으면 아래 쿼리를 통해 setting_data의 today_buy_list에 오늘 날짜를 찍는다.
            sql = "UPDATE setting_data SET today_buy_list='%s' limit 1"
            self.engine_JB.execute(sql % (self.open_api.today))
        else:
            logger.debug(
                """daily_buy_list DB에 {} 테이블이 없습니다. jackbot DB에 realtime_daily_buy_list 테이블을 생성 할 수 없습니다.
                realtime_daily_buy_list는 daily_buy_list DB 안에 오늘 날짜 테이블이 만들어져야 생성이 됩니다.
                realtime_daily_buy_list 테이블을 생성할 수 없는 이유는 아래와 같습니다.
                1. 장이 열리지 않은 날 혹은 15시 30분 ~ 23시 59분 사이에 콜렉터를 돌리지 않은 경우 
                2. 콜렉터를 오늘 날짜 까지 돌리지 않아 daily_buy_list의 오늘 날짜 테이블이 없는 경우
                """.format(self.open_api.today))

    def is_table_exist_daily_buy_list(self, date):
        sql = "select 1 from information_schema.tables where table_schema ='daily_buy_list' and table_name = '%s'"
        rows = self.open_api.engine_daily_buy_list.execute(sql % (date)).fetchall()

        if len(rows) == 1:
            return True
        elif len(rows) == 0:
            return False

    def is_table_exist(self, db_name, table_name):
        sql = "select 1 from information_schema.tables where table_schema ='{}' and table_name = '{}'"
        rows = self.open_api.engine_craw.execute(sql.format(db_name, table_name)).fetchall()
        if len(rows) == 1:
            # logger.debug("is_table_exist True!!")
            return True
        elif len(rows) == 0:
            # logger.debug("is_table_exist False!!")
            return False

    def daily_buy_list_check(self):
        # dbl 에서 가져온다
        self.dbl.daily_buy_list()
        logger.debug("daily_buy_list success !!!")

        sql = "UPDATE setting_data SET daily_buy_list='%s' limit 1"
        self.engine_JB.execute(sql % (self.open_api.today))

    # min_craw데이터베이스를 구축
    def db_to_min_craw(self):
        logger.debug("db_to_min_craw!!!!!!")
        sql = "select code,code_name, check_min_crawler from stock_item_all"
        target_code = self.open_api.engine_daily_buy_list.execute(sql).fetchall()
        num = len(target_code)

        sql = "UPDATE stock_item_all SET check_min_crawler='%s' WHERE code='%s'"

        for i in range(num):
            # check_item 확인
            if int(target_code[i][2]) != 0:
                continue

            code = target_code[i][0]
            code_name = target_code[i][1]

            logger.debug("++++++++++++++" + str(code_name) + "++++++++++++++++++++" + str(i + 1) + '/' + str(num))

            check_item_gubun = self.set_min_crawler_table(code, code_name)

            self.open_api.engine_daily_buy_list.execute(sql % (check_item_gubun, code))

    def db_to_daily_craw(self):
        logger.debug("db_to_daily_craw 함수에 들어왔습니다!")
        sql = "select code,code_name, check_daily_crawler from stock_item_all"

        # 데이타 Fetch
        # rows 는 list안에 튜플이 있는 [()] 형태로 받아온다

        target_code = self.open_api.engine_daily_buy_list.execute(sql).fetchall()
        num = len(target_code)
        # mark = ".KS"
        sql = "UPDATE stock_item_all SET check_daily_crawler='%s' WHERE code='%s'"

        for i in range(num):
            # check_daily_crawler 확인 후 1, 3이 아닌 경우만 업데이트
            # (1: 금일 콜렉팅 완료, 3:과거에 이미 콜렉팅 완료, 0: 콜렉팅 전, 4: 액면분할, 증자 등으로 인한 업데이트 필요)
            if int(target_code[i][2]) in (1, 3):
                continue

            code = target_code[i][0]
            code_name = target_code[i][1]

            logger.debug("++++++++++++++" + str(code_name) + "++++++++++++++++++++" + str(i + 1) + '/' + str(num))

            check_item_gubun = self.set_daily_crawler_table(code, code_name)

            self.open_api.engine_daily_buy_list.execute(sql % (check_item_gubun, code))

    def min_crawler_check(self):
        self.db_to_min_craw()
        logger.debug("min_crawler success !!!")

        sql = "UPDATE setting_data SET min_crawler='%s' limit 1"
        self.engine_JB.execute(sql % (self.open_api.today))

    def daily_crawler_check(self):
        self.db_to_daily_craw()
        logger.debug("daily_crawler success !!!")

        sql = "UPDATE setting_data SET daily_crawler='%s' limit 1"
        self.engine_JB.execute(sql % (self.open_api.today))

    def _stock_to_sql(self, origin_df, type):
        checking_stocks = ['kosdaq', 'kospi', 'konex', 'etf']
        stock_df = DataFrame()
        stock_df['code'] = origin_df['code']
        name_list = []
        for KIND_info in origin_df.itertuples():
            kiwoom_name = self.open_api.dynamicCall("GetMasterCodeName(QString)", KIND_info.code).strip()
            name_list.append(kiwoom_name)
            if not kiwoom_name:
                if type in checking_stocks:
                    logger.error(
                        f"종목명이 비어있습니다. - "
                        f"종목: {KIND_info.code_name}, "
                        f"코드: {KIND_info.code}"
                    )

        stock_df['code_name'] = name_list
        stock_df['check_item'] = 0
        if type in checking_stocks:
            stock_df = stock_df[stock_df['code_name'].map(len) > 0]

        if type == 'item_all':
            stock_df['check_daily_crawler'] = "0"
            stock_df['check_min_crawler'] = "0"

        dtypes = dict(zip(list(stock_df.columns), [Text] * len(stock_df.columns)))  # 모든 타입을 Text로
        dtypes['check_item'] = Integer  # check_item만 int로 변경

        stock_df.to_sql(f'stock_{type}', self.open_api.engine_daily_buy_list, if_exists='replace', dtype=dtypes)
        return stock_df

    def get_code_list(self):
        self.dc.cc.get_item()
        self.dc.cc.get_item_kospi()
        self.dc.cc.get_item_kosdaq()
        self.dc.cc.get_item_konex()
        self.dc.cc.get_item_managing()
        self.dc.cc.get_item_insincerity()

        logger.debug("get_code_list")

        # 아래 부분은 영상 촬영 후 좀 더 효율적으로 업그레이드 되었으므로 강의 영상속의 코드와 다를 수 있습니다.
        # OrderedDict를 사용해 순서 보장
        stock_data = OrderedDict(
            kospi=self.dc.cc.code_df_kospi,
            kosdaq=self.dc.cc.code_df_kosdaq,
            konex=self.dc.cc.code_df_konex,
            insincerity=self.dc.cc.code_df_insincerity,
            managing=self.dc.cc.code_df_managing
        )

        if cf.use_etf:
            stock_data['etf'] = DataFrame([(c, '') for c in self._get_code_list_by_market(8) if c],
                                          columns=['code', 'code_name'])

        for _type, data in stock_data.items():
            stock_data[_type] = self._stock_to_sql(data, _type)

        # stock_insincerity와 stock_managing의 종목은 따로 중복하여 넣지 않음
        excluded_tables = ['insincerity', 'managing']
        stock_item_all_df = pd.concat(
            [v[v['code_name'].map(len) > 0] for k, v in stock_data.items() if k not in excluded_tables],
            ignore_index=True
        ).drop_duplicates(subset=['code', 'code_name'])
        self._stock_to_sql(stock_item_all_df, "item_all")

        ### stock_item_all이 제대로 생성되는지 확인하는 코드
        # union_frags = []
        # alias_num = 0
        # for _type, data in stock_data.items():
        #     if _type not in excluded_tables:
        #         union_frags.append(f"SELECT a{alias_num}.code_name FROM daily_buy_list.stock_{_type} a{alias_num}")
        #         alias_num += 1
        # union_query = '\nUNION ALL\n'.join(union_frags)
        # testing_query = f"SELECT count(code_name) FROM ({union_query}) b " \
        #                 f"WHERE code_name != '' or code_name != null"
        #
        # stock_union_count = self.engine_JB.execute(testing_query).fetchall()
        # sia_count = self.engine_JB.execute(f"SELECT count(*) FROM daily_buy_list.stock_item_all").fetchall()
        #
        # assert sia_count == stock_union_count, "stock_item_all does not contain all data."
        ###

        sql = "UPDATE setting_data SET code_update='%s' limit 1"
        self.engine_JB.execute(sql % (self.open_api.today))

    def _get_code_list_by_market(self, market_num):
        codes = self.open_api.dynamicCall(f'GetCodeListByMarket("{market_num}")')
        return codes.split(';')

    # 틱(1분 별) 데이터를 가져오는 함수
    def set_min_crawler_table(self, code, code_name):
        df = self.open_api.get_total_data_min(code, code_name, self.open_api.today)

        df_temp = DataFrame(df,
                            columns=['date', 'check_item', 'code', 'code_name', 'd1_diff_rate', 'close', 'open', 'high',
                                     'low',
                                     'volume', 'sum_volume', 'clo5', 'clo10', 'clo20', 'clo40', 'clo60', 'clo80',
                                     'clo100', 'clo120', "clo5_diff_rate", "clo10_diff_rate",
                                     "clo20_diff_rate", "clo40_diff_rate", "clo60_diff_rate",
                                     "clo80_diff_rate", "clo100_diff_rate", "clo120_diff_rate",
                                     'yes_clo5', 'yes_clo10', 'yes_clo20', 'yes_clo40', 'yes_clo60', 'yes_clo80',
                                     'yes_clo100', 'yes_clo120',
                                     'vol5', 'vol10', 'vol20', 'vol40', 'vol60', 'vol80',
                                     'vol100', 'vol120'
                                     ])

        df_temp = df_temp.sort_values(by=['date'], ascending=True)

        df_temp['code'] = code
        # # 뒤에 0없애기 (초)
        df_temp['code_name'] = code_name
        d1_diff_rate = round((df_temp['close'] - df_temp['close'].shift(1)) / df_temp['close'].shift(1) * 100, 2)
        df_temp['d1_diff_rate'] = d1_diff_rate.replace(numpy.inf, numpy.nan)

        # 하나씩 추가할때는 append 아니면 replace
        clo5 = df_temp['close'].rolling(window=5).mean()
        clo10 = df_temp['close'].rolling(window=10).mean()
        clo20 = df_temp['close'].rolling(window=20).mean()
        clo40 = df_temp['close'].rolling(window=40).mean()
        clo60 = df_temp['close'].rolling(window=60).mean()
        clo80 = df_temp['close'].rolling(window=80).mean()
        clo100 = df_temp['close'].rolling(window=100).mean()
        clo120 = df_temp['close'].rolling(window=120).mean()
        df_temp['clo5'] = round(clo5, 2)
        df_temp['clo10'] = round(clo10, 2)
        df_temp['clo20'] = round(clo20, 2)
        df_temp['clo40'] = round(clo40, 2)
        df_temp['clo60'] = round(clo60, 2)
        df_temp['clo80'] = round(clo80, 2)
        df_temp['clo100'] = round(clo100, 2)
        df_temp['clo120'] = round(clo120, 2)

        df_temp['clo5_diff_rate'] = round((df_temp['close'] - clo5) / clo5 * 100, 2)
        df_temp['clo10_diff_rate'] = round((df_temp['close'] - clo10) / clo10 * 100, 2)
        df_temp['clo20_diff_rate'] = round((df_temp['close'] - clo20) / clo20 * 100, 2)
        df_temp['clo40_diff_rate'] = round((df_temp['close'] - clo40) / clo40 * 100, 2)
        df_temp['clo60_diff_rate'] = round((df_temp['close'] - clo60) / clo60 * 100, 2)
        df_temp['clo80_diff_rate'] = round((df_temp['close'] - clo80) / clo80 * 100, 2)
        df_temp['clo100_diff_rate'] = round((df_temp['close'] - clo100) / clo100 * 100, 2)
        df_temp['clo120_diff_rate'] = round((df_temp['close'] - clo120) / clo120 * 100, 2)

        df_temp['yes_clo5'] = df_temp['clo5'].shift(1)
        df_temp['yes_clo10'] = df_temp['clo10'].shift(1)
        df_temp['yes_clo20'] = df_temp['clo20'].shift(1)
        df_temp['yes_clo40'] = df_temp['clo40'].shift(1)
        df_temp['yes_clo60'] = df_temp['clo60'].shift(1)
        df_temp['yes_clo80'] = df_temp['clo80'].shift(1)
        df_temp['yes_clo100'] = df_temp['clo100'].shift(1)
        df_temp['yes_clo120'] = df_temp['clo120'].shift(1)

        df_temp['vol5'] = df_temp['volume'].rolling(window=5).mean()
        df_temp['vol10'] = df_temp['volume'].rolling(window=10).mean()
        df_temp['vol20'] = df_temp['volume'].rolling(window=20).mean()
        df_temp['vol40'] = df_temp['volume'].rolling(window=40).mean()
        df_temp['vol60'] = df_temp['volume'].rolling(window=60).mean()
        df_temp['vol80'] = df_temp['volume'].rolling(window=80).mean()
        df_temp['vol100'] = df_temp['volume'].rolling(window=100).mean()
        df_temp['vol120'] = df_temp['volume'].rolling(window=120).mean()

        if self.open_api.craw_table_exist:
            df_temp = df_temp[df_temp.date > self.open_api.craw_db_last_min]

        if len(df_temp) == 0:
            logger.debug("이미 min_craw db의 " + code_name + " 테이블에 콜렉팅 완료 했다! df_temp가 비었다!!")

            # 이렇게 안해주면 아래 프로세스들을 안하고 바로 넘어가기때문에 그만큼 tr 조회 하는 시간이 짧아지고 1초에 5회 이상의 조회를 할 수 가있다 따라서 비었을 경우는 sleep해줘야 안멈춘다
            time.sleep(0.03)
            check_item_gubun = 3
            return check_item_gubun

        df_temp[['close', 'open', 'high', 'low', 'volume', 'sum_volume', 'clo5', 'clo10', 'clo20', 'clo40', 'clo60',
                 'clo80', 'clo100', 'clo120',
                 'yes_clo5', 'yes_clo10', 'yes_clo20', 'yes_clo40', 'yes_clo60', 'yes_clo80', 'yes_clo100',
                 'yes_clo120',
                 'vol5', 'vol10', 'vol20', 'vol40', 'vol60', 'vol80', 'vol100', 'vol120']] = \
            df_temp[
                ['close', 'open', 'high', 'low', 'volume', 'sum_volume', 'clo5', 'clo10', 'clo20', 'clo40', 'clo60',
                 'clo80', 'clo100', 'clo120',
                 'yes_clo5', 'yes_clo10', 'yes_clo20', 'yes_clo40', 'yes_clo60', 'yes_clo80', 'yes_clo100',
                 'yes_clo120',
                 'vol5', 'vol10', 'vol20', 'vol40', 'vol60', 'vol80', 'vol100', 'vol120']].fillna(0).astype(int)
        temp_date = self.open_api.craw_db_last_min

        sum_volume = self.open_api.craw_db_last_min_sum_volume
        for i in range(0, len(df_temp)):
            try:
                # index가 역순이라 거꾸로 되어있어서 아래처럼
                temp_index = len(df_temp) - i - 1

                if ((int(df_temp.loc[temp_index, 'date']) - int(temp_date)) > 9000):
                    sum_volume = 0

                temp_date = df_temp.loc[temp_index, 'date']

                sum_volume += df_temp.loc[temp_index, 'volume']

                df_temp.loc[temp_index, 'sum_volume'] = sum_volume
            except Exception as e:
                logger.critical(e)

        df_temp.to_sql(name=code_name, con=self.open_api.engine_craw, if_exists='append')
        # 콜렉팅하다가 max_api_call 횟수까지 가게 된 경우는 다시 콜렉팅 못한 정보를 가져와야 하니까 check_item_gubun=0
        if self.open_api.rq_count == cf.max_api_call - 1:
            check_item_gubun = 0
        else:
            check_item_gubun = 1
        return check_item_gubun

    def set_daily_crawler_table(self, code, code_name):
        df = self.open_api.get_total_data(code, code_name, self.open_api.today)
        oldest_row = df.iloc[-1]
        check_row = None

        check_daily_crawler_sql = """
            UPDATE  daily_buy_list.stock_item_all SET check_daily_crawler = '4' WHERE code = '{}'
        """

        if self.engine_JB.dialect.has_table(self.open_api.engine_daily_craw, code_name):
            check_row = self.open_api.engine_daily_craw.execute(f"""
                SELECT * FROM `{code_name}` WHERE date = '{oldest_row['date']}' LIMIT 1
            """).fetchall()
        else:
            self.engine_JB.execute(check_daily_crawler_sql.format(code))

        if check_row and check_row[0]['close'] != oldest_row['close']:
            logger.info(f'{code} {code_name}의 액면분할/증자 등의 이유로 수정주가가 달라져서 처음부터 다시 콜렉팅')
            # daily_craw 삭제
            logger.info('daily_craw와 min_craw 삭제 중..')
            commands = [
                f'DROP TABLE IF EXISTS daily_craw.`{code_name}`',
                f'DROP TABLE IF EXISTS min_craw.`{code_name}`'
            ]

            for com in commands:
                self.open_api.engine_daily_buy_list.execute(com)
            logger.info('삭제 완료')
            df = self.open_api.get_total_data(code, code_name, self.open_api.today)
            self.engine_JB.execute(check_daily_crawler_sql.format(code))

        check_daily_crawler = self.engine_JB.execute(f"""
            SELECT check_daily_crawler FROM daily_buy_list.stock_item_all WHERE code = '{code}'
        """).fetchall()[0].check_daily_crawler

        df_temp = DataFrame(df,
                            columns=['date', 'check_item', 'code', 'code_name', 'd1_diff_rate', 'close', 'open', 'high',
                                     'low',
                                     'volume', 'clo5', 'clo10', 'clo20', 'clo40', 'clo60', 'clo80',
                                     'clo100', 'clo120', "clo5_diff_rate", "clo10_diff_rate",
                                     "clo20_diff_rate", "clo40_diff_rate", "clo60_diff_rate",
                                     "clo80_diff_rate", "clo100_diff_rate", "clo120_diff_rate",
                                     'yes_clo5', 'yes_clo10', 'yes_clo20', 'yes_clo40', 'yes_clo60', 'yes_clo80',
                                     'yes_clo100', 'yes_clo120',
                                     'vol5', 'vol10', 'vol20', 'vol40', 'vol60', 'vol80',
                                     'vol100', 'vol120'
                                     ])

        df_temp = df_temp.sort_values(by=['date'], ascending=True)
        # df_temp = df_temp[1:]

        df_temp['code'] = code
        df_temp['code_name'] = code_name
        df_temp['d1_diff_rate'] = round(
            (df_temp['close'] - df_temp['close'].shift(1)) / df_temp['close'].shift(1) * 100, 2)

        # 하나씩 추가할때는 append 아니면 replace
        clo5 = df_temp['close'].rolling(window=5).mean()
        clo10 = df_temp['close'].rolling(window=10).mean()
        clo20 = df_temp['close'].rolling(window=20).mean()
        clo40 = df_temp['close'].rolling(window=40).mean()
        clo60 = df_temp['close'].rolling(window=60).mean()
        clo80 = df_temp['close'].rolling(window=80).mean()
        clo100 = df_temp['close'].rolling(window=100).mean()
        clo120 = df_temp['close'].rolling(window=120).mean()
        df_temp['clo5'] = clo5
        df_temp['clo10'] = clo10
        df_temp['clo20'] = clo20
        df_temp['clo40'] = clo40
        df_temp['clo60'] = clo60
        df_temp['clo80'] = clo80
        df_temp['clo100'] = clo100
        df_temp['clo120'] = clo120

        df_temp['clo5_diff_rate'] = round((df_temp['close'] - clo5) / clo5 * 100, 2)
        df_temp['clo10_diff_rate'] = round((df_temp['close'] - clo10) / clo10 * 100, 2)
        df_temp['clo20_diff_rate'] = round((df_temp['close'] - clo20) / clo20 * 100, 2)
        df_temp['clo40_diff_rate'] = round((df_temp['close'] - clo40) / clo40 * 100, 2)
        df_temp['clo60_diff_rate'] = round((df_temp['close'] - clo60) / clo60 * 100, 2)
        df_temp['clo80_diff_rate'] = round((df_temp['close'] - clo80) / clo80 * 100, 2)
        df_temp['clo100_diff_rate'] = round((df_temp['close'] - clo100) / clo100 * 100, 2)
        df_temp['clo120_diff_rate'] = round((df_temp['close'] - clo120) / clo120 * 100, 2)

        df_temp['yes_clo5'] = df_temp['clo5'].shift(1)
        df_temp['yes_clo10'] = df_temp['clo10'].shift(1)
        df_temp['yes_clo20'] = df_temp['clo20'].shift(1)
        df_temp['yes_clo40'] = df_temp['clo40'].shift(1)
        df_temp['yes_clo60'] = df_temp['clo60'].shift(1)
        df_temp['yes_clo80'] = df_temp['clo80'].shift(1)
        df_temp['yes_clo100'] = df_temp['clo100'].shift(1)
        df_temp['yes_clo120'] = df_temp['clo120'].shift(1)

        df_temp['vol5'] = df_temp['volume'].rolling(window=5).mean()
        df_temp['vol10'] = df_temp['volume'].rolling(window=10).mean()
        df_temp['vol20'] = df_temp['volume'].rolling(window=20).mean()
        df_temp['vol40'] = df_temp['volume'].rolling(window=40).mean()
        df_temp['vol60'] = df_temp['volume'].rolling(window=60).mean()
        df_temp['vol80'] = df_temp['volume'].rolling(window=80).mean()
        df_temp['vol100'] = df_temp['volume'].rolling(window=100).mean()
        df_temp['vol120'] = df_temp['volume'].rolling(window=120).mean()

        # 여기 이렇게 추가해야함
        if self.engine_JB.dialect.has_table(self.open_api.engine_daily_craw, code_name):
            df_temp = df_temp[df_temp.date > self.open_api.get_daily_craw_db_last_date(code_name)]

        if len(df_temp) == 0 and check_daily_crawler != '4':
            logger.debug("이미 daily_craw db의 " + code_name + " 테이블에 콜렉팅 완료 했다! df_temp가 비었다!!")

            # 이렇게 안해주면 아래 프로세스들을 안하고 바로 넘어가기때문에 그만큼 tr 조회 하는 시간이 짧아지고 1초에 5회 이상의 조회를 할 수 가있다 따라서 비었을 경우는 sleep해줘야 안멈춘다
            time.sleep(0.03)
            check_item_gubun = 3
            return check_item_gubun

        df_temp[['close', 'open', 'high', 'low', 'volume', 'clo5', 'clo10', 'clo20', 'clo40', 'clo60',
                 'clo80', 'clo100', 'clo120',
                 'yes_clo5', 'yes_clo10', 'yes_clo20', 'yes_clo40', 'yes_clo60', 'yes_clo80', 'yes_clo100',
                 'yes_clo120',
                 'vol5', 'vol10', 'vol20', 'vol40', 'vol60', 'vol80', 'vol100', 'vol120']] = \
            df_temp[
                ['close', 'open', 'high', 'low', 'volume', 'clo5', 'clo10', 'clo20', 'clo40', 'clo60',
                 'clo80', 'clo100', 'clo120',
                 'yes_clo5', 'yes_clo10', 'yes_clo20', 'yes_clo40', 'yes_clo60', 'yes_clo80', 'yes_clo100',
                 'yes_clo120',
                 'vol5', 'vol10', 'vol20', 'vol40', 'vol60', 'vol80', 'vol100', 'vol120']].fillna(0).astype(int)

        df_temp.to_sql(name=code_name, con=self.open_api.engine_daily_craw, if_exists='append')

        # check_daily_crawler 가 4 인 경우는 액면분할, 증자 등으로 인해 daily_buy_list 업데이트를 해야하는 경우
        if check_daily_crawler == '4':
            logger.info(f'daily_craw.{code_name} 업데이트 완료 {code}')
            logger.info('daily_buy_list 업데이트 중..')
            dbl_dates = self.open_api.engine_daily_buy_list.execute("""
                SELECT table_name as tname FROM information_schema.tables 
                WHERE table_schema ='daily_buy_list' AND table_name REGEXP '[0-9]{8}'
            """).fetchall()

            for row in dbl_dates:
                logger.info(f'{code} {code_name} - daily_buy_list.`{row.tname}` 업데이트')
                try:
                    new_data = df_temp[df_temp['date'] == row.tname]
                except IndexError:
                    continue
                self.open_api.engine_daily_buy_list.execute(f"""
                    DELETE FROM `{row.tname}` WHERE code = {code}
                """)
                new_data.to_sql(name=row.tname, con=self.open_api.engine_daily_buy_list, if_exists='append')

            logger.info('daily_buy_list 업데이트 완료')

        check_item_gubun = 1
        return check_item_gubun

    def update_buy_list(self, buy_list):
        f = open("buy_list.txt", "wt")
        for code in buy_list:
            f.writelines("매수;%s;시장가;10;0;매수전\n" % (code))
        f.close()

    def db_to_today_profit_list(self):

        logger.debug("db_to_today_profit_list!!!")
        # 1차원 / 2차원 인스턴스 변수 생성
        self.open_api.reset_opt10073_output()
        # comm_rq_data 호출하기 전에 반드시 set_input_value 해야한다.

        self.open_api.set_input_value("계좌번호", self.open_api.account_number)
        # 여긴 시작일자가 최근 일자로 보면 된다. 하루만 가져오기 위해서 시작일자, 종료일자 동일하게 today로 했음
        self.open_api.set_input_value("시작일자", self.open_api.today)
        self.open_api.set_input_value("종료일자", self.open_api.today)

        self.open_api.comm_rq_data("opt10073_req", "opt10073", 0, "0328")

        while self.open_api.remained_data:
            # # comm_rq_data 호출하기 전에 반드시 set_input_value 해야한다. 초기화 되기 때문
            self.open_api.set_input_value("계좌번호", self.open_api.account_number)

            self.open_api.comm_rq_data("opt10073_req", "opt10073", 2, "0328")

        logger.debug("self.opt10073_output['multi']!!!!!")
        logger.debug(self.open_api.opt10073_output['multi'])

        today_profit_item_temp = {'date': [], 'code': [], 'code_name': [], 'amount': [], 'today_profit': [],
                                  'earning_rate': []}

        # logger.debug(possesed_item_temp)
        today_profit_item = DataFrame(today_profit_item_temp,
                                      columns=['date', 'code', 'code_name', 'amount', 'today_profit',
                                               'earning_rate'])

        item_count = len(self.open_api.opt10073_output['multi'])
        for i in range(item_count):
            row = self.open_api.opt10073_output['multi'][i]
            today_profit_item.loc[i, 'date'] = row[0]
            today_profit_item.loc[i, 'code'] = row[1]
            today_profit_item.loc[i, 'code_name'] = row[2]
            # logger.debug(int(row[3]))
            today_profit_item.loc[i, 'amount'] = int(row[3])
            # logger.debug(today_profit_item.loc[i, 'amount'])
            today_profit_item.loc[i, 'today_profit'] = float(row[4])
            today_profit_item.loc[i, 'earning_rate'] = float(row[5])

        logger.debug("today_profit_item!!!")
        logger.debug(today_profit_item)

        if len(today_profit_item) > 0:
            today_profit_item.to_sql('today_profit_list', self.engine_JB, if_exists='append')
        sql = "UPDATE setting_data SET today_profit='%s' limit 1"
        self.engine_JB.execute(sql % (self.open_api.today))
        # self.open_api.jackbot_db_con.commit()

    def set_invest_unit(self):
        logger.debug("set_invest_unit!!!")

        self.open_api.invest_unit = int(self.total_invest / self.open_api.max_invest_count)
        logger.debug("self.invest_unit !!!!")
        logger.debug(self.open_api.invest_unit)

        # 오늘 리스트 다 뽑았으면 today를 setting_data에 체크

        sql = "UPDATE setting_data SET invest_unit='%s',set_invest_unit='%s' limit 1"
        self.engine_JB.execute(sql % (self.open_api.invest_unit, self.open_api.today))

    def db_to_jango(self):
        self.total_invest = self.open_api.change_format(
            str(int(self.open_api.d2_deposit_before_format) + int(self.open_api.total_purchase_price)))
        jango_temp = {'id': [], 'date': [], 'total_asset': [], 'today_profit': [], 'total_profit': [],
                      'total_invest': [], 'd2_deposit': [],
                      'today_purchase': [], 'today_evaluation': [],
                      'today_invest': [], 'today_rate': [],
                      'estimate_asset': []}

        jango_col_list = ['date', 'today_earning_rate', 'total_asset', 'today_profit', 'total_profit', 'total_invest',
                          'd2_deposit', 'today_purchase', 'today_evaluation', 'today_invest', 'today_rate',
                          'estimate_asset', 'volume_limit', 'ipo_term', 'reinvest_point', 'sell_point',
                          'max_reinvest_count', 'invest_limit_rate', 'invest_unit', 'min_invest_unit',
                          'max_invest_unit',
                          'avg_close_multiply_rate', 'max_reinvest_unit', 'rate_std_sell_point', 'limit_money',
                          'total_profitcut',
                          'total_losscut', 'total_profitcut_count', 'total_losscut_count', 'loan_money',
                          'start_kospi_point',
                          'start_kosdaq_point', 'end_kospi_point', 'end_kosdaq_point', 'today_buy_count',
                          'today_buy_total_sell_count',
                          'today_buy_total_possess_count', 'today_buy_today_profitcut_count',
                          'today_buy_today_profitcut_rate',
                          'today_buy_today_losscut_count', 'today_buy_today_losscut_rate',
                          'today_buy_total_profitcut_count', 'today_buy_total_profitcut_rate',
                          'today_buy_total_losscut_count',
                          'today_buy_total_losscut_rate', 'today_buy_reinvest_count0_sell_count',
                          'today_buy_reinvest_count1_sell_count', 'today_buy_reinvest_count2_sell_count',
                          'today_buy_reinvest_count3_sell_count', 'today_buy_reinvest_count4_sell_count',
                          'today_buy_reinvest_count4_sell_profitcut_count',
                          'today_buy_reinvest_count4_sell_losscut_count', 'today_buy_reinvest_count5_sell_count',
                          'today_buy_reinvest_count5_sell_profitcut_count',
                          'today_buy_reinvest_count5_sell_losscut_count',
                          'today_buy_reinvest_count0_remain_count',
                          'today_buy_reinvest_count1_remain_count', 'today_buy_reinvest_count2_remain_count',
                          'today_buy_reinvest_count3_remain_count', 'today_buy_reinvest_count4_remain_count',
                          'today_buy_reinvest_count5_remain_count']
        jango = DataFrame(jango_temp,
                          columns=jango_col_list,
                          index=jango_temp['id'])

        jango.loc[0, 'date'] = self.open_api.today

        logger.debug("self.open_api.today!!!!!!!!")
        logger.debug(self.open_api.today)
        jango.loc[0, 'total_asset']
        # logger.debug("self.open_api.today_profit: " , self.open_api.today_profit)
        jango.loc[0, 'today_profit'] = self.open_api.today_profit
        jango.loc[0, 'total_profit'] = self.open_api.total_profit
        jango.loc[0, 'total_invest'] = self.total_invest
        jango.loc[0, 'd2_deposit'] = self.open_api.d2_deposit
        jango.loc[0, 'today_purchase'] = self.open_api.change_total_purchase_price
        jango.loc[0, 'today_evaluation'] = self.open_api.change_total_eval_price
        jango.loc[0, 'today_invest'] = self.open_api.change_total_eval_profit_loss_price
        jango.loc[0, 'today_rate'] = float(self.open_api.change_total_earning_rate) / self.open_api.mod_gubun
        jango.loc[0, 'estimate_asset'] = self.open_api.change_estimated_deposit
        # jango.loc[0, 'volume_limit'] = self.open_api.sf.volume_limit
        # jango.loc[0, 'ipo_term']=self.open_api.sf.ipo_term
        # jango.loc[0, 'reinvest_point']=self.open_api.sf.reinvest_point
        jango.loc[0, 'sell_point'] = self.open_api.sf.sell_point
        # jango.loc[0, 'max_reinvest_count']=self.open_api.sf.max_reinvest_count
        jango.loc[0, 'invest_limit_rate'] = self.open_api.sf.invest_limit_rate
        jango.loc[0, 'invest_unit'] = self.open_api.invest_unit

        jango.loc[0, 'limit_money'] = self.open_api.sf.limit_money

        # 처음시작할때는 여기 0으로 나온다.
        if self.is_table_exist(self.open_api.db_name, "today_profit_list"):
            sql = "select sum(today_profit) from today_profit_list where today_profit >='%s' and date = '%s'"
            rows = self.engine_JB.execute(sql % (0, self.open_api.today)).fetchall()

            if rows[0][0] is not None:
                jango.loc[0, 'total_profitcut'] = int(rows[0][0])
            else:
                logger.debug("today_profit_list total_profitcut 이 비었다!!!! ")

            sql = "select sum(today_profit) from today_profit_list where today_profit < '%s' and date = '%s'"
            rows = self.engine_JB.execute(sql % (0, self.open_api.today)).fetchall()

            if rows[0][0] is not None:
                jango.loc[0, 'total_losscut'] = int(rows[0][0])
            else:
                logger.debug("today_profit_list total_losscut 이 비었다!!!! ")

        # 이건 오늘 산게 아니더라도 익절한놈들
        sql = "select count(*) from (select code from all_item_db where sell_rate >='%s' and sell_date like '%s' group by code) temp"
        rows = self.engine_JB.execute(sql % (0, self.open_api.today + "%%")).fetchall()

        jango.loc[0, 'total_profitcut_count'] = int(rows[0][0])

        sql = "select count(*) from (select code from all_item_db where sell_rate < '%s' and sell_date like '%s' group by code) temp"
        rows = self.engine_JB.execute(sql % (0, self.open_api.today + "%%")).fetchall()

        jango.loc[0, 'total_losscut_count'] = int(rows[0][0])

        # 데이터베이스에 테이블이 존재할 때 수행 동작을 지정한다. 'fail', 'replace', 'append' 중 하나를 사용할 수 있는데 기본값은 'fail'이다. 'fail'은 데이터베이스에 테이블이 있다면 아무 동작도 수행하지 않는다. 'replace'는 테이블이 존재하면 기존 테이블을 삭제하고 새로 테이블을 생성한 후 데이터를 삽입한다. 'append'는 테이블이 존재하면 데이터만을 추가한다.
        jango.to_sql('jango_data', self.engine_JB, if_exists='append')

        sql = "select date from jango_data"
        rows = self.engine_JB.execute(sql).fetchall()

        logger.debug("jango_data rows!!!")
        logger.debug(rows)

        logger.debug("jango_data len(rows)!!!")

        logger.debug(len(rows))

        # 위에 전체
        for i in range(len(rows)):
            # logger.debug(rows[i][0])

            # today_earning_rate
            sql = "update jango_data set today_earning_rate =round(today_profit / total_invest  * '%s',2) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (100, rows[i][0]))

            # today_buy_count
            sql = "UPDATE jango_data SET today_buy_count=(select count(*) from (select code from all_item_db where buy_date like '%s' group by code ) temp) WHERE date='%s'"

            self.engine_JB.execute(sql % (rows[i][0] + "%%", rows[i][0]))

            # today_buy_total_sell_count ( 익절, 손절 포함)
            sql = "UPDATE jango_data SET today_buy_total_sell_count=(select count(*) from (select code from all_item_db a where buy_date like '%s' and (a.sell_date is not null or a.rate_std>='%s') group by code ) temp) WHERE date='%s'"

            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))

            # today_buy_total_possess_count
            sql = "UPDATE jango_data SET today_buy_total_possess_count=(select count(*) from (select code from all_item_db a where buy_date like '%s' and a.sell_date = '%s' group by code ) temp) WHERE date='%s'"
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))

            # today_buy_today_profitcut_count      rate_std가 0보다 큰 놈도 추가 (팔지않았더라도)
            sql = "UPDATE jango_data SET today_buy_today_profitcut_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date like '%s' and (sell_rate >='%s' or rate_std>='%s'  ) group by code ) temp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", rows[i][0] + "%%", 0, 0, rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_today_profitcut_rate , 오늘 산놈들 중에서 오늘 익절한놈
            sql = "UPDATE jango_data SET today_buy_today_profitcut_rate=(select * from (select round(today_buy_today_profitcut_count /today_buy_count*100,2)  from jango_data WHERE date ='%s' limit 1) tmp)  WHERE date ='%s' limit 1"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0], rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_today_losscut_count
            sql = "UPDATE jango_data SET today_buy_today_losscut_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date like '%s' and sell_rate < '%s'  group by code ) tmp) WHERE date='%s' limit 1"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", rows[i][0] + "%%", 0, rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_today_losscut_rate
            sql = "UPDATE jango_data SET today_buy_today_losscut_rate=(select * from (select round(today_buy_today_losscut_count /today_buy_count *100,2)  from jango_data WHERE date ='%s' limit 1) tmp) WHERE date ='%s' limit 1"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0], rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_total_profitcut_count
            sql = "UPDATE jango_data SET today_buy_total_profitcut_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_rate >='%s'  group by code ) tmp) WHERE date='%s' limit 1"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_total_profitcut_rate
            sql = "UPDATE jango_data SET today_buy_total_profitcut_rate=(select * from (select round(today_buy_total_profitcut_count /today_buy_count *100,2)  from jango_data WHERE date ='%s' limit 1) tmp) WHERE date ='%s' limit 1"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0], rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_total_losscut_count
            sql = "UPDATE jango_data SET today_buy_total_losscut_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_rate < '%s'  group by code ) tmp) WHERE date='%s' limit 1"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_total_losscut_rate
            sql = "UPDATE jango_data SET today_buy_total_losscut_rate=(select * from (select round(today_buy_total_losscut_count/today_buy_count *100,2)  from jango_data WHERE date ='%s' limit 1) tmp) WHERE date ='%s' limit 1"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0], rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count0_sell_count 오늘만 해당되는게 아니고 전체 다
            sql = "UPDATE jango_data SET today_buy_reinvest_count0_sell_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date is not null and reinvest_count=0 group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count1_sell_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count1_sell_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date is not null and reinvest_count=1 group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count2_sell_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count2_sell_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date is not null and reinvest_count=2 group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count3_sell_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count3_sell_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date is not null and reinvest_count=3 group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count4_sell_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count4_sell_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date is not null and reinvest_count=4 group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count4_sell_profitcut_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count4_sell_profitcut_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date is not null and reinvest_count=4 and sell_rate >='%s' group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            #   today_buy_reinvest_count4_sell_losscut_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count4_sell_losscut_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date is not null and reinvest_count=4 and sell_rate <'%s' group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count5_sell_count

            sql = "UPDATE jango_data SET today_buy_reinvest_count5_sell_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date is not null and reinvest_count=5 group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count5_sell_profitcut_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count5_sell_profitcut_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date is not null and reinvest_count=5 and sell_rate >='%s' group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            #  today_buy_reinvest_count5_sell_losscut_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count5_sell_losscut_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date is not null and reinvest_count=5 and sell_rate <'%s' group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count0_remain_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count0_remain_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date = '%s' and reinvest_count=0 group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count1_remain_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count1_remain_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date = '%s' and reinvest_count=1 group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count2_remain_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count2_remain_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date = '%s' and reinvest_count=2 group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))
            # self.open_api.jackbot_db_con.commit()

            # today_buy_reinvest_count3_remain_count
            sql = "UPDATE jango_data SET today_buy_reinvest_count3_remain_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date = '%s' and reinvest_count=3 group by code ) tmp) WHERE date='%s'"
            # rows[i][0] 하는 이유는 rows[i]는 튜플로 나온다 그 튜플의 원소를 꺼내기 위해 [0]을 추가
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))

            sql = "UPDATE jango_data SET today_buy_reinvest_count4_remain_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date = '%s' and reinvest_count=4 group by code ) tmp) WHERE date='%s'"
            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))

            sql = "UPDATE jango_data SET today_buy_reinvest_count5_remain_count=(select count(*) from (select code from all_item_db where buy_date like '%s' and sell_date = '%s' and reinvest_count=5 group by code ) tmp) WHERE date='%s'"

            self.engine_JB.execute(sql % (rows[i][0] + "%%", 0, rows[i][0]))

        sql = "UPDATE setting_data SET jango_data_db_check='%s' limit 1"
        self.engine_JB.execute(sql % (self.open_api.today))
        # self.open_api.jackbot_db_con.commit()

    def py_check_balance(self):
        logger.debug("py_check_balance!!!")
        # 1차원 정보 저장
        # 1차원 / 2차원 인스턴스 변수 생성
        self.open_api.reset_opw00018_output()

        self.open_api.set_input_value("계좌번호", self.open_api.account_number)
        self.open_api.set_input_value("비밀번호입력매체구분", 00);
        # 조회구분 = 1:추정조회, 2: 일반조회
        self.open_api.set_input_value("조회구분", 1);

        self.open_api.comm_rq_data("opw00001_req", "opw00001", 0, "2000")

        self.open_api.set_input_value("계좌번호", self.open_api.account_number)

        self.open_api.comm_rq_data("opw00018_req", "opw00018", 0, "2000")

        while self.open_api.remained_data:
            self.open_api.set_input_value("계좌번호", self.open_api.account_number)

            self.open_api.comm_rq_data("opw00018_req", "opw00018", 2, "2000")

        # 일자별 실현손익 출력
        self.open_api.set_input_value("계좌번호", self.open_api.account_number)
        # 	시작일자 = YYYYMMDD (20170101 연도4자리, 월 2자리, 일 2자리 형식)
        self.open_api.set_input_value("시작일자", "20170101")
        #
        # 	종료일자 = YYYYMMDD (20170101 연도4자리, 월 2자리, 일 2자리 형식)
        self.open_api.set_input_value("종료일자", self.open_api.today)
        # opt opw 구분해라!!!!

        self.open_api.comm_rq_data("opt10074_req", "opt10074", 0, "0329")
        while self.open_api.remained_data:
            # # comm_rq_data 호출하기 전에 반드시 set_input_value 해야한다. 초기화 되기 때문
            self.open_api.set_input_value("계좌번호", self.open_api.account_number)

            # 	시작일자 = YYYYMMDD (20170101 연도4자리, 월 2자리, 일 2자리 형식)
            self.open_api.set_input_value("시작일자", "20170101")
            #
            # 	종료일자 = YYYYMMDD (20170101 연도4자리, 월 2자리, 일 2자리 형식)
            self.open_api.set_input_value("종료일자", "20180930")

            # 	구분 = 0:전체, 1:입출금, 2:입출고, 3:매매, 4:매수, 5:매도, 6:입금, 7:출금, A:예탁담보대출입금, F:환전
            self.open_api.set_input_value("구분", "0")
            self.open_api.comm_rq_data("opt10074_req", "opt10074", 2, "0329")

        # 거래내역
        # # balance
        self.db_to_jango()


