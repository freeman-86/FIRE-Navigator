from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from core.domain.value_objects import AgeAt


class Prefecture(str, Enum):
    HOKKAIDO = "hokkaido"
    AOMORI = "aomori"
    IWATE = "iwate"
    MIYAGI = "miyagi"
    AKITA = "akita"
    YAMAGATA = "yamagata"
    FUKUSHIMA = "fukushima"
    IBARAKI = "ibaraki"
    TOCHIGI = "tochigi"
    GUNMA = "gunma"
    SAITAMA = "saitama"
    CHIBA = "chiba"
    TOKYO = "tokyo"
    KANAGAWA = "kanagawa"
    NIIGATA = "niigata"
    TOYAMA = "toyama"
    ISHIKAWA = "ishikawa"
    FUKUI = "fukui"
    YAMANASHI = "yamanashi"
    NAGANO = "nagano"
    GIFU = "gifu"
    SHIZUOKA = "shizuoka"
    AICHI = "aichi"
    MIE = "mie"
    SHIGA = "shiga"
    KYOTO = "kyoto"
    OSAKA = "osaka"
    HYOGO = "hyogo"
    NARA = "nara"
    WAKAYAMA = "wakayama"
    TOTTORI = "tottori"
    SHIMANE = "shimane"
    OKAYAMA = "okayama"
    HIROSHIMA = "hiroshima"
    YAMAGUCHI = "yamaguchi"
    TOKUSHIMA = "tokushima"
    KAGAWA = "kagawa"
    EHIME = "ehime"
    KOCHI = "kochi"
    FUKUOKA = "fukuoka"
    SAGA = "saga"
    NAGASAKI = "nagasaki"
    KUMAMOTO = "kumamoto"
    OITA = "oita"
    MIYAZAKI = "miyazaki"
    KAGOSHIMA = "kagoshima"
    OKINAWA = "okinawa"


@dataclass
class User:
    birth_date: date
    residence: Prefecture
    spouse: Optional["User"] = None

    def age_at(self, reference_date: date) -> AgeAt:
        return AgeAt(self.birth_date, reference_date)
