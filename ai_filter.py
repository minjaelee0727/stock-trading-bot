# version 0.1.2
import datetime
import sys

import numpy as np
import pandas as pd
import pymysql
from sqlalchemy.event import listen
from sqlalchemy.pool import Pool
from sqlalchemy.exc import InternalError, ProgrammingError
from tensorflow.keras.callbacks import EarlyStopping

from ai.SPPModel import load_data, create_model, evaluate, predict, DataNotEnough
from library import cf
from library.open_api import setup_sql_mod

listen(Pool, 'connect', setup_sql_mod)
listen(Pool, 'first_connect', setup_sql_mod)


# 모의투자, 실전투자 일때만 들어오는 함수
def filter_by_ai(db_name, simul_num):
    from library.simulator_func_mysql import simulator_func_mysql
    sf = simulator_func_mysql(simul_num, 'real', db_name)
    try:
        ai_filter(sf.ai_filter_num, sf.engine_simulator)
    except AttributeError:
        print(f"{simul_num} 알고리즘은 AI 알고리즘이 아닙니다. \n cf파일에서 simul_num 을 AI알고리즘을 사용하는 번호로 수정해주세요")


def filtered_by_basic_lstm(dataset, ai_settings):
    """
    :param dataset: 실제 주가 데이터
    :param settings: AI 알고리즘 세팅
    :return: ratio_cut(목표 수익률) 보다 ratio가 작으면 True 반환(필터링 대상)
    """

    shuffled_data = load_data(df=dataset.copy(), n_steps=ai_settings['n_steps'], test_size=ai_settings['test_size'])

    model = create_model(n_steps=ai_settings['n_steps'], loss=ai_settings['loss'], units=ai_settings['units'],
                         n_layers=ai_settings['n_layers'], dropout=ai_settings['dropout'])

    early_stopping = EarlyStopping(monitor='val_loss', patience=50)  # 50번이상 더 좋은 결과가 없으면 학습을 멈춤

    model.fit(shuffled_data["X_train"], shuffled_data["y_train"],
                        batch_size=ai_settings['batch_size'],
                        epochs=ai_settings['epochs'],
                        validation_data=(shuffled_data["X_test"], shuffled_data["y_test"]),
                        callbacks=[early_stopping],
                        verbose=1)

    scaled_data = load_data(df=dataset.copy(), n_steps=ai_settings['n_steps'], test_size=ai_settings['test_size'],
                            shuffle=False)

    mae = evaluate(scaled_data, model)
    print(f"Mean Absolute Error: {mae}")

    # 예측 가격
    future_price = predict(scaled_data, model, n_steps=ai_settings['n_steps'])

    # 스케일링 된 예측 결과
    scaled_y_pred = model.predict(scaled_data['X_test'])
    # 실제 값으로 변환 된 결과
    y_pred = np.squeeze(scaled_data['column_scaler']['close'].inverse_transform(scaled_y_pred))

    if ai_settings['is_used_predicted_close']:
        close = y_pred[-1] # 예측 그래프에서의 종가
    else:
        close = dataset.iloc[-1]['close'] # 실제 종가

    # ratio : 예상 상승률
    ratio = (future_price - close) / close * 100

    msg = f"After {ai_settings['lookup_step']}: {int(close)} -> {int(future_price)}"

    if ratio > 0: # lookup_step(분, 일) 후 상승 예상일 경우 출력 메시지
        msg += f'    {ratio:.2f}% ⯅ '
    elif ratio < 0: # lookup_step(분, 일) 후 하락 예상일 경우 출력 메시지
        msg += f'    {ratio:.2f}% ⯆ '
    print(msg, end=' ')
    return ai_settings['ratio_cut'] >= ratio # ratio_cut(목표 수익률) 보다 ratio가 작으면 True 반환(필터링 대상)


