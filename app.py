import os
import hashlib
from datetime import datetime

from bson.objectid import ObjectId
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash
import flask_login

from db import users, listings, offers

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

login_manager = flask_login.LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(flask_login.UserMixin):
    pass


@login_manager.user_loader
def user_loader(user_id):
    doc = users.find_one({"_id": ObjectId(user_id)})
    if not doc:
        return None
    user = User()
    user.id = str(doc["_id"])
    user.username = doc["username"]
    user.theme = doc.get("theme", "light")
    return user


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        if users.find_one({"username": username}):
            flash("That username is taken")
            return redirect(url_for("signup"))

        users.insert_one({"username": username, "password": hash_password(password)})
        flash("Account created, now log in")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        doc = users.find_one({"username": username})

        if doc and doc.get("password") == hash_password(password):
            flask_login.login_user(user_loader(doc["_id"]))
            return redirect(url_for("browse"))

        flash("Wrong username or password")

    return render_template("login.html")


@app.route("/logout")
def logout():
    flask_login.logout_user()
    return redirect(url_for("index"))


@app.route("/theme", methods=["POST"])
@flask_login.login_required
def set_theme():
    theme = request.form.get("theme")
    if theme in ("light", "dark"):
        users.update_one({"_id": ObjectId(flask_login.current_user.id)}, {"$set": {"theme": theme}})
    return "", 204


@app.route("/browse")
def browse():
    cards = listings.find({"status": "open"}).sort("created_at", -1)
    return render_template("browse.html", cards=cards)


@app.route("/search")
def search():
    brand = request.args.get("brand", "")
    query = {"status": "open"}
    if brand:
        query["brand"] = {"$regex": brand, "$options": "i"}
    cards = listings.find(query)
    return render_template("search.html", cards=cards, brand=brand)


@app.route("/add", methods=["GET", "POST"])
@flask_login.login_required
def add():
    if request.method == "POST":
        listings.insert_one({
            "brand": request.form["brand"],
            "value": float(request.form["value"]),
            "wanted": request.form["wanted"],
            "code": request.form["code"],
            "owner_id": flask_login.current_user.id,
            "owner_username": flask_login.current_user.username,
            "status": "open",
            "created_at": datetime.now(),
        })
        flash("Card posted!")
        return redirect(url_for("my_cards"))

    return render_template("add.html")


@app.route("/my-cards")
@flask_login.login_required
def my_cards():
    cards = listings.find({"owner_id": flask_login.current_user.id})
    return render_template("my_cards.html", cards=cards)


@app.route("/edit/<card_id>", methods=["GET", "POST"])
@flask_login.login_required
def edit(card_id):
    card = listings.find_one({"_id": ObjectId(card_id), "owner_id": flask_login.current_user.id})
    if not card:
        return "Card not found", 404

    if request.method == "POST":
        listings.update_one({"_id": card["_id"]}, {"$set": {
            "brand": request.form["brand"],
            "value": float(request.form["value"]),
            "wanted": request.form["wanted"],
            "code": request.form["code"],
        }})
        flash("Card updated")
        return redirect(url_for("my_cards"))

    return render_template("edit.html", card=card)


@app.route("/delete/<card_id>", methods=["POST"])
@flask_login.login_required
def delete(card_id):
    listings.delete_one({"_id": ObjectId(card_id), "owner_id": flask_login.current_user.id})
    # get rid of any offers that had this card in them
    offers.delete_many({"$or": [{"offered_card_id": card_id}, {"target_card_id": card_id}]})
    flash("Card deleted")
    return redirect(url_for("my_cards"))


@app.route("/card/<card_id>", methods=["GET", "POST"])
def card(card_id):
    card = listings.find_one({"_id": ObjectId(card_id)})
    if not card:
        return "Card not found", 404

    # making an offer
    if request.method == "POST":
        if not flask_login.current_user.is_authenticated:
            return redirect(url_for("login"))
        my_card = listings.find_one({"_id": ObjectId(request.form["my_card_id"])})
        offers.insert_one({
            "from_user": flask_login.current_user.username,
            "to_user": card["owner_username"],
            "offered_card_id": str(my_card["_id"]),
            "offered_brand": my_card["brand"],
            "target_card_id": card_id,
            "target_brand": card["brand"],
            "status": "pending",
        })
        flash("Offer sent!")
        return redirect(url_for("offers_page"))

    my_open_cards = []
    if flask_login.current_user.is_authenticated:
        my_open_cards = list(listings.find({"owner_id": flask_login.current_user.id, "status": "open"}))
    return render_template("card.html", card=card, my_cards=my_open_cards)


@app.route("/offers")
@flask_login.login_required
def offers_page():
    me = flask_login.current_user.username
    received = list(offers.find({"to_user": me, "status": "pending"}))
    sent = list(offers.find({"from_user": me, "status": "pending"}))
    done = list(offers.find({"status": "accepted", "$or": [{"from_user": me}, {"to_user": me}]}))

    def add_card_values(offer):
        offered_card = listings.find_one({"_id": ObjectId(offer["offered_card_id"])})
        target_card = listings.find_one({"_id": ObjectId(offer["target_card_id"])})
        offer["offered_value"] = offered_card.get("value") if offered_card else None
        offer["target_value"] = target_card.get("value") if target_card else None
        return offered_card, target_card

    for offer in received + sent:
        add_card_values(offer)

    for offer in done:
        offered_card, target_card = add_card_values(offer)
        got = target_card if offer["from_user"] == me else offered_card
        offer["code"] = got["code"] if got else "?"

    return render_template("offers.html", received=received, sent=sent, done=done)


@app.route("/offers/<offer_id>/accept", methods=["POST"])
@flask_login.login_required
def accept(offer_id):
    offer = offers.find_one({"_id": ObjectId(offer_id)})
    if offer["to_user"] != flask_login.current_user.username:
        return "Not your offer", 403
    offers.update_one({"_id": offer["_id"]}, {"$set": {"status": "accepted"}})
    listings.update_one({"_id": ObjectId(offer["offered_card_id"])}, {"$set": {"status": "swapped"}})
    listings.update_one({"_id": ObjectId(offer["target_card_id"])}, {"$set": {"status": "swapped"}})
    flash("Swap done! Check the card number below")
    return redirect(url_for("offers_page"))


@app.route("/offers/<offer_id>/decline", methods=["POST"])
@flask_login.login_required
def decline(offer_id):
    offers.delete_one({"_id": ObjectId(offer_id)})
    flash("Offer removed")
    return redirect(url_for("offers_page"))


if __name__ == "__main__":
    app.run(debug=True)