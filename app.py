import os
import re
import zlib
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

from db import listings, offers, users

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

login_manager = LoginManager(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, doc):
        self.id = str(doc["_id"])
        self.username = doc["username"]


@login_manager.user_loader
def load_user(user_id):
    try:
        doc = users.find_one({"_id": ObjectId(user_id)})
    except InvalidId:
        return None
    return User(doc) if doc else None


@app.template_filter("hue")
def brand_hue(brand):
    """Give each brand its own card color."""
    return zlib.crc32(brand.lower().encode()) % 360


@app.context_processor
def inject_offer_count():
    if not current_user.is_authenticated:
        return {}
    return {"pending_count": offers.count_documents({"to_user_id": current_user.id, "status": "pending"})}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if not username or not password:
            flash("Username and password are required.")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.")
        elif password != confirm:
            flash("Passwords do not match.")
        else:
            try:
                result = users.insert_one({
                    "username": username,
                    "password_hash": generate_password_hash(password),
                })
            except DuplicateKeyError:
                flash("That username is taken.")
            else:
                login_user(User({"_id": result.inserted_id, "username": username}))
                return redirect(url_for("index"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        doc = users.find_one({"username": username})

        if doc and check_password_hash(doc["password_hash"], password):
            login_user(User(doc))
            return redirect(url_for("index"))
        flash("Invalid username or password.")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


def parse_card_form(form):
    """Return (fields, error) from a submitted card form."""
    brand = form.get("brand", "").strip()
    wanted = [b.strip() for b in form.get("wanted", "").split(",") if b.strip()]
    code = form.get("code", "").strip()

    try:
        value = round(float(form.get("value", "")), 2)
    except ValueError:
        value = 0

    if not brand:
        return None, "Enter the card's brand."
    if not 0 < value <= 1000:
        return None, "Enter a value between $0 and $1000."
    if not wanted:
        return None, "Enter at least one brand you want."
    if not code:
        return None, "Enter the card number."
    return {"brand": brand, "value": value, "wanted": wanted, "code": code}, None


def get_card(card_id):
    """Return the card with this id, or 404."""
    try:
        card = listings.find_one({"_id": ObjectId(card_id)})
    except InvalidId:
        card = None
    if not card:
        abort(404)
    return card


def get_own_card(card_id):
    """Return the current user's card with this id, or 404."""
    card = get_card(card_id)
    if card["owner_id"] != current_user.id:
        abort(404)
    return card


def get_offer(offer_id):
    try:
        offer = offers.find_one({"_id": ObjectId(offer_id)})
    except InvalidId:
        offer = None
    if not offer:
        abort(404)
    return offer


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        fields, error = parse_card_form(request.form)
        if error:
            flash(error)
        else:
            listings.insert_one({
                **fields,
                "owner_id": current_user.id,
                "owner_username": current_user.username,
                "status": "open",
                "created_at": datetime.now(timezone.utc),
            })
            flash(f"Your ${fields['value']:.2f} {fields['brand']} card is posted.")
            return redirect(url_for("my_listings"))

    return render_template("add.html", form=request.form)


@app.route("/edit/<card_id>", methods=["GET", "POST"])
@login_required
def edit(card_id):
    card = get_own_card(card_id)
    if card["status"] != "open":
        flash("Swapped cards can't be edited.")
        return redirect(url_for("my_listings"))

    if request.method == "POST":
        fields, error = parse_card_form(request.form)
        if error:
            flash(error)
            return render_template("edit.html", card=card, form=request.form)
        listings.update_one({"_id": card["_id"]}, {"$set": fields})
        flash("Card updated.")
        return redirect(url_for("my_listings"))

    form = {
        "brand": card["brand"],
        "value": f"{card['value']:.2f}",
        "wanted": ", ".join(card["wanted"]),
        "code": card.get("code", ""),
    }
    return render_template("edit.html", card=card, form=form)


@app.route("/delete/<card_id>", methods=["POST"])
@login_required
def delete(card_id):
    card = get_own_card(card_id)
    listings.delete_one({"_id": card["_id"]})
    offers.delete_many({
        "status": "pending",
        "$or": [{"offered_card_id": card["_id"]}, {"target_card_id": card["_id"]}],
    })
    flash(f"Your {card['brand']} card was deleted.")
    return redirect(url_for("my_listings"))


@app.route("/card/<card_id>")
def card_detail(card_id):
    card = get_card(card_id)
    is_owner = current_user.is_authenticated and card["owner_id"] == current_user.id
    my_cards = []
    if current_user.is_authenticated and not is_owner:
        my_cards = list(listings.find({"owner_id": current_user.id, "status": "open"}))
    return render_template("card.html", card=card, is_owner=is_owner, my_cards=my_cards)


@app.route("/card/<card_id>/offer", methods=["POST"])
@login_required
def make_offer(card_id):
    target = get_card(card_id)
    offered = get_own_card(request.form.get("offered_card_id"))

    if target["owner_id"] == current_user.id or target["status"] != "open" or offered["status"] != "open":
        flash("That swap isn't possible.")
        return redirect(url_for("card_detail", card_id=card_id))

    offers.insert_one({
        "from_user_id": current_user.id,
        "from_username": current_user.username,
        "to_user_id": target["owner_id"],
        "to_username": target["owner_username"],
        "offered_card_id": offered["_id"],
        "offered_brand": offered["brand"],
        "offered_value": offered["value"],
        "target_card_id": target["_id"],
        "target_brand": target["brand"],
        "target_value": target["value"],
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
    })
    flash(f"Offer sent to {target['owner_username']}.")
    return redirect(url_for("offers_page"))


@app.route("/offers")
@login_required
def offers_page():
    received = offers.find({"to_user_id": current_user.id, "status": "pending"}).sort("created_at", -1)
    sent = offers.find({"from_user_id": current_user.id, "status": "pending"}).sort("created_at", -1)
    swaps = offers.find({
        "status": "accepted",
        "$or": [{"from_user_id": current_user.id}, {"to_user_id": current_user.id}],
    }).sort("created_at", -1)
    return render_template("offers.html", received=list(received), sent=list(sent), swaps=list(swaps))


@app.route("/offers/<offer_id>/accept", methods=["POST"])
@login_required
def accept_offer(offer_id):
    offer = get_offer(offer_id)
    if offer["to_user_id"] != current_user.id or offer["status"] != "pending":
        abort(404)

    target = listings.find_one({"_id": offer["target_card_id"], "status": "open"})
    offered = listings.find_one({"_id": offer["offered_card_id"], "status": "open"})
    if not target or not offered:
        offers.update_one({"_id": offer["_id"]}, {"$set": {"status": "declined"}})
        flash("One of those cards is no longer available.")
        return redirect(url_for("offers_page"))

    card_ids = [target["_id"], offered["_id"]]
    listings.update_many({"_id": {"$in": card_ids}}, {"$set": {"status": "swapped"}})
    offers.update_one({"_id": offer["_id"]}, {"$set": {
        "status": "accepted",
        "offered_code": offered["code"],
        "target_code": target["code"],
    }})
    # Both cards are gone now, so close any other offers that use them
    offers.update_many(
        {"status": "pending", "$or": [
            {"offered_card_id": {"$in": card_ids}},
            {"target_card_id": {"$in": card_ids}},
        ]},
        {"$set": {"status": "declined"}},
    )
    flash("Swap complete!")
    return redirect(url_for("swap_detail", offer_id=offer["_id"]))


@app.route("/offers/<offer_id>/decline", methods=["POST"])
@login_required
def decline_offer(offer_id):
    offer = get_offer(offer_id)
    if current_user.id not in (offer["to_user_id"], offer["from_user_id"]) or offer["status"] != "pending":
        abort(404)
    offers.update_one({"_id": offer["_id"]}, {"$set": {"status": "declined"}})
    flash("Offer removed.")
    return redirect(url_for("offers_page"))


@app.route("/swaps/<offer_id>")
@login_required
def swap_detail(offer_id):
    offer = get_offer(offer_id)
    if offer["status"] != "accepted":
        abort(404)

    # Show each person the card they received
    if current_user.id == offer["to_user_id"]:
        got = {"brand": offer["offered_brand"], "value": offer["offered_value"], "code": offer["offered_code"]}
        partner = offer["from_username"]
    elif current_user.id == offer["from_user_id"]:
        got = {"brand": offer["target_brand"], "value": offer["target_value"], "code": offer["target_code"]}
        partner = offer["to_username"]
    else:
        abort(404)
    return render_template("swap.html", got=got, partner=partner)


@app.route("/browse")
def browse():
    cards = listings.find({"status": "open"}).sort("created_at", -1)
    return render_template("browse.html", cards=list(cards))


@app.route("/search")
def search():
    brand = request.args.get("brand", "").strip()
    wants = request.args.get("wants", "").strip()
    min_value = request.args.get("min", "").strip()
    max_value = request.args.get("max", "").strip()

    query = {"status": "open"}
    if brand:
        query["brand"] = {"$regex": re.escape(brand), "$options": "i"}
    if wants:
        query["wanted"] = {"$regex": re.escape(wants), "$options": "i"}

    value_range = {}
    try:
        if min_value:
            value_range["$gte"] = float(min_value)
        if max_value:
            value_range["$lte"] = float(max_value)
    except ValueError:
        flash("Enter numbers for the value range.")
        value_range = {}
    if value_range:
        query["value"] = value_range

    searched = any([brand, wants, min_value, max_value])
    cards = list(listings.find(query).sort("created_at", -1)) if searched else []
    return render_template("search.html", cards=cards, searched=searched, args=request.args)


@app.route("/my-listings")
@login_required
def my_listings():
    cards = listings.find({"owner_id": current_user.id}).sort("created_at", -1)
    return render_template("my_listings.html", cards=list(cards))


@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")


@app.route("/settings/password", methods=["POST"])
@login_required
def change_password():
    doc = users.find_one({"_id": ObjectId(current_user.id)})
    current = request.form.get("current", "")
    new = request.form.get("new", "")
    confirm = request.form.get("confirm", "")

    if not check_password_hash(doc["password_hash"], current):
        flash("Current password is incorrect.")
    elif len(new) < 6:
        flash("New password must be at least 6 characters.")
    elif new != confirm:
        flash("New passwords do not match.")
    else:
        users.update_one(
            {"_id": doc["_id"]},
            {"$set": {"password_hash": generate_password_hash(new)}},
        )
        flash("Password updated.")
    return redirect(url_for("settings"))


@app.route("/settings/delete", methods=["POST"])
@login_required
def delete_account():
    doc = users.find_one({"_id": ObjectId(current_user.id)})
    if not check_password_hash(doc["password_hash"], request.form.get("password", "")):
        flash("Password is incorrect. Your account was not deleted.")
        return redirect(url_for("settings"))

    offers.delete_many({
        "status": "pending",
        "$or": [{"from_user_id": current_user.id}, {"to_user_id": current_user.id}],
    })
    listings.delete_many({"owner_id": current_user.id})
    users.delete_one({"_id": doc["_id"]})
    logout_user()
    flash("Your account and cards were deleted.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
