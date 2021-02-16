ver = "#version 1.3.1"
print(f"trader Version: {ver}")

from library.open_api import *
from PyQt5.QtWidgets import *

logger.debug("trader start !!!!!!")


class Trader(QMainWindow):
    def __init__(self):
        logger.debug("Trader __init__!!!")
        super().__init__()
        # 예제에 사용한 openapi는 사용하지 않습니다. library.open_api를 사용합니다.
        self.open_api = open_api()
        # 현재 시간을 저장
        self.current_time = QTime.currentTime()
        # 변수 설정 함수
        self.variable_setting()

    # 변수 설정 함수
    def variable_setting(self):
        self.open_api.py_gubun = "trader"
        ################ 모의, 실전 ####################
        # 장시작 시간 설정
        self.market_start_time = QTime(9, 0, 0)
        # 장마감 시간 설정
        self.market_end_time = QTime(15, 30, 0)
        # 매수를 몇 시 까지 할지 설정. (시, 분, 초)
        self.buy_end_time = QTime(9, 6, 0)

        ############################################

        ################ 테스트용 ###################
        # 장시작 시간 설정
        # self.market_start_time = QTime(0, 0, 0)
        # # 장마감 시간 설정
        # self.market_end_time = QTime(23, 59, 0)
        # # 매수를 몇 시 까지 할지 설정. (시, 분, 초)
        # self.buy_end_time = QTime(23, 59, 0)

        # ############################################

    # 매수를 하기 위한 함수
    def auto_trade_stock(self):
        logger.debug("auto_trade_stock함수에 들어왔습니다!")
        self.open_api.get_today_buy_list()

    # 매도 리스트를 가져온다
    def get_sell_list_trade(self):
        logger.debug("get_sell_list 함수에 들어왔습니다!")

        # 체결이 됐는지 안됐는지 확인한다. 매수했을 경우 possessd_item에는 있는데, all_item_db에 없는 경우가 있다.
        # 즉, 매수하고 all_itme_db에 추가하기 전에 봇이 꺼지는 경우!
        self.open_api.chegyul_check()
        # all_item_db에 rate를 업데이트 한다.
        self.open_api.rate_check()
        self.open_api.sf.get_date_for_simul()
        self.sell_list = self.open_api.sf.get_sell_list(len(self.open_api.sf.date_rows))
        logger.debug("매도 리스트!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        logger.debug(self.sell_list)

    # 매도 함수
    def auto_trade_sell_stock(self):
        logger.debug("auto_trade_sell_stock 함수에 들어왔습니다!")
        # mulit종목 가져와
        self.open_api.check_balance()
        # possesed_item 테이블 동기화(실제로 키움증권 계좌에서 보유한 종목을 가져오는 함수)
        self.open_api.db_to_possesed_item()
        # 봇이 꺼졌을 때 매도가 된 경우 `all_item_db` 테이블에 sell_date 반영 하는 함수
        self.open_api.final_chegyul_check()

        # 매도 할 종목 가져오는 함수(익절, 손절)
        self.get_sell_list_trade()
        # code, rate, present_price,valuation_profit FROM
        for i in range(len(self.sell_list)):
            # 종목코드명
            get_sell_code = self.sell_list[i][0]
            # 수익률
            get_sell_rate = self.sell_list[i][1]
            # 매도 수량
            get_sell_num = self.open_api.get_holding_amount(get_sell_code)

            if get_sell_num == False:
                continue

            logger.debug("매도할 종목코드: !!" + str(get_sell_code))
            logger.debug("매도 수익률: !!" + str(get_sell_rate))
            logger.debug("매도 수량: !!" + str(get_sell_num))

            if get_sell_code != False and get_sell_code != "0" and get_sell_code != 0:
                if get_sell_rate < 0:
                    logger.debug("손절!!!!$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ " + str(
                        get_sell_code) + " $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
                    self.open_api.send_order("send_order_req", "0101", self.open_api.account_number, 2, get_sell_code,
                                             get_sell_num, 0, "03", "")
                else:
                    logger.debug("익절 매도!!!!$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$ " + str(
                        get_sell_code) + " $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$")
                    # 03 : 시장가 매도
                    # 2 : 신규매도
                    # 0 : price 인데 시장가니까 0으로
                    # get_sell_num : 종목 보유 수량
                    self.open_api.send_order("send_order_req", "0101", self.open_api.account_number, 2, get_sell_code,
                                             get_sell_num, 0, "03", "")

            else:
                print("code가 없다!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                print("code!!!!")
                print(get_sell_code)
                print("name!!!!")

    # 장시간 확인
    def market_time_check(self):
        logger.debug("market_time_check!!!")
        self.current_time = QTime.currentTime()
        if self.current_time > self.market_start_time and self.current_time < self.market_end_time:
            logger.debug('''장시간입니다. 테스트하실 경우는 trader.py 파일의 variable_setting 함수에서
                     ### 모의, 실전 ### 부분을 주석 처리하시고
                     ### 테스트용 ### 부분의 주석을 풀어주시기 바랍니다.
                     실제로 모의/실전 투자 시 반드시 variable_setting을 원복해 주셔야 합니다.  ''')
            return True
        else:
            logger.debug('''장시간이 아닙니다.테스트하실 경우는 trader.py 파일의 variable_setting 함수에서
                     ### 모의, 실전 ### 부분을 주석 처리하시고
                     ### 테스트용 ### 부분의 주석을 풀어주시기 바랍니다.
                     실제로 모의/실전 투자 시 반드시 variable_setting을 원복해 주셔야 합니다. ''')
            return False

    # 매수 설정 시간 체크
    def buy_time_check(self):
        logger.debug("buy_time_check 함수에 들어왔습니다!")
        self.current_time = QTime.currentTime()
        if self.current_time < self.buy_end_time:
            return True
        else:
            logger.debug("설정한 매수 시간이 끝났습니다!")
            return False

    def run(self):
        print("run함수에 들어왔습니다!")
        # 무한히 돌아라
        while 1:
            # 안정성을 위해 0.3초 딜레이
            time.sleep(0.3)
            # 날짜 세팅
            self.open_api.date_setting()
            # 시간 체크
            if self.market_time_check():
                # 우선 조건에 맞으면 매도
                self.auto_trade_sell_stock()
                # 1. 잔액이 있는지 여부 확인
                # 2. 매수 하는 시간 인지 확인
                # 3. 매수 정지 옵션이 체크 되었는지 확인
                if self.open_api.jango_check() and self.buy_time_check() and self.open_api.buy_check():
                    # 1,2,3 조건 모두 문제 없으면 매수 시작
                    self.auto_trade_stock()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    trader = Trader()
    trader.run()
