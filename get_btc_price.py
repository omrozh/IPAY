import requests
from Kurlar import DovizKurlari


def finalDolar():
    dolar_inst = DovizKurlari()
    dolar = dolar_inst.DegerSor("USD","ForexBuying")
    return float(dolar)


def get_price():
    response = requests.get('https://api.coindesk.com/v1/bpi/currentprice.json')
    data = response.json()

    print(data["time"])

    return float(data["bpi"]["USD"]['rate'].replace(",", "")) * finalDolar()

