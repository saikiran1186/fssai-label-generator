import html
import json
import os
import re
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape as xml_escape

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import code128
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Flowable

if "_nutrition_cache_cleared" not in st.session_state:
    try:
        st.cache_data.clear()
    except (AttributeError, RuntimeError):
        pass
    st.session_state._nutrition_cache_cleared = True

COMMON_ALLERGENS = ["milk", "peanuts", "wheat", "soy", "egg", "nuts"]

SVG_VEG_SYMBOL = """<svg width="18" height="18" xmlns="http://www.w3.org/2000/svg">
  <rect x="1" y="1" width="16" height="16" fill="none" stroke="#008000" stroke-width="2"/>
  <circle cx="9" cy="9" r="5" fill="#008000"/>
</svg>"""

SVG_NONVEG_SYMBOL = """<svg width="18" height="18" xmlns="http://www.w3.org/2000/svg">
  <rect x="1" y="1" width="16" height="16" fill="none" stroke="#A52A2A" stroke-width="2"/>
  <polygon points="9,3 16,15 2,15" fill="#A52A2A"/>
</svg>"""

SVG_FSSAI_PLACEHOLDER = """<svg width="40" height="40" xmlns="http://www.w3.org/2000/svg">
  <circle cx="20" cy="20" r="18" fill="none" stroke="#008000" stroke-width="2"/>
  <text x="20" y="17" text-anchor="middle" font-size="7" fill="#008000" font-weight="bold">FSSAI</text>
  <text x="20" y="27" text-anchor="middle" font-size="5" fill="#008000">Lic. No.</text>
</svg>"""
NUTRITION_DB_PATH = Path(__file__).resolve().parent / "data" / "nutrition_db.json"
PROFILE_PATH = Path(__file__).resolve().parent / "user_profile.json"
PDF_PATH = Path(__file__).resolve().parent / "label.pdf"
PURCHASE_DB_PATH = Path(__file__).resolve().parent / "purchases.db"
LABEL_PRICE_PAISE = 9900
EDIT_WINDOW_DAYS = 7

