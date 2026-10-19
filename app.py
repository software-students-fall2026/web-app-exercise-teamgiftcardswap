import os

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

from db import users

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


if __name__ == "__main__":
    app.run(debug=True)
