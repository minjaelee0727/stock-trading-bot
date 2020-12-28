ver = "#version 1.3.1"
print(f"daily_buy_list Version: {ver}")

from sqlalchemy import event

from library.daily_crawler import *
from library import cf
from pandas import DataFrame
from .open_api import escape_percentage

MARKET_KOSPI = 0
MARKET_KOSDAQ = 10


class daily_buy_list():
    def __init__(self):
        self.variable_setting()

    def variable_setting(self):
        self.today = datetime.datetime.today().strftime("%Y%m%d")
        self.today_detail = datetime.datetime.today().strftime("%Y%m%d%H%M")
        self.start_date = cf.start_daily_buy_list
        self.engine_daily_craw = create_engine(
            "mysql+mysqldb://" + cf.db_id + ":" + cf.db_passwd + "@" + cf.db_ip + ":" + cf.db_port + "/daily_craw",
            encoding='utf-8')
        self.engine_daily_buy_list = create_engine(
            "mysql+mysqldb://" + cf.db_id + ":" + cf.db_passwd + "@" + cf.db_ip + ":" + cf.db_port + "/daily_buy_list",
            encoding='utf-8')

        event.listen(self.engine_daily_craw, 'before_execute', escape_percentage, retval=True)
        event.listen(self.engine_daily_buy_list, 'before_execute', escape_percentage, retval=True)

    def date_rows_setting(self):
        print("date_rows_setting!!")
        # 날짜 지정
        sql = "select date from `gs글로벌` where date >= '%s' group by date"
        self.date_rows = self.engine_daily_craw.execute(sql % self.start_date).fetchall()

    def is_table_exist_daily_buy_list(self, date):
        sql = "select 1 from information_schema.tables where table_schema ='daily_buy_list' and table_name = '%s'"
        rows = self.engine_daily_buy_list.execute(sql % (date)).fetchall()

        if len(rows) == 1:
            return True
        elif len(rows) == 0:
            return False

    def daily_buy_list(self):
        print("daily_buy_list!!!")
        self.date_rows_setting()
        self.get_stock_item_all()

        for k in range(len(self.date_rows)):
            # print("self.date_rows !!!!", self.date_rows)
            print(str(k) + " 번째 : " + datetime.datetime.today().strftime(" ******* %H : %M : %S *******"))
            # daily 테이블 존재하는지 확인
            if self.is_table_exist_daily_buy_list(self.date_rows[k][0]) == True:
                # continue
                print(self.date_rows[k][0] + "테이블은 존재한다 !! continue!! ")
                continue
            else:
                print(self.date_rows[k][0] + "테이블은 존재하지 않는다 !!!!!!!!!!! table create !! ")

                multi_list = list()

                for i in range(len(self.stock_item_all)):
                    code = self.stock_item_all[i][1]
                    code_name = self.stock_item_all[i][0]
                    if self.is_table_exist_daily_craw(code, code_name) == False:
                        print("daily_craw db에 " + str(code_name) + " 테이블이 존재하지 않는다 !!")
                        continue

                    sql = "select * from `" + self.stock_item_all[i][0] + "` where date = '{}' group by date"
                    # daily_craw에서 해당 날짜의 row를 한 줄 가져오는 것
                    rows = self.engine_daily_craw.execute(sql.format(self.date_rows[k][0])).fetchall()
                    multi_list += rows

                if len(multi_list) != 0:
                    df_temp = DataFrame(multi_list,
                                        columns=['index', 'date', 'check_item', 'code', 'code_name', 'd1_diff_rate',
                                                 'close', 'open', 'high', 'low',
                                                 'volume', 'clo5', 'clo10', 'clo20', 'clo40', 'clo60', 'clo80',
                                                 'clo100', 'clo120', "clo5_diff_rate", "clo10_diff_rate",
                                                 "clo20_diff_rate", "clo40_diff_rate", "clo60_diff_rate",
                                                 "clo80_diff_rate", "clo100_diff_rate", "clo120_diff_rate",
                                                 'yes_clo5', 'yes_clo10', 'yes_clo20', 'yes_clo40', 'yes_clo60',
                                                 'yes_clo80',
                                                 'yes_clo100', 'yes_clo120',
                                                 'vol5', 'vol10', 'vol20', 'vol40', 'vol60', 'vol80',
                                                 'vol100', 'vol120'
                                                 ])

                    df_temp.to_sql(name=self.date_rows[k][0], con=self.engine_daily_buy_list, if_exists='replace')

    def get_stock_item_all(self):
        print("get_stock_item_all!!!!!!")
        sql = "select code_name,code from stock_item_all"
        self.stock_item_all = self.engine_daily_buy_list.execute(sql).fetchall()

    def is_table_exist_daily_craw(self, code, code_name):
        sql = "select 1 from information_schema.tables where table_schema ='daily_craw' and table_name = '%s'"
        rows = self.engine_daily_craw.execute(sql % (code_name)).fetchall()

        if len(rows) == 1:
            # print(code + " " + code_name + " 테이블 존재한다!!!")
            return True
        elif len(rows) == 0:
            # print("####################" + code + " " + code_name + " no such table!!!")
            # self.create_new_table(self.cc.code_df.iloc[i][0])
            return False

    def run(self):

        self.transaction_info()

        # print("run end")
        return 0


if __name__ == "__main__":
    daily_buy_list = daily_buy_list()
