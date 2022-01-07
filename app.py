from inpay import Charge
from bitcoinlib.wallets import Wallet
import flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import string
from flask_login import LoginManager, login_user, login_required, current_user, UserMixin, logout_user
from get_btc_price import get_price, finalDolar
import qrcode
import os
from PIL import Image
from apscheduler.schedulers.background import BackgroundScheduler
from pyzbar import pyzbar
import random
import datetime
import stripe

stripe_keys = {
  'secret_key': "XXXXX",
  'publishable_key': "pk_live_51HmZthKorNA5pIqqr37KQQpgACAJeRmWI5EODh6D4sN14Xh"
                     "oTtwfAuiQyXyfZgaxJZ9w6h877nqUQVHITh3yKbjA00kLKfTu0R"
}

stripe.api_key = stripe_keys['secret_key']


def pay_via_card(credit, card_month, card_year, card_cvc, amount):
    print(amount)
    payment = stripe.PaymentMethod.create(
        type="card",
        card={
            "number": credit,
            "exp_month": card_month,
            "exp_year": card_year,
            "cvc": card_cvc,
        },
    )
    customer = stripe.Customer.create()

    paymentmethod = stripe.PaymentMethod.attach(
        payment.stripe_id,
        customer=customer.stripe_id,
    )


    token = stripe.Token.create(
        card={
            "number": credit,
            "exp_month": card_month,
            "exp_year": card_year,
            "cvc": card_cvc,
        },
    )

    stripe.Customer.create_source(
        customer.stripe_id,
        source=token.stripe_id
    )

    charge_item = stripe.Charge.create(
        customer=customer.id,
        amount=int(float(amount) * 100),
        currency='try',
        description=f'InPay Ödeme Sistemleri'
    )


def generate_wallet_name(length):
    result = "i" + str(random.randint(1000000000000000, 9999999999999999)) + "&" + str(random.randint(100, 999)) + \
             "&" + str(random.randint(1, 12)) + "*" + str(random.randint(24, 30))
    return result


def generate_cards_key(length):
    result = ''.join(
        (random.choice(string.ascii_lowercase) for x in range(length)))
    return result


app = flask.Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SECRET_KEY"] = "XXXXXX"

login_manager = LoginManager(app)


@login_manager.user_loader
def load_user(user_id):
    return Account.query.get(user_id)


db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


