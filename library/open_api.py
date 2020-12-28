ver = "#version 1.3.10"
print(f"open_api Version: {ver}")

from library.simulator_func_mysql import *
import datetime
import sys
from PyQt5.QAxContainer import *
from PyQt5.QtCore import *
import time
from library import cf
from collections import defaultdict

import warnings
warnings.simplefilter(action='ignore', category=UserWarning)
from pandas import DataFrame
import re
import pandas as pd
import os

from sqlalchemy import create_engine, event, Text, Float
from sqlalchemy.pool import Pool

import pymysql

pymysql.install_as_MySQLdb()
TR_REQ_TIME_INTERVAL = 0.5
code_pattern = re.compile(r'\d{6}')  # 숫자 6자리가 연속으로오는 패턴


def escape_percentage(conn, clauseelement, multiparams, params):
    # execute로 실행한 sql문이 들어왔을 때 %를 %%로 replace
    if isinstance(clauseelement, str) and '%' in clauseelement and multiparams is not None:
        while True:
            replaced = re.sub(r'([^%])%([^%s])', r'\1%%\2', clauseelement)
            if replaced == clauseelement:
                break
            clauseelement = replaced

    return clauseelement, multiparams, params


def setup_sql_mod(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("SET sql_mode = ''")


event.listen(Pool, 'connect', setup_sql_mod)
event.listen(Pool, 'first_connect', setup_sql_mod)


class RateLimitExceeded(BaseException):
    pass


class open_api(QAxWidget):
    def __init__(self):
        super().__init__()

        # openapi 호출 횟수를 저장하는 변수
        self.rq_count = 0
        self.date_setting()
        self.tr_loop_count = 0
        self.call_time = datetime.datetime.now()
        # openapi연동
        self._create_open_api_instance()
        self._set_signal_slots()
        self.comm_connect()

        # 계좌 정보 가져오는 함수
        self.account_info()
        self.variable_setting()

        # open_api가 호출 되는 경우 (콜렉터, 모의투자, 실전투자) 의 경우는
        # 아래 simulator_func_mysql 클래스를 호출 할 때 두번째 인자에 real을 보낸다.
        self.sf = simulator_func_mysql(self.simul_num, 'real', self.db_name)
        logger.debug("self.sf.simul_num(알고리즘 번호) : %s", self.sf.simul_num)
        logger.debug("self.sf.db_to_realtime_daily_buy_list_num : %s", self.sf.db_to_realtime_daily_buy_list_num)
        logger.debug("self.sf.sell_list_num : %s", self.sf.sell_list_num)

        # 만약에 setting_data 테이블이 존재하지 않으면 구축 하는 로직
        if not self.sf.is_simul_table_exist(self.db_name, "setting_data"):
            self.init_db_setting_data()
        else:
            logger.debug("setting_data db 존재한다!!!")

        # 여기서 invest_unit 설정함
        self.sf_variable_setting()
        self.ohlcv = defaultdict(list)

    # 날짜 세팅
    def date_setting(self):
        self.today = datetime.datetime.today().strftime("%Y%m%d")
        self.today_detail = datetime.datetime.today().strftime("%Y%m%d%H%M")

    # invest_unit을 가져오는 함수
    def get_invest_unit(self):
        logger.debug("get_invest_unit 함수에 들어왔습니다!")
        sql = "select invest_unit from setting_data limit 1"
        # 데이타 Fetch
        # rows 는 list안에 튜플이 있는 [()] 형태로 받아온다
        return self.engine_JB.execute(sql).fetchall()[0][0]

    # simulator_func_mysql 에서 설정한 값을 가져오는 함수
    def sf_variable_setting(self):
        self.date_rows_yesterday = self.sf.get_recent_daily_buy_list_date()

        if not self.sf.is_simul_table_exist(self.db_name, "all_item_db"):
            logger.debug("all_item_db 없어서 생성!! init !! ")
            self.invest_unit = 0
            self.db_to_all_item(0, 0, 0, 0, 0)
            self.delete_all_item("0")

        # setting_data에 invest_unit값이 설정 되어 있는지 확인
        if not self.check_set_invest_unit():
            # setting_data에 invest_unit 값이 설정 되어 있지 않으면 세팅
            self.set_invest_unit()
        # setting_data에 invest_unit값이 설정 되어 있으면 해당 값을 가져온다.
        else:
            self.invest_unit = self.get_invest_unit()
            self.sf.invest_unit = self.invest_unit
        # setting_data에 invest_unit값이 설정 되어 있는지 확인 하는 함수

    # 보유량 가져오는 함수
    def get_holding_amount(self, code):
        logger.debug("get_holding_amount 함수에 들어왔습니다!")
        sql = "select holding_amount from possessed_item where code = '%s' group by code"
        rows = self.engine_JB.execute(sql % (code)).fetchall()
        if len(rows):
            return rows[0][0]
        else:
            logger.debug("get_holding_amount 비어있다 !")
            return False

    # setting_data에 invest_unit값이 설정 되어 있는지 확인 하는 함수
    def check_set_invest_unit(self):
        sql = "select invest_unit, set_invest_unit from setting_data limit 1"
        rows = self.engine_JB.execute(sql).fetchall()
        if rows[0][1] == self.today:
            self.invest_unit = rows[0][0]
            return True
        else:
            return False

    # 매수 금액을 설정 하는 함수
    def set_invest_unit(self):
        self.get_d2_deposit()
        self.check_balance()
        self.total_invest = self.change_format(
            str(int(self.d2_deposit_before_format) + int(self.total_purchase_price)))

        # 이런식으로 변수에 값 할당
        self.invest_unit = self.sf.invest_unit
        sql = "UPDATE setting_data SET invest_unit='%s',set_invest_unit='%s' limit 1"
        self.engine_JB.execute(sql % (self.invest_unit, self.today))

    # 변수 설정 함수
    def variable_setting(self):
        logger.debug("variable_setting 함수에 들어왔다.")
        self.get_today_buy_list_code = 0
        self.cf = cf
        self.reset_opw00018_output()
        # 아래 분기문은 실전 투자 인지, 모의 투자 인지 결정
        if self.account_number == cf.real_account:  # 실전
            self.simul_num = cf.real_simul_num
            logger.debug("실전!@@@@@@@@@@@" + cf.real_account)
            self.db_name_setting(cf.real_db_name)
            # 실전과 모의투자가 다른 것은 아래 mod_gubun 이 다르다.
            # 금일 수익률 표시 하는게 달라서(중요X)
            self.mod_gubun = 100

        elif self.account_number == cf.imi1_accout:  # 모의1
            logger.debug("모의투자 1!!")
            self.simul_num = cf.imi1_simul_num
            self.db_name_setting(cf.imi1_db_name)
            self.mod_gubun = 1

        else:
            logger.debug("계정이 존재하지 않습니다!! library/cf.py 파일에 계좌번호를 입력해주세요!")
            exit(1)
        # 여기에 이렇게 true로 고정해놔야 exit check 할때 false 인 경우에 들어갔을 때  today_buy_code is null 이런 에러 안생긴다.
        self.jango_is_null = True

        self.py_gubun = False


    # 봇 데이터 베이스를 만드는 함수
    def create_database(self, cursor):
        logger.debug("create_database!!! {}".format(self.db_name))
        sql = 'CREATE DATABASE {}'
        cursor.execute(sql.format(self.db_name))

    # 봇 데이터 베이스 존재 여부 확인 함수
    def is_database_exist(self, cursor):
        sql = "SELECT 1 FROM Information_schema.SCHEMATA WHERE SCHEMA_NAME = '{}'"
        if cursor.execute(sql.format(self.db_name)):
            logger.debug("%s 데이터 베이스가 존재한다! ", self.db_name)
            return True
        else:
            logger.debug("%s 데이터 베이스가 존재하지 않는다! ", self.db_name)
            return False

    # db 세팅 함수
    def db_name_setting(self, db_name):
        self.db_name = db_name
        logger.debug("db name !!! : %s", self.db_name)
        conn = pymysql.connect(
            host=cf.db_ip,
            port=int(cf.db_port),
            user=cf.db_id,
            password=cf.db_passwd,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        with conn.cursor() as cursor:
            if not self.is_database_exist(cursor):
                self.create_database(cursor)
            self.engine_JB = create_engine(
                "mysql+mysqldb://" + cf.db_id + ":" + cf.db_passwd + "@" + cf.db_ip + ":" + cf.db_port + "/" + db_name,
                encoding='utf-8'
            )
            self.basic_db_check(cursor)

        conn.commit()
        conn.close()

        self.engine_craw = create_engine(
            "mysql+mysqldb://" + cf.db_id + ":" + cf.db_passwd + "@" + cf.db_ip + ":" + cf.db_port + "/min_craw",
            encoding='utf-8')
        self.engine_daily_craw = create_engine(
            "mysql+mysqldb://" + cf.db_id + ":" + cf.db_passwd + "@" + cf.db_ip + ":" + cf.db_port + "/daily_craw",
            encoding='utf-8')
        self.engine_daily_buy_list = create_engine(
            "mysql+mysqldb://" + cf.db_id + ":" + cf.db_passwd + "@" + cf.db_ip + ":" + cf.db_port + "/daily_buy_list",
            encoding='utf-8')

        event.listen(self.engine_craw, 'before_execute', escape_percentage, retval=True)
        event.listen(self.engine_daily_craw, 'before_execute', escape_percentage, retval=True)
        event.listen(self.engine_daily_buy_list, 'before_execute', escape_percentage, retval=True)

    # 계좌 정보 함수
    def account_info(self):
        logger.debug("account_info 함수에 들어왔습니다!")
        account_number = self.get_login_info("ACCNO")
        self.account_number = account_number.split(';')[0]
        logger.debug("계좌번호 : " + self.account_number)

    # OpenAPI+에서 계좌 정보 및 로그인 사용자 정보를 얻어오는 메서드는 GetLoginInfo입니다.
    def get_login_info(self, tag):
        logger.debug("get_login_info 함수에 들어왔습니다!")
        try:
            ret = self.dynamicCall("GetLoginInfo(QString)", tag)
            # logger.debug(ret)
            return ret
        except Exception as e:
            logger.critical(e)

    def _create_open_api_instance(self):
        try:
            self.setControl("KHOPENAPI.KHOpenAPICtrl.1")
        except Exception as e:
            logger.critical(e)

    def _set_signal_slots(self):
        try:
            self.OnEventConnect.connect(self._event_connect)
            self.OnReceiveTrData.connect(self._receive_tr_data)
            self.OnReceiveMsg.connect(self._receive_msg)
            # 주문체결 시점에서 키움증권 서버가 발생시키는 OnReceiveChejanData 이벤트를 처리하는 메서드
            self.OnReceiveChejanData.connect(self._receive_chejan_data)


        except Exception as e:
            is_64bits = sys.maxsize > 2**32
            if is_64bits:
                logger.critical('현재 Anaconda는 64bit 환경입니다. 32bit 환경으로 실행하여 주시기 바랍니다.')
            else:
                logger.critical(e)

    def comm_connect(self):
        try:
            self.dynamicCall("CommConnect()")
            self.login_event_loop = QEventLoop()
            self.login_event_loop.exec_()
        except Exception as e:
            logger.critical(e)

    def _receive_msg(self, sScrNo, sRQName, sTrCode, sMsg):
        logger.debug("_receive_msg 함수에 들어왔습니다!")
        # logger.debug("sScrNo!!!")
        # logger.debug(sScrNo)
        # logger.debug("sRQName!!!")
        # logger.debug(sRQName)
        # logger.debug("sTrCode!!!")
        # logger.debug(sTrCode)
        # logger.debug("sMsg!!!")
        logger.debug(sMsg)

    def _event_connect(self, err_code):
        try:
            if err_code == 0:
                logger.debug("connected")
            else:
                logger.debug("disconnected")

            self.login_event_loop.exit()
        except Exception as e:
            logger.critical(e)

    def set_input_value(self, id, value):
        try:
            self.dynamicCall("SetInputValue(QString, QString)", id, value)
        except Exception as e:
            logger.critical(e)

    def comm_rq_data(self, rqname, trcode, next, screen_no):
        self.exit_check()
        ret = self.dynamicCall("CommRqData(QString, QString, int, QString", rqname, trcode, next, screen_no)
        if ret == -200:
            raise RateLimitExceeded('요청제한 횟수를 초과하였습니다.')

        self.call_time = datetime.datetime.now()

        if ret == 0:
            self.tr_event_loop = QEventLoop()
            self.tr_loop_count += 1
            self.tr_event_loop.exec_()

    def _get_comm_data(self, code, field_name, index, item_name):
        # logger.debug('calling GetCommData...')
        # self.exit_check()
        ret = self.dynamicCall("GetCommData(QString, QString, int, QString", code, field_name, index, item_name)
        return ret.strip()

    def _get_repeat_cnt(self, trcode, rqname):
        try:
            ret = self.dynamicCall("GetRepeatCnt(QString, QString)", trcode, rqname)
            return ret
        except Exception as e:
            logger.critical(e)

    def _receive_tr_data(self, screen_no, rqname, trcode, record_name, next, unused1, unused2, unused3, unused4):
        # print("screen_no, rqname, trcode", screen_no, rqname, trcode)
        if next == '2':
            self.remained_data = True
        else:
            self.remained_data = False
        # print("self.py_gubun!!", self.py_gubun)
        if rqname == "opt10081_req" and self.py_gubun == "trader":
            # logger.debug("opt10081_req trader!!!")
            # logger.debug("Get an item info !!!!")
            self._opt10081(rqname, trcode)
        elif rqname == "opt10081_req" and self.py_gubun == "collector":
            # logger.debug("opt10081_req collector!!!")
            # logger.debug("Get an item info !!!!")
            self.collector_opt10081(rqname, trcode)
        elif rqname == "opw00001_req":
            # logger.debug("opw00001_req!!!")
            # logger.debug("Get an de_deposit!!!")
            self._opw00001(rqname, trcode)
        elif rqname == "opw00018_req":
            # logger.debug("opw00018_req!!!")
            # logger.debug("Get the possessed item !!!!")
            self._opw00018(rqname, trcode)
        elif rqname == "opt10074_req":
            # logger.debug("opt10074_req!!!")
            # logger.debug("Get the profit")
            self._opt10074(rqname, trcode)
        elif rqname == "opw00015_req":
            # logger.debug("opw00015_req!!!")
            # logger.debug("deal list!!!!")
            self._opw00015(rqname, trcode)
        elif rqname == "opt10076_req":
            # logger.debug("opt10076_req")
            # logger.debug("chegyul list!!!!")
            self._opt10076(rqname, trcode)
        elif rqname == "opt10073_req":
            # logger.debug("opt10073_req")
            # logger.debug("Get today profit !!!!")
            self._opt10073(rqname, trcode)
        elif rqname == "opt10080_req":
            # logger.debug("opt10080_req!!!")
            # logger.debug("Get an de_deposit!!!")
            self._opt10080(rqname, trcode)
        elif rqname == "send_order_req":
            pass
        else:
            logger.debug(f'non existence code {rqname}, {trcode}')
        # except Exception as e:
        #     logger.critical(e)

        if rqname != 'send_order_req':
            self.tr_loop_count -= 1
        try:
            if self.tr_loop_count <= 0:
                self.tr_event_loop.exit()
                self.tr_loop_count = 0
        except AttributeError:
            pass

    # setting_data를 초기화 하는 함수
    def init_db_setting_data(self):
        logger.debug("init_db_setting_data !! ")

        #  추가하면 여기에도 추가해야함
        df_setting_data_temp = {'loan_money': [], 'limit_money': [], 'invest_unit': [], 'max_invest_unit': [],
                                'min_invest_unit': [],
                                'set_invest_unit': [], 'code_update': [], 'today_buy_stop': [],
                                'jango_data_db_check': [], 'possessed_item': [], 'today_profit': [],
                                'final_chegyul_check': [],
                                'db_to_buy_list': [], 'today_buy_list': [], 'daily_crawler': [],
                                'daily_buy_list': []}

        df_setting_data = DataFrame(df_setting_data_temp,
                                    columns=['loan_money', 'limit_money', 'invest_unit', 'max_invest_unit',
                                             'min_invest_unit',
                                             'set_invest_unit', 'code_update', 'today_buy_stop',
                                             'jango_data_db_check', 'possessed_item', 'today_profit',
                                             'final_chegyul_check',
                                             'db_to_buy_list', 'today_buy_list', 'daily_crawler',
                                             'daily_buy_list'])

        # 자료형
        df_setting_data.loc[0, 'loan_money'] = int(0)
        df_setting_data.loc[0, 'limit_money'] = int(0)
        df_setting_data.loc[0, 'invest_unit'] = int(0)
        df_setting_data.loc[0, 'max_invest_unit'] = int(0)
        df_setting_data.loc[0, 'min_invest_unit'] = int(0)

        df_setting_data.loc[0, 'set_invest_unit'] = str(0)
        df_setting_data.loc[0, 'code_update'] = str(0)
        df_setting_data.loc[0, 'today_buy_stop'] = str(0)
        df_setting_data.loc[0, 'jango_data_db_check'] = str(0)

        df_setting_data.loc[0, 'possessed_item'] = str(0)
        df_setting_data.loc[0, 'today_profit'] = str(0)
        df_setting_data.loc[0, 'final_chegyul_check'] = str(0)
        df_setting_data.loc[0, 'db_to_buy_list'] = str(0)
        df_setting_data.loc[0, 'today_buy_list'] = str(0)
        df_setting_data.loc[0, 'daily_crawler'] = str(0)
        df_setting_data.loc[0, 'min_crawler'] = str(0)
        df_setting_data.loc[0, 'daily_buy_list'] = str(0)

        df_setting_data.to_sql('setting_data', self.engine_JB, if_exists='replace')

    # all_item_db에 추가하는 함수
    def db_to_all_item(self, order_num, code, chegyul_check, purchase_price, rate):
        logger.debug("db_to_all_item 함수에 들어왔다!!!")
        self.date_setting()
        self.sf.init_df_all_item()
        self.sf.df_all_item.loc[0, 'order_num'] = order_num
        self.sf.df_all_item.loc[0, 'code'] = str(code)
        self.sf.df_all_item.loc[0, 'rate'] = float(rate)

        self.sf.df_all_item.loc[0, 'buy_date'] = self.today_detail
        # 사는 순간 chegyul_check 1 로 만드는거다.
        self.sf.df_all_item.loc[0, 'chegyul_check'] = chegyul_check
        # int로 넣어야 나중에 ++ 할수 있다.
        self.sf.df_all_item.loc[0, 'reinvest_date'] = '#'
        # df_all_item.loc[0, 'reinvest_count'] = int(0)
        # 다음에 투자할 금액은 invest_unit과 같은 금액이다.
        self.sf.df_all_item.loc[0, 'invest_unit'] = self.invest_unit
        # df_all_item.loc[0, 'reinvest_unit'] = self.invest_unit
        self.sf.df_all_item.loc[0, 'purchase_price'] = purchase_price

        # 신규 매수의 경우
        if order_num != 0:
            recent_daily_buy_list_date = self.sf.get_recent_daily_buy_list_date()
            if recent_daily_buy_list_date:
                df = self.sf.get_daily_buy_list_by_code(code, recent_daily_buy_list_date)
                if not df.empty:
                    self.sf.df_all_item.loc[0, 'code_name'] = df.loc[0, 'code_name']
                    self.sf.df_all_item.loc[0, 'close'] = df.loc[0, 'close']
                    self.sf.df_all_item.loc[0, 'open'] = df.loc[0, 'open']
                    self.sf.df_all_item.loc[0, 'high'] = df.loc[0, 'high']
                    self.sf.df_all_item.loc[0, 'low'] = df.loc[0, 'low']
                    self.sf.df_all_item.loc[0, 'volume'] = df.loc[0, 'volume']
                    self.sf.df_all_item.loc[0, 'd1_diff_rate'] = float(df.loc[0, 'd1_diff_rate'])
                    self.sf.df_all_item.loc[0, 'clo5'] = df.loc[0, 'clo5']
                    self.sf.df_all_item.loc[0, 'clo10'] = df.loc[0, 'clo10']
                    self.sf.df_all_item.loc[0, 'clo20'] = df.loc[0, 'clo20']
                    self.sf.df_all_item.loc[0, 'clo40'] = df.loc[0, 'clo40']
                    self.sf.df_all_item.loc[0, 'clo60'] = df.loc[0, 'clo60']
                    self.sf.df_all_item.loc[0, 'clo80'] = df.loc[0, 'clo80']
                    self.sf.df_all_item.loc[0, 'clo100'] = df.loc[0, 'clo100']
                    self.sf.df_all_item.loc[0, 'clo120'] = df.loc[0, 'clo120']

                    if df.loc[0, 'clo5_diff_rate'] is not None:
                        self.sf.df_all_item.loc[0, 'clo5_diff_rate'] = float(df.loc[0, 'clo5_diff_rate'])
                    if df.loc[0, 'clo10_diff_rate'] is not None:
                        self.sf.df_all_item.loc[0, 'clo10_diff_rate'] = float(df.loc[0, 'clo10_diff_rate'])
                    if df.loc[0, 'clo20_diff_rate'] is not None:
                        self.sf.df_all_item.loc[0, 'clo20_diff_rate'] = float(df.loc[0, 'clo20_diff_rate'])
                    if df.loc[0, 'clo40_diff_rate'] is not None:
                        self.sf.df_all_item.loc[0, 'clo40_diff_rate'] = float(df.loc[0, 'clo40_diff_rate'])

                    if df.loc[0, 'clo60_diff_rate'] is not None:
                        self.sf.df_all_item.loc[0, 'clo60_diff_rate'] = float(df.loc[0, 'clo60_diff_rate'])
                    if df.loc[0, 'clo80_diff_rate'] is not None:
                        self.sf.df_all_item.loc[0, 'clo80_diff_rate'] = float(df.loc[0, 'clo80_diff_rate'])
                    if df.loc[0, 'clo100_diff_rate'] is not None:
                        self.sf.df_all_item.loc[0, 'clo100_diff_rate'] = float(df.loc[0, 'clo100_diff_rate'])
                    if df.loc[0, 'clo120_diff_rate'] is not None:
                        self.sf.df_all_item.loc[0, 'clo120_diff_rate'] = float(df.loc[0, 'clo120_diff_rate'])

        # 컬럼 중에 nan 값이 있는 경우 0으로 변경 -> 이렇게 안하면 아래 데이터베이스에 넣을 때
        # AttributeError: 'numpy.int64' object has no attribute 'translate' 에러 발생
        self.sf.df_all_item = self.sf.df_all_item.fillna(0)
        self.sf.df_all_item.to_sql('all_item_db', self.engine_JB, if_exists='append', dtype={
            'code_name': Text,
            'rate': Float,
            'sell_rate': Float,
            'purchase_rate': Float,
            'sell_date': Text,
            'd1_diff_rate': Float,
            'clo5_diff_rate': Float,
            'clo10_diff_rate': Float,
            'clo20_diff_rate': Float,
            'clo40_diff_rate': Float,
            'clo60_diff_rate': Float,
            'clo80_diff_rate': Float,
            'clo100_diff_rate': Float,
            'clo120_diff_rate': Float
        })

    def check_balance(self):

        logger.debug("check_balance 함수에 들어왔습니다!")
        # 1차원 / 2차원 인스턴스 변수 생성
        self.reset_opw00018_output()

        # # 예수금 가져오기
        # self.get_d2_deposit()

        # 여기서 부터는 1차원 2차원 데이터 다 불러오는거다 opw00018에 1차원 2차원 다 있다.
        # 1차원 : 위에 한 줄 표  2차원 : 매수한 종목들

        # comm_rq_data 호출하기 전에 반드시 set_input_value 해야한다.
        self.set_input_value("계좌번호", self.account_number)
        # 사용자구분명, tran명, 3째는 0은 조회, 2는 연속, 네번째 2000은 화면 번호
        self.comm_rq_data("opw00018_req", "opw00018", 0, "2000")

        while self.remained_data:
            # # comm_rq_data 호출하기 전에 반드시 set_input_value 해야한다. 초기화 되기 때문
            self.set_input_value("계좌번호", self.account_number)

            self.comm_rq_data("opw00018_req", "opw00018", 2, "2000")
            # print("self.opw00018_output: ", self.opw00018_output)

    def get_count_possesed_item(self):
        logger.debug("get_count_possesed_item!!!")

        sql = "select count(*) from possessed_item"
        rows = self.engine_JB.execute(sql).fetchall()
        # 데이타 Fetch
        # rows 는 list안에 튜플이 있는 [()] 형태로 받아온다

        return rows[0][0]

    def setting_data_possesed_item(self):

        sql = "UPDATE setting_data SET possessed_item='%s' limit 1"
        self.engine_JB.execute(sql % (self.today))
        # self.jackbot_db_con.commit()

    # 실제로 키움증권에서 보유한 종목들의 리스트를 가져오는 함수
    def db_to_possesed_item(self):
        logger.debug("db_to_possesed_item 함수에 들어왔습니다!")
        item_count = len(self.opw00018_output['multi'])
        possesed_item_temp = {'date': [], 'code': [], 'code_name': [], 'holding_amount': [], 'puchase_price': [],
                              'present_price': [], 'valuation_profit': [], 'rate': [], 'item_total_purchase': []}

        possesed_item = DataFrame(possesed_item_temp,
                                  columns=['date', 'code', 'code_name', 'holding_amount', 'puchase_price',
                                           'present_price', 'valuation_profit', 'rate', 'item_total_purchase'])

        for i in range(item_count):
            row = self.opw00018_output['multi'][i]
            # 오늘 일자
            possesed_item.loc[i, 'date'] = self.today
            possesed_item.loc[i, 'code'] = row[7]
            possesed_item.loc[i, 'code_name'] = row[0]
            # 보유량
            possesed_item.loc[i, 'holding_amount'] = int(row[1])
            # 매수가
            possesed_item.loc[i, 'puchase_price'] = int(row[2])
            # 현재가
            possesed_item.loc[i, 'present_price'] = int(row[3])

            # valuation_profit은 사실상 의미가 없다. 백만원 어치 종목 매도 시 한번에 매도 되는게 아니고
            # 10만원 씩 10번 체결 될 수 있기 때문에
            # 마지막 체결 된 10만원이 possessd_item 테이블의 valuation_profit컬럼에 적용이 된다. 따라서 그냥 무시
            possesed_item.loc[i, 'valuation_profit'] = int(row[4])
            # 수익률, 반드시 float로 넣어줘야한다.
            possesed_item.loc[i, 'rate'] = float(row[5])
            # 총 매수 금액
            possesed_item.loc[i, 'item_total_purchase'] = int(row[6])
        # possessed_item 테이블에 현재 보유 종목을 넣는다.
        possesed_item.to_sql('possessed_item', self.engine_JB, if_exists='replace')
        self.chegyul_sync()

    # get_total_data_min : 특정 종목의 틱 (1분별) 데이터 조회 함수
    # 사용방법
    # code: 종목코드(ex. '005930' )
    # date : 기준일자. (ex. '20200424') => 20200424 일자 까지의 모든 open, high, low, close, volume 데이터 출력
    def get_total_data_min(self, code, code_name, start):
        self.ohlcv = defaultdict(list)

        self.set_input_value("종목코드", code)
        self.set_input_value("틱범위", 1)
        self.set_input_value("수정주가구분", 1)
        self.comm_rq_data("opt10080_req", "opt10080", 0, "1999")

        self.craw_table_exist = False

        if self.is_min_craw_table_exist(code_name):
            self.craw_table_exist = True
            self.craw_db_last_min = self.get_craw_db_last_min(code_name)
            self.craw_db_last_min_sum_volume = self.get_craw_db_last_min_sum_volume(code_name)

        else:
            self.craw_db_last_min = str(0)
            self.craw_db_last_min_sum_volume = 0

        while self.remained_data == True:
            time.sleep(TR_REQ_TIME_INTERVAL)
            self.set_input_value("종목코드", code)
            self.set_input_value("틱범위", 1)
            # self.set_input_value("기준일자", start)
            self.set_input_value("수정주가구분", 1)
            self.comm_rq_data("opt10080_req", "opt10080", 2, "1999")

            if self.ohlcv['date'][-1] < self.craw_db_last_min:
                break

        time.sleep(TR_REQ_TIME_INTERVAL)

        if len(self.ohlcv['date']) == 0 or self.ohlcv['date'][0] == '':
            return []
        # 위에 에러나면 이거해봐 일단 여기 try catch 해야함
        if self.ohlcv['date'] == '':
            return []

        df = DataFrame(self.ohlcv, columns=['date', 'open', 'high', 'low', 'close', 'volume', 'sum_volume'])

        return df

    # get_total_data : 특정 종목의 일자별 거래 데이터 조회 함수
    # 사용방법
    # code: 종목코드(ex. '005930' )
    # date : 기준일자. (ex. '20200424') => 20200424 일자 까지의 모든 open, high, low, close, volume 데이터 출력
    def get_total_data(self, code, code_name, date):
        logger.debug("get_total_data 함수에 들어왔다!")

        self.ohlcv = defaultdict(list)
        self.set_input_value("종목코드", code)
        self.set_input_value("기준일자", date)
        self.set_input_value("수정주가구분", 1)

        # 아래에 이거 하나만 있고 while없애면 600일 한번만 가져오는거
        self.comm_rq_data("opt10081_req", "opt10081", 0, "0101")

        # 만약에 종목 테이블이 없으면 600일 한번만 가져오는게 아니고 몇 천일이던 싹다 가져오는거다.
        if not self.is_craw_table_exist(code_name):
            while self.remained_data == True:
                self.set_input_value("종목코드", code)
                self.set_input_value("기준일자", date)
                self.set_input_value("수정주가구분", 1)
                self.comm_rq_data("opt10081_req", "opt10081", 2, "0101")

        # data 비어있는 경우
        if len(self.ohlcv) == 0:
            return []
        # 위에 에러나면 이거해봐 일단 여기 try catch 해야함
        if self.ohlcv['date'] == '':
            return []
        # logger.debug(7)
        df = DataFrame(self.ohlcv, columns=['date', 'open', 'high', 'low', 'close', 'volume'])

        return df

    # except Exception as e:
    #     logger.critical(e)

    # daily_craw에 종목 테이블 존재 여부 확인 함수
    def is_craw_table_exist(self, code_name):
        # #jackbot("******************************** is_craw_table_exist !!")
        sql = "select 1 from information_schema.tables where table_schema ='daily_craw' and table_name = '{}'"
        rows = self.engine_daily_craw.execute(sql.format(code_name)).fetchall()
        if rows:
            return True
        else:
            logger.debug(str(code_name) + " 테이블이 daily_craw db 에 없다. 새로 생성! ", )
            return False

    def is_min_craw_table_exist(self, code_name):
        # #jackbot("******************************** is_craw_table_exist !!")
        sql = "select 1 from information_schema.tables where table_schema ='min_craw' and table_name = '{}'"
        rows = self.engine_craw.execute(sql.format(code_name)).fetchall()
        if rows:
            return True
        else:
            logger.debug(str(code_name) + " min_craw db에 없다 새로 생성! ", )
            return False

    # min_craw 테이블에서 마지막 콜렉팅한 row의 sum_volume을 가져오는 함수
    def get_craw_db_last_min_sum_volume(self, code_name):
        sql = "SELECT sum_volume from `" + code_name + "` order by date desc limit 1"
        rows = self.engine_craw.execute(sql).fetchall()
        if len(rows):
            return rows[0][0]
        # 신생
        else:
            return str(0)

    # min_craw db 특정 종목의 테이블에서 마지막으로 콜렉팅한 date를 가져오는 함수
    def get_craw_db_last_min(self, code_name):
        sql = "SELECT date from `" + code_name + "` order by date desc limit 1"
        rows = self.engine_craw.execute(sql).fetchall()
        if len(rows):
            return rows[0][0]
        # 신생
        else:
            return str(0)

    # daily_craw 특정 종목의 테이블에서 마지막으로 콜렉팅한 date를 가져오는 함수
    def get_daily_craw_db_last_date(self, code_name):
        sql = "SELECT date from `" + code_name + "` order by date desc limit 1"
        rows = self.engine_daily_craw.execute(sql).fetchall()
        if len(rows):
            return rows[0][0]
        # 신생
        else:
            return str(0)

    # get_one_day_option_data : 특정 종목의 특정 일 open(시작가), high(최고가), low(최저가), close(종가), volume(거래량) 조회 함수
    # 사용방법
    # code : 종목코드
    # start : 조회 일자
    # option : open(시작가), high(최고가), low(최저가), close(종가), volume(거래량)
    def get_one_day_option_data(self, code, start, option):
        self.ohlcv = defaultdict(list)

        self.set_input_value("종목코드", code)

        self.set_input_value("기준일자", start)

        self.set_input_value("수정주가구분", 1)

        self.comm_rq_data("opt10081_req", "opt10081", 0, "0101")

        if self.ohlcv['date'] == '':
            return False

        df = DataFrame(self.ohlcv, columns=['open', 'high', 'low', 'close', 'volume'], index=self.ohlcv['date'])


        # 데이터 프레임이 비어있으면 False를 반환한다.
        if df.empty:
            return False
        logger.debug("get_one_day_option_data df : {} ".format(df))
        logger.debug("code : {},type(code): {}, start: {}, option: {} ".format(code, type(code), start, option))
        logger.debug("df.iloc[0, 3] (close) : {} ".format(df.iloc[0, 3]))

        if option == 'open':
            return df.iloc[0, 0]
        elif option == 'high':
            return df.iloc[0, 1]
        elif option == 'low':
            return df.iloc[0, 2]
        elif option == 'close':
            return df.iloc[0, 3]
        elif option == 'volume':
            return df.iloc[0, 4]
        else:
            return False

    def collector_opt10081(self, rqname, trcode):
        # 몇 개의 row를 읽어 왔는지 담는 변수
        ohlcv_cnt = self._get_repeat_cnt(trcode, rqname)

        for i in range(ohlcv_cnt):
            date = self._get_comm_data(trcode, rqname, i, "일자")
            open = self._get_comm_data(trcode, rqname, i, "시가")
            high = self._get_comm_data(trcode, rqname, i, "고가")
            low = self._get_comm_data(trcode, rqname, i, "저가")
            close = self._get_comm_data(trcode, rqname, i, "현재가")
            volume = self._get_comm_data(trcode, rqname, i, "거래량")

            self.ohlcv['date'].append(date)
            self.ohlcv['open'].append(int(open))
            self.ohlcv['high'].append(int(high))
            self.ohlcv['low'].append(int(low))
            self.ohlcv['close'].append(int(close))
            self.ohlcv['volume'].append(int(volume))

    # except Exception as e:
    #     logger.critical(e)

    # open_api 클래스에 send_order 메서드를 추가해줍니다. 매수
    #     SendOrder 메서드를 사용하면 주식 주문에 대한 정보를 서버로 전송할 수 있습니다. 다만, 증권사 서버에 주문 요청을 했다고 해서 즉시 체결되는 것이 아니므로 이벤트 루프를 사용해 대기하고 있어야 합니다.
    # rqname - 사용자 구분 요청 명
    # screen_no - 화면번호[4]
    # acc_no - 계좌번호[10]
    # order_type - 주문유형 (1:신규매수, 2:신규매도, 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정
    # 정)
    # code, - 주식종목코드
    # quantity – 주문수량
    # price – 주문단가
    # hoga - 거래구분
    # order_no  – 원주문번호

    def _opt10080(self, rqname, trcode):
        data_cnt = self._get_repeat_cnt(trcode, rqname)
        for i in range(data_cnt):
            date = self._get_comm_data(trcode, rqname, i, "체결시간")
            open = self._get_comm_data(trcode, rqname, i, "시가")
            high = self._get_comm_data(trcode, rqname, i, "고가")
            low = self._get_comm_data(trcode, rqname, i, "저가")
            close = self._get_comm_data(trcode, rqname, i, "현재가")
            volume = self._get_comm_data(trcode, rqname, i, "거래량")

            self.ohlcv['date'].append(date[:-2])
            self.ohlcv['open'].append(abs(int(open)))
            self.ohlcv['high'].append(abs(int(high)))
            self.ohlcv['low'].append(abs(int(low)))
            self.ohlcv['close'].append(abs(int(close)))
            self.ohlcv['volume'].append(int(volume))
            self.ohlcv['sum_volume'].append(int(0))

    # trader가 호출 할때는 collector_opt10081과 다르게 1회만 _get_comm_data 호출 하면 된다.
    def _opt10081(self, rqname, trcode):
        code = self._get_comm_data(trcode, rqname, 0, "종목코드")
        if code != self.get_today_buy_list_code:
            logger.critical(
                f'_opt10081: ({code}, {self.get_today_buy_list_code})'
            )
        try:
            logger.debug("_opt10081!!!")
            date = self._get_comm_data(trcode, rqname, 0, "일자")
            open = self._get_comm_data(trcode, rqname, 0, "시가")
            high = self._get_comm_data(trcode, rqname, 0, "고가")
            low = self._get_comm_data(trcode, rqname, 0, "저가")
            close = self._get_comm_data(trcode, rqname, 0, "현재가")
            volume = self._get_comm_data(trcode, rqname, 0, "거래량")

            self.ohlcv['date'].append(date)
            self.ohlcv['open'].append(int(open))
            self.ohlcv['high'].append(int(high))
            self.ohlcv['low'].append(int(low))
            self.ohlcv['close'].append(int(close))
            self.ohlcv['volume'].append(int(volume))
        except Exception as e:
            logger.critical(e)

    #          [SendOrder() 함수]
    #
    #           SendOrder(
    #           BSTR sRQName, // 사용자 구분명
    #           BSTR sScreenNo, // 화면번호
    #           BSTR sAccNo,  // 계좌번호 10자리
    #           LONG nOrderType,  // 주문유형 1:신규매수, 2:신규매도 3:매수취소, 4:매도취소, 5:매수정정, 6:매도정정
    #           BSTR sCode, // 종목코드
    #           LONG nQty,  // 주문수량
    #           LONG nPrice, // 주문가격
    #           BSTR sHogaGb,   // 거래구분(혹은 호가구분)은 아래 참고
    #           BSTR sOrgOrderNo  // 원주문번호입니다. 신규주문에는 공백, 정정(취소)주문할 원주문번호를 입력합니다.
    #           )
    #
    #           9개 인자값을 가진 국내 주식주문 함수이며 리턴값이 0이면 성공이며 나머지는 에러입니다.
    #           1초에 5회만 주문가능하며 그 이상 주문요청하면 에러 -308을 리턴합니다.
    #
    #           [거래구분]
    #           모의투자에서는 지정가 주문과 시장가 주문만 가능합니다.
    #
    #           00 : 지정가
    #           03 : 시장가
    #           05 : 조건부지정가
    #           06 : 최유리지정가
    #           07 : 최우선지정가
    #           10 : 지정가IOC
    #           13 : 시장가IOC
    #           16 : 최유리IOC
    #           20 : 지정가FOK
    #           23 : 시장가FOK
    #           26 : 최유리FOK
    #           61 : 장전시간외종가
    #           62 : 시간외단일가매매
    #           81 : 장후시간외종가
    #
    # openapi 매수 요청
    def send_order(self, rqname, screen_no, acc_no, order_type, code, quantity, price, hoga, order_no):
        logger.debug("send_order!!!")
        try:
            self.exit_check()
            self.dynamicCall("SendOrder(QString, QString, QString, int, QString, int, int, QString, QString)",
                             [rqname, screen_no, acc_no, order_type, code, quantity, price, hoga, order_no])
        except Exception as e:
            logger.critical(e)

    # # 체결 데이터를 가져오는 메서드인 GetChejanData를 사용하는
    # get_chejan_data 메서드
    def get_chejan_data(self, fid):
        # logger.debug("get_chejan_data!!!")
        try:
            ret = self.dynamicCall("GetChejanData(int)", fid)
            return ret
        except Exception as e:
            logger.critical(e)

    #  코드명에 해당 하는 종목코드를 반환해주는 함수
    def codename_to_code(self, codename):
        # logger.debug("codename_to_code!!!")

        sql = "select code from stock_item_all where code_name='%s'"
        rows = self.engine_daily_buy_list.execute(sql % (codename)).fetchall()
        # 데이타 Fetch
        # rows 는 list안에 튜플이 있는 [()] 형태로 받아온다

        if len(rows) != 0:
            return rows[0][0]

        logger.debug("code를 찾을 수 없다!! name이 긴놈이다!!!!")
        logger.debug(codename)

        sql = f"select code from stock_item_all where code_name like '{codename}%'"
        rows = self.engine_daily_buy_list.execute(sql).fetchall()

        if len(rows) != 0:
            return rows[0][0]

        logger.debug("codename이 존재하지 않는다 ..... 긴 것도 아니다...")

        return False

    def end_invest_count_check(self, code):
        logger.debug("end_invest_count_check 함수로 들어왔습니다!")
        logger.debug("end_invest_count_check_code!!!!!!!!")
        logger.debug(code)

        sql = "UPDATE all_item_db SET chegyul_check='%s' WHERE code='%s' and sell_date = '%s' ORDER BY buy_date desc LIMIT 1"

        self.engine_JB.execute(sql % (0, code, 0))

        # 중복적으로 possessed_item 테이블에 반영되는 이슈가 있어서 일단 possesed_item 테이블에서 해당 종목을 지운다.
        # 어차피 다시 possessed_item은 업데이트가 된다.
        sql = "delete from possessed_item where code ='%s'"
        self.engine_JB.execute(sql % (code,))

    # 매도 했는데 완벽히 매도 못한 경우
    def sell_chegyul_fail_check(self, code):
        logger.debug("sell_chegyul_fail_check 함수에 들어왔습니다!")
        logger.debug(code + " check!")
        sql = "UPDATE all_item_db SET chegyul_check='%s' WHERE code='%s' and sell_date = '%s' ORDER BY buy_date desc LIMIT 1"
        self.engine_JB.execute(sql % (1, code, 0))

    # 잔액이 생겨서 다시 매수 할 수 있는 상황인 경우 setting_data의 today_buy_stop 옵션을 0으로 변경
    def buy_check_reset(self):
        logger.debug("buy_check_reset!!!")

        sql = "UPDATE setting_data SET today_buy_stop='%s' WHERE id='%s'"
        self.engine_JB.execute(sql % (0, 1))

    # 투자 가능한 잔액이 부족한 경우이거나, 매수할 종목이 더이상 없는 경우
    # setting_data의 today_buy_stop 옵션을 1로 변경-> 더이상 매수 하지 않는다.
    def buy_check_stop(self):
        logger.debug("buy_check_stop!!!")
        sql = "UPDATE setting_data SET today_buy_stop='%s' limit 1"
        self.engine_JB.execute(sql % (self.today))

    # 잔액 체크 함수
    def jango_check(self):
        logger.debug("jango_check 함수에 들어왔습니다!")
        self.get_d2_deposit()
        # 아래에 1.5 곱해준 이유는 invest unit보다 d2가 조금 많으면 못사네 ; 그래서 넉넉히 잡은거임  매수증거금때문이다.
        # if (int(self.d2_deposit_before_format) > (int(self.sf.limit_money) + int(self.invest_unit)*1.5)) :
        try:
            if int(self.d2_deposit_before_format) > (int(self.sf.limit_money)):
                # jango_is_null 역할은 trade 루프 돌다가 하나 샀더니 돈 부족해질때 그때 루프를 빠져나오는 용도
                self.jango_is_null = False
                logger.debug("돈안부족해 투자 가능!!!!!!!!")
                return True
            else:
                # self.open_api.buy_check_stop()
                logger.debug("돈부족해서 invest 불가!!!!!!!!")
                self.jango_is_null = True
                return False
        except Exception as e:
            logger.critical(e)

    # 현재 잔액 부족, 매수할 종목 리스트가 없는 경우로 인해
    # setting_data 테이블의 today_buy_stop 컬럼에 오늘 날짜가 찍혀있는지 확인하는 함수
    # setting_data 테이블의 today_buy_stop에 날짜가 찍혀 있으면 매수 중지, 0이면 매수 진행 가능
    def buy_check(self):
        logger.debug("buy_check 함수에 들어왔습니다!")
        sql = "select today_buy_stop from setting_data limit 1"
        rows = self.engine_JB.execute(sql).fetchall()[0][0]

        if rows != self.today:
            logger.debug("GoGo Buying!!!!!!")
            return True
        else:
            logger.debug("Stop Buying!!!!!!")
            return False

    # 몇 개의 주를 살지 계산 하는 함수
    def buy_num_count(self, invest_unit, present_price):
        logger.debug("buy_num_count 함수에 들어왔습니다!")
        return int(invest_unit / present_price)

    # 매수 함수
    def trade(self):
        logger.debug("trade 함수에 들어왔다!")
        logger.debug("매수 대상 종목 코드! " + self.get_today_buy_list_code)

        # 실시간 현재가(close) 가져오는 함수
        # close는 종가 이지만, 현재 시점의 종가를 가져오기 때문에 현재가를 가져온다.
        current_price = self.get_one_day_option_data(self.get_today_buy_list_code, self.today, 'close')

        if current_price == False:
            logger.debug(self.get_today_buy_list_code + " 의 현재가가 비어있다 !!!")
            return False

        # 매수 가격 최저 범위
        min_buy_limit = int(self.get_today_buy_list_close) * self.sf.invest_min_limit_rate
        # 매수 가격 최고 범위
        max_buy_limit = int(self.get_today_buy_list_close) * self.sf.invest_limit_rate
        # 현재가가 매수 가격 최저 범위와 매수 가격 최고 범위 안에 들어와 있다면 매수 한다.
        if min_buy_limit < current_price < max_buy_limit:
            buy_num = self.buy_num_count(self.invest_unit, int(current_price))
            logger.debug(
                "매수!!!!+-+-+-+-+-+-+-+-+-+-+-+-+-+-+- code :%s, 목표가: %s, 현재가: %s, 매수량: %s, min_buy_limit: %s, max_buy_limit: %s , invest_limit_rate: %s,예수금: %s , today : %s, today_min : %s, date_rows_yesterday : %s, invest_unit : %s, real_invest_unit : %s +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-",
                self.get_today_buy_list_code, self.get_today_buy_list_close, current_price, buy_num, min_buy_limit,
                max_buy_limit, self.sf.invest_limit_rate, self.d2_deposit_before_format, self.today, self.today_detail,
                self.date_rows_yesterday, self.invest_unit, int(current_price) * int(buy_num))

            # 03 시장가 매수
            # 4번째 인자: 1: 신규매수 / 2: 신규매도 / 3:매수취소 / 4:매도취소 / 5: 매수정정 / 6:매도정정
            self.send_order("send_order_req", "0101", self.account_number, 1, self.get_today_buy_list_code, buy_num, 0,
                            "03", "")

            # 만약 sf.only_nine_buy가 False 이면 즉, 한번 매수하고 금일 매수를 중단하는 것이 아니라면, 매도 후에 잔액이 생기면 다시 매수를 시작
            # sf.only_nine_buy가 True이면 1회만 매수, 1회 매수 시 잔액이 부족해지면 바로 매수 중단 
            if not self.jango_check() and self.sf.only_nine_buy:
                logger.debug("하나 샀더니 잔고가 부족해진 구간!!!!!")
                # setting_data에 today_buy_stop을 1 로 설정
                self.buy_check_stop()
        else:
            logger.debug(
                "invest_limit_rate 만큼 급등 or invest_min_limit_rate 만큼 급락 해서 매수 안함 !!! code :%s, 목표가: %s , 현재가: %s, invest_limit_rate: %s , invest_min_limit_rate : %s, today : %s, today_min : %s, date_rows_yesterday : %s",
                self.get_today_buy_list_code, self.get_today_buy_list_close, current_price, self.sf.invest_limit_rate,
                self.sf.invest_min_limit_rate, self.today, self.today_detail, self.date_rows_yesterday)

    # 오늘 매수 할 종목들을 가져오는 함수
    def get_today_buy_list(self):
        logger.debug("get_today_buy_list 함수에 들어왔습니다!")

        logger.debug("self.today : %s , self.date_rows_yesterday : %s !", self.today, self.date_rows_yesterday)

        if self.sf.is_simul_table_exist(self.db_name, "realtime_daily_buy_list"):
            logger.debug("realtime_daily_buy_list 생겼다!!!!! ")
            self.sf.get_realtime_daily_buy_list()
            if self.sf.len_df_realtime_daily_buy_list == 0:
                logger.debug("realtime_daily_buy_list 생겼지만 아직 data가 없다!!!!! ")
                return
        else:
            logger.debug("realtime_daily_buy_list 없다 !! ")
            return


        logger.debug("self.sf.len_df_realtime_daily_buy_list 이제 사러간다!! ")
        logger.debug("매수 리스트!!!!")
        logger.debug(self.sf.df_realtime_daily_buy_list)
        # 만약에 realtime_daily_buy_list 의 종목 수가 1개 이상이면 아래 로직을 들어간다
        for i in range(self.sf.len_df_realtime_daily_buy_list):
            # code를 가져온다
            code = self.sf.df_realtime_daily_buy_list.loc[i, 'code']
            # 종가를 가져온다
            close = self.sf.df_realtime_daily_buy_list.loc[i, 'close']
            # 이미 오늘 매수 한 종목이면 check_item은 1 / 아직 매수 안했으면 0
            check_item = self.sf.df_realtime_daily_buy_list.loc[i, 'check_item']

            if self.jango_is_null:
                break
            # 이미 매수한 종목은 넘기고 다음 종목을 사라는 의미
            if check_item == True:
                continue
            else:
                # (추가) 매수 조건 함수(trade_check) ##########################################
                # trade_check_num(실시간 조건 체크-> 실시간으로 조건 비교 하여 매수하는 경우)
                # 고급챕터에서 수업 할 때 아래 주석을 풀어주세요!
                # if self.sf.trade_check_num:
                #     # 시작가를 가져온다
                #     current_open = self.get_one_day_option_data(code, self.today, 'open')
                #     current_price = self.get_one_day_option_data(code, self.today, 'close')
                #     current_sum_volume = self.get_one_day_option_data(code, self.today, 'volume')
                #     if not self.sf.trade_check(self.sf.df_realtime_daily_buy_list.loc[i], current_open, current_price, current_sum_volume):
                #         continue
                ###################################################################################

                self.get_today_buy_list_code = code
                self.get_today_buy_list_close = close
                # 매수 하기 전에 해당 종목의 check_item을 1로 변경. 즉, 이미 매수 했으니까 다시 매수 하지말라고 체크 하는 로직
                sql = "UPDATE realtime_daily_buy_list SET check_item='%s' WHERE code='%s'"
                self.engine_JB.execute(sql % (1, self.get_today_buy_list_code))
                self.trade()

        # 모든 매수를 마쳤으면 더이상 매수 하지 않도록 설정하는 함수
        if self.sf.only_nine_buy:
            self.buy_check_stop()

    # openapi 조회 카운트를 체크 하고 cf.max_api_call 횟수 만큼 카운트 되면 봇이 꺼지게 하는 함수
    def exit_check(self):
        rq_delay = datetime.timedelta(seconds=0.6)
        time_diff = datetime.datetime.now() - self.call_time
        if rq_delay > datetime.datetime.now() - self.call_time:
            time.sleep((rq_delay - time_diff).total_seconds())

        self.rq_count += 1
        # openapi 조회 count 출력
        logger.debug(self.rq_count)
        if self.rq_count == cf.max_api_call:
            sys.exit(1)

    # 매도 했는데 bot이 꺼져있을때 매도해서 possessed_item 테이블에는 없는데 all_item_db에 sell_date 안찍힌 종목들 처리해준다.
    def final_chegyul_check(self):
        sql = "select code from all_item_db a where (a.sell_date = '%s' or a.sell_date ='%s') and a.code not in ( select code from possessed_item) and a.chegyul_check != '%s'"

        rows = self.engine_JB.execute(sql % (0, "", 1)).fetchall()
        logger.debug("possess_item 테이블에는 없는데 all_item_db에 sell_date가 없는 리스트 처리!!!")
        logger.debug(rows)
        num = len(rows)

        for t in range(num):
            logger.debug(f"t!!! {t}")
            self.sell_final_check2(rows[t][0])

        # 오늘 리스트 다 뽑았으면 today를 setting_data에 체크
        sql = "UPDATE setting_data SET final_chegyul_check='%s' limit 1"
        self.engine_JB.execute(sql % (self.today))

    # all_item_db의 rate를 업데이트 한다.
    def rate_check(self):
        logger.debug("rate_check!!!")
        sql = "select code ,holding_amount, puchase_price, present_price, valuation_profit, rate,item_total_purchase from possessed_item group by code"
        rows = self.engine_JB.execute(sql).fetchall()

        logger.debug("rate 업데이트 !!!")
        logger.debug(rows)
        num = len(rows)

        for k in range(num):
            # logger.debug("k!!!")
            # logger.debug(k)
            code = rows[k][0]
            holding_amount = rows[k][1]
            purchase_price = rows[k][2]
            present_price =rows[k][3]
            valuation_profit=rows[k][4]
            rate = rows[k][5]
            item_total_purchase = rows[k][6]
            # print("rate!!", rate)
            sql = "update all_item_db set holding_amount ='%s', purchase_price ='%s', present_price='%s',valuation_profit='%s',rate='%s',item_total_purchase='%s' where code='%s' and sell_date = '%s'"
            self.engine_JB.execute(sql % (holding_amount,purchase_price,present_price,valuation_profit,float(rate),item_total_purchase, code, 0))

    def chegyul_sync(self):
        # 먼저 possessd_item 테이블에는 있는데 all_item_db에 없는 종목들 추가해준다
        sql = """select code, code_name, rate from possessed_item p
            where p.code not in (select a.code from all_item_db a
                                 where a.sell_date = '0' group by a.code)
            group by p.code"""

        rows = self.engine_JB.execute(sql).fetchall()

        logger.debug("possess_item 테이블에는 있는데 all_item_db에 없는 종목들 처리!!!")
        logger.debug(rows)

        for r in rows:
            self.set_input_value("종목코드", r.code)
            # 	조회구분 = 0:전체, 1:종목
            self.set_input_value("조회구분", 1)
            # SetInputValue("조회구분"	,  "입력값 2");
            # 	계좌번호 = 전문 조회할 보유계좌번호
            self.set_input_value("계좌번호", self.account_number)
            # 	비밀번호 = 사용안함(공백)
            # 	SetInputValue("비밀번호"	,  "입력값 5");
            self.comm_rq_data("opt10076_req", "opt10076", 0, "0350")

            if self._data['주문구분'] == '+매수':
                if self._data['미체결수량'] == 0:
                    chegyul_check = 0
                else:
                    chegyul_check = 1
            elif self._data['주문구분'] == '':
                self.db_to_all_item(self.today, r.code, 0, 0, r.rate)
                continue
            else:
                continue

            self.db_to_all_item(self._data['주문번호'], r.code, chegyul_check, self._data['체결가'], r.rate)

    # 체결이 됐는지 안됐는지 확인한다.
    # 매수 했을 경우 possessd_item 테이블에는 있는데, all_item_db에 없는 경우가 있다.
    # why ? 매수 한 뒤에 all_item_db에 추가하기 전에 봇이 꺼지는 경우!
    # 따라서 아래 체결 체크를 확인하는 함수가 필요로 하다.
    def chegyul_check(self):
        sql = "SELECT code FROM all_item_db where chegyul_check='1' and (sell_date = '0' or sell_date= '')"
        rows = self.engine_JB.execute(sql).fetchall()

        logger.debug("in chegyul_check!!!!! all_item_db에서 cheguyl_check가 1인 종목들(미체결상태) 확인!!!")
        logger.debug(rows)

        # 여기서 너무많이 rq_count 올라간다. 매수를 한 만큼, 매도를 한만큼 그 2배의 시간이 걸림 무조건 .
        for r in rows:
            # 1. Open API 조회 함수 입력값을 설정합니다.
            # 	종목코드 = 전문 조회할 종목코드
            logger.debug(f"chegyul_check code!! : {r.code}")
            self.set_input_value("종목코드", r.code)
            # 	조회구분 = 0:전체, 1:종목
            self.set_input_value("조회구분", 1)
            self.set_input_value("계좌번호", self.account_number)
            self.comm_rq_data("opt10076_req", "opt10076", 0, "0350")

            update_sql = f"UPDATE all_item_db SET chegyul_check='0' WHERE code='{r.code}' and sell_date = '0'" \
                         f"ORDER BY buy_date DESC LIMIT 1"
            if not self._data['주문번호']: # 과거에 거래한 경우 opt10076 조회 시 주문번호 등의 데이터가 존재하지 않음.
                logger.debug(f"{r.code} 체결 완료 (과거 거래 한 경우)")
                self.engine_JB.execute(update_sql)

            elif self._data['미체결수량'] == 0:
                logger.debug(f"{r.code} 체결 완료 (오늘 거래 한 경우)")
                # 제일 최근 종목하나만 체결정보 업데이트하는거다
                self.engine_JB.execute(update_sql)

            else:
                logger.debug(f"아직 매수 혹은 매도 중인 종목 !!!! 미체결 수량: {self._data['미체결수량']}")

    # 하나의 종목이 체결이 됐는지 확인
    # 그래야 재매수든, 초기매수든 한번 샀는데 미체결량이 남아서 다시 사는건지 확인이 가능하다.
    def stock_chegyul_check(self, code):
        logger.debug("stock_chegyul_check 함수에 들어왔다!")

        sql = "SELECT chegyul_check FROM all_item_db where code='%s' and sell_date = '%s' ORDER BY buy_date desc LIMIT 1"
        # 무조건 튜플 형태로 실행해야한다. 따라서 인자 하나를 보내더라도 ( , ) 안에 하나 넣어서 보낸다.
        # self.engine_JB.execute(sql % (self.today,))

        rows = self.engine_JB.execute(sql % (code, 0)).fetchall()

        if rows[0][0] == 1:
            return True
        else:
            return False

    # 매도 후 all item db 에 작업하는거
    def sell_final_check(self, code):
        logger.debug("sell_final_check")

        # sell_price가 없어서 에러가났음
        get_list = self.engine_JB.execute(f"""
            SELECT valuation_profit, rate, item_total_purchase, present_price 
            FROM possessed_item WHERE code='{code}' LIMIT 1
        """).fetchall()
        if get_list:
            item = get_list[0]
            sql = f"""UPDATE all_item_db
                SET item_total_purchase = {item.item_total_purchase}, chegyul_check = 0,
                 sell_date = '{self.today_detail}', valuation_profit = {item.valuation_profit},
                 sell_rate = {item.rate}, sell_price = {item.present_price}
                WHERE code = '{code}' and sell_date = '0' ORDER BY buy_date desc LIMIT 1"""
            self.engine_JB.execute(sql)

            # 팔았으면 즉각 possess db에서 삭제한다. 왜냐하면 checgyul_check 들어가기 직전에 possess_db를 최신화 하긴 하지만 possess db 최신화와 chegyul_check 사이에 매도가 이뤄져서 receive로 가게 되면 sell_date를 찍어버리기 때문에 checgyul_check 입장에서는 possess에는 존재하고 all_db는 sell_date찍혀있다고 판단해서 새롭게 all_db추가해버린다.
            self.engine_JB.execute(f"DELETE FROM possessed_item WHERE code = '{code}'")

            logger.debug(f"delete {code}!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        else:
            logger.debug("possess가 없다!!!!!!!!!!!!!!!!!!!!!")

    def delete_all_item(self, code):
        logger.debug("delete_all_item!!!!!!!!")

        # 팔았으면 즉각 possess db에서 삭제한다. 왜냐하면 checgyul_check 들어가기 직전에 possess_db를 최신화 하긴 하지만 possess db 최신화와 chegyul_check 사이에 매도가 이뤄져서 receive로 가게 되면 sell_date를 찍어버리기 때문에 checgyul_check 입장에서는 possess에는 존재하고 all_db는 sell_date찍혀있다고 판단해서 새롭게 all_db추가해버린다.
        sql = "delete from all_item_db where code = '%s'"
        # self.engine_JB.execute(sql % (code,))
        # self.jackbot_db_con.commit()
        self.engine_JB.execute(sql % (code))

        logger.debug("delete_all_item!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        logger.debug(code)

    #
    def sell_final_check2(self, code):
        logger.debug(f"sell_final_check2 possessed_item에는 없는데 all_item_db에 sell_date 추가 안된 종목 처리 !!! {code}")
        sql = "UPDATE all_item_db SET chegyul_check='%s', sell_date ='%s' WHERE code='%s' and sell_date ='%s' ORDER BY buy_date desc LIMIT 1"

        self.engine_JB.execute(sql % (0, self.today_detail, code, 0))

    # all_item_db 보유한 종목이 있는지 확인 (sell_date가 0이거나 비어있으면 아직 매도하지 않고 보유한 종목이다)
    # 보유한 경우 true 반환, 보유 하지 않았으면 False 반환
    def is_all_item_db_check(self, code):
        logger.debug(f"is_all_item_db_check code!! {code}")
        sql = "select code from all_item_db where code='%s' and (sell_date ='%s' or sell_date='%s') ORDER BY buy_date desc LIMIT 1"

        rows = self.engine_JB.execute(sql % (code, 0, "")).fetchall()
        if len(rows) != 0:
            return True
        else:
            return False

    # 리씨브
    # OnReceiveChejanData 이벤트가 발생할 때 호출되는 _receive_chejan_data는 다음과 같이 구현합니다.
    # get_chejan_data 메서드는 함수 인자인 FID 값을 통해 서로 다른 데이터를 얻을 수 있습니다.
    # 주문체결 FID
    # FID	설명
    # 9203	주문번호
    # 302	종목명
    # 900	주문수량
    # 901	주문가격

    # 902	미체결수량
    # 904	원주문번호
    # 905	주문구분
    # 908	주문/체결시간
    # 909	체결번호
    # 910	체결가
    # 911	체결량
    # 10	현재가, 체결가, 실시간종가

    # 여기는 주문을 하는 함수가 아니라 주문을 한뒤에 결과값을 받아서 DB 에다가 처리 하는 함수
    # OnReceiveChejanData이벤트는 주문전용 이벤트로 주문접수, 체결, 잔고발생시 호출됩니다. 
    # 첫번째 매개변수 gubun 값으로 구분하며 체결구분 접수와 체결시 '0'값, 국내주식 잔고전달은 '1'값, 파생잔고 전달은 '4'가 됩니다. 
    def _receive_chejan_data(self, gubun, item_cnt, fid_list):
        logger.debug("_receive_chejan_data 함수로 들어왔습니다!!!")
        logger.debug("gubun !!! :" + gubun)
        # 체결구분 접수와 체결
        if gubun == "0":
            logger.debug("in 체결 data!!!!!")
            # 현재 체결 진행 중인 코드를 키움증권으로 부터 가져온다
            # 종목 코드
            code = code_pattern.search(self.get_chejan_data(9001)).group(0)  # 주식 코드가 숫자만오지 않아서 정규식으로 필터링
            # 주문 번호
            order_num = self.get_chejan_data(9203)
            if not order_num:
                logger.debug(f'{code} 주문 실패')
                return

            # logger.debug("주문수량!!!")
            # logger.debug(self.get_chejan_data(900))
            # logger.debug("주문가격!!!")
            # logger.debug(self.get_chejan_data(901))

            # logger.debug("미체결수량!!!")
            # 미체결 수량
            chegyul_fail_amount_temp = self.get_chejan_data(902)
            # logger.debug(chegyul_fail_amount_temp)
            # logger.debug("원주문번호!!!")
            # logger.debug(self.get_chejan_data(904))
            # logger.debug("주문구분!!!")
            # order_gubun -> "+매수" or "-매도"
            order_gubun = self.get_chejan_data(905)
            # logger.debug(order_gubun)
            # logger.debug("주문/체결시간!!!")
            # logger.debug(self.get_chejan_data(908))
            # logger.debug("체결번호!!!")
            # logger.debug(self.get_chejan_data(909))
            # logger.debug("체결가!!!")
            # purchase_price=self.get_chejan_data(910)
            # logger.debug(self.get_chejan_data(910))
            # logger.debug("체결량!!!")
            # logger.debug(self.get_chejan_data(911))
            # logger.debug("현재가, 체결가, 실시간종가")
            purchase_price = self.get_chejan_data(10)

            if code:
                # 미체결 수량이 ""가 아닌 경우
                if chegyul_fail_amount_temp != "":
                    logger.debug("일단 체결은 된 경우!")
                    if self.is_all_item_db_check(code) == False:
                        logger.debug("all_item_db에 매수한 종목이 없음 ! 즉 신규 매수하는 종목이다!!!!")
                        if chegyul_fail_amount_temp == "0":
                            logger.debug("완벽히 싹 다 체결됨!!!!!!!!!!!!!!!!!!!!!!!!!")
                            self.db_to_all_item(order_num, code, 0, purchase_price, 0)
                        else:
                            logger.debug("체결 되었지만 덜 체결 됨!!!!!!!!!!!!!!!!!!")
                            self.db_to_all_item(order_num, code, 1, purchase_price, 0)

                    elif order_gubun == "+매수":
                        if chegyul_fail_amount_temp != "0" and self.stock_chegyul_check(code) == True:
                            logger.debug("아직 미체결 수량이 남아있다. 매수 진행 중!")
                            pass
                        elif chegyul_fail_amount_temp == "0" and self.stock_chegyul_check(code) == True:
                            logger.debug("미체결 수량이 없다 / 즉, 매수 끝났다!!!!!!!")
                            self.end_invest_count_check(code)
                        elif self.stock_chegyul_check(code) == False:
                            logger.debug("현재 all_item_db에 존재하고 체결 체크가 0인 종목, 재매수 하는 경우!!!!!!!")
                            # self.reinvest_count_check(code)
                        else:
                            pass

                    elif order_gubun == "-매도":
                        if chegyul_fail_amount_temp == "0":
                            logger.debug("all db에 존재하고 전량 매도하는 경우!!!!!")
                            self.sell_final_check(code)
                        else:
                            logger.debug("all db에 존재하고 수량 남겨 놓고 매도하는 경우!!!!!")
                            self.sell_chegyul_fail_check(code)

                    else:
                        logger.debug(f"order_gubun이 매수, 매도가 아닌 다른 구분!(ex. 매수취소) gubun : {order_gubun}")
                else:
                    logger.debug("_receive_chejan_data 에서 code 가 불량은 아닌데 chegyul_fail_amount_temp 가 비어있는 경우")
            else:
                logger.debug("get_chejan_data(9001): code를 받아오지 못함")

        # 국내주식 잔고전달
        elif gubun == "1":
            logger.debug("잔고데이터!!!!!")
            # logger.debug("item_cnt!!!")
            # logger.debug(item_cnt)
            # logger.debug("fid_list!!!")
            # logger.debug(fid_list)
            # try:
            # logger.debug("주문번호!!!")
            # logger.debug(self.get_chejan_data(9203))
            # logger.debug("종목명!!!")
            # logger.debug(self.get_chejan_data(302))
            # logger.debug("주문수량!!!")
            # logger.debug(self.get_chejan_data(900))
            # logger.debug("주문가격!!!")
            # logger.debug(self.get_chejan_data(901))
            #
            # logger.debug("미체결수량!!!")
            chegyul_fail_amount_temp = self.get_chejan_data(902)
            logger.debug(chegyul_fail_amount_temp)
            # logger.debug("원주문번호!!!")
            # logger.debug(self.get_chejan_data(904))
            # logger.debug("주문구분!!!")
            # logger.debug(self.get_chejan_data(905))
            # logger.debug("주문/체결시간!!!")
            # logger.debug(self.get_chejan_data(908))
            # logger.debug("체결번호!!!")
            # logger.debug(self.get_chejan_data(909))
            # logger.debug("체결가!!!")
            # logger.debug(self.get_chejan_data(910))
            # logger.debug("체결량!!!")
            # logger.debug(self.get_chejan_data(911))
            # logger.debug("현재가, 체결가, 실시간종가")
            # logger.debug(self.get_chejan_data(10))
        else:
            logger.debug(
                "_receive_chejan_data 에서 아무것도 해당 되지않음!")

    # 예수금(계좌 잔액) 호출 함수
    def get_d2_deposit(self):
        logger.debug("get_d2_deposit 함수에 들어왔습니다!")
        # 이번에는 예수금 데이터를 얻기 위해 opw00001 TR을 요청하는 코드를 구현해 봅시다. opw00001 TR은 연속적으로 데이터를 요청할 필요가 없으므로 상당히 간단합니다.
        # 비밀번호 입력매체 구분, 조회구분 다 작성해야 된다. 안그러면 0 으로 출력됨
        self.set_input_value("계좌번호", self.account_number)
        self.set_input_value("비밀번호입력매체구분", 00)
        # 조회구분 = 1:추정조회, 2: 일반조회
        self.set_input_value("조회구분", 1)
        self.comm_rq_data("opw00001_req", "opw00001", 0, "2000")

    # 먼저 OnReceiveTrData 이벤트가 발생할 때 수신 데이터를 가져오는 함수인 _opw00001를 open_api 클래스에 추가합니다.
    def _opw00001(self, rqname, trcode):
        logger.debug("_opw00001!!!")
        try:
            self.d2_deposit_before_format = self._get_comm_data(trcode, rqname, 0, "d+2출금가능금액")
            self.d2_deposit = self.change_format(self.d2_deposit_before_format)
            logger.debug("예수금!!!!")
            logger.debug(self.d2_deposit_before_format)
        except Exception as e:
            logger.critical(e)

    # 보통 금액은 천의 자리마다 콤마를 사용해서 표시합니다. 이를 위해 open_api 클래스에 change_format이라는 정적 메서드(static method)를 추가합니다. change_format 메서드는 입력된 문자열에 대해 lstrip 메서드를 통해 문자열 왼쪽에 존재하는 '-' 또는 '0'을 제거합니다. 그리고 format 함수를 통해 천의 자리마다 콤마를 추가한 문자열로 변경합니다.
    # startswith(prefix, [start, [end]])
    # prefix로 문자열이 시작하면 True를 반환하고 그 외의 경우에는 False를 반환한다.
    # "python is powerful".startswith('py')
    # True

    # 일별실현손익
    def _opt10074(self, rqname, trcode):
        logger.debug("_opt10074!!!")
        try:
            rows = self._get_repeat_cnt(trcode, rqname)
            # total 실현손익
            self.total_profit = self._get_comm_data(trcode, rqname, 0, "실현손익")

            # KOA STUDIO에서 output에 있는 내용을 4번째 인자에 넣으면된다 (총매수금액, 당일매도순익 등등)
            # 오늘 실현손익
            self.today_profit = self._get_comm_data(trcode, rqname, 0, "당일매도손익")
            logger.debug("today_profit")
            logger.debug(self.today_profit)

            # 아래는 모든 당일매도 실현손익가져오는거다.
            # for i in range(rows):
            #     today_profit = self._get_comm_data(trcode, rqname, i, "당일매도손익")
            #     logger.debug("today_profit")
            #     logger.debug(today_profit)



        except Exception as e:
            logger.critical(e)
            # self.opw00018_output['multi'].append(
            #     [name, quantity, purchase_price, current_price, eval_profit_loss_price, earning_rate])

    def _opw00015(self, rqname, trcode):
        logger.debug("_opw00015!!!")
        try:

            rows = self._get_repeat_cnt(trcode, rqname)

            name = self._get_comm_data(trcode, rqname, 1, "계좌번호")

            for i in range(rows):
                name = self._get_comm_data(trcode, rqname, i, "거래일자")

                # self.opw00018_output['multi'].append(
                #     [name, quantity, purchase_price, current_price, eval_profit_loss_price, earning_rate])
        except Exception as e:
            logger.critical(e)

    # @staticmethod  # 이건머지
    # 아래에서 일단 위로 바꿔봄
    def change_format(self, data):
        try:
            strip_data = data.lstrip('0')
            if strip_data == '':
                strip_data = '0'

            # format_data = format(int(strip_data), ',d')

            # if data.startswith('-'):
            #     format_data = '-' + format_data
            return int(strip_data)
        except Exception as e:
            logger.critical(e)

    # 수익률에 대한 포맷 변경은 change_format2라는 정적 메서드를 사용합니다.
    #     @staticmethod
    def change_format2(self, data):
        try:
            # 앞에 0 제거
            strip_data = data.lstrip('-0')

            # 이렇게 추가해야 소수점으로 나온다.
            if strip_data == '':
                strip_data = '0'
            else:
                # 여기서 strip_data가 0이거나 " " 되니까 100 나눴을 때 갑자기 동작안함. 에러도 안뜸 그래서 원래는 if 위에 있었는데 else 아래로 내림
                strip_data = str(float(strip_data) / self.mod_gubun)
                if strip_data.startswith('.'):
                    strip_data = '0' + strip_data

                #     strip 하면 -도 사라지나보네 여기서 else 하면 안된다. 바로 위에 소수 읻네 음수 인 경우가 있기 때문
                if data.startswith('-'):
                    strip_data = '-' + strip_data

            return strip_data
        except Exception as e:
            logger.critical(e)

    # 특수문자, 앞뒤 공백 제거 함수
    def change_format3(self, data):
        try:
            # 특수문자 제거
            strip_data = data.strip('%')
            # 앞뒤 공백 제거
            strip_data = strip_data.strip()

            return strip_data
        except Exception as e:
            logger.critical(e)

    # 코드 앞에 A제거
    def change_format4(self, data):
        try:
            strip_data = data.lstrip('A')
            return strip_data
        except Exception as e:
            logger.critical(e)

    def _opt10073(self, rqname, trcode):
        logger.debug("_opt10073!!!")

        # multi data
        rows = self._get_repeat_cnt(trcode, rqname)
        for i in range(rows):
            date = self._get_comm_data(trcode, rqname, i, "일자")
            code = self._get_comm_data(trcode, rqname, i, "종목코드")
            code_name = self._get_comm_data(trcode, rqname, i, "종목명")
            amount = self._get_comm_data(trcode, rqname, i, "체결량")
            today_profit = self._get_comm_data(trcode, rqname, i, "당일매도손익")
            earning_rate = self._get_comm_data(trcode, rqname, i, "손익율")
            code = self.change_format4(code)

            # earning_rate = self.change_format2(earning_rate)

            # logger.debug("multi item_total_purchase type!!!!!!!!!!!!!!")
            # int로 나온다!!!!
            # logger.debug(type(item_total_purchase))

            self.opt10073_output['multi'].append([date, code, code_name, amount, today_profit, earning_rate])

        logger.debug("_opt10073 end!!!")

    # 이번에는 opw00018 TR을 통해 얻어온 데이터를 인스턴스 변수에 저장해 보겠습니다. 먼저 open_api 클래스에 다음 메서드를 추가합니다.
    # 싱글 데이터는 1차원 리스트로 데이터를 저장하며, 멀티 데이터는 2차원 리스트로 데이터를 저장합니다.

    # 최대 20개 보유 종목에 대한 데이터를 얻어 올 수 있다.
    # 600개면 30*2 60회 조회
    # 800개면 40*2 80회 조회
    # 1000개는 절대 불가능.

    # 이번에는 opw00018 TR을 위한 코드를 추가하겠습니다. opw00018 TR은 싱글 데이터를 통해 계좌에 대한 평가 잔고 데이터를 제공하며 멀티 데이터를 통해 보유 종목별 평가 잔고 데이터를 제공합니다.
    # 먼저 총매입금액, 총평가금액, 총평가손익금액, 총수익률, 추정예탁자산을 _get_comm_data 메서드를 통해 얻어옵니다. 얻어온 데이터는 change_format 메서드를 통해 포맷을 문자열로 변경합니다.
    def _opw00018(self, rqname, trcode):
        logger.debug("_opw00018!!!")
        # try:
        # 전역변수로 사용하기 위해서 총매입금액은 self로 선언
        # logger.debug(1)
        self.total_purchase_price = self._get_comm_data(trcode, rqname, 0, "총매입금액")
        # logger.debug(2)
        self.total_eval_price = self._get_comm_data(trcode, rqname, 0, "총평가금액")
        # logger.debug(3)
        self.total_eval_profit_loss_price = self._get_comm_data(trcode, rqname, 0, "총평가손익금액")
        # logger.debug(4)
        self.total_earning_rate = self._get_comm_data(trcode, rqname, 0, "총수익률(%)")
        # logger.debug(5)
        self.estimated_deposit = self._get_comm_data(trcode, rqname, 0, "추정예탁자산")
        # logger.debug(6)
        self.change_total_purchase_price = self.change_format(self.total_purchase_price)
        self.change_total_eval_price = self.change_format(self.total_eval_price)
        self.change_total_eval_profit_loss_price = self.change_format(self.total_eval_profit_loss_price)
        self.change_total_earning_rate = self.change_format2(self.total_earning_rate)

        self.change_estimated_deposit = self.change_format(self.estimated_deposit)

        self.opw00018_output['single'].append(self.change_total_purchase_price)
        self.opw00018_output['single'].append(self.change_total_eval_price)
        self.opw00018_output['single'].append(self.change_total_eval_profit_loss_price)
        self.opw00018_output['single'].append(self.change_total_earning_rate)
        self.opw00018_output['single'].append(self.change_estimated_deposit)
        # 이번에는 멀티 데이터를 통해 보유 종목별로 평가 잔고 데이터를 얻어와 보겠습니다.
        # 다음 코드를 _opw00018에 추가합니다.
        # 멀티 데이터는 먼저 _get_repeat_cnt 메서드를 호출해 보유 종목의 개수를 얻어옵니다.
        # 그런 다음 해당 개수만큼 반복하면서 각 보유 종목에 대한 상세 데이터를
        # _get_comm_data를 통해 얻어옵니다.
        # 참고로 opw00018 TR을 사용하는 경우 한 번의 TR 요청으로
        # 최대 20개의 보유 종목에 대한 데이터를 얻을 수 있습니다.
        # multi data
        rows = self._get_repeat_cnt(trcode, rqname)

        for i in range(rows):
            code = code_pattern.search(self._get_comm_data(trcode, rqname, i, "종목번호")).group(0)
            name = self._get_comm_data(trcode, rqname, i, "종목명")
            quantity = self._get_comm_data(trcode, rqname, i, "보유수량")
            purchase_price = self._get_comm_data(trcode, rqname, i, "매입가")
            current_price = self._get_comm_data(trcode, rqname, i, "현재가")
            eval_profit_loss_price = self._get_comm_data(trcode, rqname, i, "평가손익")
            earning_rate = self._get_comm_data(trcode, rqname, i, "수익률(%)")
            item_total_purchase = self._get_comm_data(trcode, rqname, i, "매입금액")

            quantity = self.change_format(quantity)
            purchase_price = self.change_format(purchase_price)
            current_price = self.change_format(current_price)
            eval_profit_loss_price = self.change_format(eval_profit_loss_price)
            earning_rate = self.change_format2(earning_rate)
            item_total_purchase = self.change_format(item_total_purchase)

            self.opw00018_output['multi'].append(
                [name, quantity, purchase_price, current_price,
                 eval_profit_loss_price, earning_rate, item_total_purchase, code]
            )

    # 이번에는 opw00018 TR을 통해 얻어온 데이터를 인스턴스 변수에 저장해 보겠습니다.
    # 먼저 open_api 클래스에 다음 메서드를 추가합니다.
    # 싱글 데이터는 1차원 리스트로 데이터를 저장하며, 멀티 데이터는 2차원 리스트로 데이터를 저장합니다.
    def reset_opw00018_output(self):
        try:
            self.opw00018_output = {'single': [], 'multi': []}
        except Exception as e:
            logger.critical(e)

    #   일자별 종목별 실현손익
    def reset_opt10073_output(self):
        logger.debug("reset_opt10073_output!!!")
        try:
            self.opt10073_output = {'single': [], 'multi': []}
        except Exception as e:
            logger.critical(e)

    #   미체결 정보
    def _opt10076(self, rqname, trcode):
        logger.debug("func in !!! _opt10076!!!!!!!!! ")
        output_keys = ['주문번호', '종목명', '주문구분', '주문가격', '주문수량', '체결가', '체결량', '미체결수량',
                       '당일매매수수료', '당일매매세금', '주문상태', '매매구분', '원주문번호', '주문시간', '종목코드']
        self._data = {}

        for key in output_keys:
            if key not in ('주문번호', '원주문번호', '주문시간', '종목코드'):
                try:
                    self._data[key] = int(self._get_comm_data(trcode, rqname, 0, key))
                    continue
                except ValueError:
                    pass

            self._data[key] = self._get_comm_data(trcode, rqname, 0, key)

    def basic_db_check(self, cursor):
        check_list = ['daily_craw', 'daily_buy_list', 'min_craw']
        sql = "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA"
        cursor.execute(sql)
        rows = cursor.fetchall()
        db_list = [n['SCHEMA_NAME'].lower() for n in rows]
        create_db_tmp = "CREATE DATABASE {}"
        has_created = False
        for check_name in check_list:
            if check_name not in db_list:
                has_created = True
                logger.debug(f'{check_name} DB가 존재하지 않아 생성 중...')
                create_db_sql = create_db_tmp.format(check_name)
                cursor.execute(create_db_sql)
                logger.debug(f'{check_name} 생성 완료')

        if has_created and self.engine_JB.has_table('setting_data'):
            self.engine_JB.execute("""
                UPDATE setting_data SET code_update = '0';
            """)
