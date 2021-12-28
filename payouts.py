from app import TransactionRequestOrg, db

for i in TransactionRequestOrg.query.all():
    print(i.transaction_request.replace("Wallet ID: ", "₺ && Wallet ID: " ))
    if input("Onayla? ").upper() == "Y":
        db.session.delete(i)
        db.session.commit()

