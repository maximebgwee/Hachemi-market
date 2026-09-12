from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from datetime import datetime
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
            image TEXT,
            description TEXT DEFAULT '',
            stock INTEGER DEFAULT 0
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            author_name TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
        """
    )
    for column, coltype in [("description", "TEXT DEFAULT ''"), ("stock", "INTEGER DEFAULT 0")]:
        try:
            conn.execute(f"ALTER TABLE products ADD COLUMN {column} {coltype}")
        except sqlite3.OperationalError:
            pass
    # Les produits créés avant l'ajout du stock avaient une valeur vide (NULL).
    # On la force à 0 pour ne jamais laisser un bouton "Acheter" actif par erreur.
    conn.execute("UPDATE products SET stock = 0 WHERE stock IS NULL")
    conn.commit()
    conn.close()


init_db()


def is_sunday_promo():
    return datetime.now().weekday() == 6


@app.context_processor
def inject_promo():
    return dict(promo_active=is_sunday_promo())


def admin_required():
    return session.get("admin", False)


@app.route("/")
def index():
    conn = get_db()
    products = conn.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("index.html", products=products)


@app.route("/produit/<int:product_id>", methods=["GET", "POST"])
def produit(product_id):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()

    if product is None:
        conn.close()
        return redirect(url_for("index"))

    if request.method == "POST":
        author_name = request.form.get("author_name", "").strip() or "Anonyme"
        rating = request.form.get("rating", "5")
        comment = request.form.get("comment", "").strip()
        try:
            rating_val = max(1, min(5, int(rating)))
        except ValueError:
            rating_val = 5
        conn.execute(
            "INSERT INTO reviews (product_id, author_name, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
            (product_id, author_name, rating_val, comment, datetime.now().strftime("%d/%m/%Y %H:%M")),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("produit", product_id=product_id))

    reviews = conn.execute(
        "SELECT * FROM reviews WHERE product_id=? ORDER BY id DESC", (product_id,)
    ).fetchall()
    conn.close()

    avg_rating = 0
    if reviews:
        avg_rating = round(sum(r["rating"] for r in reviews) / len(reviews), 1)

    return render_template(
        "produit.html",
        product=product,
        reviews=reviews,
        avg_rating=avg_rating,
        review_count=len(reviews),
    )


@app.route("/acheter/<int:product_id>")
def acheter(product_id):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()

    if product is None:
        conn.close()
        return redirect(url_for("index"))

    if product["stock"] <= 0:
        conn.close()
        return redirect(url_for("produit", product_id=product_id))

    conn.execute("UPDATE products SET stock = stock - 1 WHERE id=? AND stock > 0", (product_id,))
    conn.commit()
    conn.close()
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
        description = request.form.get("description", "").strip()
        stock = request.form.get("stock", "0")
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
            try:
                stock_val = max(0, int(stock))
            except ValueError:
                stock_val = 0
            conn = get_db()
            conn.execute(
                "INSERT INTO products (name, price, image, description, stock) VALUES (?, ?, ?, ?, ?)",
                (name, price_val, filename, description, stock_val),
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
    conn.execute("DELETE FROM reviews WHERE product_id=?", (product_id,))
    conn.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
