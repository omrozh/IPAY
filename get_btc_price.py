import requests
from Kurlar import DovizKurlari


def finalDolar():
    dolar_inst = DovizKurlari()
    dolar = dolar_inst.DegerSor("USD","ForexBuying")
    return float(dolar)


def get_price():
    response = requests.get('https://api.binance.com/api/v3/avgPrice?symbol=LTCUSDT')
    data = response.json()

    return float(data["price"]) * finalDolar()

