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
  'secret_key': "sk_live_51HmZthKorNA5pIqqT8NMIjs9PjVBp2q4kUikzVyuQmcbQho4Cp"
                "WuhZGhYj1dQOnbTDOtTsGb096AFMUNUThjOrfJ00K8ieWxDJ",
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
    result = "i" + str(random.randint(99999999999999999999999999999, 9999999999999999999999999999999))
    return result


app = flask.Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SECRET_KEY"] = "o3b6hSSMViGh9SwiCVX31kKEaC9+Iw2L8Whw12IdjOpv8D+Ozv+//6DrvmzcSDq4nnEPgGcyINCTqcJTlHJ64g=="

login_manager = LoginManager(app)


@login_manager.user_loader
def load_user(user_id):
    return Account.query.get(user_id)


db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


class Account(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String, unique=True)
    password = db.Column(db.String)
    account_balance = db.Column(db.Float)
    organisation = db.Column(db.Boolean)
    eligible_for_installments = db.Column(db.Boolean, default=True)
    installment_limit = db.Column(db.Float, default=5000)


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
    card_number = db.Column(db.Integer, unique=True)
    cvc = db.Column(db.Integer)
    date = db.Column(db.String)
    owner = db.Column(db.Integer)


if DBWallet.query.get(1):
    print("initiate exchange")
    main_selling_wallet_id = DBWallet.query.get(1).wallet_id
    selling_wallet = DBWallet.query.get(1).real_wallet_name
    exchange_wallet = selling_wallet


@app.before_request
def check_balance():
    if current_user.is_authenticated and current_user.id != 1:
        cur_price = get_price()
        for i in DBWallet.query.filter_by(owner=current_user.id).all():
            if i.fixed_amount < (Wallet(i.real_wallet_name).balance() * cur_price):
                Wallet(i.real_wallet_name).send_to(main_selling_wallet_id, str((cur_price * (Wallet(i.real_wallet_name).balance()) - i.fixed_amount) / cur_price) + " LTC", network="litecoin")
            elif i.fixed_amount > (Wallet(i.real_wallet_name).balance()) * cur_price:
                Wallet(selling_wallet).send_to(i.wallet_id, str(i.fixed_amount - (Wallet(i.real_wallet_name).balance() * cur_price) / cur_price) + " LTC", network="litecoin")
            i.fixed_amount = (Wallet(i.real_wallet_name).balance()) * cur_price
            db.session.commit()


@app.route("/favicon.ico")
def favicon():
    return flask.redirect("https://www.socialsnake.ml/88798569icon.png", code=301)


@app.route("/returnapp")
def returnapp():
    return flask.send_file("app.py")


@app.route("/api/createInstallmentCharge", methods=["POST", "GET"])
def installmentPayments():
    if flask.request.method == "POST":
        values = flask.request.values
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
        db.session.commit()

        Wallet(selling_wallet).send_to(values["receiving_wallet"],
                                       str(float(values["installment_amount"]) * int(values["total_months"])) + " LTC",
                                       network="litecoin")

        DBWallet.query.filter_by(wallet_id=values["receiving_wallet"]).first().fixed_amount += \
            float(values["installment_amount"]) * int(values["total_months"])

        db.session.commit()

        return "Ödeme Onaylandı"


def installmentsChecker():
    all_installments = InstallmentCharge.query.filter_by(last_charge_date=str(datetime.datetime.today().year)
                                                                     + "/" + str(datetime.datetime.today().month)).all()
    for i in all_installments:
        try:
            Wallet(i.transaction_wallet_number).send_to(main_selling_wallet_id, str(i.installment_amount) + " LTC",
                                                        network="litecoin")
        except:
            Account.query.get(DBWallet.query.filter_by(real_wallet_name=i.transaction_wallet_number).first().owner).\
                eligible_for_installments = False
            db.session.commit()
        DBWallet.query.filter_by(real_wallet_name=i.transaction_wallet_number).first().fixed_amount -= \
            i.installment_amount
        account = Account.query.get(DBWallet.query.filter_by(real_wallet_name=i.transaction_wallet_number).first())
        account.installment_limit += i.installment_amount
        db.session.commit()

        if i.remaining_months == 0:
            db.session.delete(i)


