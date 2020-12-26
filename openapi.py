import sys
from PyQt5.QtWidgets import *
from PyQt5.QAxContainer import *
from PyQt5.QtCore import *
import logging.handlers
import time
from pandas import DataFrame

is_64bits = sys.maxsize > 2**32
if is_64bits:
    print('64bit 환경입니다.')
else:
    print('32bit 환경입니다.')

formatter = logging.Formatter('[%(levelname)s|%(filename)s:%(lineno)s] %(asctime)s > %(message)s')
logger = logging.getLogger("crumbs")
logger.setLevel(logging.DEBUG)
streamHandler = logging.StreamHandler()
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

TR_REQ_TIME_INTERVAL = 0.2


class Openapi(QAxWidget):
    def __init__(self):
        print("openapi __name__:", __name__)
        super().__init__()
        self._create_open_api_instance()
        self._set_signal_slots()
        self.comm_connect()
        self.account_info()

    def _opt10081(self, rqname, trcode):

        # 몇번 반복 실행 할지 설정
        ohlcv_cnt = self._get_repeat_cnt(trcode, rqname)

        # 하나의 row씩 append
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

    def _receive_tr_data(self, screen_no, rqname, trcode, record_name, next, unused1, unused2, unused3, unused4):
        # print("_receive_tr_data!!!")
        # print(rqname, trcode, next)
        if next == '2':
            self.remained_data = True
        else:
            self.remained_data = False

        if rqname == "opt10081_req":

            self._opt10081(rqname, trcode)
        elif rqname == "opw00001_req":
            # print("opw00001_req!!!")
            # print("Get an de_deposit!!!")
            self._opw00001(rqname, trcode)
        elif rqname == "opw00018_req":
            # print("opw00018_req!!!")
            # print("Get the possessed item !!!!")
            self._opw00018(rqname, trcode)
        elif rqname == "opt10074_req":
            # print("opt10074_req!!!")
            # print("Get the profit")
            self._opt10074(rqname, trcode)
        elif rqname == "opw00015_req":
            # print("opw00015_req!!!")
            # print("deal list!!!!")
            self._opw00015(rqname, trcode)
        elif rqname == "opt10076_req":
            # print("opt10076_req")
            # print("chegyul list!!!!")
            self._opt10076(rqname, trcode)
        elif rqname == "opt10073_req":
            # print("opt10073_req")
            # print("Get today profit !!!!")
            self._opt10073(rqname, trcode)
        elif rqname == "opt10080_req":
            # print("opt10080_req!!!")
            # print("Get an de_deposit!!!")
            self._opt10080(rqname, trcode)

        try:
            self.tr_event_loop.exit()
        except AttributeError:
            pass

    # get_total_data : 특정 종목의 일자별 거래 데이터 조회 함수

    # 사용방법
    # code: 종목코드(ex. '005930' )
    # start : 기준일자. (ex. '20200424') => 20200424 일자 까지의 모든 open, high, low, close, volume 데이터 출력
    def get_total_data(self, code, start):

        self.ohlcv = {'date': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': []}
        self.set_input_value("종목코드", code)
        self.set_input_value("기준일자", start)
        self.set_input_value("수정주가구분", 1)
        self.comm_rq_data("opt10081_req", "opt10081", 0, "0101")

        # 이 밑에는 한번만 가져오는게 아니고 싹다 가져오는거다.

        while self.remained_data == True:
            # time.sleep(TR_REQ_TIME_INTERVAL)
            self.set_input_value("종목코드", code)
            self.set_input_value("기준일자", start)
            self.set_input_value("수정주가구분", 1)
            self.comm_rq_data("opt10081_req", "opt10081", 2, "0101")

        time.sleep(0.2)
        # data 비어있는 경우
        if len(self.ohlcv) == 0:
            return []

        if self.ohlcv['date'] == '':
            return []

        df = DataFrame(self.ohlcv, columns=['open', 'high', 'low', 'close', 'volume'], index=self.ohlcv['date'])

        return df

    # get_one_day_option_data : 특정 종목의 특정 일 open(시작가), high(최고가), low(최저가), close(종가), volume(거래량) 조회 함수
    # 사용방법
    # code : 종목코드
    # start : 조회 일자
    # option : open(시작가), high(최고가), low(최저가), close(종가), volume(거래량)
    def get_one_day_option_data(self, code, start, option):

        self.ohlcv = {'date': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': []}

        self.set_input_value("종목코드", code)

        self.set_input_value("기준일자", start)

        self.set_input_value("수정주가구분", 1)

        self.comm_rq_data("opt10081_req", "opt10081", 0, "0101")

        if self.ohlcv['date'] == '':
            return False

        df = DataFrame(self.ohlcv, columns=['open', 'high', 'low', 'close', 'volume'], index=self.ohlcv['date'])
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

    def multi_601_get_ohlcv_daliy_craw(self, code, code_name, start):
        self.ohlcv = {'index': [], 'date': [], 'open': [], 'high': [], 'low': [], 'close': [], 'volume': []}

        self.set_input_value("종목코드", code)
        self.set_input_value("기준일자", start)
        self.set_input_value("수정주가구분", 1)
        self.comm_rq_data("opt10081_req", "opt10081", 0, "0101")
        time.sleep(0.2)

        if self.ohlcv['date'][0] == '':
            return []

        if self.ohlcv['date'] == '':
            return []

        df = DataFrame(self.ohlcv, columns=['date', 'open', 'high', 'low', 'close', 'volume'])

        return df

    def account_info(self):
        account_number = self.get_login_info("ACCNO")
        self.account_number = account_number.split(';')[0]
        logger.debug("계좌번호: " + self.account_number)

    def get_login_info(self, tag):
        try:
            ret = self.dynamicCall("GetLoginInfo(QString)", tag)
            time.sleep(TR_REQ_TIME_INTERVAL)
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

    def _receive_chejan_data(self, gubun, item_cnt, fid_list):
        print("_receive_chejan_data!!!")
        print("gubun!!!")
        print(gubun)

        # 체결 data!
        if gubun == "0":
            print("in 체결 data!!!!!")
            order_num = self.get_chejan_data(9203)
            code_name_temp = self.get_chejan_data(302)

            code_name = self.change_format3(code_name_temp)

            code = self.codename_to_code(code_name)

            chegyul_fail_amount_temp = self.get_chejan_data(902)
            order_gubun = self.get_chejan_data(905)
            purchase_price = self.get_chejan_data(10)

            if code != False and code != "" and code != 0 and code != "0":
                if chegyul_fail_amount_temp != "":
                    if self.is_all_item_db_check(code) == False:
                        print("all_item_db에 매도 안 된 종목이 없음 ! 즉 신규다!!")
                        if chegyul_fail_amount_temp == "0":
                            print("완벽히 싹 다 체결됨!")
                            self.db_to_all_item(order_num, code, code_name, 0, purchase_price)
                        else:
                            print("체결 되었지만 덜 체결 됨!")
                            self.db_to_all_item(order_num, code, code_name, 1, purchase_price)

                    elif order_gubun == "+매수":
                        if chegyul_fail_amount_temp != "0" and self.stock_chegyul_check(code) == True:
                            print("재매수던 매수던 미체결 수량이 남아있고, stock_chegyul_check True인 놈 / 즉, 계속 사야되는 종목!")
                            pass
                        elif chegyul_fail_amount_temp == "0" and self.stock_chegyul_check(code) == True:
                            print("재매수던 매수던 미체결 수량이 없고, stock_chegyul_check True인 놈 / 즉, 매수 끝난 종목!")
                            self.end_invest_count_check(code)
                        elif self.stock_chegyul_check(code) == False:
                            print("현재 all db에 존재하고 체결 체크가 0인 종목, 재매수 하는 경우!")

                        else:
                            pass
                    elif order_gubun == "-매도":
                        if chegyul_fail_amount_temp == "0":
                            print("all db에 존재하고 전량 매도하는 경우!")
                            self.sell_final_check(code)
                        else:
                            print("all db에 존재하고 수량 남겨 놓고 매도하는 경우!")
                            self.sell_chegyul_fail_check(code)

                    else:
                        pass
                else:
                    print("_receive_chejan_data 에서 code 가 불량은 아닌데 체결된 종목이 빈공간인 경우!")
            else:
                print("_receive_chejan_data 에서 code가 불량이다!!")

        elif gubun == "1":
            print("잔고데이터!!!!!")

            chegyul_fail_amount_temp = self.get_chejan_data(902)
            print(chegyul_fail_amount_temp)

        else:
            pass

    def comm_connect(self):
        try:
            self.dynamicCall("CommConnect()")
            time.sleep(TR_REQ_TIME_INTERVAL)
            self.login_event_loop = QEventLoop()
            self.login_event_loop.exec_()
        except Exception as e:
            logger.critical(e)

    def _receive_msg(self, sScrNo, sRQName, sTrCode, sMsg):
        print(sMsg)

    def _event_connect(self, err_code):
        try:
            if err_code == 0:
                logger.debug("connected")
            else:
                logger.debug(f"disconnected. err_code : {err_code}")
            self.login_event_loop.exit()
        except Exception as e:
            logger.critical(e)

    def get_connect_state(self):
        try:
            ret = self.dynamicCall("GetConnectState()")
            time.sleep(TR_REQ_TIME_INTERVAL)
            return ret
        except Exception as e:
            logger.critical(e)

    def set_input_value(self, id, value):
        try:
            self.dynamicCall("SetInputValue(QString, QString)", id, value)
        except Exception as e:
            logger.critical(e)

    def comm_rq_data(self, rqname, trcode, next, screen_no):

        self.dynamicCall("CommRqData(QString, QString, int, QString", rqname, trcode, next, screen_no)
        time.sleep(TR_REQ_TIME_INTERVAL)
        self.tr_event_loop = QEventLoop()
        self.tr_event_loop.exec_()

    def _get_comm_data(self, code, field_name, index, item_name):
        ret = self.dynamicCall("GetCommData(QString, QString, int, QString", code, field_name, index, item_name)
        return ret.strip()

    def _get_repeat_cnt(self, trcode, rqname):
        try:
            ret = self.dynamicCall("GetRepeatCnt(QString, QString)", trcode, rqname)
            return ret
        except Exception as e:
            logger.critical(e)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    Openapi()
