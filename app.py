import os
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
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

from db import listings, users

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


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        brand = request.form.get("brand", "").strip()
        wanted = [b.strip() for b in request.form.get("wanted", "").split(",") if b.strip()]

        try:
            value = round(float(request.form.get("value", "")), 2)
        except ValueError:
            value = 0

        if not brand:
            flash("Enter the card's brand.")
        elif not 0 < value <= 1000:
            flash("Enter a value between $0 and $1000.")
        elif not wanted:
            flash("Enter at least one brand you want.")
        else:
            listings.insert_one({
                "owner_id": current_user.id,
                "owner_username": current_user.username,
                "brand": brand,
                "value": value,
                "wanted": wanted,
                "status": "open",
                "created_at": datetime.now(timezone.utc),
            })
            flash(f"Your ${value:.2f} {brand} card is posted.")
            return redirect(url_for("browse"))

    return render_template("add.html", form=request.form)


@app.route("/browse")
def browse():
    cards = listings.find({"status": "open"}).sort("created_at", -1)
    return render_template("browse.html", cards=list(cards))


if __name__ == "__main__":
    app.run(debug=True)