def create_training_engine(db_name):
    return pymysql.connect(
        host=cf.db_ip,
        port=int(cf.db_port),
        user=cf.db_id,
        password=cf.db_passwd,
        db=db_name,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


def ai_filter(ai_filter_num, engine, until=datetime.datetime.today()):
    if ai_filter_num == 1:
        ai_settings = {
            "n_steps": 100, # 시퀀스 데이터를 몇개씩 담을지 설정
            "lookup_step": 30, #단위 :(일/분) 몇 일(분) 뒤의 종가를 예측 할 것 인지 설정 : daily_craw -> 일 / min_craw -> 분
            "test_size": 0.2, # train 범위 : test_size 가 0.2 이면 X_train, y_train에 80% 데이터로 트레이닝 하고 X_test,y_test에 나머지 20%로 테스트를 하겠다는 의미
            "n_layers": 4, # LSTM layer 개수
            "units": 50, # LSTM neurons 개수
            "dropout": 0.2, # overfitting 방지를 위해 몇개의 노드를 죽이고 남은 노드들을 통해서만 훈련을 하는 것(0.2 -> 20%를 죽인다)
            "loss": "mae", # loss : 최적화 과정에서 최소화될 손실 함수(loss function)를 설정 # mae : mean absolute error (평균 절대 오차)
            "optimizer": "adam", # optimizer : 최적화 알고리즘 선택
            "batch_size": 64, # 각 학습 반복에 사용할 데이터 샘플 수
            "epochs": 400, # 몇 번 테스트 할지
            "ratio_cut": 3, #단위:(%) lookup_step 기간 뒤 ratio_cut(%) 만큼 증가 할 것이 예측 된다면 매수
            "table": "daily_craw",  #분석 시 daily_craw(일별데이터)를 이용 할지 min_craw(분별데이터)를 이용 할지 선택. ** 주의: min_craw 선택 시 최근 1년 데이터만 있기 때문에 simulator_func_mysql.py에서 self.simul_start_date를 최근 1년 전으로 설정 필요
            "is_used_predicted_close" : True # ratio(예상 상승률) 계산 시 예측 그래프의 close 값을 이용 할 경우 True, 실제 close 값을 이용할 시 False
        }
        tr_engine = create_training_engine(ai_settings['table'])

        try:
            buy_list = engine.execute("""
                SELECT DISTINCT code_name FROM realtime_daily_buy_list
            """).fetchall()
        except (InternalError, ProgrammingError) as err:
            if 'Table' in str(err):
                print(f"{err} \n realtime_daily_buy_list 테이블이 존재 하지 않습니다. \n 콜렉터를 실행해주세요 ")
            else:
                print(f"{err} \n jackbot 데이터베이스가 존재 하지 않습니다. \n 콜렉터를 실행해주세요 ")
            exit(1)

        feature_columns = ["close", "volume", "open", "high", "low"]
        filtered_list = []
        for code_name, in buy_list:
            print(f"{code_name} 종목 분석 중....")

            sql = """
                SELECT {} FROM `{}`
                WHERE STR_TO_DATE(date, '%Y%m%d%H%i') <= '{}'
            """.format(','.join(feature_columns), code_name, until)
            # pandas(pd) read_sql 을 사용하면 sql, engine을 넘겼을 때 return 값을 바로 데이터프레임으로 받을 수 있음
            df = pd.read_sql(sql, tr_engine)

            # 데이터가 1000개(1000일 or 1000분)가 넘지 않으면 예측도가 떨어지기 때문에 필터링
            if len(df) < 1000:
                filtered_list.append(code_name)
                print(f"테스트 데이터가 적어서 realtime_daily_buy_list 에서 제외")
                continue
            try:
                filtered = filtered_by_basic_lstm(df, ai_settings)
            except (DataNotEnough, ValueError):
                print(f"테스트 데이터가 적어서 realtime_daily_buy_list 에서 제외")
                filtered_list.append(code_name)
                continue

            print(code_name)

            # filtered가 True 이면 filtered_list(필터링 종목)에 해당 종목을 append
            if filtered:
                print(f"기준에 부합하지 않으므로 realtime_daily_buy_list 에서 제외")
                filtered_list.append(code_name)

    # filtered_list에 있는 종목들을 realtime_daily_buy_list(매수리스트)에서 제거
    # 모든 조건문에서 filtered_list를 생성해줘야 함
    if len(filtered_list) > 0:
        engine.execute(f"""
            DELETE FROM realtime_daily_buy_list WHERE code_name in ({','.join(map('"{}"'.format, filtered_list))})
        """)


if __name__ == '__main__':
    # 모의투자, 실전투자 일때만 들어오는 함수
    filter_by_ai(*sys.argv[1:])
