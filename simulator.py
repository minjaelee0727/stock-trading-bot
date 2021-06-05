# -*- coding: utf-8 -*-

from library.simulator_func_mysql import *


class simulator():
    def __init__(self):
        self.set_variables()
        self.call_library()

    def set_variables(self):
        # 시뮬레이터 번호 설정
        self.simul_num = int(input("시뮬레이팅 할 알고리즘 번호를 입력 하세요: "))

        # self.simul_reset 설정
        #       'y'  :  self.simul_num 에서 설정한 번호에 해당 하는 시뮬레이터 데이터베이스를 초기화 하고 처음 부터 실행
        #       'n' : self.simul_num 에서 설정한 번호에 해당 하는 시뮬레이터 데이터베이스를 초기화 하지 않고 이어서 실행
        #                    ex) 2020년 01월 01일까지 시뮬레이터를 마쳤는데, 그 이후로 연달아서 2020년 01월 02일 부터 시뮬레이터 테스트를 하고 싶은 경우

        input_reset = str(input("시뮬레이팅 데이터베이스 초기화 여부 : (y or n) "))

        if input_reset == 'y':
            self.simul_reset= True
        elif input_reset =='n':
            self.simul_reset= False
        else:
            print("y or n (소문자) 만 입력 가능 합니다.")
            exit(1)


    def call_library(self):
        # simulator_func_mysql 라이브러리 클래스 호출
        simulator_func_mysql(self.simul_num, self.simul_reset, True, 0)


if __name__ == "__main__":
    # simulator 클래스 호출
    simulator()