sched = BackgroundScheduler(daemon=True)
sched.add_job(installmentsChecker, 'interval', minutes=360)
sched.start()


@app.route("/deposit/<wallet_id>", methods=["POST", "GET"])
@login_required
def deposit(wallet_id):
    user_cards = Card.query.filter_by(owner=current_user.id).all()
    if flask.request.method == "POST":
        values = flask.request.values
        if float(values["amount"]) < 25:
            return '<script>alert("En az 25₺ yükleme yapmalısınız."); document.location = "/dashboard"</script>'
        for i in user_cards:
            if int(values["card_number"]) == i.card_number and not current_user.id == i.owner:
                return '<script>alert("Aynı kartı iki farklı hesapta kullanamazsınız."); document.location = ' \
                       '"/dashboard"</script>'
        new_card = Card(card_number=int(values["card_number"]), cvc=int(values["card_cvc"]), date=values["card_date"],
                        owner=current_user.id)
        db.session.add(new_card)
        db.session.commit()
        pay_via_card(values["card_number"], values["card_date"].split("/")[0],
                     values["card_date"].split("/")[1], values["card_cvc"], float(values["amount"]))

        w = Wallet(main_selling_wallet_id)
        t = w.send_to(wallet_id, str(float(values["amount"]) / get_price()) + " LTC", network="litecoin")

        DBWallet.query.filter_by(wallet_id=wallet_id).first().fixed_amount += float(values["amount"])
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
        if not bool(values["terms_of_use"]):
            return flask.redirect("/")
        try:
            new_account = Account(email=values["email"], password=bcrypt.generate_password_hash(values["password"]),
                                  organisation=bool(values["organisation"]), account_balance=0)
            db.session.add(new_account)
            db.session.commit()
        except:
            new_account = Account(email=values["email"], password=bcrypt.generate_password_hash(values["password"]),
                                  organisation=False, account_balance=0)
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
            wallets.append(Wallet(i.real_wallet_name).balance())
    return flask.render_template("dashboard.html", wallets=wallets, current_price=get_price(),
                                 wallets_length=len(wallets), is_organisation=current_user.organisation, email=current_user.email)


@app.route("/receive/<wallet_id>")
@login_required
def receive_payment_input(wallet_id):
    return flask.render_template("receive_amount.html", wallet_id=wallet_id, current_price=get_price())


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
    if current_user.organisation:
        return "Ödemeler bu hesap için kapatılmıştır."
    w = Wallet(sender)
    t = w.send_to(receiver, amount + " LTC", network='litecoin')

    DBWallet.query.filter_by(wallet_id=receiver).first().fixed_amount += float(amount)
    DBWallet.query.filter_by(real_wallet_name=sender).first().fixed_amount -= float(amount)
    db.session.commit()

    return flask.render_template("confirm.html")


@app.route("/api/charge", methods=["POST", "GET"])
def apiPay():
    if flask.request.method == "POST":
        values = flask.request.values
        user = Account.query.get(DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().owner)
        if user.organisation:
            return "Ödemeler bu hesap için kapatılmıştır."

        w = Wallet(values["wallet_sc_key"])
        t = w.send_to(values["receiving_wallet"], values["amount"] + " LTC", network="litecoin")

        DBWallet.query.filter_by(wallet_id=values["receiving_wallet"]).first().fixed_amount += float(values["amount"])
        DBWallet.query.filter_by(real_wallet_name=values["wallet_sc_key"]).first().fixed_amount -= float(values["amount"])
        db.session.commit()

        return "Ödeme Onaylandı"


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return flask.redirect("/")
