from app import Account, db

for i in Account.query.all():
    if i.tc_kimlik and not i.eligible_for_installments:
        print(f"TC NO: {i.tc_kimlik}, İSİM SOYAD: {i.ad_soyad}, DOĞUM: {i.dogum}")
        if input("Onayla? ") == "Y":
            i.eligible_for_installments = True
            db.session.commit()