INGREDIENT_DB = {
    "almonds": {"calories":579,"protein":21.2,"carbs":21.6,"sugar":4.4,"fat":49.9,"saturated_fat":3.8,"trans_fat":0,"sodium":1},
    "atta": {"calories":340,"protein":13,"carbs":71,"sugar":0,"fat":2.5,"saturated_fat":0.4,"trans_fat":0,"sodium":2},
    "baking powder": {"calories":53,"protein":0,"carbs":28,"sugar":0,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":10600},
    "besan": {"calories":387,"protein":22,"carbs":58,"sugar":10,"fat":6.7,"saturated_fat":0.9,"trans_fat":0,"sodium":64},
    "gram flour": {"calories":387,"protein":22,"carbs":58,"sugar":10,"fat":6.7,"saturated_fat":0.9,"trans_fat":0,"sodium":64},
    "butter": {"calories":717,"protein":0.85,"carbs":0.1,"sugar":0.1,"fat":81,"saturated_fat":51,"trans_fat":3.3,"sodium":643},
    "cardamom": {"calories":311,"protein":11,"carbs":68,"sugar":0,"fat":6.7,"saturated_fat":0.8,"trans_fat":0,"sodium":18},
    "cashews": {"calories":553,"protein":18,"carbs":30,"sugar":5.9,"fat":44,"saturated_fat":7.8,"trans_fat":0,"sodium":12},
    "cheese": {"calories":402,"protein":25,"carbs":1.3,"sugar":0.5,"fat":33,"saturated_fat":21,"trans_fat":1.1,"sodium":621},
    "chana dal": {"calories":360,"protein":20,"carbs":61,"sugar":8,"fat":5.9,"saturated_fat":0.8,"trans_fat":0,"sodium":20},
    "chocolate": {"calories":546,"protein":4.9,"carbs":60,"sugar":48,"fat":31,"saturated_fat":19,"trans_fat":0.1,"sodium":24},
    "cinnamon": {"calories":247,"protein":4,"carbs":81,"sugar":2.2,"fat":1.2,"saturated_fat":0.3,"trans_fat":0,"sodium":10},
    "cocoa": {"calories":228,"protein":20,"carbs":58,"sugar":1.8,"fat":14,"saturated_fat":8,"trans_fat":0,"sodium":21},
    "coconut": {"calories":354,"protein":3.3,"carbs":15,"sugar":6.2,"fat":33,"saturated_fat":30,"trans_fat":0,"sodium":20},
    "coconut milk": {"calories":230,"protein":2.3,"carbs":6,"sugar":3.3,"fat":24,"saturated_fat":21,"trans_fat":0,"sodium":15},
    "coconut oil": {"calories":862,"protein":0,"carbs":0,"sugar":0,"fat":100,"saturated_fat":86,"trans_fat":0,"sodium":0},
    "condensed milk": {"calories":321,"protein":7.9,"carbs":54,"sugar":54,"fat":8.7,"saturated_fat":5.5,"trans_fat":0,"sodium":127},
    "corn flour": {"calories":381,"protein":6.9,"carbs":79,"sugar":0,"fat":3.9,"saturated_fat":0.6,"trans_fat":0,"sodium":5},
    "coriander": {"calories":23,"protein":2.1,"carbs":3.7,"sugar":0,"fat":0.5,"saturated_fat":0,"trans_fat":0,"sodium":46},
    "cream": {"calories":340,"protein":2.1,"carbs":2.8,"sugar":2.8,"fat":36,"saturated_fat":23,"trans_fat":1.1,"sodium":38},
    "cumin": {"calories":375,"protein":18,"carbs":44,"sugar":2.3,"fat":22,"saturated_fat":1.5,"trans_fat":0,"sodium":168},
    "yogurt": {"calories":61,"protein":3.5,"carbs":4.7,"sugar":4.7,"fat":3.3,"saturated_fat":2.1,"trans_fat":0,"sodium":46},
    "dates": {"calories":277,"protein":1.8,"carbs":75,"sugar":63,"fat":0.2,"saturated_fat":0,"trans_fat":0,"sodium":1},
    "garlic": {"calories":149,"protein":6.4,"carbs":33,"sugar":1,"fat":0.5,"saturated_fat":0.1,"trans_fat":0,"sodium":17},
    "ghee": {"calories":900,"protein":0,"carbs":0,"sugar":0,"fat":100,"saturated_fat":62,"trans_fat":4,"sodium":2},
    "ginger": {"calories":80,"protein":1.8,"carbs":18,"sugar":1.7,"fat":0.8,"saturated_fat":0.2,"trans_fat":0,"sodium":13},
    "green chilli": {"calories":40,"protein":2,"carbs":9,"sugar":5.1,"fat":0.4,"saturated_fat":0,"trans_fat":0,"sodium":9},
    "honey": {"calories":304,"protein":0.3,"carbs":82,"sugar":82,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":4},
    "jaggery": {"calories":383,"protein":0.4,"carbs":98,"sugar":97,"fat":0.1,"saturated_fat":0,"trans_fat":0,"sodium":40},
    "maida": {"calories":364,"protein":10,"carbs":76,"sugar":0.3,"fat":1,"saturated_fat":0.2,"trans_fat":0,"sodium":2},
    "milk": {"calories":42,"protein":3.4,"carbs":5,"sugar":5,"fat":3.3,"saturated_fat":1.9,"trans_fat":0,"sodium":44},
    "milk powder": {"calories":496,"protein":26,"carbs":38,"sugar":38,"fat":27,"saturated_fat":17,"trans_fat":0,"sodium":371},
    "moong dal": {"calories":347,"protein":24,"carbs":63,"sugar":6,"fat":1.2,"saturated_fat":0.3,"trans_fat":0,"sodium":15},
    "mustard oil": {"calories":884,"protein":0,"carbs":0,"sugar":0,"fat":100,"saturated_fat":12,"trans_fat":0,"sodium":0},
    "oil": {"calories":884,"protein":0,"carbs":0,"sugar":0,"fat":100,"saturated_fat":14,"trans_fat":0.5,"sodium":0},
    "onion": {"calories":40,"protein":1.1,"carbs":9.3,"sugar":4.2,"fat":0.1,"saturated_fat":0,"trans_fat":0,"sodium":4},
    "paneer": {"calories":296,"protein":18,"carbs":1.2,"sugar":0,"fat":20,"saturated_fat":13,"trans_fat":0,"sodium":18},
    "peanut oil": {"calories":884,"protein":0,"carbs":0,"sugar":0,"fat":100,"saturated_fat":17,"trans_fat":0,"sodium":0},
    "peanuts": {"calories":567,"protein":25.8,"carbs":16,"sugar":4,"fat":49,"saturated_fat":7,"trans_fat":0,"sodium":18},
    "rava": {"calories":360,"protein":12,"carbs":73,"sugar":0.4,"fat":1.2,"saturated_fat":0.2,"trans_fat":0,"sodium":1},
    "raisins": {"calories":299,"protein":3.1,"carbs":79,"sugar":59,"fat":0.5,"saturated_fat":0.2,"trans_fat":0,"sodium":11},
    "red chilli powder": {"calories":282,"protein":13,"carbs":50,"sugar":7,"fat":14,"saturated_fat":2,"trans_fat":0,"sodium":93},
    "rice": {"calories":130,"protein":2.7,"carbs":28,"sugar":0,"fat":0.3,"saturated_fat":0.1,"trans_fat":0,"sodium":1},
    "rice flour": {"calories":366,"protein":5.9,"carbs":80,"sugar":0,"fat":1.4,"saturated_fat":0.4,"trans_fat":0,"sodium":0},
    "salt": {"calories":0,"protein":0,"carbs":0,"sugar":0,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":38758},
    "sesame seeds": {"calories":573,"protein":18,"carbs":23,"sugar":0.3,"fat":50,"saturated_fat":7,"trans_fat":0,"sodium":11},
    "sugar": {"calories":387,"protein":0,"carbs":100,"sugar":100,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":1},
    "toor dal": {"calories":343,"protein":22,"carbs":63,"sugar":6,"fat":1.5,"saturated_fat":0.3,"trans_fat":0,"sodium":17},
    "tomato": {"calories":18,"protein":0.9,"carbs":3.9,"sugar":2.6,"fat":0.2,"saturated_fat":0,"trans_fat":0,"sodium":5},
    "turmeric": {"calories":354,"protein":8,"carbs":65,"sugar":3.2,"fat":10,"saturated_fat":3,"trans_fat":0,"sodium":38},
    "vanilla": {"calories":288,"protein":0,"carbs":13,"sugar":13,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":9},
    "water": {"calories":0,"protein":0,"carbs":0,"sugar":0,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":0},
    "wheat": {"calories":340,"protein":13,"carbs":71,"sugar":0,"fat":2.5,"saturated_fat":0.4,"trans_fat":0,"sodium":2},
    "yeast": {"calories":325,"protein":40,"carbs":38,"sugar":0,"fat":7.6,"saturated_fat":1,"trans_fat":0,"sodium":51},
}


def _db_conn():
    conn = sqlite3.connect(PURCHASE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_purchase_db():
    """Create purchases table for pay-per-label and edit window control."""
    with _db_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS purchases (
              id TEXT PRIMARY KEY,
              user_id TEXT,
              product_id TEXT,
              product_name TEXT,
              payment_id TEXT,
              razorpay_order_id TEXT,
              amount INTEGER DEFAULT 9900,
              status TEXT CHECK(status IN ('pending','paid','failed')) DEFAULT 'pending',
              created_at TEXT DEFAULT CURRENT_TIMESTAMP,
              expires_at TEXT,
              download_count INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_purchases_payment_id "
            "ON purchases(payment_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_purchases_user_product "
            "ON purchases(user_id, product_id, status)"
        )
        conn.commit()


def _utc_now():
    return datetime.utcnow()


def _dt_to_db(ts):
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def _dt_from_db(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def product_id_from_name(product_name):
    token = re.sub(r"[^a-z0-9]+", "-", (product_name or "").strip().lower()).strip("-")
    if not token:
        token = "unnamed-product"
    return token[:50]


def get_or_create_user_id():
    profile = load_user_profile()
    existing = str(profile.get("user_id", "")).strip()
    if existing:
        return existing
    new_id = "usr_" + uuid4().hex[:12]
    profile["user_id"] = new_id
    save_user_profile(profile)
    return new_id


def get_active_purchase(user_id, product_id):
    with _db_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM purchases
            WHERE user_id = ? AND product_id = ? AND status = 'paid'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id, product_id),
        ).fetchone()
    if not row:
        return None
    expires = _dt_from_db(row["expires_at"])
    if not expires or _utc_now() > expires:
        return None
    return row


def list_paid_products(user_id):
    """Latest paid products for this user (deduped by product_id)."""
    with _db_conn() as conn:
        rows = conn.execute(
            """
            SELECT product_id, product_name, expires_at, created_at
            FROM purchases
            WHERE user_id = ? AND status = 'paid'
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    seen = set()
    products = []
    for row in rows:
        pid = str(row["product_id"] or "").strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        products.append(
            {
                "product_id": pid,
                "product_name": str(row["product_name"] or "").strip() or "Unnamed Product",
                "expires_at": str(row["expires_at"] or "").strip(),
                "created_at": str(row["created_at"] or "").strip(),
            }
        )
    return products


def verify_razorpay_payment(payment_id, expected_amount=LABEL_PRICE_PAISE):
    """Temporary manual mode: accept any payment id with pay_ prefix."""
    _ = expected_amount
    pid = str(payment_id or "").strip()
    if not pid.startswith("pay_"):
        return False, "Invalid ID format. Payment ID must start with 'pay_'.", None
    if not re.fullmatch(r"[A-Za-z0-9_]+", pid):
        return False, "Invalid ID format.", None
    return True, "Payment ID accepted (manual verification mode).", None


def record_paid_purchase(user_id, product_id, product_name, payment_id, razorpay_order_id):
    with _db_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM purchases WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
        if existing and (
            existing["user_id"] != user_id or existing["product_id"] != product_id
        ):
            return False, "This payment ID is already linked to another label."

        now = _utc_now()
        expires = now + timedelta(days=EDIT_WINDOW_DAYS)
        purchase_id = "pur_" + uuid4().hex[:12]
        if existing:
            conn.execute(
                """
                UPDATE purchases
                SET status='paid',
                    product_name=?,
                    razorpay_order_id=?,
                    amount=?,
                    expires_at=?,
                    created_at=?
                WHERE payment_id=?
                """,
                (
                    product_name,
                    razorpay_order_id or "",
                    LABEL_PRICE_PAISE,
                    _dt_to_db(expires),
                    _dt_to_db(now),
                    payment_id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO purchases
                (id, user_id, product_id, product_name, payment_id, razorpay_order_id,
                 amount, status, created_at, expires_at, download_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'paid', ?, ?, 0)
                """,
                (
                    purchase_id,
                    user_id,
                    product_id,
                    product_name,
                    payment_id,
                    razorpay_order_id or "",
                    LABEL_PRICE_PAISE,
                    _dt_to_db(now),
                    _dt_to_db(expires),
                ),
            )
        conn.commit()
    return True, "Payment verified. Download unlocked for 7 days (free edits)."


def increment_download_count(purchase_id):
    with _db_conn() as conn:
        conn.execute(
            "UPDATE purchases SET download_count = COALESCE(download_count, 0) + 1 WHERE id = ?",
            (purchase_id,),
        )
        conn.commit()


nutrition_db = {}


def reload_nutrition_db():
    global nutrition_db
    nutrition_db = {k: dict(v) for k, v in INGREDIENT_DB.items()}
    try:
        with NUTRITION_DB_PATH.open("r", encoding="utf-8") as file:
            nutrition_db.update(json.load(file))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass


reload_nutrition_db()
init_purchase_db()


def load_user_profile():
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_user_profile(profile):
    existing = load_user_profile()
    merged = dict(existing)
    merged.update(profile or {})
    PROFILE_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")


def init_profile_session_state():
    data = load_user_profile()
    defaults = {
        "prof_manufacturer_name": data.get("manufacturer_name", ""),
        "prof_manufacturer_address": data.get("manufacturer_address", ""),
        "prof_license_number": data.get("license_number", ""),
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def append_nutrition_entry(
    key: str,
    calories: float,
    protein: float,
    fat: float = 0.0,
    carbs: float = 0.0,
    sugar: float = 0.0,
):
    """Persist one ingredient into nutrition_db.json (AI cache overlay) and refresh in-memory db."""
    global nutrition_db
    key = key.strip().lower()
    entry = {
        "calories": round(float(calories), 2),
        "protein": round(float(protein), 2),
        "fat": round(float(fat), 2),
        "carbs": round(float(carbs), 2),
        "sugar": round(float(sugar), 2),
    }
    try:
        if NUTRITION_DB_PATH.exists():
            db = json.loads(NUTRITION_DB_PATH.read_text(encoding="utf-8"))
        else:
            db = {}
        db[key] = entry
        NUTRITION_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        NUTRITION_DB_PATH.write_text(
            json.dumps(db, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        nutrition_db[key] = entry
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        nutrition_db[key] = entry


def _ai_estimate_nutrition(ingredient: str) -> dict:
    """LLM estimate per 100g. Returns dict with calories, protein, fat, carbs; _failed True if not usable."""
    fallback = {
        "calories": 150.0,
        "protein": 3.0,
        "fat": 8.0,
        "carbs": 20.0,
        "sugar": 2.0,
        "_failed": True,
    }
    groq_key = os.environ.get("GROQ_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if groq_key:
        url = "https://api.groq.com/openai/v1/chat/completions"
        model = "llama-3.1-8b-instant"
        api_key = groq_key
    elif openai_key:
        url = "https://api.openai.com/v1/chat/completions"
        model = "gpt-4o-mini"
        api_key = openai_key
    else:
        return fallback

    prompt = (
        f"Give approximate per-100g nutrition for food ingredient: {ingredient!r}.\n"
        'Return only valid JSON with this exact shape: '
        '{"calories": <number>, "protein": <number>, "fat": <number>, "carbs": <number>, "sugar": <number>}\n'
        '"carbs" is total carbohydrates in grams, "sugar" is total sugars in grams. '
        'No markdown, no explanation.'
    )
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```\s*$", "", text)
        parsed = json.loads(text)
        cal = float(parsed.get("calories", fallback["calories"]))
        prot = float(parsed.get("protein", fallback["protein"]))
        fat = float(parsed.get("fat", fallback["fat"]))
        carbs = float(parsed.get("carbs", parsed.get("carbohydrates", fallback["carbs"])))
        sugar = float(parsed.get("sugar", parsed.get("sugars", fallback["sugar"])))
        return {
            "calories": max(0.0, cal),
            "protein": max(0.0, prot),
            "fat": max(0.0, fat),
            "carbs": max(0.0, carbs),
            "sugar": max(0.0, sugar),
        }
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return fallback


def get_nutrition(ingredient_lower: str) -> dict:
    """
    3-layer: direct JSON key → fuzzy substring (longest key) → AI estimate (cached to JSON).
    Returns dict: calories, protein, fat, carbs, source in {'direct','fuzzy','ai','fallback','empty'}.
    """
    ing = ingredient_lower.strip().lower()
    if not ing:
        return {
            "calories": 0.0,
            "protein": 0.0,
            "fat": 0.0,
            "carbs": 0.0,
            "source": "empty",
        }

    if ing in nutrition_db:
        row = nutrition_db[ing]
        return {
            "calories": float(row.get("calories", 0)),
            "protein": float(row.get("protein", 0)),
            "fat": float(row.get("fat", 0)),
            "carbs": float(row.get("carbs", 0)),
            "sugar": float(row.get("sugar", 0)),
            "source": "direct",
        }

    best = None
    best_len = -1
    for key, vals in nutrition_db.items():
        kl = key.lower()
        if kl in ing or ing in kl:
            if len(key) > best_len:
                best = (
                    float(vals.get("calories", 0)),
                    float(vals.get("protein", 0)),
                    float(vals.get("fat", 0)),
                    float(vals.get("carbs", 0)),
                    float(vals.get("sugar", 0)),
                    key,
                )
                best_len = len(key)
    if best:
        return {
            "calories": best[0],
            "protein": best[1],
            "fat": best[2],
            "carbs": best[3],
            "sugar": best[4],
            "source": "fuzzy",
            "matched_key": best[5],
        }

    est = _ai_estimate_nutrition(ing)
    if est.get("_failed"):
        return {
            "calories": float(est["calories"]),
            "protein": float(est["protein"]),
            "fat": float(est.get("fat", 0)),
            "carbs": float(est.get("carbs", 0)),
            "sugar": float(est.get("sugar", 0)),
            "source": "fallback",
        }

    append_nutrition_entry(
        ing,
        est["calories"],
        est["protein"],
        est.get("fat", 0),
        est.get("carbs", 0),
        est.get("sugar", 0),
    )
    return {
        "calories": float(est["calories"]),
        "protein": float(est["protein"]),
        "fat": float(est.get("fat", 0)),
        "carbs": float(est.get("carbs", 0)),
        "sugar": float(est.get("sugar", 0)),
        "source": "ai",
    }


def _nutrient_value(row, *keys):
    for key in keys:
        if key in row:
            try:
                return float(row.get(key, 0) or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def calculate_nutrition():
    """Calculate nutrition from selected ingredients list.

    Custom ingredients contribute 0 nutrition.
    """
    total_nutrition = {
        "calories": 0.0,
        "protein": 0.0,
        "carbs": 0.0,
        "fat": 0.0,
        "sugar": 0.0,
        "sodium": 0.0,
        "saturated_fat": 0.0,
        "trans_fat": 0.0,
    }
    for ing in st.session_state.get("ingredients_list", []):
        try:
            pct = float(ing.get("percentage", 0)) / 100.0
        except (TypeError, ValueError):
            pct = 0.0
        if pct <= 0:
            continue
        if ing.get("is_verified") and ing.get("key") in VERIFIED_DB:
            db_data = VERIFIED_DB[ing["key"]]
            total_nutrition["calories"] += _nutrient_value(db_data, "calories", "energy") * pct
            total_nutrition["protein"] += _nutrient_value(db_data, "protein") * pct
            total_nutrition["carbs"] += _nutrient_value(db_data, "carbs", "carbohydrates") * pct
            total_nutrition["fat"] += _nutrient_value(db_data, "fat", "total_fat") * pct
            total_nutrition["sugar"] += _nutrient_value(db_data, "sugar", "total_sugars") * pct
            total_nutrition["sodium"] += _nutrient_value(db_data, "sodium") * pct
            total_nutrition["saturated_fat"] += _nutrient_value(db_data, "saturated_fat") * pct
            total_nutrition["trans_fat"] += _nutrient_value(db_data, "trans_fat") * pct
    return total_nutrition


def calculate_nutrition_from_ingredients(ingredient_rows):
    """
    Weighted per-100g nutrition using ingredient percentages.

    ``ingredient_rows`` is a list of dicts:
      [{"ingredient": "salt", "ingredient_lower": "salt", "percentage": 15.0}, ...]

    Each nutrient is computed as:
      contribution = ingredient_nutrient_per_100g * (percentage / 100)
    and then summed across all ingredients.
    """
    if not ingredient_rows:
        return 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, []

    totals = {
        "calories": 0.0,
        "protein": 0.0,
        "carbs": 0.0,
        "sugar": 0.0,
        "fat": 0.0,
        "saturated_fat": 0.0,
        "trans_fat": 0.0,
        "sodium": 0.0,
    }
    fallback_names = []
    for row in ingredient_rows:
        ing = str(row.get("ingredient", "")).strip() or "Unknown"
        ing_lower = str(row.get("ingredient_lower", ing.lower())).strip().lower()
        is_custom = bool(row.get("is_custom", False))
        try:
            pct = float(row.get("percentage", 0))
        except (TypeError, ValueError):
            pct = 0.0
        if pct <= 0:
            continue

        if is_custom:
            r = {
                "calories": 0.0,
                "protein": 0.0,
                "carbs": 0.0,
                "sugar": 0.0,
                "fat": 0.0,
                "source": "custom_zero",
            }
            db_row = {}
        else:
            db_row = VERIFIED_DB.get(ing_lower) or INGREDIENT_DB.get(ing_lower, {})
            if db_row:
                r = {
                    "calories": _nutrient_value(db_row, "calories", "energy"),
                    "protein": _nutrient_value(db_row, "protein"),
                    "carbs": _nutrient_value(db_row, "carbs", "carbohydrates"),
                    "sugar": _nutrient_value(db_row, "sugar", "total_sugars"),
                    "fat": _nutrient_value(db_row, "fat", "total_fat"),
                    "source": "verified_db",
                }
            else:
                r = get_nutrition(ing_lower)
        factor = pct / 100.0

        cal = _nutrient_value(db_row, "calories", "energy") or float(r.get("calories", 0))
        prot = _nutrient_value(db_row, "protein") or float(r.get("protein", 0))
        carbs = _nutrient_value(db_row, "carbs", "carbohydrates") or float(r.get("carbs", 0))
        sugar = _nutrient_value(db_row, "sugar", "total_sugars") or float(r.get("sugar", 0))
        fat = _nutrient_value(db_row, "fat", "total_fat") or float(r.get("fat", 0))
        sat = _nutrient_value(db_row, "saturated_fat")
        trans = _nutrient_value(db_row, "trans_fat")
        sodium = _nutrient_value(db_row, "sodium")

        totals["calories"] += cal * factor
        totals["protein"] += prot * factor
        totals["carbs"] += carbs * factor
        totals["sugar"] += sugar * factor
        totals["fat"] += fat * factor
        totals["saturated_fat"] += sat * factor
        totals["trans_fat"] += trans * factor
        totals["sodium"] += sodium * factor

        if is_custom:
            fallback_names.append(f"{ing} (custom: 0 values)")
        elif r.get("source") == "fallback":
            fallback_names.append(ing)

    return (
        round(totals["calories"], 2),
        round(totals["protein"], 2),
        round(totals["carbs"], 2),
        round(totals["sugar"], 2),
        round(totals["fat"], 2),
        round(totals["saturated_fat"], 2),
        round(totals["trans_fat"], 2),
        round(totals["sodium"], 2),
        sorted(set(fallback_names)),
    )


def next_batch_number():
    """BN-YYYYMMDD-XX with XX incrementing per day in this session."""
    today_k = datetime.now().strftime("%Y%m%d")
    if st.session_state.get("_batch_day") != today_k:
        st.session_state._batch_day = today_k
        st.session_state._batch_seq = 0
    st.session_state._batch_seq = int(st.session_state.get("_batch_seq", 0)) + 1
    seq = st.session_state._batch_seq
    return f"BN-{today_k}-{seq:02d}"


def clean_ingredients(ingredients_text):
    parts = ingredients_text.split(",")
    cleaned = []
    seen = set()

    for part in parts:
        item = part.strip().lower()
        if item and item not in seen:
            cleaned.append(item)
            seen.add(item)

    return cleaned


def render_nutrient_warnings(
    sodium_mg,
    total_sugars_g,
    saturated_fat_g,
    total_fat_g,
    trans_fat_g,
    salt_percentage=0.0,
):
    """Render complete FSSAI multi-nutrient warnings with reformulation tips."""
    sodium = float(sodium_mg or 0)
    sugar = float(total_sugars_g or 0)
    sat_fat = float(saturated_fat_g or 0)
    fat = float(total_fat_g or 0)
    trans = float(trans_fat_g or 0)
    salt_pct = float(salt_percentage or 0)

    thresholds = {
        "sodium_high": 600.0,
        "sugar_high": 22.5,
        "satfat_high": 5.0,
        "fat_high": 17.5,
        "transfat_limit": 0.2,
    }
    rda = {
        "sodium": 2000.0,   # mg/day
        "sugar": 50.0,      # g/day reference
        "sat_fat": 22.0,    # g/day
        "fat": 67.0,        # g/day
    }

    warnings = []
    tips = []
    severity_scores = []

    if sodium > thresholds["sodium_high"]:
        sodium_rda = int(round((sodium / rda["sodium"]) * 100))
        sodium_5g = int(round(sodium / 20.0))
        warnings.append(
            f"⚠️ High Sodium: {int(round(sodium))}mg ({sodium_rda}%) - Per 5g serving: ~{sodium_5g}mg"
        )
        if salt_pct > 8:
            tips.append(f"Reduce salt to 8% (current: {salt_pct:g}%)")
        elif salt_pct > 0:
            tips.append("Salt level good")
        else:
            tips.append("Reduce salt to 8%")
        severity_scores.append(("sodium", sodium / thresholds["sodium_high"]))

    if sugar > thresholds["sugar_high"]:
        sugar_rda = int(round((sugar / rda["sugar"]) * 100))
        warnings.append(f"⚠️ High Sugar: {round(sugar, 2):g}g ({sugar_rda}%)")
        tips.append("Reduce sugar or use natural sweetener")
        severity_scores.append(("sugar", sugar / thresholds["sugar_high"]))

    if sat_fat > thresholds["satfat_high"]:
        sat_rda = int(round((sat_fat / rda["sat_fat"]) * 100))
        warnings.append(
            f"⚠️ High Saturated Fat: {round(sat_fat, 2):g}g ({sat_rda}%)"
        )
        tips.append("Use unsaturated oil")
        severity_scores.append(
            ("saturated fat", sat_fat / thresholds["satfat_high"])
        )

    if fat > thresholds["fat_high"]:
        fat_rda = int(round((fat / rda["fat"]) * 100))
        warnings.append(f"⚠️ High Fat: {round(fat, 2):g}g ({fat_rda}%)")
        tips.append("Reduce oil by 5%")
        severity_scores.append(("fat", fat / thresholds["fat_high"]))

    if trans > thresholds["transfat_limit"]:
        warnings.append(
            f"🚨 Contains Trans Fat: {round(trans, 2):g}g - FSSAI recommends 0"
        )
        tips.append("Avoid hydrogenated oils")
        severity_scores.append(("trans fat", trans / thresholds["transfat_limit"]))

    dedup_tips = []
    for tip in tips:
        if tip not in dedup_tips:
            dedup_tips.append(tip)

    if not warnings:
        st.markdown(
            """
            <div style="background:#e8f5e9;border-radius:8px;padding:12px 14px;margin:8px 0;
            color:#1f4d22;font-size:15px;line-height:1.4;">
              ✅ All nutrients within recommended limits
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        bg = "#fff3e0" if len(warnings) <= 2 else "#ffebee"
        border = "#ffcc80" if len(warnings) <= 2 else "#ef9a9a"
        list_html = "".join(f"<li>{w}</li>" for w in warnings)
        tips_html = "".join(f"<li>{t}</li>" for t in dedup_tips)
        reform_html = ""
        if len(warnings) >= 3 and severity_scores:
            top_nutrient = max(severity_scores, key=lambda x: x[1])[0]
            reform_html = (
                f'<div style="margin-top:8px;"><strong>Tip:</strong> Consider reformulating '
                f"to reduce {top_nutrient}.</div>"
            )
        st.markdown(
            f"""
            <div style="background:{bg};border:1px solid {border};border-radius:8px;padding:12px 14px;margin:8px 0;
            color:#222;font-size:15px;line-height:1.45;">
              <div style="font-weight:700;margin-bottom:6px;">Nutrient checks</div>
              <ul style="margin:0 0 0 18px;padding:0;">{list_html}</ul>
              <div style="margin-top:8px;font-weight:600;">Helpful tips:</div>
              <ul style="margin:2px 0 0 18px;padding:0;">{tips_html}</ul>
              {reform_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.caption(
        "FSSAI threshold guide (per 100g): Sodium 600mg, Total Sugars 22.5g, "
        "Saturated Fat 5g, Total Fat 17.5g, Trans Fat 0.2g."
    )


def detect_allergens(ingredients_list):
    detected = []
    for allergen in COMMON_ALLERGENS:
        allergen_singular = allergen[:-1] if allergen.endswith("s") else allergen
        if any(allergen in ingredient or allergen_singular in ingredient for ingredient in ingredients_list):
            detected.append(allergen)
    if "peanuts" in detected and "nuts" in detected:
        detected.remove("nuts")
    return detected


def format_quantity_display(quantity_text):
    text = quantity_text.strip()
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([a-zA-Z]+)$", text)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return text


def format_mrp_display(mrp_text):
    text = mrp_text.strip()
    if not text:
        return ""

    cleaned = text.replace("₹", "").replace("Rs.", "").replace("rs.", "").strip()
    cleaned = re.sub(r"(?i)^\s*mrp\s*:\s*", "", cleaned)
    cleaned = re.sub(r"\s*\(.*?\)\s*$", "", cleaned).strip()
    num_match = re.search(r"[\d.]+", cleaned)
    value = num_match.group(0) if num_match else cleaned
    return f"MRP: Rs. {value} (Incl. of all taxes)"


def format_address_display(address_text):
    cleaned = " ".join(address_text.strip().split())
    if not cleaned:
        return ""
    parts = [part.strip().title() for part in cleaned.split(",")]
    return ", ".join(part for part in parts if part)


def _ingredient_chunk_is_bold(chunk):
    """Bold only allergen-related words (aligned with COMMON_ALLERGENS)."""
    words = re.findall(r"[A-Za-z]+", chunk)
    for w in words:
        low = w.lower()
        if low in ("milk", "wheat", "soy", "soya", "egg", "eggs", "peanuts", "nuts"):
            return True
        if low == "peanut" or low.startswith("peanut"):
            return True
    return False


def draw_ingredients_line_with_bold(pdf, x, y, text, size, font_body, font_bold):
    pdf.setFillColorRGB(0, 0, 0)
    parts = re.split(r"(\W+)", text)
    xpos = x
    for part in parts:
        if part == "":
            continue
        bold = _ingredient_chunk_is_bold(part)
        font = font_bold if bold else font_body
        pdf.setFont(font, size)
        pdf.drawString(xpos, y, part)
        xpos += stringWidth(part, font, size)
    return xpos


def _pdf_horizontal_rule(pdf, x1, x2, y, width_pt=0.35, gray=0.55):
    pdf.saveState()
    pdf.setStrokeColorRGB(gray, gray, gray)
    pdf.setLineWidth(width_pt)
    pdf.line(x1, y, x2, y)
    pdf.restoreState()
    pdf.setStrokeColorRGB(0, 0, 0)


PAGE_WIDTH, PAGE_HEIGHT = 297, 420


def _label_truncate(text, font_name, font_size, max_width_pt):
    if not text:
        return ""
    t = text.strip()
    if stringWidth(t, font_name, font_size) <= max_width_pt:
        return t
    ell = "..."
    while len(t) > 1:
        t = t[:-1].rstrip()
        if stringWidth(t + ell, font_name, font_size) <= max_width_pt:
            return t + ell
    return ell


def _label_wrap_lines(text, font_name, font_size, max_width_pt, max_lines):
    """Word-wrap to up to max_lines; last line truncated if still too wide."""
    if not (text or "").strip():
        return []
    words = (text or "").replace("\n", " ").split()
    if not words:
        return []
    lines = []
    cur = []
    for w in words:
        trial = " ".join(cur + [w])
        if stringWidth(trial, font_name, font_size) <= max_width_pt:
            cur.append(w)
            continue
        if cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            lines.append(_label_truncate(w, font_name, font_size, max_width_pt))
            cur = []
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(" ".join(cur))
    lines = lines[:max_lines]
    if lines:
        lines[-1] = _label_truncate(lines[-1], font_name, font_size, max_width_pt)
    return lines


class VegMarkFlowable(Flowable):
    """FSSAI 2021 veg/non-veg mark flowable."""

    def __init__(self, is_vegetarian):
        Flowable.__init__(self)
        self.is_veg = is_vegetarian
        self.width = 40
        self.height = 40

    def draw(self):
        draw_fssai_veg_nonveg(
            self.canv, 0, 0, "veg" if self.is_veg else "non-veg"
        )


class FssaiLogoFlowable(Flowable):
    """Vector FSSAI placeholder (max ~30×26 pt), matches HTML logo intent."""

    def __init__(self):
        Flowable.__init__(self)
        self.width = 30
        self.height = 26

    def draw(self):
        c = self.canv
        c.saveState()
        c.setStrokeColorRGB(0, 0.5, 0)
        c.setFillColorRGB(0, 0.5, 0)
        c.setLineWidth(1.2)
        c.circle(15, 13, 9, stroke=1, fill=0)
        c.setFont("Helvetica-Bold", 5)
        c.drawCentredString(15, 12, "FSSAI")
        c.setFont("Helvetica", 4)
        c.drawCentredString(15, 6, "Lic. No.")
        c.restoreState()


def _pdf_wrap_lines_full(text, font_name, font_size, max_width_pt):
    if not (text or "").strip():
        return []
    words = (text or "").replace("\n", " ").split()
    if not words:
        return []
    lines = []
    cur = []
    for w in words:
        trial = " ".join(cur + [w])
        if stringWidth(trial, font_name, font_size) <= max_width_pt:
            cur.append(w)
            continue
        if cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            lines.append(_label_truncate(w, font_name, font_size, max_width_pt))
            cur = []
    if cur:
        lines.append(" ".join(cur))
    return lines


LABEL_FONTS = {
    "head": "Helvetica-Bold",
    "semi": "Helvetica-Bold",
    "med": "Helvetica-Bold",
    "body": "Helvetica",
    "bold": "Helvetica-Bold",
}

_LABEL_FONTS_REGISTERED = False


def _register_label_fonts():
    """Register Poppins / Inter if available locally or in system fonts.
    Falls back to Helvetica/Helvetica-Bold silently.
    """
    global _LABEL_FONTS_REGISTERED
    if _LABEL_FONTS_REGISTERED:
        return
    _LABEL_FONTS_REGISTERED = True

    here = Path(__file__).resolve().parent
    search_dirs = [
        here / "fonts",
        here / "assets" / "fonts",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        Path.home() / ".local/share/fonts",
    ]
    mapping = {
        "head": ["Poppins-Bold.ttf", "Poppins-ExtraBold.ttf"],
        "semi": ["Poppins-SemiBold.ttf", "Poppins-Medium.ttf"],
        "med": ["Poppins-Medium.ttf", "Poppins-Regular.ttf"],
        "body": [
            "Inter-Regular.ttf",
            "Inter_18pt-Regular.ttf",
            "Inter_24pt-Regular.ttf",
        ],
        "bold": [
            "Inter-Bold.ttf",
            "Inter_18pt-Bold.ttf",
            "Inter_24pt-Bold.ttf",
        ],
    }
    for key, names in mapping.items():
        for name in names:
            found = None
            for d in search_dirs:
                try:
                    p = d / name
                    if p.exists():
                        found = p
                        break
                except OSError:
                    continue
            if found is None:
                continue
            try:
                internal = f"Lbl_{key}_{found.stem}"
                pdfmetrics.registerFont(TTFont(internal, str(found)))
                LABEL_FONTS[key] = internal
                break
            except (OSError, ValueError, TypeError):
                continue


def _mm(v):
    return v * mm


NON_VEG_MARKERS = (
    "chicken", "egg", "fish", "meat", "gelatin", "gelatine",
    "beef", "pork", "mutton", "lamb", "prawn", "shrimp",
    "crab", "lobster", "bacon", "ham", "sausage", "anchovy",
    "tuna", "salmon", "squid", "octopus",
)


def _detect_non_veg(ingredients_text):
    """Return True if any non-veg marker is present in the ingredient list."""
    t = (ingredients_text or "").lower()
    return any(m in t for m in NON_VEG_MARKERS)


def draw_fssai_veg_nonveg(pdf, x, y, food_type):
    """
    Draw 100% FSSAI compliant symbol
    - Veg: Green circle in green square
    - Non-veg: Brown TRIANGLE in brown square (2021 update)
    """
    # FSSAI specification: 6mm x 6mm = ~17 points.
    size = 17

    pdf.saveState()
    if "non" not in str(food_type).lower():
        # GREEN
        r, g, b = 0, 0.6, 0
        pdf.setStrokeColorRGB(r, g, b)
        pdf.setFillColorRGB(0, 0.8, 0)

        # Draw square outline
        pdf.setLineWidth(1)
        pdf.rect(x, y, size, size, stroke=1, fill=0)

        # Circle (60% of square)
        circle_radius = size * 0.3
        pdf.circle(
            x + size / 2, y + size / 2, circle_radius, stroke=0, fill=1
        )

    else:  # non-veg
        # BROWN
        r, g, b = 0.55, 0.27, 0.07
        pdf.setStrokeColorRGB(r, g, b)
        pdf.setFillColorRGB(r, g, b)

        # Draw square outline
        pdf.setLineWidth(1)
        pdf.rect(x, y, size, size, stroke=1, fill=0)

        # Draw filled TRIANGLE in center (NEW 2021 RULE)
        cx = x + size / 2
        cy = y + size / 2
        tri_size = size * 0.28

        p = pdf.beginPath()
        p.moveTo(cx, cy + tri_size)  # top
        p.lineTo(cx - tri_size, cy - tri_size)  # bottom left
        p.lineTo(cx + tri_size, cy - tri_size)  # bottom right
        p.close()
        pdf.drawPath(p, stroke=0, fill=1)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.restoreState()


def _veg_nonveg_mark(c, x, y, size, is_veg):
    """Compatibility wrapper for existing label layout calls."""
    _ = size
    draw_fssai_veg_nonveg(c, x, y, "veg" if is_veg else "non-veg")


def _draw_qr(c, x, y, size, text):
    qr = QrCodeWidget(text)
    b = qr.getBounds()
    w = b[2] - b[0]
    h = b[3] - b[1]
    if w <= 0 or h <= 0:
        return
    d = Drawing(size, size, transform=[size / w, 0, 0, size / h, -b[0], -b[1]])
    d.add(qr)
    renderPDF.draw(d, c, x, y)


def _pct_rda(value, rda_target):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "-"
    if not rda_target:
        return "-"
    return f"{int(round(f / rda_target * 100))}%"


def _fmt_num(v, suffix=""):
    if v in (None, "", "—"):
        return "—"
    try:
        f = float(v)
        if f.is_integer():
            s = f"{int(f)}"
        else:
            s = f"{f:g}"
        return f"{s} {suffix}".strip()
    except (TypeError, ValueError):
        return str(v)


def generate_premium_label(data: dict) -> bytes:
    """Render a premium FSSAI back-label PDF (100mm x 140mm) from ``data`` and
    return PDF bytes. ``data`` uses the same field names as the Streamlit form:
    product_name, ingredients, allergens, calories, protein, carbs, sugar,
    quantity, license_no, manufacture_date, best_before, manufacturer_name,
    manufacturer_address, mrp, batch_number, storage_instructions,
    is_vegetarian, consumer_phone, consumer_email, plus optional added_sugars,
    total_fat, saturated_fat, trans_fat, sodium.
    """
    _register_label_fonts()

    F_HEAD = LABEL_FONTS["head"]
    F_SEMI = LABEL_FONTS["semi"]
    F_MED = LABEL_FONTS["med"]
    F_BODY = LABEL_FONTS["body"]
    F_BOLD = LABEL_FONTS["bold"]

    TEXT = HexColor("#1A1A1A")
    GOLD = HexColor("#C9A86A")
    GREEN = HexColor("#0A7F2E")
    BORDER_GREY = HexColor("#CCCCCC")
    TABLE_HEAD_BG = HexColor("#F5F5F5")
    GRID_BLACK = colors.black

    PW = _mm(100)
    PH = _mm(140)
    MARGIN = _mm(4)
    HEADER_H = _mm(18)
    FOOTER_H = _mm(22)
    LEFT_W = _mm(48)
    GAP = _mm(2)
    RIGHT_W = _mm(42)

    x_L = MARGIN
    x_R = PW - MARGIN
    y_B = MARGIN
    y_T = PH - MARGIN
    header_y_bot = y_T - HEADER_H
    footer_y_top = y_B + FOOTER_H
    x_lcol_L = MARGIN
    x_lcol_R = MARGIN + LEFT_W
    x_rcol_L = MARGIN + LEFT_W + GAP
    x_rcol_R = PW - MARGIN

    main_top = header_y_bot - 4
    main_bot = footer_y_top + 4

    qr_size = _mm(18)
    qr_cap_size = 7.0
    qr_y = _mm(18)
    cap_baseline_y = _mm(12)
    content_bot = qr_y + qr_size + _mm(2)

    product_name = str(data.get("product_name") or "").strip() or "Milk Sweet"
    ingredients = (
        str(data.get("ingredients") or "").strip() or "Not specified"
    )
    raw_all = data.get("allergens") or []
    if isinstance(raw_all, str):
        allergen_items = [a.strip() for a in raw_all.split(",") if a.strip()]
    else:
        allergen_items = [str(a).strip() for a in raw_all if str(a).strip()]
    if allergen_items:
        allergen_text = "Contains: " + ", ".join(
            a.replace("_", " ").title() for a in allergen_items
        )
    else:
        allergen_text = "Contains: None"

    quantity_raw = str(data.get("quantity") or "").strip()
    net_qty = (
        format_quantity_display(quantity_raw) or quantity_raw or "Not specified"
    ).strip()

    mrp_raw = str(data.get("mrp") or "").strip()
    if mrp_raw:
        m = re.search(r"\d+(?:\.\d+)?", mrp_raw)
        mrp_rs = m.group(0) if m else mrp_raw
    else:
        mrp_rs = "—"

    license_no = str(data.get("license_no") or "").strip() or "Not provided"
    mfg_date = str(data.get("manufacture_date") or "").strip() or "—"
    best_before = str(data.get("best_before") or "").strip() or "—"
    batch_no = str(data.get("batch_number") or "").strip() or "—"
    mfr_name = str(data.get("manufacturer_name") or "").strip()
    mfr_addr = format_address_display(
        str(data.get("manufacturer_address") or "")
    ).strip()
    storage = (
        str(data.get("storage_instructions") or "").strip()
        or "Store in a cool and dry place"
    )
    phone = str(data.get("consumer_phone") or "").strip()
    email = str(data.get("consumer_email") or "").strip()
    custom_warning_text = str(data.get("custom_warning_text") or "").strip()
    is_veg = bool(data.get("is_vegetarian", True))

    calories = data.get("calories", 0)
    protein = data.get("protein", 0)
    carbs = data.get("carbs", 0)
    sugar = data.get("sugar", 0)
    added_sugars = data.get("added_sugars", 0)
    total_fat = data.get("total_fat", 0)
    saturated_fat = data.get("saturated_fat", 0)
    trans_fat = data.get("trans_fat", 0)
    sodium = data.get("sodium", 0)

    QR_URL = (
        "https://fssai-label-generator-bqu5mmz7apzpw2siqexquv.streamlit.app"
    )

    buf = BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=(PW, PH))
    c.setFillColor(colors.white)
    c.rect(0, 0, PW, PH, stroke=0, fill=1)

    c.setStrokeColor(BORDER_GREY)
    c.setLineWidth(0.5)
    c.rect(x_L, y_B, x_R - x_L, y_T - y_B, stroke=1, fill=0)

    veg_size = 17
    veg_x = PW - _mm(5) - veg_size
    veg_y = PH - _mm(5) - veg_size
    _veg_nonveg_mark(c, veg_x, veg_y, veg_size, is_veg)

    c.setFillColor(TEXT)
    c.setFont(F_HEAD, 16)
    pname_x = x_L + _mm(2)
    pname_y = y_T - _mm(6) - 4
    pname_max_w = (veg_x - _mm(2)) - pname_x
    pname_disp = _label_truncate(product_name, F_HEAD, 16, pname_max_w)
    c.drawString(pname_x, pname_y, pname_disp)

    fssai_lab = "FSSAI Lic. No: "
    fssai_y = pname_y - 16
    c.setFont(F_BOLD, 8)
    w_fssai_lab = stringWidth(fssai_lab, F_BOLD, 8)
    c.setFont(F_BODY, 8)
    w_fssai_val = stringWidth(license_no, F_BODY, 8)
    total_fssai_w = w_fssai_lab + w_fssai_val
    fssai_right_limit = veg_x - _mm(1.5)
    fssai_x = max(pname_x, fssai_right_limit - total_fssai_w)
    if fssai_x + total_fssai_w > fssai_right_limit:
        avail = fssai_right_limit - pname_x - w_fssai_lab
        lic_short = _label_truncate(license_no, F_BODY, 8, max(20, avail))
        w_fssai_val = stringWidth(lic_short, F_BODY, 8)
        fssai_x = fssai_right_limit - (w_fssai_lab + w_fssai_val)
        license_no = lic_short
    c.setFillColor(TEXT)
    c.setFont(F_BOLD, 8)
    c.drawString(fssai_x, fssai_y, fssai_lab)
    c.setFont(F_BODY, 8)
    c.drawString(fssai_x + w_fssai_lab, fssai_y, license_no)

    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.line(x_L + _mm(2), header_y_bot + 1, x_R - _mm(2), header_y_bot + 1)

    c.setStrokeColor(BORDER_GREY)
    c.setLineWidth(0.4)
    col_div_x = x_lcol_R + GAP / 2
    c.line(col_div_x, header_y_bot - 2, col_div_x, content_bot + 2)

    x_l_text = x_lcol_L + _mm(2)
    x_l_right = x_lcol_R - _mm(1)
    left_wrap_w = x_l_right - x_l_text

    def draw_section(y, title, body_lines, body_font, body_size, body_lead):
        c.setFillColor(TEXT)
        c.setFont(F_SEMI, 9)
        c.drawString(x_l_text, y, title)
        y -= 11
        c.setFont(body_font, body_size)
        for ln in body_lines:
            c.drawString(x_l_text, y, ln)
            y -= body_lead
        return y - 6

    y_l = main_top - 10

    ing_lines = _pdf_wrap_lines_full(ingredients, F_BODY, 8, left_wrap_w)
    if not ing_lines:
        ing_lines = [ingredients]
    y_l = draw_section(y_l, "Ingredients:", ing_lines, F_BODY, 8, 10)

    y_l = draw_section(
        y_l,
        "Allergens:",
        _pdf_wrap_lines_full(allergen_text, F_BOLD, 8, left_wrap_w)
        or [allergen_text],
        F_BOLD,
        8,
        10,
    )

    mfr_lines = []
    if mfr_name:
        mfr_lines.append(mfr_name)
    if mfr_addr:
        mfr_lines.extend(
            _pdf_wrap_lines_full(mfr_addr, F_BODY, 7.5, left_wrap_w)
        )
    if not mfr_lines:
        mfr_lines = ["Not specified"]
    y_l = draw_section(
        y_l, "Manufacturer & Packed By:", mfr_lines, F_BODY, 7.5, 9.5
    )

    if phone or email:
        if phone and email:
            care_text = f"Ph: {phone} | {email}"
        elif phone:
            care_text = f"Ph: {phone}"
        else:
            care_text = email
        care_lines = _pdf_wrap_lines_full(care_text, F_BODY, 7.5, left_wrap_w) or [
            care_text
        ]
        y_l = draw_section(
            y_l, "Consumer Care:", care_lines, F_BODY, 7.5, 9.5
        )

    storage_lines = _pdf_wrap_lines_full(storage, F_BODY, 8, left_wrap_w) or [
        storage
    ]
    y_l = draw_section(y_l, "Storage:", storage_lines, F_BODY, 8, 10)

    x_r_text = x_rcol_L
    right_w_inner = x_rcol_R - x_rcol_L

    c.setFillColor(TEXT)
    c.setFont(F_SEMI, 7.5)
    c.drawString(x_r_text, main_top - 10, "Nutrition Information (Per 100g)")
    c.setFont(F_BODY, 6.2)
    c.drawString(x_r_text, main_top - 10 - 8.5, "* % RDA based on 2000 kcal diet")

    table_top = main_top - 10 - 8.5 - 6
    tbl_hdr_sz = 6.5
    tbl_body_sz = 6.5
    col_val = 38.0
    col_rda = 26.0
    col_nut = right_w_inner - col_val - col_rda
    x_c0 = x_r_text
    x_c1 = x_c0 + col_nut
    x_c2 = x_c1 + col_val
    x_c3 = x_c2 + col_rda

    header_row = ("Nutrient", "Per 100g", "%RDA")
    data_rows = [
        ("Energy", _fmt_num(calories, "kcal"), _pct_rda(calories, 2000)),
        ("Protein", _fmt_num(protein, "g"), _pct_rda(protein, 60)),
        (
            "Carbohydrates",
            _fmt_num(carbs, "g"),
            _pct_rda(carbs, 300),
        ),
        ("Total Sugars", _fmt_num(sugar, "g"), "-"),
        ("Added Sugars", _fmt_num(added_sugars, "g"), "-"),
        ("Total Fat", _fmt_num(total_fat, "g"), _pct_rda(total_fat, 67)),
        ("Saturated Fat", _fmt_num(saturated_fat, "g"), _pct_rda(saturated_fat, 22)),
        ("Trans Fat", _fmt_num(trans_fat, "g"), "-"),
        ("Sodium", _fmt_num(sodium, "mg"), _pct_rda(sodium, 2000)),
    ]
    all_rows = [header_row] + data_rows
    nrows = len(all_rows)
    avail_h = (table_top) - (content_bot + 4)
    row_h = max(10.0, min(12.5, avail_h / nrows))
    table_h = row_h * nrows
    table_bot = table_top - table_h

    c.setFillColor(TABLE_HEAD_BG)
    c.rect(x_c0, table_top - row_h, right_w_inner, row_h, stroke=0, fill=1)

    c.setStrokeColor(GRID_BLACK)
    c.setLineWidth(0.5)
    c.rect(x_c0, table_bot, right_w_inner, table_h, stroke=1, fill=0)
    for i in range(1, nrows):
        yy = table_top - i * row_h
        c.line(x_c0, yy, x_c3, yy)
    c.line(x_c1, table_bot, x_c1, table_top)
    c.line(x_c2, table_bot, x_c2, table_top)

    for i, (a, b, d_) in enumerate(all_rows):
        y_cell_top = table_top - i * row_h
        baseline = y_cell_top - row_h / 2 - 2.1
        if i == 0:
            row_font = F_BOLD
            sz = tbl_hdr_sz
        else:
            row_font = F_BODY
            sz = tbl_body_sz
        c.setFont(row_font, sz)
        c.setFillColor(TEXT)
        a_disp = _label_truncate(a, row_font, sz, col_nut - 2)
        b_disp = _label_truncate(b, row_font, sz, col_val - 2)
        d_disp = _label_truncate(d_, row_font, sz, col_rda - 2)
        c.drawString(x_c0 + 2, baseline, a_disp)
        c.drawString(x_c1 + 2, baseline, b_disp)
        c.drawString(x_c2 + 2, baseline, d_disp)

    qr_x = PW - _mm(10) - qr_size

    text_L = x_L + _mm(2)
    text_R_limit = qr_x - _mm(2)
    text_w = text_R_limit - text_L

    BLACK = colors.black
    row_font = F_BODY
    row_size = 8

    row1_y = _mm(32)
    row2a_y = _mm(28)
    row2b_y = _mm(24)

    row1_text = (
        f"NET QTY: {net_qty}    MRP: Rs. {mrp_rs} (Incl. of all taxes)"
    )
    row2a_text = f"Best Before: {best_before}"
    row2b_text = f"Batch: {batch_no}    MFG: {mfg_date}"

    c.setFillColor(BLACK)
    c.setFont(row_font, row_size)
    c.drawString(
        text_L,
        row1_y,
        _label_truncate(row1_text, row_font, row_size, text_w),
    )
    c.drawString(
        text_L,
        row2a_y,
        _label_truncate(row2a_text, row_font, row_size, text_w),
    )
    c.drawString(
        text_L,
        row2b_y,
        _label_truncate(row2b_text, row_font, row_size, text_w),
    )

    bc_value = batch_no if batch_no and batch_no != "—" else "NOBATCH0001"
    try:
        bc = code128.Code128(
            bc_value,
            barWidth=0.28 * mm,
            barHeight=_mm(8),
            humanReadable=False,
        )
        bc_w = bc.width
        target_w = _mm(40)
        scale = target_w / bc_w if bc_w > 0 else 1.0
        c.saveState()
        c.translate(_mm(8), _mm(15))
        c.scale(scale, 1)
        bc.drawOn(c, 0, 0)
        c.restoreState()
    except (ValueError, TypeError):
        pass

    _draw_qr(c, qr_x, qr_y, qr_size, QR_URL)
    c.setFont(F_BODY, qr_cap_size)
    c.setFillColor(HexColor("#666666"))
    c.drawCentredString(
        qr_x + qr_size / 2, cap_baseline_y, "Scan to create label"
    )

    c.showPage()
    c.save()
    return buf.getvalue()


def _find_system_font(bold=False):
    """Locate a usable TTF (Arial / DejaVu / Liberation) on Windows, Linux, macOS."""
    if bold:
        names = [
            "arialbd.ttf", "Arial-Bold.ttf", "Arial Bold.ttf",
            "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf",
            "Helvetica-Bold.ttf",
        ]
    else:
        names = [
            "arial.ttf", "Arial.ttf",
            "DejaVuSans.ttf", "LiberationSans-Regular.ttf",
            "Helvetica.ttf",
        ]
    dirs = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/liberation"),
        Path("/usr/share/fonts/TTF"),
        Path("/usr/share/fonts"),
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
    ]
    for n in names:
        for d in dirs:
            try:
                p = d / n
                if p.exists():
                    return str(p)
            except OSError:
                continue
    return None


def _pil_font(size, bold=False):
    path = _find_system_font(bold=bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, ValueError):
            pass
    return ImageFont.load_default()


def _pil_text_width(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except (AttributeError, TypeError):
        return len(text) * 6


def _pil_wrap(text, font, max_width, draw):
    if not text:
        return []
    words = str(text).replace("\n", " ").split()
    lines = []
    cur = []
    for w in words:
        trial = " ".join(cur + [w])
        if _pil_text_width(draw, trial, font) <= max_width:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
                cur = [w]
            else:
                lines.append(w)
                cur = []
    if cur:
        lines.append(" ".join(cur))
    return lines


def _draw_veg_mark_png(draw, x, y, size, is_veg):
    """FSSAI 2021 veg/non-veg mark for the PNG preview."""
    stroke_w = max(2, int(round(size * 0.05)))
    if is_veg:
        outline = (0, 153, 0)
        fill = (0, 204, 0)
        draw.rectangle([x, y, x + size, y + size],
                       outline=outline, width=stroke_w)
        cx, cy = x + size / 2, y + size / 2
        r = size * 0.3
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
    else:
        color = (140, 69, 18)
        draw.rectangle([x, y, x + size, y + size],
                       outline=color, width=stroke_w)
        cx, cy = x + size / 2, y + size / 2
        half = size * 0.28
        draw.polygon(
            [
                (cx, cy - half),
                (cx + half, cy + half),
                (cx - half, cy + half),
            ],
            fill=color,
        )


def generate_preview_png(data: dict) -> bytes:
    """Watermarked preview PNG that mirrors the paid PDF layout exactly.

    The label is rendered at 800 x 1120 px (8 px/mm, ~72 DPI) using the same
    mm-based two-column geometry as ``generate_premium_label()``:

    * Header: product name + veg/non-veg mark + FSSAI licence + gold rule.
    * Left column: Ingredients, Allergens, Manufacturer, Consumer Care,
      Storage.
    * Right column: Full nutrition table WITH the %RDA column.
    * Footer: NET QTY / MRP / Best Before / Batch / MFG text rows, plus a
      grey placeholder in the barcode slot (left) and another in the QR
      slot (right).

    On top of this, a diagonal red "PREVIEW ONLY - PAY Rs.99 TO DOWNLOAD"
    watermark is composited 3 times across the entire label so the PNG is
    unusable for printing. The clean, unwatermarked version is produced by
    ``generate_premium_label()`` after payment.
    """
    W, H = 800, 1120
    MM = 8.0
    PT = MM * 25.4 / 72.0

    def mmx(v):
        return int(round(v * MM))

    def ptx(v):
        return max(1, int(round(v * PT)))

    def _pct(value, rda):
        try:
            f = float(value)
        except (TypeError, ValueError):
            return "-"
        if not rda:
            return "-"
        return f"{int(round(f / rda * 100))}%"

    TEXT = (26, 26, 26)
    GOLD = (201, 168, 106)
    BORDER_GREY = (204, 204, 204)
    COL_DIV = (210, 210, 210)
    TABLE_HEAD_BG = (245, 245, 245)
    BLACK = (0, 0, 0)
    GREY_FILL = (220, 220, 220)
    GREY_OUT = (140, 140, 140)
    GREY_TEXT = (102, 102, 102)

    base = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    draw = ImageDraw.Draw(base)

    x_L = mmx(4)
    x_R = W - mmx(4)
    y_T = mmx(4)
    y_B = H - mmx(4)
    HEADER_H = mmx(18)
    LEFT_W = mmx(48)
    GAP = mmx(2)

    y_header_bot = y_T + HEADER_H
    x_lcol_L = x_L
    x_lcol_R = x_L + LEFT_W
    x_rcol_L = x_L + LEFT_W + GAP
    x_rcol_R = x_R

    y_main_top = y_header_bot + mmx(2)

    qr_size = mmx(18)
    qr_top = y_B - mmx(18) - qr_size
    qr_bot = qr_top + qr_size
    qr_L = W - mmx(10) - qr_size
    qr_R = qr_L + qr_size
    y_content_bot = qr_top - mmx(2)

    f_name = _pil_font(ptx(16), bold=True)
    f_lic_lab = _pil_font(ptx(8), bold=True)
    f_lic = _pil_font(ptx(8), bold=False)
    f_sect = _pil_font(ptx(9), bold=True)
    f_body = _pil_font(ptx(8), bold=False)
    f_body_b = _pil_font(ptx(8), bold=True)
    f_body_sm = _pil_font(ptx(7.5), bold=False)
    f_row = _pil_font(ptx(8), bold=False)
    f_tbl_h = _pil_font(ptx(6.5), bold=True)
    f_tbl = _pil_font(ptx(6.5), bold=False)
    f_tbl_note = _pil_font(ptx(6.2), bold=False)
    f_qrcap = _pil_font(ptx(7), bold=False)
    f_box = _pil_font(ptx(8), bold=True)

    product_name = str(data.get("product_name") or "Milk Sweet").strip()
    ingredients = str(data.get("ingredients") or "Not specified").strip()
    is_veg = bool(data.get("is_vegetarian", True))

    raw_all = data.get("allergens") or []
    if isinstance(raw_all, str):
        alist = [a.strip() for a in raw_all.split(",") if a.strip()]
    else:
        alist = [str(a).strip() for a in raw_all if str(a).strip()]
    allergen_text = "Contains: " + (
        ", ".join(a.replace("_", " ").title() for a in alist) if alist else "None"
    )

    qty_raw = str(data.get("quantity") or "").strip()
    net_qty = format_quantity_display(qty_raw) or qty_raw or "Not specified"
    mrp_raw = str(data.get("mrp") or "").strip()
    m = re.search(r"[\d.]+", mrp_raw)
    mrp_rs = m.group(0) if m else "—"
    license_no = str(data.get("license_no") or "Not provided").strip()
    mfg_date = str(data.get("manufacture_date") or "—").strip()
    best_before = str(data.get("best_before") or "—").strip()
    batch_no = str(data.get("batch_number") or "—").strip()
    mfr_name = str(data.get("manufacturer_name") or "").strip()
    mfr_addr = format_address_display(
        str(data.get("manufacturer_address") or "")
    ).strip()
    storage = (
        str(data.get("storage_instructions") or "").strip()
        or "Store in a cool and dry place"
    )
    phone = str(data.get("consumer_phone") or "").strip()
    email = str(data.get("consumer_email") or "").strip()

    def _trunc(text, font, max_w):
        if _pil_text_width(draw, text, font) <= max_w:
            return text
        out = text
        while len(out) > 1 and _pil_text_width(draw, out + "...", font) > max_w:
            out = out[:-1]
        return out.rstrip() + "..."

    draw.rectangle([x_L, y_T, x_R, y_B], outline=BORDER_GREY, width=1)

    veg_size = mmx(6)
    veg_x = x_R - mmx(1) - veg_size
    veg_y = y_T + mmx(1)
    _draw_veg_mark_png(draw, veg_x, veg_y, veg_size, is_veg)

    pname_x = x_L + mmx(2)
    pname_y = y_T + mmx(2)
    pname_max_w = veg_x - mmx(2) - pname_x
    pname_disp = _trunc(product_name, f_name, pname_max_w)
    draw.text((pname_x, pname_y), pname_disp, font=f_name, fill=TEXT)

    fssai_y = pname_y + ptx(19)
    fssai_lab = "FSSAI Lic. No: "
    w_lab = _pil_text_width(draw, fssai_lab, f_lic_lab)
    avail = veg_x - mmx(1) - pname_x - w_lab
    lic_disp = _trunc(license_no, f_lic, max(mmx(10), avail))
    total_w = w_lab + _pil_text_width(draw, lic_disp, f_lic)
    fssai_x = max(pname_x, veg_x - mmx(1) - total_w)
    draw.text((fssai_x, fssai_y), fssai_lab, font=f_lic_lab, fill=TEXT)
    draw.text((fssai_x + w_lab, fssai_y), lic_disp, font=f_lic, fill=TEXT)

    draw.line(
        [(x_L + mmx(2), y_header_bot), (x_R - mmx(2), y_header_bot)],
        fill=GOLD,
        width=2,
    )

    col_div_x = x_lcol_R + GAP // 2
    draw.line(
        [
            (col_div_x, y_header_bot + mmx(1)),
            (col_div_x, y_content_bot - mmx(1)),
        ],
        fill=COL_DIV,
        width=1,
    )

    x_l_text = x_lcol_L + mmx(2)
    x_l_right = x_lcol_R - mmx(1)
    left_wrap_w = x_l_right - x_l_text

    def draw_section_left(y, title, body_lines, body_font, body_lead):
        draw.text((x_l_text, y), title, font=f_sect, fill=TEXT)
        y += ptx(11)
        for ln in body_lines:
            draw.text((x_l_text, y), ln, font=body_font, fill=TEXT)
            y += body_lead
        return y + ptx(5)

    y_l = y_main_top + mmx(1)

    ing_lines = _pil_wrap(ingredients, f_body, left_wrap_w, draw) or [ingredients]
    y_l = draw_section_left(y_l, "Ingredients:", ing_lines, f_body, ptx(10))

    alg_lines = _pil_wrap(allergen_text, f_body_b, left_wrap_w, draw) or [
        allergen_text
    ]
    y_l = draw_section_left(y_l, "Allergens:", alg_lines, f_body_b, ptx(10))

    if custom_warning_text:
        warn_lines = _pil_wrap(custom_warning_text, f_body_sm, left_wrap_w - 8, draw)[:4]
        if warn_lines:
            box_top = y_l
            line_h = ptx(9)
            box_h = max(ptx(22), line_h * len(warn_lines) + ptx(8))
            draw.rectangle(
                [x_l_text, box_top, x_l_text + left_wrap_w, box_top + box_h],
                fill=(255, 243, 224),
                outline=(245, 124, 0),
                width=1,
            )
            wy = box_top + ptx(4)
            for ln in warn_lines:
                draw.text((x_l_text + 4, wy), ln, font=f_body_sm, fill=(120, 70, 0))
                wy += line_h
            y_l = box_top + box_h + ptx(5)

    mfr_lines = []
    if mfr_name:
        mfr_lines.append(mfr_name)
    if mfr_addr:
        mfr_lines.extend(_pil_wrap(mfr_addr, f_body_sm, left_wrap_w, draw))
    if not mfr_lines:
        mfr_lines = ["Not specified"]
    y_l = draw_section_left(
        y_l, "Manufacturer & Packed By:", mfr_lines, f_body_sm, ptx(9.5)
    )

    if phone or email:
        if phone and email:
            care_text = f"Ph: {phone} | {email}"
        elif phone:
            care_text = f"Ph: {phone}"
        else:
            care_text = email
        care_lines = _pil_wrap(care_text, f_body_sm, left_wrap_w, draw) or [care_text]
        y_l = draw_section_left(
            y_l, "Consumer Care:", care_lines, f_body_sm, ptx(9.5)
        )

    storage_lines = _pil_wrap(storage, f_body, left_wrap_w, draw) or [storage]
    draw_section_left(y_l, "Storage:", storage_lines, f_body, ptx(10))

    x_r_text = x_rcol_L
    right_w_inner = x_rcol_R - x_rcol_L

    y_r = y_main_top + mmx(1)
    draw.text(
        (x_r_text, y_r),
        "Nutrition Information (Per 100g)",
        font=f_sect,
        fill=TEXT,
    )
    y_r += ptx(10)
    draw.text(
        (x_r_text, y_r),
        "* % RDA based on 2000 kcal diet",
        font=f_tbl_note,
        fill=TEXT,
    )
    y_r += ptx(8)

    col_val_w = ptx(38)
    col_rda_w = ptx(26)
    col_nut_w = right_w_inner - col_val_w - col_rda_w
    x_c0 = x_r_text
    x_c1 = x_c0 + col_nut_w
    x_c2 = x_c1 + col_val_w
    x_c3 = x_c2 + col_rda_w

    calories = data.get("calories", 0)
    protein = data.get("protein", 0)
    carbs = data.get("carbs", 0)
    sugar = data.get("sugar", 0)
    added_sugars = data.get("added_sugars", 0)
    total_fat = data.get("total_fat", 0)
    saturated_fat = data.get("saturated_fat", 0)
    trans_fat = data.get("trans_fat", 0)
    sodium = data.get("sodium", 0)

    header_row = ("Nutrient", "Per 100g", "%RDA")
    data_rows = [
        ("Energy", _fmt_num(calories, "kcal"), _pct(calories, 2000)),
        ("Protein", _fmt_num(protein, "g"), _pct(protein, 60)),
        ("Carbohydrates", _fmt_num(carbs, "g"), _pct(carbs, 300)),
        ("Total Sugars", _fmt_num(sugar, "g"), "-"),
        ("Added Sugars", _fmt_num(added_sugars, "g"), "-"),
        ("Total Fat", _fmt_num(total_fat, "g"), _pct(total_fat, 67)),
        ("Saturated Fat", _fmt_num(saturated_fat, "g"), _pct(saturated_fat, 22)),
        ("Trans Fat", _fmt_num(trans_fat, "g"), "-"),
        ("Sodium", _fmt_num(sodium, "mg"), _pct(sodium, 2000)),
    ]
    all_rows = [header_row] + data_rows
    nrows = len(all_rows)
    table_top = y_r
    avail_h = (y_content_bot - mmx(1)) - table_top
    row_h = max(ptx(10), min(ptx(12.5), int(avail_h / nrows)))
    table_h = row_h * nrows

    draw.rectangle(
        [x_c0, table_top, x_c3, table_top + row_h], fill=TABLE_HEAD_BG
    )
    draw.rectangle(
        [x_c0, table_top, x_c3, table_top + table_h],
        outline=BLACK,
        width=1,
    )
    for i in range(1, nrows):
        yy = table_top + i * row_h
        draw.line([(x_c0, yy), (x_c3, yy)], fill=BLACK, width=1)
    draw.line(
        [(x_c1, table_top), (x_c1, table_top + table_h)], fill=BLACK, width=1
    )
    draw.line(
        [(x_c2, table_top), (x_c2, table_top + table_h)], fill=BLACK, width=1
    )

    cell_pad_top = max(2, (row_h - ptx(6.5)) // 2 - 1)
    for i, (a, b, c_) in enumerate(all_rows):
        yy = table_top + i * row_h
        fnt = f_tbl_h if i == 0 else f_tbl
        a_disp = _trunc(a, fnt, col_nut_w - 6)
        b_disp = _trunc(b, fnt, col_val_w - 6)
        c_disp = _trunc(c_, fnt, col_rda_w - 6)
        draw.text((x_c0 + 3, yy + cell_pad_top), a_disp, font=fnt, fill=TEXT)
        draw.text((x_c1 + 3, yy + cell_pad_top), b_disp, font=fnt, fill=TEXT)
        draw.text((x_c2 + 3, yy + cell_pad_top), c_disp, font=fnt, fill=TEXT)

    text_L = x_L + mmx(2)
    text_R_limit = qr_L - mmx(2)
    text_w = text_R_limit - text_L

    # PDF row baselines sit at 32/28/24 mm from the bottom. In PIL draw.text
    # the y arg is the top of the text bbox, so lift each row by the font
    # ascent (~82% of the font px size) so the visible text lines up with the
    # PDF baselines and clears the barcode placeholder below.
    _row_ascent = int(round(ptx(8) * 0.82))
    row1_top = H - mmx(32) - _row_ascent
    row2a_top = H - mmx(28) - _row_ascent
    row2b_top = H - mmx(24) - _row_ascent

    row1_text = f"NET QTY: {net_qty}    MRP: Rs. {mrp_rs} (Incl. of all taxes)"
    row2a_text = f"Best Before: {best_before}"
    row2b_text = f"Batch: {batch_no}    MFG: {mfg_date}"

    draw.text(
        (text_L, row1_top),
        _trunc(row1_text, f_row, text_w),
        font=f_row,
        fill=BLACK,
    )
    draw.text(
        (text_L, row2a_top),
        _trunc(row2a_text, f_row, text_w),
        font=f_row,
        fill=BLACK,
    )
    draw.text(
        (text_L, row2b_top),
        _trunc(row2b_text, f_row, text_w),
        font=f_row,
        fill=BLACK,
    )

    bc_L = mmx(8)
    bc_top_y = H - mmx(15) - mmx(8)
    bc_R = bc_L + mmx(40)
    bc_bot_y = H - mmx(15)
    draw.rectangle(
        [bc_L, bc_top_y, bc_R, bc_bot_y],
        fill=GREY_FILL,
        outline=GREY_OUT,
        width=2,
    )
    bc_text = "Barcode appears after payment"
    btw = _pil_text_width(draw, bc_text, f_box)
    try:
        bb = draw.textbbox((0, 0), bc_text, font=f_box)
        bth = bb[3] - bb[1]
    except (AttributeError, TypeError):
        bth = ptx(8)
    draw.text(
        (
            (bc_L + bc_R) // 2 - btw // 2,
            (bc_top_y + bc_bot_y) // 2 - bth // 2,
        ),
        bc_text,
        font=f_box,
        fill=(80, 80, 80),
    )

    draw.rectangle(
        [qr_L, qr_top, qr_R, qr_bot],
        fill=GREY_FILL,
        outline=GREY_OUT,
        width=2,
    )
    qr_lines = ["QR code", "appears", "after payment"]
    line_h = ptx(9)
    total_h = line_h * len(qr_lines)
    y0 = (qr_top + qr_bot) // 2 - total_h // 2
    for i, ln in enumerate(qr_lines):
        lw = _pil_text_width(draw, ln, f_box)
        draw.text(
            ((qr_L + qr_R) // 2 - lw // 2, y0 + i * line_h),
            ln,
            font=f_box,
            fill=(80, 80, 80),
        )

    cap_text = "Scan to create label"
    ctw = _pil_text_width(draw, cap_text, f_qrcap)
    draw.text(
        ((qr_L + qr_R) // 2 - ctw // 2, qr_bot + mmx(3)),
        cap_text,
        font=f_qrcap,
        fill=GREY_TEXT,
    )

    watermark = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    wm_font = _pil_font(48, bold=True)
    wm_text = "PREVIEW ONLY - PAY Rs.99 TO DOWNLOAD"
    tmp_draw = ImageDraw.Draw(watermark)
    tw = _pil_text_width(tmp_draw, wm_text, wm_font)
    try:
        bb2 = tmp_draw.textbbox((0, 0), wm_text, font=wm_font)
        th = bb2[3] - bb2[1]
    except (AttributeError, TypeError):
        th = 56
    pad = 40
    text_layer = Image.new(
        "RGBA", (int(tw) + pad * 2, int(th) + pad * 2), (0, 0, 0, 0)
    )
    td = ImageDraw.Draw(text_layer)
    td.text((pad, pad), wm_text, font=wm_font, fill=(255, 0, 0, 77))
    rotated = text_layer.rotate(45, resample=Image.BICUBIC, expand=True)
    rw, rh = rotated.size
    for cy in [int(H * 0.22), int(H * 0.5), int(H * 0.78)]:
        watermark.alpha_composite(
            rotated, dest=(W // 2 - rw // 2, cy - rh // 2)
        )

    final = Image.alpha_composite(base, watermark).convert("RGB")

    buf = BytesIO()
    final.save(buf, format="PNG", dpi=(72, 72), optimize=True)
    return buf.getvalue()


def generate_pdf(
    product_name,
    ingredients,
    allergens,
    calories,
    protein,
    carbs,
    sugar,
    quantity,
    license_no,
    manufacture_date,
    best_before,
    manufacturer_name,
    manufacturer_address,
    mrp,
    batch_number,
    storage_instructions,
    include_fssai_logo,
    is_vegetarian,
    consumer_phone,
    consumer_email,
    total_fat=0,
    saturated_fat=0,
    trans_fat=0,
    sodium=0,
    added_sugars=0,
):
    _ = include_fssai_logo
    data = {
        "product_name": product_name,
        "ingredients": ingredients,
        "allergens": allergens,
        "calories": calories,
        "protein": protein,
        "carbs": carbs,
        "sugar": sugar,
        "total_fat": total_fat,
        "saturated_fat": saturated_fat,
        "trans_fat": trans_fat,
        "sodium": sodium,
        "added_sugars": added_sugars,
        "quantity": quantity,
        "license_no": license_no,
        "manufacture_date": manufacture_date,
        "best_before": best_before,
        "manufacturer_name": manufacturer_name,
        "manufacturer_address": manufacturer_address,
        "mrp": mrp,
        "batch_number": batch_number,
        "storage_instructions": storage_instructions,
        "is_vegetarian": is_vegetarian,
        "consumer_phone": consumer_phone,
        "consumer_email": consumer_email,
    }
    PDF_PATH.write_bytes(generate_premium_label(data))
    return PDF_PATH


def build_label_html(
    product_name,
    is_vegetarian,
    license_no,
    net_qty_display,
    mrp_rs,
    ingredients_text,
    allergens_list,
    total_calories,
    total_protein,
    total_carbs,
    total_sugar,
    batch_number,
    manufacture_date,
    best_before,
    manufacturer_name,
    manufacturer_address,
    storage_instructions,
    consumer_phone,
    consumer_email,
):
    # HTML_LABEL_VERSION = PDF_LABEL_VERSION = "v4"
    name = (product_name or "").strip() or "Not specified"
    safe_name = html.escape(name)
    lic = (license_no or "").strip() or "Not provided"
    safe_lic = html.escape(lic)
    safe_qty = html.escape(net_qty_display or "Not specified")
    safe_mrp_rs = html.escape(mrp_rs or "—")
    safe_ing = html.escape((ingredients_text or "").strip() or "Not provided")
    if allergens_list:
        alg = ", ".join(
            html.escape(a.strip().replace("_", " ").title()) for a in allergens_list
        )
        allergens_html = (
            f'<span style="font-size:8px;font-weight:bold;color:#000000;">'
            f"Allergens: {alg}</span>"
        )
    else:
        allergens_html = (
            '<span style="font-size:8px;font-weight:bold;color:#000000;">'
            "Allergens: None</span>"
        )
    veg_sym = SVG_VEG_SYMBOL if is_vegetarian else SVG_NONVEG_SYMBOL
    safe_batch = html.escape((batch_number or "").strip() or "Not specified")
    safe_mfg = html.escape((manufacture_date or "").strip() or "Not specified")
    safe_bb = html.escape((best_before or "").strip() or "Not specified")
    mfr_html = (manufacturer_name or "").strip()
    addr_html = format_address_display(manufacturer_address).strip()
    _addr_cap_html = 500
    if addr_html and len(addr_html) > _addr_cap_html:
        addr_html = addr_html[:_addr_cap_html].rstrip() + "…"
    manufacturer_div = (
        f'  <div style="font-size:8px;"><strong>Manufacturer:</strong> '
        f"{html.escape(mfr_html)}</div>\n"
        if mfr_html
        else ""
    )
    addr_margin = "margin-top:4px;" if mfr_html else ""
    address_div = (
        f'  <div style="font-size:8px;{addr_margin}"><strong>Address:</strong> '
        f"{html.escape(addr_html)}</div>\n"
        if addr_html
        else ""
    )
    phone_h = (consumer_phone or "").strip()
    email_h = (consumer_email or "").strip()
    if phone_h and email_h:
        care_line2_h = f"Ph: {html.escape(phone_h)}  |  {html.escape(email_h)}"
    elif phone_h:
        care_line2_h = f"Ph: {html.escape(phone_h)}"
    elif email_h:
        care_line2_h = html.escape(email_h)
    else:
        care_line2_h = ""
    consumer_div = (
        f'  <div style="font-size:7px;color:#000000;line-height:1.4;">'
        f"<strong>Consumer Care:</strong><br/>{care_line2_h}</div>\n"
        if care_line2_h
        else ""
    )
    safe_storage = html.escape(
        (storage_instructions or "").strip() or "Store in a cool and dry place"
    )
    cal_s = html.escape(str(total_calories))
    prot_s = html.escape(str(total_protein))
    carb_s = html.escape(str(total_carbs))
    sugar_s = html.escape(str(total_sugar))

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/></head><body style="margin:0;">
<style>
.label-box {{
  width: 400px;
  border: 2px solid black;
  padding: 12px;
  font-family: Arial, sans-serif;
  font-size: 11px;
  line-height: 1.6;
  word-wrap: break-word;
  box-sizing: border-box;
  color: #000000;
}}
.label-hr {{
  border: none;
  border-top: 0.5px solid #ccc;
  margin: 4px 0 3px 0;
}}
table.nutrition {{
  width: 100%;
  border-collapse: collapse;
  font-size: 10px;
  margin-top: 4px;
}}
table.nutrition td, table.nutrition th {{
  border: 1px solid #000000;
  padding: 3px 6px;
  color: #000000;
}}
table.nutrition th {{
  background: #ffffff;
  font-weight: bold;
}}
.label-batch-block {{
  font-size: 7px;
  line-height: 1.5;
  color: #000000;
}}
</style>
<div class="label-box">
  <div style="
  display: grid;
  grid-template-columns: 1fr 50px;
  grid-template-rows: auto auto;
  gap: 0;
  margin-bottom: 6px;
">
  <div style="
    grid-column: 1;
    grid-row: 1;
    text-align: center;
    font-size: 16px;
    font-weight: bold;
    padding: 4px 0;
    color: #000000;
  ">
    {safe_name} &nbsp; {veg_sym}
  </div>

  <div style="
    grid-column: 2;
    grid-row: 1 / span 2;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    justify-content: flex-start;
    padding-top: 4px;
    text-align: right;
    font-size: 7px;
    color: #000000;
    max-width: 50px;
    line-height: 1.25;
    word-wrap: break-word;
  ">
    FSSAI Lic. No: {safe_lic}
  </div>

  <div style="
    grid-column: 1;
    grid-row: 2;
    display: flex;
    justify-content: space-between;
    padding: 4px 6px 4px 4px;
    font-size: 9px;
    color: #000000;
  ">
    <span><b>Net Qty:</b> {safe_qty}</span>
    <span><b>MRP:</b> Rs.{safe_mrp_rs} (Incl. of all taxes)</span>
  </div>
</div>
  <hr class="label-hr"/>
  <div><span style="font-size:9px;font-weight:bold;color:#000000;">Ingredients:</span>
    <div style="font-size:8px;margin-top:4px;white-space:pre-wrap;color:#000000;">{safe_ing}</div></div>
  <div>{allergens_html}</div>
  <hr class="label-hr"/>
  <div><span style="font-size:9px;font-weight:bold;color:#000000;">Nutrition Information (Per 100 g)</span>
  <div style="font-size:6px;font-style:italic;color:#000000;margin-top:2px;">*Values are approximate</div>
  <table class="nutrition">
    <tr><th>Nutrient</th><th>Per 100g</th></tr>
    <tr><td>Energy (kcal)</td><td>{cal_s}</td></tr>
    <tr><td>Protein (g)</td><td>{prot_s}</td></tr>
    <tr><td>Carbohydrates (g)</td><td>{carb_s}</td></tr>
    <tr><td>Sugar (g)</td><td>{sugar_s}</td></tr>
  </table></div>
  <hr class="label-hr"/>
  <div class="label-batch-block">
    <div><strong>Batch No:</strong> {safe_batch}</div>
    <div><strong>MFG Date:</strong> {safe_mfg}</div>
    <div><strong>Best Before:</strong> {safe_bb}</div>
  </div>
{manufacturer_div}{address_div}  <div style="font-size:8px;color:#000000;"><strong>Storage:</strong> {safe_storage}</div>
{consumer_div}</div>
</body></html>"""


st.title("Get FSSAI compliant label for ₹99")
st.write("")

init_profile_session_state()

_debug_q = st.query_params.get("debug", "")
if isinstance(_debug_q, (list, tuple)):
    _debug_q = _debug_q[0] if _debug_q else ""
DEBUG_MODE = str(_debug_q).strip().lower() in {"1", "true", "yes", "y", "on"}

STORAGE_OPTIONS = [
    "Store in a cool and dry place",
    "Refrigerate after opening",
    "Keep frozen",
]

DEFAULT_INGREDIENT_PERCENTAGES = [
    {"Ingredient Name": "Red Chilli Powder", "Percentage (%)": 50.0},
    {"Ingredient Name": "Mustard Oil", "Percentage (%)": 20.0},
    {"Ingredient Name": "Ginger", "Percentage (%)": 5.0},
    {"Ingredient Name": "Garlic", "Percentage (%)": 5.0},
    {"Ingredient Name": "Turmeric", "Percentage (%)": 5.0},
    {"Ingredient Name": "Salt", "Percentage (%)": 15.0},
]
if "ingredients_list" not in st.session_state:
    st.session_state.ingredients_list = []
if "search_counter" not in st.session_state:
    st.session_state.search_counter = 0


def _display_name_from_key(key):
    return " ".join(word.capitalize() for word in str(key).split())


VERIFIED_DB = {
    # Spices & Seeds
    "ajwain": {"calories":305,"protein":16,"carbs":50,"sugar":0,"fat":14,"saturated_fat":0.7,"trans_fat":0,"sodium":10},
    "asafoetida": {"calories":297,"protein":4,"carbs":67.8,"sugar":0,"fat":1.1,"saturated_fat":0.3,"trans_fat":0,"sodium":1400},
    "black pepper": {"calories":251,"protein":10.4,"carbs":63.9,"sugar":0.6,"fat":3.3,"saturated_fat":0.9,"trans_fat":0,"sodium":20},
    "cardamom": {"calories":311,"protein":11,"carbs":68,"sugar":0,"fat":6.7,"saturated_fat":0.8,"trans_fat":0,"sodium":18},
    "carom seeds": {"calories":305,"protein":16,"carbs":50,"sugar":0,"fat":14,"saturated_fat":0.7,"trans_fat":0,"sodium":10},
    "cinnamon": {"calories":247,"protein":4,"carbs":81,"sugar":2.2,"fat":1.2,"saturated_fat":0.3,"trans_fat":0,"sodium":10},
    "coriander": {"calories":23,"protein":2.1,"carbs":3.7,"sugar":0,"fat":0.5,"saturated_fat":0,"trans_fat":0,"sodium":46},
    "cumin": {"calories":375,"protein":18,"carbs":44,"sugar":2.3,"fat":22,"saturated_fat":1.5,"trans_fat":0,"sodium":168},
    "fennel seeds": {"calories":345,"protein":15.8,"carbs":52.3,"sugar":0,"fat":14.9,"saturated_fat":0.5,"trans_fat":0,"sodium":88},
    "fenugreek seeds": {"calories":323,"protein":23,"carbs":58.4,"sugar":0,"fat":6.4,"saturated_fat":1.5,"trans_fat":0,"sodium":67},
    "garam masala": {
        "energy": 346,
        "protein": 13.0,
        "carbohydrates": 42.0,
        "total_sugars": 0.5,
        "added_sugars": 0,
        "total_fat": 14.0,
        "saturated_fat": 2.0,
        "trans_fat": 0,
        "sodium": 36,
    },
    "hing": {"calories":297,"protein":4,"carbs":67.8,"sugar":0,"fat":1.1,"saturated_fat":0.3,"trans_fat":0,"sodium":1400},
    "kalonji": {"calories":400,"protein":17,"carbs":45,"sugar":0,"fat":22,"saturated_fat":3,"trans_fat":0,"sodium":80},
    "mustard seeds": {"calories":508,"protein":26.1,"carbs":28.1,"sugar":6.8,"fat":36.2,"saturated_fat":2.0,"trans_fat":0,"sodium":13},
    "nigella seeds": {"calories":400,"protein":17,"carbs":45,"sugar":0,"fat":22,"saturated_fat":3,"trans_fat":0,"sodium":80},
    "red chilli powder": {"calories":282,"protein":13,"carbs":50,"sugar":7,"fat":14,"saturated_fat":2,"trans_fat":0,"sodium":93},
    "turmeric": {"calories":354,"protein":8,"carbs":65,"sugar":3.2,"fat":10,"saturated_fat":3,"trans_fat":0,"sodium":38},

    # Main Pickle Bases - Veg & Non-Veg
    "amla": {"calories":44,"protein":0.9,"carbs":10.2,"sugar":0,"fat":0.6,"saturated_fat":0.1,"trans_fat":0,"sodium":1},
    "carrot": {"calories":41,"protein":0.9,"carbs":9.6,"sugar":4.7,"fat":0.2,"saturated_fat":0,"trans_fat":0,"sodium":69},
    "cauliflower": {"calories":25,"protein":1.9,"carbs":5,"sugar":1.9,"fat":0.3,"saturated_fat":0.1,"trans_fat":0,"sodium":30},
    "chicken": {"calories":239,"protein":27.3,"carbs":0,"sugar":0,"fat":13.6,"saturated_fat":3.8,"trans_fat":0.1,"sodium":82},
    "chicken masala": {
        "energy": 289,
        "protein": 14.0,
        "carbohydrates": 30.0,
        "total_sugars": 0,
        "added_sugars": 0,
        "total_fat": 12.8,
        "saturated_fat": 0,
        "trans_fat": 0,
        "sodium": 2150,
    },
    "egg": {
        "energy": 148,
        "protein": 12.4,
        "carbohydrates": 0.96,
        "total_sugars": 0.2,
        "added_sugars": 0,
        "total_fat": 9.96,
        "saturated_fat": 3.2,
        "trans_fat": 0,
        "sodium": 129,
    },
    "fish": {"calories":97,"protein":16.5,"carbs":0,"sugar":0,"fat":2.9,"saturated_fat":0.6,"trans_fat":0,"sodium":60},
    "garlic": {"calories":149,"protein":6.4,"carbs":33,"sugar":1,"fat":0.5,"saturated_fat":0.1,"trans_fat":0,"sodium":17},
    "ginger": {"calories":80,"protein":1.8,"carbs":18,"sugar":1.7,"fat":0.8,"saturated_fat":0.2,"trans_fat":0,"sodium":13},
    "gongura": {"calories":43,"protein":3.2,"carbs":7.5,"sugar":0,"fat":0.4,"saturated_fat":0,"trans_fat":0,"sodium":6},
    "gooseberry": {"calories":44,"protein":0.9,"carbs":10.2,"sugar":0,"fat":0.6,"saturated_fat":0.1,"trans_fat":0,"sodium":1},
    "green chilli": {"calories":40,"protein":2,"carbs":9,"sugar":5.1,"fat":0.4,"saturated_fat":0,"trans_fat":0,"sodium":9},
    "lemon": {"calories":29,"protein":1.1,"carbs":9.3,"sugar":2.5,"fat":0.3,"saturated_fat":0,"trans_fat":0,"sodium":2},
    "lime": {"calories":30,"protein":0.7,"carbs":10.5,"sugar":1.7,"fat":0.2,"saturated_fat":0,"trans_fat":0,"sodium":2},
    "mango": {"calories":60,"protein":0.8,"carbs":15,"sugar":13.7,"fat":0.4,"saturated_fat":0.1,"trans_fat":0,"sodium":1},
    "mango raw": {"calories":60,"protein":0.8,"carbs":15,"sugar":13.7,"fat":0.4,"saturated_fat":0.1,"trans_fat":0,"sodium":1},
    "mutton": {"calories":143,"protein":27.1,"carbs":0,"sugar":0,"fat":3.0,"saturated_fat":0.9,"trans_fat":0,"sodium":86},
    "onion": {"calories":40,"protein":1.1,"carbs":9.3,"sugar":4.2,"fat":0.1,"saturated_fat":0,"trans_fat":0,"sodium":4},
    "prawn": {"calories":99,"protein":24,"carbs":0.2,"sugar":0,"fat":0.3,"saturated_fat":0.1,"trans_fat":0,"sodium":111},
    "prawns": {"calories":99,"protein":24,"carbs":0.2,"sugar":0,"fat":0.3,"saturated_fat":0.1,"trans_fat":0,"sodium":111},
    "roselle leaves": {"calories":43,"protein":3.2,"carbs":7.5,"sugar":0,"fat":0.4,"saturated_fat":0,"trans_fat":0,"sodium":6},
    "tamarind": {"calories":239,"protein":2.8,"carbs":62.5,"sugar":57.4,"fat":0.6,"saturated_fat":0.3,"trans_fat":0,"sodium":28},
    "tomato": {"calories":18,"protein":0.9,"carbs":3.9,"sugar":2.6,"fat":0.2,"saturated_fat":0,"trans_fat":0,"sodium":5},

    # Oils & Fats
    "coconut oil": {"calories":862,"protein":0,"carbs":0,"sugar":0,"fat":100,"saturated_fat":86,"trans_fat":0,"sodium":0},
    "ghee": {"calories":900,"protein":0,"carbs":0,"sugar":0,"fat":100,"saturated_fat":62,"trans_fat":4,"sodium":2},
    "mustard oil": {"calories":884,"protein":0,"carbs":0,"sugar":0,"fat":100,"saturated_fat":12,"trans_fat":0,"sodium":0},
    "oil": {"calories":884,"protein":0,"carbs":0,"sugar":0,"fat":100,"saturated_fat":14,"trans_fat":0.5,"sodium":0},
    "peanut oil": {"calories":884,"protein":0,"carbs":0,"sugar":0,"fat":100,"saturated_fat":17,"trans_fat":0,"sodium":0},

    # Flours & Grains
    "atta": {"calories":340,"protein":13,"carbs":71,"sugar":0,"fat":2.5,"saturated_fat":0.4,"trans_fat":0,"sodium":2},
    "besan": {"calories":387,"protein":22,"carbs":58,"sugar":10,"fat":6.7,"saturated_fat":0.9,"trans_fat":0,"sodium":64},
    "corn flour": {"calories":381,"protein":6.9,"carbs":79,"sugar":0,"fat":3.9,"saturated_fat":0.6,"trans_fat":0,"sodium":5},
    "gram flour": {"calories":387,"protein":22,"carbs":58,"sugar":10,"fat":6.7,"saturated_fat":0.9,"trans_fat":0,"sodium":64},
    "maida": {"calories":364,"protein":10,"carbs":76,"sugar":0.3,"fat":1,"saturated_fat":0.2,"trans_fat":0,"sodium":2},
    "rava": {"calories":360,"protein":12,"carbs":73,"sugar":0.4,"fat":1.2,"saturated_fat":0.2,"trans_fat":0,"sodium":1},
    "rice": {"calories":130,"protein":2.7,"carbs":28,"sugar":0,"fat":0.3,"saturated_fat":0.1,"trans_fat":0,"sodium":1},
    "rice flour": {"calories":366,"protein":5.9,"carbs":80,"sugar":0,"fat":1.4,"saturated_fat":0.4,"trans_fat":0,"sodium":0},
    "wheat": {"calories":340,"protein":13,"carbs":71,"sugar":0,"fat":2.5,"saturated_fat":0.4,"trans_fat":0,"sodium":2},

    # Dairy & Others
    "butter": {"calories":717,"protein":0.85,"carbs":0.1,"sugar":0.1,"fat":81,"saturated_fat":51,"trans_fat":3.3,"sodium":643},
    "cheese": {"calories":402,"protein":25,"carbs":1.3,"sugar":0.5,"fat":33,"saturated_fat":21,"trans_fat":1.1,"sodium":621},
    "cream": {"calories":340,"protein":2.1,"carbs":2.8,"sugar":2.8,"fat":36,"saturated_fat":23,"trans_fat":1.1,"sodium":38},
    "milk": {"calories":42,"protein":3.4,"carbs":5,"sugar":5,"fat":3.3,"saturated_fat":1.9,"trans_fat":0,"sodium":44},
    "milk powder": {"calories":496,"protein":26,"carbs":38,"sugar":38,"fat":27,"saturated_fat":17,"trans_fat":0,"sodium":371},
    "paneer": {"calories":296,"protein":18,"carbs":1.2,"sugar":0,"fat":20,"saturated_fat":13,"trans_fat":0,"sodium":18},
    "yogurt": {"calories":61,"protein":3.5,"carbs":4.7,"sugar":4.7,"fat":3.3,"saturated_fat":2.1,"trans_fat":0,"sodium":46},
    "curd": {"calories":61,"protein":3.5,"carbs":4.7,"sugar":4.7,"fat":3.3,"saturated_fat":2.1,"trans_fat":0,"sodium":46},
    "perugu": {"calories":61,"protein":3.5,"carbs":4.7,"sugar":4.7,"fat":3.3,"saturated_fat":2.1,"trans_fat":0,"sodium":46},
    "condensed milk": {"calories":321,"protein":7.9,"carbs":54,"sugar":54,"fat":8.7,"saturated_fat":5.5,"trans_fat":0,"sodium":127},

    # Pulses & Nuts
    "almonds": {"calories":579,"protein":21.2,"carbs":21.6,"sugar":4.4,"fat":49.9,"saturated_fat":3.8,"trans_fat":0,"sodium":1},
    "cashews": {"calories":553,"protein":18,"carbs":30,"sugar":5.9,"fat":44,"saturated_fat":7.8,"trans_fat":0,"sodium":12},
    "chana dal": {"calories":360,"protein":20,"carbs":61,"sugar":8,"fat":5.9,"saturated_fat":0.8,"trans_fat":0,"sodium":20},
    "moong dal": {"calories":347,"protein":24,"carbs":63,"sugar":6,"fat":1.2,"saturated_fat":0.3,"trans_fat":0,"sodium":15},
    "peanuts": {"calories":567,"protein":25.8,"carbs":16,"sugar":4,"fat":49,"saturated_fat":7,"trans_fat":0,"sodium":18},
    "sesame seeds": {"calories":573,"protein":18,"carbs":23,"sugar":0.3,"fat":50,"saturated_fat":7,"trans_fat":0,"sodium":11},
    "toor dal": {"calories":343,"protein":22,"carbs":63,"sugar":6,"fat":1.5,"saturated_fat":0.3,"trans_fat":0,"sodium":17},

    # Sweeteners & Others
    "amchur": {"calories":360,"protein":2.5,"carbs":85,"sugar":45,"fat":0.8,"saturated_fat":0.2,"trans_fat":0,"sodium":7},
    "coconut": {"calories":354,"protein":3.3,"carbs":15,"sugar":6.2,"fat":33,"saturated_fat":30,"trans_fat":0,"sodium":20},
    "coconut milk": {"calories":230,"protein":2.3,"carbs":6,"sugar":3.3,"fat":24,"saturated_fat":21,"trans_fat":0,"sodium":15},
    "curry leaves": {"calories":108,"protein":6.1,"carbs":18.7,"sugar":0,"fat":1,"saturated_fat":0.2,"trans_fat":0,"sodium":15},
    "dates": {"calories":277,"protein":1.8,"carbs":75,"sugar":63,"fat":0.2,"saturated_fat":0,"trans_fat":0,"sodium":1},
    "dry mango powder": {"calories":360,"protein":2.5,"carbs":85,"sugar":45,"fat":0.8,"saturated_fat":0.2,"trans_fat":0,"sodium":7},
    "honey": {"calories":304,"protein":0.3,"carbs":82,"sugar":82,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":4},
    "jaggery": {"calories":383,"protein":0.4,"carbs":98,"sugar":97,"fat":0.1,"saturated_fat":0,"trans_fat":0,"sodium":40},
    "raisins": {"calories":299,"protein":3.1,"carbs":79,"sugar":59,"fat":0.5,"saturated_fat":0.2,"trans_fat":0,"sodium":11},
    "salt": {"calories":0,"protein":0,"carbs":0,"sugar":0,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":38758},
    "sugar": {"calories":387,"protein":0,"carbs":100,"sugar":100,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":1},
    "vinegar": {"calories":18,"protein":0,"carbs":0.4,"sugar":0.4,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":2},
    "water": {"calories":0,"protein":0,"carbs":0,"sugar":0,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":0},

    # Miscellaneous
    "baking powder": {"calories":53,"protein":0,"carbs":28,"sugar":0,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":10600},
    "chocolate": {"calories":546,"protein":4.9,"carbs":60,"sugar":48,"fat":31,"saturated_fat":19,"trans_fat":0.1,"sodium":24},
    "cocoa": {"calories":228,"protein":20,"carbs":58,"sugar":1.8,"fat":14,"saturated_fat":8,"trans_fat":0,"sodium":21},
    "vanilla": {"calories":288,"protein":0,"carbs":13,"sugar":13,"fat":0,"saturated_fat":0,"trans_fat":0,"sodium":9},
    "yeast": {"calories":325,"protein":40,"carbs":38,"sugar":0,"fat":7.6,"saturated_fat":1,"trans_fat":0,"sodium":51},
}
VERIFIED_INGREDIENT_KEYS = sorted(VERIFIED_DB.keys())

current_user_id = get_or_create_user_id()
paid_product_rows = list_paid_products(current_user_id)
product_history_map = {"➕ Create New Product": ""}
for row in paid_product_rows:
    pname = str(row.get("product_name", "")).strip()
    if not pname:
        continue
    expires = str(row.get("expires_at", "")).strip()
    if expires:
        label = f"{pname} (paid, edits till {expires})"
    else:
        label = f"{pname} (paid)"
    # Keep latest visible label if duplicates occur.
    product_history_map[label] = pname

with st.sidebar:
    st.subheader("User profile")
    st.caption("Saved locally — auto-fills each label.")
    prof_name = st.text_input("Manufacturer Name", key="prof_manufacturer_name")
    prof_addr = st.text_input("Manufacturer Address", key="prof_manufacturer_address")
    prof_lic = st.text_input("License Number", key="prof_license_number")
    if st.button("Save profile"):
        save_user_profile(
            {
                "manufacturer_name": prof_name,
                "manufacturer_address": prof_addr,
                "license_number": prof_lic,
            }
        )
        st.success("Profile saved.")

with st.expander("Upload Recipe Image (Coming Soon)", expanded=False):
    st.file_uploader(
        "Upload Recipe Image (Coming Soon)",
        disabled=True,
        help="Placeholder — no backend processing yet.",
    )

if True:
    st.info(
        "You can edit all details after payment. Changing product name requires a new payment."
    )
    st.subheader("Quick label (required fields only)")
    c1, c2 = st.columns(2)
    with c1:
        history_choice = st.selectbox(
            "📦 My Products",
            options=list(product_history_map.keys()),
            key="product_history_choice",
            help="Select an existing paid product to edit, or choose Create New Product.",
        )
        selected_history_product = product_history_map.get(history_choice, "")
        if selected_history_product:
            if st.session_state.get("_last_history_choice") != history_choice:
                st.session_state["product_name"] = selected_history_product
                st.session_state["_last_history_choice"] = history_choice
        else:
            st.session_state["_last_history_choice"] = history_choice
        st.caption("Select existing product to edit, or create new.")
        product_name = st.text_input(
            "Product Name", value="Milk Sweet", key="product_name"
        )
        st.caption(
            "⚠️ Changing product name after payment requires new payment."
        )
        net_quantity = st.text_input(
            "Net Quantity", placeholder="e.g. 200g", key="net_qty"
        )
        mrp = st.text_input(
            "MRP (price)", placeholder="e.g. 29", key="mrp"
        )
    with c2:
        shelf_life_days = st.number_input(
            "Shelf life (days)",
            min_value=1,
            value=30,
            step=1,
        )
        food_type = st.radio(
            "Food type",
            ["Vegetarian", "Non-vegetarian"],
            horizontal=True,
            index=0,
            key="food_type",
        )
        storage_instructions = st.selectbox("Storage instructions", STORAGE_OPTIONS)
        batch_override = st.text_input(
            "Batch No (optional override)",
            placeholder="Leave blank for auto BN-YYYYMMDD-XX",
        )

    # === STEP 3: INGREDIENT SEARCH UI ===
    st.markdown("### Add Ingredients")
    st.caption("Type any ingredient name and **press Enter** to search. Example: type 'c' to see chicken, carrot, curd...")

    search_key = f"search_{st.session_state.search_counter}"
    query = st.text_input(
        "Search ingredients",
        key=search_key,
        placeholder="Type ingredient name and press Enter (e.g., 'o' for onion)",
        label_visibility="collapsed",
    )
    st.info("💡 Tip: Type 1-2 letters and press Enter to see all matching ingredients from our 86-item database")

    # === STEP 4: SHOW CLICKABLE SUGGESTIONS ===
    if query and len(query.strip()) > 0:
        query_lower = query.lower().strip()
        matches = sorted([name for name in VERIFIED_DB.keys() if query_lower in name])

        if matches:
            st.markdown(f"**{len(matches)} ingredients found containing '{query}':**")
            cols = st.columns(4)
            for idx, match_name in enumerate(matches[:32]):
                display_name = _display_name_from_key(match_name)
                col = cols[idx % 4]
                with col:
                    if st.button(
                        display_name,
                        key=f"btn_{match_name}_{idx}_{st.session_state.search_counter}",
                        use_container_width=True,
                        help=f"Click to add {display_name} (verified)",
                    ):
                        if match_name not in [
                            ing.get("key", "") for ing in st.session_state.ingredients_list
                        ]:
                            st.session_state.ingredients_list.append(
                                {
                                    "name": display_name,
                                    "key": match_name,
                                    "is_verified": True,
                                    "percentage": 0.0,
                                }
                            )
                            st.session_state.search_counter += 1
                            st.rerun()
        st.markdown("---")
        if st.button(
            f"➕ Add '{query}' as Custom Ingredient (0 nutrition)",
            key=f"custom_{st.session_state.search_counter}",
            use_container_width=True,
            type="secondary",
        ):
            custom_key = query_lower
            if custom_key not in [
                ing.get("key", "") for ing in st.session_state.ingredients_list
            ]:
                st.session_state.ingredients_list.append(
                    {
                        "name": query.strip(),
                        "key": custom_key,
                        "is_verified": False,
                        "percentage": 0.0,
                    }
                )
                st.session_state.search_counter += 1
                st.rerun()

    # === STEP 5: INGREDIENTS TABLE WITH PERCENTAGES ===
    if st.session_state.ingredients_list:
        st.markdown("---")
        st.markdown("### Current Ingredients")
        st.info(
            "⚠️ **Please enter percentage for the respective ingredient** "
            "(Total must equal 100%)"
        )

        col1, col2, col3 = st.columns([4, 2, 1])
        with col1:
            st.markdown("**Ingredient**")
        with col2:
            st.markdown("**Percentage %**")
        with col3:
            st.markdown("**Action**")

        total_percentage = 0.0
        to_delete = []
        for idx, ingredient in enumerate(st.session_state.ingredients_list):
            col1, col2, col3 = st.columns([4, 2, 1])
            with col1:
                if ingredient.get("is_verified"):
                    st.markdown(f"✓ **{ingredient.get('name', '')}**")
                    st.caption("Verified - auto nutrition")
                else:
                    st.markdown(f"⚠ **{ingredient.get('name', '')}**")
                    st.caption("Custom - nutrition = 0")

            with col2:
                pct = st.number_input(
                    "percentage",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(ingredient.get("percentage", 0)),
                    step=0.1,
                    key=f"pct_{idx}_{ingredient.get('key', '')}",
                    label_visibility="collapsed",
                )
                st.session_state.ingredients_list[idx]["percentage"] = pct
                total_percentage += pct

            with col3:
                if st.button("❌", key=f"del_{idx}", help="Remove"):
                    to_delete.append(idx)

        for idx in sorted(to_delete, reverse=True):
            st.session_state.ingredients_list.pop(idx)
            st.rerun()

        st.markdown("---")
        if abs(total_percentage - 100) < 0.01:
            st.success(f"✓ Total: {total_percentage:.1f}% - Perfect!")
        else:
            st.error(f"⚠ Total: {total_percentage:.1f}% - Must equal 100%")

        custom_items = [ing for ing in st.session_state.ingredients_list if not ing.get("is_verified")]
        if custom_items:
            st.warning(
                f"⚠ {len(custom_items)} custom ingredient(s) will use 0 values in nutrition "
                f"calculation. Names: {', '.join([i.get('name', '') for i in custom_items])}"
            )
    else:
        st.info("👆 Start typing above to add ingredients")

    if st.button("🧹 Clear All Old Data & Start Fresh", type="primary"):
        st.session_state.ingredients_list = []
        st.session_state.search_counter = 0
        st.success("All data cleared! Start fresh below.")
        st.rerun()

    consumer_phone = st.text_input(
        "Consumer care phone",
        placeholder="e.g. 1800-XXX-XXXX",
    )
    consumer_email = st.text_input(
        "Consumer care email",
        placeholder="e.g. support@example.com",
    )

    st.markdown("<p style='color:black;'>click the 'preview label' to see all the changes made above</p>", unsafe_allow_html=True)
    generate_label = st.button("Preview Label")

if "label_data" not in st.session_state:
    st.session_state.label_data = None

if generate_label:
    # Clean ingredients - remove any with 0% or less before label generation.
    original_count = len(st.session_state.get("ingredients_list", []))
    st.session_state.ingredients_list = [
        ing
        for ing in st.session_state.get("ingredients_list", [])
        if float(ing.get("percentage", 0) or 0) > 0
    ]
    removed_count = original_count - len(st.session_state.ingredients_list)
    if removed_count > 0:
        st.warning(
            f"⚠️ Removed {removed_count} ingredient(s) with 0% - they won't appear on label"
        )

    ingredient_rows = []
    custom_ingredients = []
    ingredients_for_label = []
    total_percentage = 0.0
    for ing in st.session_state.ingredients_list:
        name = str(ing.get("name", "")).strip()
        key = str(ing.get("key", "")).strip().lower()
        try:
            pct = float(ing.get("percentage", 0) or 0)
        except (TypeError, ValueError):
            pct = 0.0
        if not name or pct <= 0:
            continue

        is_verified = bool(ing.get("is_verified")) and key in VERIFIED_DB
        ingredient_rows.append(
            {
                "ingredient": name,
                "ingredient_lower": key if is_verified else "",
                "percentage": pct,
                "is_verified": is_verified,
                "is_custom": not is_verified,
            }
        )
        ingredients_for_label.append(name)
        total_percentage += pct
        if not is_verified:
            custom_ingredients.append(name)

    if not ingredient_rows:
        st.error("Add at least one ingredient with a valid percentage.")
    elif abs(total_percentage - 100.0) > 0.01:
        st.error(
            f"Ingredient percentages must total 100%. Current total: {total_percentage:.2f}%"
        )
    else:
        cleaned_ingredients = [
            (r.get("ingredient_lower") or r.get("ingredient", "").lower())
            for r in ingredient_rows
        ]
        ingredients = ", ".join(ingredients_for_label)
        detected_allergens = detect_allergens(cleaned_ingredients)
        nutrition_totals = calculate_nutrition()
        total_calories = round(float(nutrition_totals.get("calories", 0)), 2)
        total_protein = round(float(nutrition_totals.get("protein", 0)), 2)
        total_carbs = round(float(nutrition_totals.get("carbs", 0)), 2)
        total_sugar = round(float(nutrition_totals.get("sugar", 0)), 2)
        total_fat = round(float(nutrition_totals.get("fat", 0)), 2)
        total_saturated_fat = round(float(nutrition_totals.get("saturated_fat", 0)), 2)
        total_trans_fat = round(float(nutrition_totals.get("trans_fat", 0)), 2)
        total_sodium = round(float(nutrition_totals.get("sodium", 0)), 2)
        nutrition_fallback = list(custom_ingredients)
        custom_ingredients = sorted(set(custom_ingredients))
        if custom_ingredients:
            st.warning(
                "Custom ingredients detected (0 nutrition values applied): "
                + ", ".join(custom_ingredients[:6])
                + ("..." if len(custom_ingredients) > 6 else "")
            )
        custom_warning_text = ""
        if custom_ingredients:
            custom_warning_text = (
                "⚠ CUSTOM INGREDIENTS: "
                + ", ".join(custom_ingredients)
                + " - Nutrition values assumed as 0. "
                + "For FSSAI compliance, obtain lab testing for accurate values."
            )

        salt_pct = round(
            sum(
                float(r.get("percentage", 0))
                for r in ingredient_rows
                if "salt" in str(r.get("ingredient_lower", ""))
            ),
            2,
        )

        mfg_date = datetime.now().date()
        best_before_date = mfg_date + timedelta(days=int(shelf_life_days))
        manufacture_str = mfg_date.strftime("%d-%m-%Y")
        best_before_str = best_before_date.strftime("%d-%m-%Y")

        if batch_override.strip():
            final_batch = batch_override.strip()
        else:
            final_batch = next_batch_number()

        license_number = st.session_state.get("prof_license_number", "")
        manufacturer_name = st.session_state.get("prof_manufacturer_name", "")
        manufacturer_address = st.session_state.get("prof_manufacturer_address", "")

        net_qty_value = st.session_state.get("net_qty", net_quantity) or ""
        mrp_value = st.session_state.get("mrp", mrp) or ""

        st.session_state.label_data = {
            "product_name": product_name,
            "ingredients": ingredients,
            "ingredient_rows": ingredient_rows,
            "cleaned_ingredients": cleaned_ingredients,
            "allergens": detected_allergens,
            "total_percentage": total_percentage,
            "custom_ingredients": custom_ingredients,
            "salt_percentage": salt_pct,
            "total_calories": total_calories,
            "total_protein": total_protein,
            "total_carbs": total_carbs,
            "total_sugar": total_sugar,
            "total_fat": total_fat,
            "total_saturated_fat": total_saturated_fat,
            "total_trans_fat": total_trans_fat,
            "total_sodium": total_sodium,
            "nutrition_fallback": nutrition_fallback,
            "is_vegetarian": food_type == "Vegetarian",
            "quantity": net_qty_value,
            "license_no": license_number,
            "manufacture_date": manufacture_str,
            "best_before": best_before_str,
            "shelf_life_days": int(shelf_life_days),
            "include_fssai_logo": False,
            "manufacturer_name": manufacturer_name,
            "manufacturer_address": manufacturer_address,
            "mrp": mrp_value,
            "batch_number": final_batch,
            "storage_instructions": storage_instructions,
            "consumer_phone": consumer_phone,
            "consumer_email": consumer_email,
            "custom_warning_text": custom_warning_text,
        }

if st.session_state.label_data:
    label_data = st.session_state.label_data
    product_name = label_data.get("product_name", "")
    ingredients = label_data.get("ingredients", "")
    ingredient_rows = label_data.get("ingredient_rows", [])
    cleaned_ingredients = label_data.get("cleaned_ingredients", [])
    allergens = label_data.get("allergens", [])
    total_percentage = float(label_data.get("total_percentage", 0) or 0)
    custom_ingredients = label_data.get("custom_ingredients", [])
    custom_warning_text = label_data.get("custom_warning_text", "")
    salt_percentage = float(label_data.get("salt_percentage", 0) or 0)
    total_calories = label_data.get("total_calories", 0)
    total_protein = label_data.get("total_protein", 0)
    total_carbs = label_data.get("total_carbs", 0)
    total_sugar = label_data.get("total_sugar", 0)
    total_fat = label_data.get("total_fat", 0)
    total_saturated_fat = label_data.get("total_saturated_fat", 0)
    total_trans_fat = label_data.get("total_trans_fat", 0)
    total_sodium = label_data.get("total_sodium", 0)
    is_vegetarian = label_data.get("is_vegetarian", True)
    consumer_phone = label_data.get("consumer_phone", "")
    consumer_email = label_data.get("consumer_email", "")
    quantity = label_data.get("quantity", "")
    qty_raw = str(quantity).strip() if quantity is not None else ""
    formatted_quantity = format_quantity_display(qty_raw) or qty_raw
    nutrition_fallback = label_data.get("nutrition_fallback") or label_data.get(
        "nutrition_missing", []
    )
    license_no = label_data.get("license_no", "")
    manufacture_date = label_data.get("manufacture_date", "")
    best_before = label_data.get("best_before", label_data.get("expiry", ""))
    include_fssai_logo = label_data.get("include_fssai_logo", False)
    manufacturer_name = label_data.get("manufacturer_name", "")
    manufacturer_address = label_data.get("manufacturer_address", "")
    formatted_address = format_address_display(manufacturer_address)
    mrp = label_data.get("mrp", "")
    batch_number = label_data.get("batch_number", "")
    storage_instructions = label_data.get("storage_instructions", "Store in a cool and dry place")

    st.write("")
    st.subheader("Label Preview (watermarked)")

    preview_payload = {
        "product_name": product_name,
        "ingredients": ingredients,
        "allergens": allergens,
        "calories": total_calories,
        "protein": total_protein,
        "carbs": total_carbs,
        "sugar": total_sugar,
        "total_fat": total_fat,
        "saturated_fat": total_saturated_fat,
        "trans_fat": total_trans_fat,
        "sodium": total_sodium,
        "added_sugars": 0,
        "quantity": quantity,
        "license_no": license_no,
        "manufacture_date": manufacture_date,
        "best_before": best_before,
        "manufacturer_name": manufacturer_name,
        "manufacturer_address": manufacturer_address,
        "mrp": mrp,
        "batch_number": batch_number,
        "storage_instructions": storage_instructions,
        "is_vegetarian": is_vegetarian,
        "consumer_phone": consumer_phone,
        "consumer_email": consumer_email,
        "custom_warning_text": custom_warning_text,
    }
    try:
        preview_png = generate_preview_png(preview_payload)
        st.image(
            preview_png,
            caption="Preview only — not print-ready. Pay Rs. 99 to download the clean, high-resolution PDF.",
            use_container_width=True,
        )
    except (OSError, ValueError) as exc:
        st.error(f"Could not render preview image: {exc}")
    st.caption(
        "Nutritional values are approximate and derived from standard ingredient data."
    )
    if custom_ingredients:
        st.warning(
            "Custom ingredients included with 0 nutrition values: "
            + ", ".join(custom_ingredients[:8])
            + ("..." if len(custom_ingredients) > 8 else "")
        )
    render_nutrient_warnings(
        sodium_mg=total_sodium,
        total_sugars_g=total_sugar,
        saturated_fat_g=total_saturated_fat,
        total_fat_g=total_fat,
        trans_fat_g=total_trans_fat,
        salt_percentage=salt_percentage,
    )
    if nutrition_fallback:
        st.caption(
            "Used default estimate (no DB / AI match) for: "
            + ", ".join(nutrition_fallback)
        )

    if DEBUG_MODE:
        with st.expander("🔍 Nutrition calculation debug"):
            n_ings = len(ingredient_rows)
            if n_ings == 0:
                st.write("No valid ingredient percentages parsed.")
            else:
                st.write(
                    f"Method: weighted contribution by user-entered percentages "
                    f"across {n_ings} ingredient(s). Total entered = {total_percentage:.2f}%."
                )
                rows = []
                cal_sum = prot_sum = car_sum = sug_sum = sodium_sum = 0.0
                for row in ingredient_rows:
                    ing = row.get("ingredient", "")
                    ing_lower = row.get("ingredient_lower", str(ing).lower())
                    pct = float(row.get("percentage", 0) or 0)
                    factor = pct / 100.0
                    r = get_nutrition(ing_lower)
                    db_row = INGREDIENT_DB.get(ing_lower, {})
                    cal_v = float(db_row.get("calories", r.get("calories", 0)))
                    prot_v = float(db_row.get("protein", r.get("protein", 0)))
                    carb_v = float(db_row.get("carbs", r.get("carbs", 0)))
                    sug_v = float(db_row.get("sugar", r.get("sugar", 0)))
                    sodium_v = float(db_row.get("sodium", 0))
                    cal_c = cal_v * factor
                    prot_c = prot_v * factor
                    car_c = carb_v * factor
                    sug_c = sug_v * factor
                    sodium_c = sodium_v * factor
                    cal_sum += cal_c
                    prot_sum += prot_c
                    car_sum += car_c
                    sug_sum += sug_c
                    sodium_sum += sodium_c
                    rows.append(
                        {
                            "ingredient": ing,
                            "percentage (%)": round(pct, 2),
                            "source": r.get("source", "?"),
                            "carbs/100g": round(carb_v, 2),
                            "carbs contribution": round(car_c, 3),
                            "sugar/100g": round(sug_v, 2),
                            "sugar contribution": round(sug_c, 3),
                            "sodium/100g (mg)": round(sodium_v, 2),
                            "sodium contribution (mg)": round(sodium_c, 3),
                            "cal/100g": round(cal_v, 2),
                            "cal contribution": round(cal_c, 3),
                            "protein/100g": round(prot_v, 2),
                            "protein contribution": round(prot_c, 3),
                        }
                    )
                st.table(rows)
                st.write(
                    f"**Final totals** → Energy: {round(cal_sum, 2)} kcal  |  "
                    f"Protein: {round(prot_sum, 2)} g  |  "
                    f"Carbohydrates: {round(car_sum, 2)} g  |  "
                    f"Sugar: {round(sug_sum, 2)} g  |  "
                    f"Sodium: {round(sodium_sum, 2)} mg"
                )

    # Secure payment gate: pay per product label, with 7-day free edits.
    user_id = get_or_create_user_id()
    product_id = product_id_from_name(product_name)
    active_purchase = get_active_purchase(user_id, product_id)

    st.subheader("Unlock Download")
    if active_purchase:
        expires_at = active_purchase["expires_at"] or ""
        st.success(
            "✅ Payment active for this label. "
            f"Free edits + downloads available until {expires_at}."
        )
    else:
        st.markdown(
            '<a href="https://rzp.io/rzp/J6o3Qfq1" target="_blank" '
            'style="display:inline-block;padding:12px 22px;background:#0A7F2E;'
            "color:#fff;border-radius:8px;font-weight:700;text-decoration:none;"
            'font-family:Arial,sans-serif;font-size:16px;">'
            "Pay Rs. 99 - Unlock This Label</a>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Pay once per product. Edits and re-downloads are free for 7 days "
            "for the same product."
        )
        payment_id = st.text_input(
            "Enter Razorpay Payment ID (pay_xxxxx)",
            key="payment_id_input",
        )
        if st.button("Verify Payment Securely"):
            pid = payment_id.strip()
            if not pid or len(pid) < 10:
                st.error("Enter a valid Payment ID.")
            elif not pid.startswith("pay_"):
                st.error("Invalid ID format. Payment ID must start with 'pay_'.")
            elif not re.fullmatch(r"[A-Za-z0-9_]+", pid):
                st.error("Invalid ID format.")
            else:
                ok, msg, order_id = verify_razorpay_payment(pid, LABEL_PRICE_PAISE)
                if not ok:
                    st.error(f"❌ {msg}")
                else:
                    saved, save_msg = record_paid_purchase(
                        user_id=user_id,
                        product_id=product_id,
                        product_name=product_name.strip() or "Unnamed Product",
                        payment_id=pid,
                        razorpay_order_id=order_id,
                    )
                    if saved:
                        st.success(f"✅ {save_msg}")
                        st.rerun()
                    else:
                        st.error(f"❌ {save_msg}")
        active_purchase = get_active_purchase(user_id, product_id)

    st.write("")
    if active_purchase:
        generate_pdf(
            product_name=product_name,
            ingredients=ingredients,
            allergens=allergens,
            calories=total_calories,
            protein=total_protein,
            carbs=total_carbs,
            sugar=total_sugar,
            total_fat=total_fat,
            saturated_fat=total_saturated_fat,
            trans_fat=total_trans_fat,
            sodium=total_sodium,
            quantity=quantity,
            license_no=license_no,
            manufacture_date=manufacture_date,
            best_before=best_before,
            manufacturer_name=manufacturer_name,
            manufacturer_address=manufacturer_address,
            mrp=mrp,
            batch_number=batch_number,
            storage_instructions=storage_instructions,
            include_fssai_logo=include_fssai_logo,
            is_vegetarian=is_vegetarian,
            consumer_phone=consumer_phone,
            consumer_email=consumer_email,
        )
        with PDF_PATH.open("rb") as f:
            pdf_bytes = f.read()
        downloaded = st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="label.pdf",
            mime="application/pdf",
        )
        if downloaded:
            increment_download_count(active_purchase["id"])
    else:
        st.warning("🔒 Please complete payment verification to download.")
