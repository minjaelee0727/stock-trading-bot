
import math
import pymysql
import datetime
from sqlalchemy import create_engine
import pandas as pd

pymysql.install_as_MySQLdb()
from library import cf
from PyQt5.QtCore import *


class daily_craw_config():
    def __init__(self, db_name, daily_craw_db_name, daily_buy_list_db_name):
        # db_name 0 인 경우는 simul 일때! 종목 데이터 가져오는 함수만 사용하기위해서
        if db_name != 0:
            self.db_name = db_name
            self.daily_craw_db_name = daily_craw_db_name

            self.daily_buy_list_db_name = daily_buy_list_db_name

            self.engine = create_engine(
                "mysql+mysqldb://" + cf.db_id + ":" + cf.db_passwd + "@" + cf.db_ip + ":" + cf.db_port + "/daily_craw",
                encoding='utf-8')
            self.daily_craw_db_con = self.engine.connect()

            self.get_item()
            # self.date_rows_setting()
            self.variable_setting()
            # print("db name 0아니다!!!!!!!!!!!!!!!!!!!!!!")
        else:
            pass
            # print("db name 0!!!!!!!!!!!!!!!!!!!")

    # 업데이트가 금일 제대로 끝났는지 확인
    def variable_setting(self):

        self.market_start_time = QTime(9, 0, 0)
        # self.market_start_time = QTime(15, 11, 0)
        self.market_end_time = QTime(15, 31, 0)
        # self.market_end_time = QTime(23, 12, 0)

        self.today = datetime.datetime.today().strftime("%Y%m%d")
        self.today_detail = datetime.datetime.today().strftime("%Y%m%d%H%M")
        # self.today_detail_seconds = datetime.datetime.today().strftime("%H / %M / %S")

    def market_time_check(self):
        # print("market_time_check!!!")
        self.current_time = QTime.currentTime()
        if self.current_time > self.market_start_time and self.current_time < self.market_end_time:
            return True
        else:
            print("end!!!")
            return False

    # 불성실공시법인 가져오는 함수
    def get_item_insincerity(self):
        print("get_item_insincerity!!")

        self.code_df_insincerity = pd.read_html('http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=05', header=0)[0]
        # print(self.code_df_insincerity)

        # 6자리 만들고 앞에 0을 붙인다.
        self.code_df_insincerity.종목코드 = self.code_df_insincerity.종목코드.map('{:06d}'.format)

        # 우리가 필요한 것은 회사명과 종목코드이기 때문에 필요없는 column들은 제외해준다.
        self.code_df_insincerity = self.code_df_insincerity[['회사명', '종목코드']]

        # 한글로된 컬럼명을 영어로 바꿔준다.
        self.code_df_insincerity = self.code_df_insincerity.rename(columns={'회사명': 'code_name', '종목코드': 'code'})

    # 관리 종목을 가져오는 함수
    def get_item_managing(self):
        print("get_item_managing!!")
        self.code_df_managing = pd.read_html('http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=01', header=0)[0]  # 종목코드가 6자리이기 때문에 6자리를 맞춰주기 위해 설정해줌

        # 6자리 만들고 앞에 0을 붙인다.strPath --> str(unicode(strPath))
        self.code_df_managing.종목코드 = self.code_df_managing.종목코드.map('{:06d}'.format)

        # 우리가 필요한 것은 회사명과 종목코드이기 때문에 필요없는 column들은 제외해준다.
        self.code_df_managing = self.code_df_managing[['회사명', '종목코드']]

        # 한글로된 컬럼명을 영어로 바꿔준다.
        self.code_df_managing = self.code_df_managing.rename(columns={'회사명': 'code_name', '종목코드': 'code'})

    # 코넥스 종목을 가져오는 함수
    def get_item_konex(self):
        print("get_item_konex!!")
        self.code_df_konex = pd.read_html('http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType=konexMkt',header=0)[0]  # 종목코드가 6자리이기 때문에 6자리를 맞춰주기 위해 설정해줌

        # 6자리 만들고 앞에 0을 붙인다.
        self.code_df_konex.종목코드 = self.code_df_konex.종목코드.map('{:06d}'.format)

        # 우리가 필요한 것은 회사명과 종목코드이기 때문에 필요없는 column들은 제외해준다.
        self.code_df_konex = self.code_df_konex[['회사명', '종목코드']]

        # 한글로된 컬럼명을 영어로 바꿔준다.
        self.code_df_konex = self.code_df_konex.rename(columns={'회사명': 'code_name', '종목코드': 'code'})

    # 코스피 종목을 가져오는 함수
    def get_item_kospi(self):
        print("get_item_kospi!!")
        self.code_df_kospi = \
        pd.read_html('http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType=stockMkt',header=0)[0]  # 종목코드가 6자리이기 때문에 6자리를 맞춰주기 위해 설정해줌

        # 6자리 만들고 앞에 0을 붙인다.
        self.code_df_kospi.종목코드 = self.code_df_kospi.종목코드.map('{:06d}'.format)

        # 우리가 필요한 것은 회사명과 종목코드이기 때문에 필요없는 column들은 제외해준다.
        self.code_df_kospi = self.code_df_kospi[['회사명', '종목코드']]

        # 한글로된 컬럼명을 영어로 바꿔준다.
        self.code_df_kospi = self.code_df_kospi.rename(columns={'회사명': 'code_name', '종목코드': 'code'})

    # 코스닥 종목을 가져오는 함수
    def get_item_kosdaq(self):
        print("get_item_kosdaq!!")
        self.code_df_kosdaq = pd.read_html('http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13&marketType=kosdaqMkt',header=0)[0]  # 종목코드가 6자리이기 때문에 6자리를 맞춰주기 위해 설정해줌

        # 6자리 만들고 앞에 0을 붙인다.
        self.code_df_kosdaq.종목코드 = self.code_df_kosdaq.종목코드.map('{:06d}'.format)

        # 우리가 필요한 것은 회사명과 종목코드이기 때문에 필요없는 column들은 제외해준다.
        self.code_df_kosdaq = self.code_df_kosdaq[['회사명', '종목코드']]

        # 한글로된 컬럼명을 영어로 바꿔준다.
        self.code_df_kosdaq = self.code_df_kosdaq.rename(columns={'회사명': 'code_name', '종목코드': 'code'})

    # 코스피, 코스닥, 코넥스 모든 정보를 가져오는 함수
    def get_item(self):
        # print("get_item!!")
        self.code_df = pd.read_html('http://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13', header=0)[0]  # 종목코드가 6자리이기 때문에 6자리를 맞춰주기 위해 설정해줌

        # 6자리 만들고 앞에 0을 붙인다.
        self.code_df.종목코드 = self.code_df.종목코드.map('{:06d}'.format)

        # 우리가 필요한 것은 회사명과 종목코드이기 때문에 필요없는 column들은 제외해준다.
        self.code_df = self.code_df[['회사명', '종목코드']]

        # 한글로된 컬럼명을 영어로 바꿔준다.
        self.code_df = self.code_df.rename(columns={'회사명': 'code_name', '종목코드': 'code'})

    def change_format(self, data):
        strip_data = data.replace('.', '')

        return strip_data

if __name__ == "__main__":
    daily_craw_config = daily_craw_config()

