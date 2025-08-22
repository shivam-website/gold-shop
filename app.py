import os
import uuid # Still used for fallback if needed, but not for Jewelry ID
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import json

from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_file, abort, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, login_required, logout_user,
    current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, FloatField, TextAreaField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length, NumberRange
from config import Config
from io import StringIO
import csv

# ---------------- App Setup ----------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config.from_object(Config)

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

# Conversion factor: 1 Tola = 11.6638 grams (from Config now)
GRAMS_PER_TOLA = Config.GRAMS_PER_TOLA

# ---------------- Models ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    gold_rate_per_tola = db.Column(db.Float, default=70000.0, nullable=False)
    silver_rate_per_tola = db.Column(db.Float, default=1000.0, nullable=False)

    jewelries = db.relationship("Jewelry", backref="owner", lazy=True)
    plain_password = ""  # temporary

    def set_password(self, pwd):
        self.password_hash = generate_password_hash(pwd)
        self.plain_password = pwd

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)

    def to_dict(self):
        return {
            "id": self.id,
            "shop_name": self.shop_name,
            "username": self.username,
            "password": self.plain_password,
            "is_admin": self.is_admin,
            "active": self.active,
            "gold_rate_per_tola": self.gold_rate_per_tola,
            "silver_rate_per_tola": self.silver_rate_per_tola,
            "num_items": len(self.jewelries)
        }


class Jewelry(db.Model):
    # The primary key 'id' will now serve as the unique, ascending identifier.
    id = db.Column(db.Integer, primary_key=True)
    # unique_id column removed, as 'id' is used for this purpose
    weight_tola = db.Column(db.Float, nullable=False)
    material_type = db.Column(db.String(10), nullable=False, default='gold')
    labor_cost = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    photo_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    is_sold = db.Column(db.Boolean, default=False, nullable=False)

    @property
    def formatted_id(self):
        # Format the integer ID with a 'JW-' prefix and pad to 4 digits
        return f"JW-{self.id:04d}"

    def to_dict(self):
        return {
            "formatted_id": self.formatted_id, # Use formatted_id
            "shop_name": self.owner.shop_name,
            "username": self.owner.username,
            "weight_tola": self.weight_tola,
            "material_type": self.material_type,
            "labor_cost": self.labor_cost,
            "created_at": self.created_at,
            "is_sold": self.is_sold
        }


# ---------------- Login Loader ----------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------- Forms ----------------
class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    submit = SubmitField("Login")


class JewelryForm(FlaskForm):
    material_type = SelectField("Material Type", choices=[('gold', 'Gold'), ('silver', 'Silver')], validators=[DataRequired()])
    weight_tola = FloatField("Weight (Tola)", validators=[DataRequired(), NumberRange(min=0.01)])
    labor_cost = FloatField("Labor Cost", validators=[DataRequired(), NumberRange(min=0.0)])
    description = TextAreaField("Description (optional)")
    submit = SubmitField("Save")


class SearchForm(FlaskForm):
    # Input is still a string, will parse to int for query
    jewelry_id_string = StringField("Jewelry ID", validators=[DataRequired(), Length(min=3, max=20)])
    submit = SubmitField("Search")


# ---------------- Helpers ----------------
def allowed_file(filename: str) -> bool:
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in app.config["ALLOWED_EXTENSIONS"]

# new_unique_id() function removed, as IDs are now based on item.id