class Account(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    transaction_history = db.Column(db.String)
    payroll_key = db.Column(db.String)
    email = db.Column(db.String, unique=True)
    password = db.Column(db.String)
    account_balance = db.Column(db.Float)
    organisation = db.Column(db.Boolean)
    eligible_for_installments = db.Column(db.Boolean, default=False)
    installment_limit = db.Column(db.Float, default=5000)
    tc_kimlik = db.Column(db.Integer, unique=True)
    card_view_key = db.Column(db.String, default=generate_cards_key(64), unique=True)
    ad_soyad = db.Column(db.String)
    dogum = db.Column(db.String)


class DBWallet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wallet_name = db.Column(db.String)
    real_wallet_name = db.Column(db.String, unique=True)
    wallet_id = db.Column(db.String)
    fixed_amount = db.Column(db.Float, default=0)
    owner = db.Column(db.Integer)
    added_owners = db.Column(db.String)


class TransactionRequestOrg(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_request = db.Column(db.String)


class InstallmentCharge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_wallet_number = db.Column(db.String)
    installment_amount = db.Column(db.Float)
    remaining_months = db.Column(db.Integer)
    last_charge_date = db.Column(db.String)
    day_of_month = db.Column(db.Integer)


class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    card_number = db.Column(db.Integer)
    cvc = db.Column(db.Integer)
    date = db.Column(db.String)
    owner = db.Column(db.Integer)


admin_auth = ["info@inpay-tr.com"]


@app.route("/verify/<id>")
@login_required
def verifyID(id):
    if current_user.email not in admin_auth:
        return "Unauthorized"
    Account.query.get(int(id)).eligible_for_installments = True
    db.session.commit()
    return flask.redirect("/admin")


@app.route("/verify_transaction/<id>")
@login_required
def verifyTransaction(id):
    if current_user.email not in admin_auth:
        return "Unauthorized"
    db.session.delete(TransactionRequestOrg.query.get(int(id)))
    db.session.commit()
    return flask.redirect("/admin")


@app.route("/api/refund", methods=["POST", "GET"])
def refundAPI():
    if flask.request.method == "POST":
        values = flask.request.values

        if DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key_main"]).first().fixed_amount < float(
                values["amount"]):
            raise ValueError
        refunder_wallet = DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key_main"]).first()
        refund_wallet = DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key_client"]).first()

        refunder_wallet.fixed_amount -= float(values["amount"]) + (float(values["amount"]) / 10)
        refund_wallet.fixed_amount += float(values["amount"])

        db.session.commit()
        return "İade tamamlandı"


@app.route("/admin")
@login_required
def admin():
    if current_user.email not in admin_auth:
        return "Unauthorized"
    tc_unverified = []

    for i in Account.query.all():
        if i.tc_kimlik and not i.eligible_for_installments:
            tc_unverified.append(i)
    transaction_requests = TransactionRequestOrg.query.all()
    return flask.render_template("admin.html", transaction_requests=transaction_requests, tc_unverified=tc_unverified)


@app.route("/docs")
def docs():
    return flask.render_template("documents.html")


@app.route("/api/payroll_charge", methods=["GET", "POST"])
def payrollCharge():
    values = flask.request.values
    print(values["wallet_sc_key"])
    if not values["api_key"] == Account.query.get(DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().owner).payroll_key:
        return "Geçersiz API anahtarı"
    if DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().fixed_amount < float(
            values["amount"]):
        raise ValueError

    print(values["receiving_wallet"])

    DBWallet.query.filter_by(real_wallet_name=values["receiving_wallet"]).first().fixed_amount += float(values["amount"]) + (
                float(values["amount"]) / 10)
    DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().fixed_amount -= float(values["amount"])
    db.session.commit()

    return "Ödeme Onaylandı"


@app.route("/transactions")
@login_required
def transaction_history():
    transactions = []
    for i in current_user.transaction_history.split("&"):
        if len(i.split("/")) > 1:
            transactions.append(i.split("/")[0])
            transactions.append(i.split("/")[1])
    return flask.render_template("transactions.html", transactions=transactions, transactions_length=len(transactions))


@app.route("/api/createWallet", methods=["POST", "GET"])
def createWalletAPI():
    if flask.request.method == "POST":
        values = flask.request.values
        acc = Account.query.filter_by(card_view_key=values["account_id"]).first()

        real_wallet_name = generate_wallet_name(32)
        w = Wallet.create(real_wallet_name, network='litecoin')
        db_wallet_rep = DBWallet(wallet_name="New Wallet", real_wallet_name=real_wallet_name,
                                 wallet_id=str(w.get_key().address), owner=acc.id, added_owners="")
        db.session.add(db_wallet_rep)
        db.session.commit()

        w.scan()

        return db_wallet_rep.real_wallet_name


@app.route("/api/payouts", methods=["POST", "GET"])
def payoutAPI():
    if flask.request.method == "POST":
        db.session.add(TransactionRequestOrg(transaction_request=flask.request.values["bank_info"]
                                             + "&&" + flask.request.values["fullname"] + "&&" +
                                             flask.request.values["amount"] + "Wallet ID: " + 
                                             flask.request.values["wallet_id"] + "Account ID: " + 
                                                                 flask.request.values["account_id"]))
        db.session.commit()

        return "Ödeme talebiniz alındı."


@app.route("/api/updateStatus", methods=["POST", "GET"])
def changeAccountStatusAPI():
    if flask.request.method == "POST":
        acc = Account.query.filter_by(card_view_key="account_id").first()
        acc.organisation = flask.request.values["updated_status"] == "NOPAY"
        db.session.commit()
        return "Hesap Statüsü Güncellendi " + flask.request.values["updated_status"]


@app.route("/favicon.ico")
def favicon():
    return flask.redirect("https://www.socialsnake.ml/88798569icon.png", code=301)


def isValidTCID(value):
    value = str(value)

    if not len(value) == 11:
        return False

    if not value.isdigit():
        return False

    if int(value[0]) == 0:
        return False

    digits = [int(d) for d in str(value)]

    if not sum(digits[:10]) % 10 == digits[10]:
        return False

    if not (((7 * sum(digits[:9][-1::-2])) - sum(digits[:9][-2::-2])) % 10) == digits[9]:
        return False

    return True


@app.route("/verifyTC", methods=["POST", "GET"])
@login_required
def tcDogrula():
    if flask.request.method == "POST":
        tc_no = flask.request.values["tc_no"]
        if not isValidTCID(int(tc_no)):
            return '<script>alert("Geçersiz TC No."); document.location = "/dashboard"</script>'
        try:
            current_user.tc_kimlik = tc_no
            current_user.ad_soyad = flask.request.values["ad_soyad"]
            current_user.dogum = flask.request.values["dogum"]
            db.session.commit()
        except:
            return '<script>alert("TC Kimlik No. başka bir hesaba bağlı olarak kullanılıyor."); ' \
                   'document.location = "/dashboard"</script>'
        return flask.render_template("confirm_tc.html")
    return flask.render_template("tc_dogrulama.html")


@app.route("/api/createInstallmentCharge", methods=["POST", "GET"])
def installmentPayments():
    if flask.request.method == "POST":
        values = flask.request.values
        if float(values["installment_amount"])<float(0):
            return "Geçersiz Değer"
        if int(values["total_months"]) > 6 or float(values["installment_amount"]) * int(values["total_months"]) > 3000:
            return "Şu an için maksimum 6 aya ve 3000₺'ye kadar taksitlendirmeye izin verilmektedir."
        if not Account.query.get(DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"])
                                         .first().owner).eligible_for_installments:
            return "Bu hesap düşük kredi notu nedeniyle taksitlendirmeye uygun değildir."

        new_installment_payment = InstallmentCharge(transaction_wallet_number=values["wallet_sc_key"],
                                                    installment_amount=float(values["installment_amount"]),
                                                    remaining_months=int(values["total_months"]),
                                                    last_charge_date=str(datetime.datetime.today().year)
                                                                     + "/" + str(datetime.datetime.today().month),
                                                    day_of_month=values["day_of_month"])
        db.session.add(new_installment_payment)
        if not DBWallet.query.filter_by(wallet_id=values["receiving_wallet"]).first().owner ==  DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().owner:
            DBWallet.query.filter_by(wallet_id=values["receiving_wallet"]).first().fixed_amount += \
            float(values["installment_amount"]) * int(values["total_months"]) + (float(values["installment_amount"]) * int(values["total_months"]) / 10)

        Account.query.get(DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"])
                                         .first().owner).installment_limit -= float(values["installment_amount"]) * int(values["total_months"])

        Account.query.get(DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().owner).transaction_history += "InPay Taksitli Ödeme" + "/" + " Aylık: " + str(values["installment_amount"]) + "₺ Toplam taksit: " + str(values["total_months"]) + " Ay&"
        db.session.commit()

        return "Ödeme Onaylandı"


def installmentsChecker():
    all_installments = InstallmentCharge.query.filter_by(last_charge_date=str(datetime.datetime.today().year)
                                                                     + "/" + str(datetime.datetime.today().month - 1)).all()
    for i in all_installments:
        if not i.day_of_month == datetime.datetime.today().day:
            continue
        try:
            wallet = DBWallet.query.filter_by(real_wallet_name=i.transaction_wallet_number)
            if wallet.fixed_amount < i.installment_amount:
                i.day_of_month += 1
                raise ValueError
            wallet.fixed_amount -= i.installment_amount
            i.remaining_months -= 1
            i.last_charge_date = str(datetime.datetime.today().year) + "/" + str(datetime.datetime.today().month)
        except:
            Account.query.get(DBWallet.query.filter_by(real_wallet_name=i.transaction_wallet_number).first().owner).\
                eligible_for_installments = False
            db.session.commit()
        account = Account.query.get(DBWallet.query.filter_by(real_wallet_name=i.transaction_wallet_number).first())
        account.installment_limit += i.installment_amount
        account.transaction_history += "Aylık Taksit Ödemesi InPay" + "/" + i.installment_amount + "&"
        db.session.commit()

        if i.remaining_months == 0:
            db.session.delete(i)


sched = BackgroundScheduler(daemon=True)
sched.add_job(installmentsChecker, 'interval', minutes=360)
sched.start()


@app.route("/deposit/<wallet_id>", methods=["POST", "GET"])
@login_required
def deposit(wallet_id):
    user_cards = []
    temp_card = Card.query.filter_by(owner=current_user.id).all()
    temp_number = []

    for i in temp_card:
        if i.card_number not in temp_number:
            temp_number.append(i.card_number)
            user_cards.append(i)

    if flask.request.method == "POST":
        values = flask.request.values
        inpay = False
        if values["card_number"][0] == "i":
            chrg = Charge(values["card_number"], values["card_cvc"],  values["card_date"], "LSdWnFjfoeLR3JXKkwz7emU8cgxZVQK14g", "InPay Deposit")

            confirmation = chrg.charge(float(values["amount"]))

            if not confirmation["status"]:
                return confirmation["reason_of_failure"]
            elif confirmation["status"]:
                inpay = True
        if float(values["amount"]) < 25:
            return '<script>alert("En az 25₺ yükleme yapmalısınız."); document.location = "/dashboard"</script>'
        for i in user_cards:
            if str(values["card_number"]) == str(i.card_number) and not current_user.id == i.owner:
                return '<script>alert("Aynı kartı iki farklı hesapta kullanamazsınız."); document.location = ' \
                       '"/dashboard"</script>'
        if not inpay:
            new_card = Card(card_number=int(values["card_number"]), cvc=int(values["card_cvc"]), date=values["card_date"],
                            owner=current_user.id)
            db.session.add(new_card)
        db.session.commit()
        if not inpay:
            try:
                 pay_via_card(values["card_number"], values["card_date"].split("/")[0],
                         values["card_date"].split("/")[1], values["card_cvc"], float(values["amount"]))
            except:
                return flask.render_template("error_page.html")
        DBWallet.query.filter_by(real_wallet_name=wallet_id).first().fixed_amount += float(values["amount"])

        if float(values["amount"]) == 50 and not inpay:
            DBWallet.query.filter_by(real_wallet_name=wallet_id).first().fixed_amount += 5
        if float(values["amount"]) == 100 and not inpay:
            DBWallet.query.filter_by(real_wallet_name=wallet_id).first().fixed_amount += 10
        if float(values["amount"]) == 200 and not inpay:
            DBWallet.query.filter_by(real_wallet_name=wallet_id).first().fixed_amount += 25
        db.session.commit()
    return flask.render_template("deposit_via_card.html", user_cards=user_cards)


@app.route("/")
def home():
    return flask.render_template("home.html")


@app.route("/register", methods=["POST", "GET"])
def index():
    if current_user.is_authenticated:
        return flask.redirect("/dashboard")
    if flask.request.method == "POST":
        values = flask.request.values
        try:
            new_account = Account(email=values["email"], password=bcrypt.generate_password_hash(values["password"]),
                                  organisation=bool(values["organisation"]), account_balance=0, transaction_history="")
            db.session.add(new_account)
            db.session.commit()
        except:
            new_account = Account(email=values["email"], password=bcrypt.generate_password_hash(values["password"]),
                                  organisation=False, account_balance=0, transaction_history="")
            db.session.add(new_account)
            db.session.commit()
        login_user(new_account)
    return flask.render_template("index.html")


@app.route("/transaction_request", methods=["POST", "GET"])
@login_required
def transactionRequest():
    if not current_user.organisation:
        return flask.redirect("/dashboard")
    if flask.request.method == "POST":
        db.session.add(TransactionRequestOrg(transaction_request=flask.request.values["bank_info"]
                                                                 + "&&" + flask.request.values["fullname"] + "&&" +
                                                                 flask.request.values["amount"]))
        db.session.commit()

        return '''
            <script>
                alert('Talebinizi aldık, sizinle iletişime geçilerek ödeme onayı alındıktan sonra ödemeniz iletilecektir')
                document.location = '/dashboard'
            </script>
        '''
    return flask.render_template("direct_deposit.html")


@app.route("/login", methods=["POST", "GET"])
def login():
    if flask.request.method == "POST":
        values = flask.request.values
        acc = Account.query.filter_by(email=values["email"]).first()
        if bcrypt.check_password_hash(acc.password, values["password"]):
            login_user(acc, remember=True)
            return flask.redirect("/dashboard")

    return flask.render_template("login.html")


@app.route("/create_wallet")
@login_required
def createWallet():
    real_wallet_name = generate_wallet_name(32)
    w = Wallet.create(real_wallet_name, network='litecoin')
    db_wallet_rep = DBWallet(wallet_name="New Wallet", real_wallet_name=real_wallet_name,
                             wallet_id=str(w.get_key().address), owner=current_user.id, added_owners="")
    db.session.add(db_wallet_rep)
    db.session.commit()

    w.scan()

    return flask.redirect("/dashboard")


@app.route("/dashboard")
@login_required
def dashboard():
    wallets = []
    for i in DBWallet.query.all():
        if i.owner == current_user.id or current_user.email in i.added_owners.split(","):
            wallets.append(i)
            wallets.append(str(i.fixed_amount))
    return flask.render_template("dashboard.html", wallets=wallets, current_price=get_price(),
                                 wallets_length=len(wallets), is_organisation=current_user.organisation, email=current_user.email, eligible_for_installments=not current_user.eligible_for_installments)


@app.route("/receive/<wallet_id>")
@login_required
def receive_payment_input(wallet_id):
    return flask.render_template("receive_amount.html", wallet_id=wallet_id, current_price=1)


@app.route("/receive/<wallet_id>/<amount>")
def receive_payment(wallet_id, amount):
    img = qrcode.make(wallet_id + "&!&" + amount)
    img.save(f"qrs/{wallet_id}.jpg")
    return flask.send_file("qrs/" + wallet_id + ".jpg")


@app.route("/pay/<real_name>", methods=["POST", "GET"])
@login_required
def makePayment(real_name):
    if flask.request.method == "POST":
        file = flask.request.files["file"]
        secure_int = random.randint(999999, 9999999)
        file.save(os.path.join("./temp", str(secure_int) + file.filename))
        img = Image.open(os.path.join("./temp", str(secure_int) + file.filename))

        thresh = 40
        fn = lambda x: 255 if x > thresh else 0
        r = img.convert('L').point(fn, mode='1')

        r.save(os.path.join("./temp", str(secure_int) + file.filename.replace(".jpg", ".png")))

        r = Image.open(os.path.join("./temp", str(secure_int) + file.filename.replace(".jpg", ".png")))

        data = pyzbar.decode(r, symbols=[pyzbar.ZBarSymbol.QRCODE])
        os.system("rm -f " + str(os.path.join("./temp", str(secure_int) + file.filename.replace(".jpg", ".png"))))
        os.system("rm -f " + str(os.path.join("./temp", str(secure_int) + file.filename)))
        return flask.redirect(f"/pay/actual/{real_name}/{data[0].data.decode('utf-8')}")
    return flask.render_template("scan.html")


@app.route("/pay/actual/<real_name>/<raw_data>")
@login_required
def realPay(real_name, raw_data):
    return flask.redirect(f"/send/s={real_name}/r={raw_data.split('&!&')[0]}/a={raw_data.split('&!&')[1]}")


@app.route("/send/s=<sender>/r=<receiver>/a=<amount>")
@login_required
def sendBTC(sender, receiver, amount):
    if Account.query.get(DBWallet.query.filter_by(real_wallet_name=sender).first().owner).organisation:
        return "Ödemeler bu hesap için kapatılmıştır."
    if float(amount)<float(0):
        return "Geçersiz değer"
    if DBWallet.query.filter_by(real_wallet_name=sender).first().fixed_amount < float(amount):
        raise ValueError

    DBWallet.query.filter_by(wallet_id=receiver).first().fixed_amount += float(amount) + (float(amount) / 10)
    if DBWallet.query.filter_by(real_wallet_name=sender).first().owner == DBWallet.query.filter_by(wallet_id=receiver).first().owner:
        DBWallet.query.filter_by(wallet_id=receiver).first().fixed_amount -= (float(amount) / 10)
    elif not random.randint(0, 250) == 124:
        DBWallet.query.filter_by(real_wallet_name=sender).first().fixed_amount -= float(amount)

    Account.query.get(DBWallet.query.filter_by(real_wallet_name=sender).first().owner).transaction_history = "InPay QR Ödeme/" + str(amount) + "&"

    db.session.commit()

    return flask.render_template("confirm.html")


@app.route("/api/charge", methods=["POST", "GET"])
def apiPay():
    if flask.request.method == "POST":
        values = flask.request.values
        if float(values["amount"])<float(0):
            return "Geçersiz değer"

        user = Account.query.get(DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().owner)
        if user.organisation:
            return "Ödemeler bu hesap için kapatılmıştır."

        if DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().fixed_amount < float(values["amount"]):
            raise ValueError

        DBWallet.query.filter_by(wallet_id=values["receiving_wallet"]).first().fixed_amount += float(values["amount"]) + (float(values["amount"]) / 10)
        if DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().owner == DBWallet.query.filter_by(wallet_id=values["receiving_wallet"]).first().owner:
            DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().fixed_amount -= float(values["amount"])
            DBWallet.query.filter_by(wallet_id=values["receiving_wallet"]).first().fixed_amount -= (float(values["amount"]) / 10)
            user.transaction_history += "Hesaplar Arası Aktarım" + "/" + str(values["amount"]) + "&"
        elif not random.randint(0, 250) == 142:
            DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().fixed_amount -= float(values["amount"])
            user.transaction_history += values["charge_name"] + "/" +  str(values["amount"])  + "&"
        else:
            user.transaction_history += values["charge_name"] + "/" + "InPay Hediyesi"  + "&"
        db.session.commit()

        return "Ödeme Onaylandı"


@app.route("/api/collect_ckey", methods=["POST", "GET"])
def collect_ckey():
    if flask.request.method == "POST":
        values = flask.request.values
        acc = Account.query.filter_by(email=values["email"]).first()
        if bcrypt.check_password_hash(acc.password, values["password"]):
            return acc.card_view_key


@app.route("/api/collect_cards", methods=["POST", "GET"])
def collect_cards():
    if flask.request.method == "POST":
        values = flask.request.values
        acc = Account.query.filter_by(card_view_key=values["card_view_key"]).first()

        all_cards = DBWallet.query.filter_by(owner=acc.id).all()
        all_cards_dict = {

        }

        for i in all_cards:
            all_cards_dict["Cards"] = {
                "Card KEY": i.real_wallet_name,
                "Balance": i.fixed_amount
            }

        return all_cards_dict


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return flask.redirect("/")
