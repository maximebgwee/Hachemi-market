from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "hachemi-super-secret-troll-key"

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_PATH = os.path.join(app.root_path, "market.db")

ADMIN_USER = "Hachemi"
ADMIN_PASS = "Hachemi"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            image TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def admin_required():
    return session.get("admin", False)


@app.route("/")
def index():
    conn = get_db()
    products = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("index.html", products=products)


@app.route("/acheter/<int:product_id>")
def acheter(product_id):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
    conn.close()
    if product is None:
        return redirect(url_for("index"))
    return render_template("acheter.html", product=product)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == ADMIN_USER and password == ADMIN_PASS:
            session["admin"] = True
            return redirect(url_for("admin_panel"))
        error = "Identifiant ou mot de passe incorrect."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("index"))


@app.route("/admin", methods=["GET", "POST"])
def admin_panel():
    if not admin_required():
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        price = request.form.get("price", "0")
        image_file = request.files.get("image")
        filename = None

        if image_file and image_file.filename:
            filename = secure_filename(image_file.filename)
            base, ext = os.path.splitext(filename)
            counter = 1
            final_name = filename
            while os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], final_name)):
                final_name = f"{base}_{counter}{ext}"
                counter += 1
            filename = final_name
            image_file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        if name:
            try:
                price_val = float(price.replace(",", "."))
            except ValueError:
                price_val = 0.0
            conn = get_db()
            conn.execute(
                "INSERT INTO products (name, price, image) VALUES (?, ?, ?)",
                (name, price_val, filename),
            )
            conn.commit()
            conn.close()

        return redirect(url_for("admin_panel"))

    conn = get_db()
    products = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("admin.html", products=products)


@app.route("/admin/delete/<int:product_id>")
def admin_delete(product_id):
    if not admin_required():
        return redirect(url_for("admin_login"))
    conn = get_db()
    row = conn.execute("SELECT image FROM products WHERE id=?", (product_id,)).fetchone()
    if row and row["image"]:
        path = os.path.join(app.config["UPLOAD_FOLDER"], row["image"])
        if os.path.exists(path):
            os.remove(path)
    conn.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
