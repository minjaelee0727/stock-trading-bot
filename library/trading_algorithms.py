import numpy as np
import pandas as pd


def BBands(df_close, w=20, k=2):
    """
    :param df_close:
    :param w: moving average term (default= 20)
    :param k: multiplier (default= 2)
    :return:
        Bolinger bands uses std and mbb
        1. ubb - Upper Bounds Band
        2. lbb - Lower Bounds Band
        3. perb - %b: close position in the BBands
        4. bw - Band Width
    """
    """         0
    df_close: 1 x
    """
    df_close = df_close.astype(int)
    std = df_close[:w].std()[0]
    mbb = df_close[:w].mean()[0]
    close = df_close[0][0]

    ubb = mbb + std * k
    lbb = mbb - std * k

    if ubb > lbb:
        perb = (close - lbb) / (ubb - lbb)
        bw = (ubb - lbb) / mbb

        return mbb, ubb, lbb, perb, bw
    else:
        return False


def macd_with_bbands(df_close: pd.DataFrame, fast_ema_period=12, slow_ema_period=26, signal_period=9, buy=True) -> bool:
    emaFast = df_close.ewm(span=fast_ema_period).mean()
    emaSlow = df_close.ewm(span=slow_ema_period).mean()
    macd = emaFast - emaSlow

    if macd[0][1] - macd[0][2] > 0:
        if buy:
            return True
        else:
            return False
    else:
        if buy:
            return False
        else:
            return True

