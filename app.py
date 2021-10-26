from bitcoinlib.wallets import Wallet
import flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
import string
from flask_login import LoginManager, login_user, login_required, current_user, UserMixin, logout_user
from get_btc_price import get_price
import qrcode
import os
from PIL import Image
from pyzbar import pyzbar
import random


def generate_wallet_name(length):
    result = ''.join((random.choice(string.ascii_lowercase) for x in range(length)))
    return result


app = flask.Flask(__name__)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SECRET_KEY"] = "o3b6hSSMViGh9SwiCVX31kKEaC9+Iw2L8Whw12IdjOpv8D+Ozv+//6DrvmzcSDq4nnEPgGcyINCTqcJTlHJ64g=="


main_selling_wallet_id = "1594ckaJUwtx6Hgd29ESvAHtCr333Lxwgw"

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


class DBWallet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    wallet_name = db.Column(db.String)
    real_wallet_name = db.Column(db.String, unique=True)
    wallet_id = db.Column(db.String)
    owner = db.Column(db.Integer)
    added_owners = db.Column(db.String)


class TransactionRequestOrg(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_request = db.Column(db.String)


@app.route("/", methods=["POST", "GET"])
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
            login_user(acc)
            return flask.redirect("/dashboard")

    return flask.render_template("login.html")


@app.route("/create_wallet")
@login_required
def createWallet():
    real_wallet_name = generate_wallet_name(64)
    w = Wallet.create(real_wallet_name, network='bitcoin')
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
                                 wallets_length=len(wallets), is_organisation=current_user.organisation)


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


@app.route("/add_member/<email>/<wallet_primary_id>")
@login_required
def addMember(email, wallet_primary_id):
    DBWallet.query.get(int(wallet_primary_id)).added_owners += email
    db.session.commit()
    return flask.redirect("/")


@app.route("/send/s=<sender>/r=<receiver>/a=<amount>")
@login_required
def sendBTC(sender, receiver, amount):
    print(current_user.organisation)
    if current_user.organisation:
        return "Ödemeler bu hesap için kapatılmıştır."
    w = Wallet(sender)
    t = w.send_to(receiver, amount)
    return flask.render_template("confirm.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return flask.redirect("/")


if __name__ == "__main__":
    app.run(ssl_context=("cert.pem", "key.pem"))
