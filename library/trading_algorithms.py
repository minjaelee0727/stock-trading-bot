import numpy as np
import pandas as pd


def BBands(df_close, w=20, m=2):
    """
    :param df_close:
    :param w: moving average term (default= 20)
    :param m: multiplier (default= 2)
    :return:
        Bolinger bands uses std and mbb
        1. ubb - Upper Bounds Band
        2. lbb - Lower Bounds Band
        3. perb - %b: close position in the BBands
        4. bw - Band Width
    """
    print(df_close)
    df_close = df_close.astype(int)
    std = df_close[:w].std()[0]
    mbb = df_close[:w].mean()[0]
    close = df_close[0][0]

    ubb = mbb + std * m
    lbb = mbb - std * m

    if ubb > lbb:
        perb = (close - lbb) / (ubb - lbb)
        bw = (ubb - lbb) / mbb

        return mbb, ubb, lbb, perb, bw
    else:
        return False