def money(n) -> str:
    return str(Decimal(str(n)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

# Rates are now fetched from the current_user object
def get_gold_rate_per_tola():
    if current_user.is_authenticated:
        return current_user.gold_rate_per_tola
    return 70000.0 # Default if not logged in (should not happen in protected routes)

def get_silver_rate_per_tola():
    if current_user.is_authenticated:
        return current_user.silver_rate_per_tola
    return 1000.0 # Default if not logged in (should not happen in protected routes)


# ---------------- Routes ----------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    flash("Registration is disabled. Contact admin for login credentials.", "warning")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user and user.active and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Invalid credentials or inactive account.", "danger")
    return render_template("login.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    items = Jewelry.query.filter_by(owner=current_user, is_sold=False).order_by(Jewelry.created_at.desc()).all()
    gold_rate = get_gold_rate_per_tola()
    silver_rate = get_silver_rate_per_tola()
    return render_template("dashboard.html", items=items, current_gold_rate=gold_rate, current_silver_rate=silver_rate)


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_jewelry():
    form = JewelryForm()
    if form.validate_on_submit():
        # unique_id is no longer explicitly generated here, it will be item.id
        photo_path = None
        file = request.files.get("photo")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Invalid image type. Use png/jpg/jpeg/webp.", "warning")
                return render_template("add_jewelry.html", form=form)
            # Use a temporary UUID for filename before item.id is available, or generalize
            fname = secure_filename(f"{uuid.uuid4().hex[:8]}_{file.filename}") # Using temp UUID for filename
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], fname)
            file.save(save_path)
            photo_path = save_path

        item = Jewelry(
            weight_tola=form.weight_tola.data,
            material_type=form.material_type.data,
            labor_cost=form.labor_cost.data,
            description=form.description.data.strip() if form.description.data else None,
            photo_path=photo_path,
            owner=current_user,
            is_sold=False
        )
        db.session.add(item)
        db.session.commit()
        # After commit, item.id is available, so we can use item.formatted_id
        flash(f"Jewelry added with ID {item.formatted_id}", "success")
        return redirect(url_for("dashboard"))
    return render_template("add_jewelry.html", form=form)


@app.route("/search", methods=["GET", "POST"])
@login_required
def search():
    form = SearchForm()
    found = price = gold_rate = silver_rate = None
    if form.validate_on_submit():
        input_id_string = form.jewelry_id_string.data.strip().upper()
        # Parse the input string to get the integer ID
        if input_id_string.startswith("JW-") and len(input_id_string) > 3:
            try:
                item_id = int(input_id_string[3:]) # Extract numeric part
                found = Jewelry.query.get(item_id) # Search by primary key
            except ValueError:
                found = None
        else:
            found = None

        if found:
            # Use the rates of the item's owner
            gold_rate = found.owner.gold_rate_per_tola
            silver_rate = found.owner.silver_rate_per_tola

            if found.material_type == 'gold':
                price = found.weight_tola * gold_rate + found.labor_cost
            elif found.material_type == 'silver':
                price = found.weight_tola * silver_rate + found.labor_cost
            else:
                price = None # Should not happen with validation
        else:
            flash("No jewelry found for that ID.", "warning")
    return render_template("search.html", form=form, item=found, gold_rate=gold_rate, silver_rate=silver_rate, price=price)


@app.route("/invoice/<int:item_id>") # Route now expects integer ID
@login_required
def invoice(item_id):
    item = Jewelry.query.get_or_404(item_id) # Retrieve by integer ID
    if item.owner.id != current_user.id and not current_user.is_admin:
        abort(403)

    gold_rate = item.owner.gold_rate_per_tola
    silver_rate = item.owner.silver_rate_per_tola
    
    if item.material_type == 'gold':
        material_rate = gold_rate
        price_before_discount = item.weight_tola * gold_rate + item.labor_cost
    elif item.material_type == 'silver':
        material_rate = silver_rate
        price_before_discount = item.weight_tola * silver_rate + item.labor_cost
    else:
        material_rate = 0
        price_before_discount = item.labor_cost

    discount_amount = request.args.get('discount', type=float, default=0.0)
    
    final_price = price_before_discount - discount_amount
    if final_price < 0:
        final_price = 0

    return render_template(
        "invoice.html",
        item=item,
        gold_rate=gold_rate,
        silver_rate=silver_rate,
        material_rate=material_rate,
        price_before_discount=price_before_discount,
        discount_amount=discount_amount,
        final_price=final_price
    )


@app.route("/update-gold-rate", methods=["POST"])
@login_required
def update_gold_rate():
    data = request.json
    if not data or "rate" not in data:
        return jsonify({"error": "No rate provided"}), 400
    try:
        rate = float(data["rate"])
    except ValueError:
        return jsonify({"error": "Invalid rate"}), 400

    current_user.gold_rate_per_tola = rate
    db.session.commit()
    return jsonify({"message": f"Your Gold rate updated to {rate} NPR/tola."})


@app.route("/update-silver-rate", methods=["POST"])
@login_required
def update_silver_rate():
    data = request.json
    if not data or "rate" not in data:
        return jsonify({"error": "No rate provided"}), 400
    try:
        rate = float(data["rate"])
    except ValueError:
        return jsonify({"error": "Invalid rate"}), 400

    current_user.silver_rate_per_tola = rate
    db.session.commit()
    return jsonify({"message": f"Your Silver rate updated to {rate} NPR/tola."})


@app.route("/mark-sold/<int:item_id>", methods=["POST"]) # Expects integer ID
@login_required
def mark_sold(item_id):
    item = Jewelry.query.get_or_404(item_id) # Retrieve by integer ID
    # Allow owner OR admin to mark as sold
    if item.owner.id != current_user.id and not current_user.is_admin:
        abort(403)
    item.is_sold = True
    db.session.commit()
    flash(f"Jewelry ID {item.formatted_id} marked as sold and moved to history.", "success")
    return redirect(url_for("dashboard"))


@app.route("/sold-history")
@login_required
def sold_history():
    sold_items = Jewelry.query.filter_by(owner=current_user, is_sold=True).order_by(Jewelry.created_at.desc()).all()
    return render_template("sold_history.html", items=sold_items)


# ---------------- Admin ----------------
def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


@app.route("/admin")
@login_required
def admin_dashboard():
    admin_required()
    shops = User.query.order_by(User.shop_name.asc()).all()
    items = Jewelry.query.order_by(Jewelry.created_at.desc()).all()
    admin_gold_rate = current_user.gold_rate_per_tola
    admin_silver_rate = current_user.silver_rate_per_tola
    return render_template("admin.html", shops=shops, items=items, admin_gold_rate=admin_gold_rate, admin_silver_rate=admin_silver_rate)


@app.route("/admin/create-shopkeeper", methods=["POST"])
@login_required
def admin_create_shopkeeper():
    admin_required()
    shop_name = request.form.get("shop_name").strip()
    username = request.form.get("username").strip()
    password = request.form.get("password").strip()
    
    if not shop_name or not username or not password:
        flash("All fields are required.", "warning")
        return redirect(url_for("admin_dashboard"))
    if User.query.filter_by(username=username).first():
        flash("Username already exists.", "danger")
        return redirect(url_for("admin_dashboard"))

    user = User(shop_name=shop_name, username=username, active=True, is_admin=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(f"Shopkeeper '{shop_name}' created successfully with default rates!", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/toggle-shop/<int:user_id>")
@login_required
def admin_toggle_shop(user_id):
    admin_required()
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id:
        flash("You cannot deactivate yourself.", "warning")
        return redirect(url_for("admin_dashboard"))
    u.active = not u.active
    db.session.commit()
    flash(f"Shop '{u.shop_name}' active = {u.active}", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete-shop/<int:user_id>")
@login_required
def admin_delete_shop(user_id):
    admin_required()
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id:
        flash("You cannot delete yourself.", "warning")
        return redirect(url_for("admin_dashboard"))
    for item in u.jewelries:
        if item.photo_path and os.path.exists(item.photo_path):
            os.remove(item.photo_path)
        db.session.delete(item)
    db.session.delete(u)
    db.session.commit()
    flash(f"Shopkeeper '{u.shop_name}' deleted.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete-item/<int:item_id>")
@login_required
def admin_delete_item(item_id):
    admin_required()
    it = Jewelry.query.get_or_404(item_id)
    if it.photo_path and os.path.exists(it.photo_path):
        os.remove(it.photo_path)
    db.session.delete(it)
    db.session.commit()
    flash("Item deleted.", "info")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/export.csv")
@login_required
def admin_export_csv():
    admin_required()
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["id", "formatted_id", "shop_name", "username", "material_type", "weight_tola", "labor_cost", "is_sold", "created_at"])
    for it in Jewelry.query.order_by(Jewelry.created_at.asc()).all():
        writer.writerow([it.id, it.formatted_id, it.owner.shop_name, it.owner.username, it.material_type,
                         money(it.weight_tola), money(it.labor_cost), "Yes" if it.is_sold else "No", it.created_at.isoformat()])
    si.seek(0)
    return send_file(si, mimetype="text/csv", as_attachment=True, download_name="jewelry_export.csv")


# ---------------- CLI ----------------
@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("Database initialized.")


@app.cli.command("create-admin")
def create_admin():
    username = os.environ.get("ADMIN_USERNAME", "admin")
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    shop_name = os.environ.get("ADMIN_SHOP", "Main Admin")
    existing = User.query.filter_by(username=username).first()
    if existing:
        print("Admin already exists.")
        return
    u = User(shop_name=shop_name, username=username, is_admin=True, active=True)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    print(f"Admin created: {username} / {password} (change later!)")


@app.cli.command("create-shop")
def create_shop():
    username = input("Shop username: ").strip()
    shop_name = input("Shop name: ").strip()
    password = input("Password: ").strip()
    if User.query.filter_by(username=username).first():
        print("Username already exists.")
        return
    user = User(shop_name=shop_name, username=username, active=True, is_admin=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"Shopkeeper account created: {shop_name} / {username}")


# ---------------- Run ----------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
