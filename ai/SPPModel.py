import sys
import logging

logger = logging.getLogger(__name__)
is_64bits = sys.maxsize > 2**32
if not is_64bits:
    logger.critical('64bit 환경으로 실행해 주시기 바랍니다.')
    exit(1)

from collections import deque

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn import preprocessing
from sklearn.model_selection import train_test_split
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.models import Sequential
from tensorflow.python.keras.callbacks import EarlyStopping

plt.rcParams['font.family'] = 'Malgun Gothic'


class DataNotEnough(BaseException):
    pass

# 학습 함수
def train(data, model, n_epochs=400, batch_size=64, verbose=0):
    early_stopping = EarlyStopping(monitor='val_loss', patience=50)  # 50번이상 더 좋은 결과가 없으면 학습을 멈춤

    # verbose 옵션은 실행 과정을 콘솔에 띄워줄지 말지에 대한 옵션
    # 0 - 끔, 1 - 움직이는 실시간 그래프, 2 - 정적 메시지
    history = model.fit(data["X_train"], data["y_train"],
                        batch_size=batch_size,
                        epochs=n_epochs,
                        validation_data=(data["X_test"], data["y_test"]),
                        callbacks=[early_stopping],
                        verbose=verbose)

    return history

# 에러 평가 함수
def evaluate(data, model):
    mse, mae = model.evaluate(data["X_test"], data["y_test"], verbose=0)
    mean_absolute_error = data["column_scaler"]["close"].inverse_transform([[mae]])[0][0]
    return mean_absolute_error

# 예측 주가를 계산 해주는 함수
def predict(data, model, n_steps=100):
    last_sequence = data["last_sequence"][-n_steps:]
    column_scaler = data["column_scaler"]
    # last_sequence를 reshape 합니다
    last_sequence = last_sequence.reshape((last_sequence.shape[1], last_sequence.shape[0]))
    # 3차원으로 변경
    last_sequence = np.expand_dims(last_sequence, axis=0)
    # 스케일 된 예측값을 계산 (0과 1사이의 값)
    prediction = model.predict(last_sequence)
    # 스케일 된 값에서 실제 값으로 변환
    predicted_price = column_scaler["close"].inverse_transform(prediction)[0][0]

    return predicted_price

# 스케일링 and "X_train", "X_test", "y_train", "y_test" 추출 함수
def load_data(df, n_steps=100, lookup_step=1, test_size=0.2, shuffle=True):
    # return 해줘야 할 모든 값들은 result 변수에 넣을 예정
    result = {}

    column_scaler = {}
    # data를 칼럼별로 0과 1사이의 값으로 scale
    for column in df.columns:
        scaler = preprocessing.MinMaxScaler()
        df[column] = scaler.fit_transform(np.expand_dims(df[column].to_numpy(), axis=1))
        # 해당 칼럼에 쓰인 scaler를 저장한다
        column_scaler[column] = scaler

    # result에 칼럼별 scaler들을 넣어준다
    result["column_scaler"] = column_scaler
    last_sequence = np.array(df.tail(lookup_step))
    df['future'] = df['close'].shift(-lookup_step)
    # drop NaNs (비어있는 row는 제거)
    df.dropna(inplace=True)
    sequence_data = []
    sequences = deque(maxlen=n_steps)
    for entry, target in zip(df.loc[:, df.columns != 'future'].to_numpy(), df['future'].to_numpy()):
        sequences.append(entry)
        if len(sequences) == n_steps:
            sequence_data.append([np.array(sequences), target])

    if not sequence_data:
        raise DataNotEnough()

    # dataset의 뒤에서 lookup_step 만큼 짤라온 last_sequence와 기존의 sequence를 합쳐서 last_sequence를 만듦
    # last_sequence는 향후 dataset에 없는 미래데이터 예측에 쓰임
    last_sequence = list(sequences) + list(last_sequence)
    # shift the last sequence by -1
    last_sequence = np.array(pd.DataFrame(last_sequence).shift(-1).dropna())
    # 결과 값을 result에 넣어준다
    result['last_sequence'] = last_sequence

    X, y = [], []

    for seq, target in sequence_data:
        X.append(seq)
        y.append(target)

    # numpy로 변환
    X = np.array(X)
    y = np.array(y)
    # 신경망에 적용(fit)하기위해 X의 shape을 변경
    X = X.reshape((X.shape[0], X.shape[2], X.shape[1]))

    # dataset을 train용도와 test 용도에 맞춰 나누어 줍니다.
    # test_size 가 0.2 이면 X_train, y_train에 80% 데이터로 트레이닝 하고 X_test,y_test에 나머지 20%로 테스트를 하겠다는 의미
    result["X_train"], result["X_test"], result["y_train"], result["y_test"] = \
        train_test_split(X, y, test_size=test_size, shuffle=shuffle)

    return result

# 모델 생성 함수
def create_model(units=50, dropout=0.3, n_steps=100, loss='mae', optimizer='adam', n_layers=4, cell=LSTM):
    model = Sequential()
    for i in range(n_layers):
        if i == 0:
            model.add(cell(units, return_sequences=True, input_shape=(None, n_steps)))
        elif i == n_layers - 1:  # 마지막 layer
            model.add(cell(units))
        else:
            model.add(cell(units, return_sequences=True))
        # 매 layer마다 dropout을 해줌
        model.add(Dropout(dropout))
    model.add(Dense(1))
    model.compile(loss=loss, metrics=[loss], optimizer=optimizer)

    return model

# 그래프 출력 함수
def plot_graph(model, data):
    y_test = data["y_test"]
    X_test = data["X_test"]
    y_pred = model.predict(X_test)
    y_test = np.squeeze(data["column_scaler"]["close"].inverse_transform(np.expand_dims(y_test, axis=0)))
    y_pred = np.squeeze(data["column_scaler"]["close"].inverse_transform(y_pred))
    # 마지막 200개의 데이터를 보여줌. 기간 수정을 원하시면 이 숫자를 바꿔주세요.
    plt.plot(y_test[-200:], c='b')
    plt.plot(y_pred[-200:], c='r')
    plt.xlabel("Days")
    plt.ylabel("Price")
    plt.legend(["Actual Price", "Predicted Price"])
    plt.show()
