from __future__ import annotations

import random
from typing import Optional


def create_rng(seed: Optional[int] = None) -> random.Random:
    """乱数生成器を初期化する。テスト実行時は固定シードを渡すことで結果を再現可能にする
    （Regression Testでの再現性を担保するため）。
    """

    return random.Random(seed)
