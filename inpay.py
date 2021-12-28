import requests
import datetime


def retrieveCards(wallet_key):
    req = requests.post("https://inpay-tr.com/api/collect_cards", data={
        "card_view_key": wallet_key,
    })

    return req.text


class AccountManagement:
    def __init__(self, card_view_key):
        self.card_view_key = card_view_key

    def createWallet(self):
        req = requests.post("https://inpay-tr.com/api/createWallet", data={
            "account_id": self.card_view_key
        })

        return req.text

    def payoutRequest(self, amount, wallet_id, bank_info, account_holder_fullname):
        req = requests.post("https://inpay-tr.com/api/payouts", data={
            "account_id": self.card_view_key,
            "amount": amount,
            "wallet_id": wallet_id,
            "bank_info": bank_info,
            "fullname": account_holder_fullname
        })

        return req.text

    def changeAccountStatus(self, new_status):
        req = requests.post("https://inpay-tr.com/api/updateStatus", data={
            "account_id": self.card_view_key,
            "updated_status": new_status
            # NOPAY(Organisation) or TPAY(Individual)
        })

        return req.text


class WalletKeys:
    def __init__(self, email, password):
        self.password = password
        self.email = email

    def retrieveAccountKey(self):
        req = requests.post("https://inpay-tr.com/api/collect_ckey", data={
            "email": self.email,
            "password": self.password
        })

        return req.text


class Charge:
    def __init__(self, number, cvc, date, receiving_wallet, charge_name):
        date = date.replace("/", "*")
        self.sc_key = str(number) + "&" + str(cvc) + "&" + str(date)
        self.charge_name = charge_name
        self.receiving_wallet = receiving_wallet

    def charge(self, amount):
        r = requests.post("https://inpay-tr.com/api/charge", data={"wallet_sc_key": self.sc_key,
                                                                   "receiving_wallet": self.receiving_wallet,
                                                                   "amount": amount,
                                                                   "charge_name": self.charge_name})
        if r.text == "Ödeme Onaylandı":
            return {"status": True, "reason_of_failure": "Success"}
        elif not r.ok:
            return {"status": False, "reason_of_failure": "Yetersiz cüzdan bakiyesi"}
        else:
            return {"status": False, "reason_of_failure": r.text}

    def installmentCharge(self, installment_amount, total_months):
        r = requests.post("https://inpay-tr.com/api/createInstallmentCharge",
                          data={"wallet_sc_key": self.sc_key,
                                "receiving_wallet": self.receiving_wallet,
                                "installment_amount": installment_amount,
                                "total_months": total_months,
                                "day_of_month": datetime.datetime.today().day,
                                "charge_name": self.charge_name
                                })

        if r.text == "Ödeme Onaylandı":
            return {"status": True, "reason_of_failure": "Success"}
        elif not r.ok:
            return {"status": False, "reason_of_failure": "Yetersiz cüzdan bakiyesi"}
        else:
            return {"status": False, "reason_of_failure": r.text}

    def marketplaceCharge(self, amount, second_receiver, commission_percentage):
        data_init = {"wallet_sc_key": self.sc_key,
                     "receiving_wallet": self.receiving_wallet,
                     "amount": amount / 100 * (100 - commission_percentage),
                     "charge_name": self.charge_name}
        data_commission = {
            "wallet_sc_key": self.sc_key,
            "receiving_wallet": second_receiver,
            "amount": amount / 100 * commission_percentage,
            "charge_name": self.charge_name
        }

        r = requests.post("https://inpay-tr.com/api/charge", data=data_init)
        r_com = requests.post("https://inpay-tr.com/api/charge", data=data_commission)

        if r.text == "Ödeme Onaylandı" and r_com.text == "Ödeme Onaylandı":
            return "Ödeme Başarılı"
        elif r.text == "Ödeme Onaylandı":
            return "Ana ödeme başarılı komisyon işlemi tamamlanamadı"
        else:
            return "Başarısız"

    def marketplaceInstallmentCharge(self, installment_amount, total_months, second_receiver, commission_percentage):
        r = requests.post("https://inpay-tr.com/api/createInstallmentCharge",
                          data={"wallet_sc_key": self.sc_key,
                                "receiving_wallet": self.receiving_wallet,
                                "installment_amount": installment_amount / 100 * (100 - commission_percentage),
                                "total_months": total_months,
                                "day_of_month": datetime.datetime.today().day,
                                "charge_name": self.charge_name
                                })

        r_com = requests.post("https://inpay-tr.com/api/createInstallmentCharge",
                              data={"wallet_sc_key": self.sc_key,
                                    "receiving_wallet": second_receiver,
                                    "installment_amount": installment_amount / 100 * commission_percentage,
                                    "total_months": total_months,
                                    "day_of_month": datetime.datetime.today().day,
                                    "charge_name": self.charge_name
                                    })

        if r.text == "Ödeme Onaylandı" and r_com.text == "Ödeme Onaylandı":
            return "Ödeme Başarılı"
        elif r.text == "Ödeme Onaylandı":
            return "Ana ödeme başarılı komisyon işlemi tamamlanamadı"
        else:
            return "Başarısız"

