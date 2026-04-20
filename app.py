import html
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import streamlit as st
import streamlit.components.v1 as components
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Flowable,
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

if "payment_done" not in st.session_state:
    st.session_state.payment_done = False
if "locked_product_name" not in st.session_state:
    st.session_state.locked_product_name = ""

COMMON_ALLERGENS = ["milk", "peanuts", "wheat", "soy", "egg", "nuts"]

SVG_VEG_SYMBOL = """<svg width="18" height="18" xmlns="http://www.w3.org/2000/svg">
  <rect width="18" height="18" fill="none" stroke="#008000" stroke-width="2"/>
  <circle cx="9" cy="9" r="5" fill="#008000"/>
</svg>"""

SVG_NONVEG_SYMBOL = """<svg width="18" height="18" xmlns="http://www.w3.org/2000/svg">
  <rect width="18" height="18" fill="none" stroke="#800000" stroke-width="2"/>
  <polygon points="9,3 16,15 2,15" fill="#800000"/>
</svg>"""

SVG_FSSAI_PLACEHOLDER = """<svg width="40" height="40" xmlns="http://www.w3.org/2000/svg">
  <circle cx="20" cy="20" r="18" fill="none" stroke="#008000" stroke-width="2"/>
  <text x="20" y="17" text-anchor="middle" font-size="7" fill="#008000" font-weight="bold">FSSAI</text>
  <text x="20" y="27" text-anchor="middle" font-size="5" fill="#008000">Lic. No.</text>
</svg>"""
NUTRITION_DB_PATH = Path(__file__).resolve().parent / "data" / "nutrition_db.json"
PROFILE_PATH = Path(__file__).resolve().parent / "user_profile.json"
PDF_PATH = Path(__file__).resolve().parent / "label.pdf"
ID_MAP_FILE = Path(__file__).resolve().parent / "payment_id_map.json"

INGREDIENT_DB = {
    "almonds": {"calories": 579, "protein": 21, "carbs": 22, "sugar": 4.4},
    "baking powder": {"calories": 53, "protein": 0, "carbs": 28, "sugar": 0},
    "besan": {"calories": 387, "protein": 22, "carbs": 58, "sugar": 10},
    "butter": {"calories": 717, "protein": 0.85, "carbs": 0.1, "sugar": 0.1},
    "cardamom": {"calories": 311, "protein": 11, "carbs": 68, "sugar": 0},
    "cashews": {"calories": 553, "protein": 18, "carbs": 30, "sugar": 5.9},
    "chana dal": {"calories": 360, "protein": 20, "carbs": 61, "sugar": 8},
    "chocolate": {"calories": 546, "protein": 4.9, "carbs": 60, "sugar": 48},
    "cinnamon": {"calories": 247, "protein": 4, "carbs": 81, "sugar": 2.2},
    "cocoa": {"calories": 228, "protein": 20, "carbs": 58, "sugar": 1.8},
    "coconut": {"calories": 354, "protein": 3.3, "carbs": 15, "sugar": 6.2},
    "coconut milk": {"calories": 230, "protein": 2.3, "carbs": 6, "sugar": 3.3},
    "coconut oil": {"calories": 862, "protein": 0, "carbs": 0, "sugar": 0},
    "corn flour": {"calories": 381, "protein": 6.9, "carbs": 79, "sugar": 0},
    "coriander": {"calories": 23, "protein": 2.1, "carbs": 3.7, "sugar": 0},
    "cumin": {"calories": 375, "protein": 18, "carbs": 44, "sugar": 2.3},
    "curd": {"calories": 61, "protein": 3.5, "carbs": 4.7, "sugar": 4.7},
    "garlic": {"calories": 149, "protein": 6.4, "carbs": 33, "sugar": 1},
    "ghee": {"calories": 900, "protein": 0, "carbs": 0, "sugar": 0},
    "ginger": {"calories": 80, "protein": 1.8, "carbs": 18, "sugar": 1.7},
    "gram flour": {"calories": 387, "protein": 22, "carbs": 58, "sugar": 10},
    "green chilli": {"calories": 40, "protein": 2, "carbs": 9, "sugar": 5.1},
    "honey": {"calories": 304, "protein": 0.3, "carbs": 82, "sugar": 82},
    "jaggery": {"calories": 383, "protein": 0.4, "carbs": 98, "sugar": 97},
    "maida": {"calories": 364, "protein": 10, "carbs": 76, "sugar": 0.3},
    "milk": {"calories": 42, "protein": 3.4, "carbs": 5, "sugar": 5},
    "moong dal": {"calories": 347, "protein": 24, "carbs": 63, "sugar": 6},
    "mustard oil": {"calories": 884, "protein": 0, "carbs": 0, "sugar": 0},
    "oil": {"calories": 884, "protein": 0, "carbs": 0, "sugar": 0},
    "onion": {"calories": 40, "protein": 1.1, "carbs": 9.3, "sugar": 4.2},
    "paneer": {"calories": 296, "protein": 18, "carbs": 1.2, "sugar": 0},
    "peanut oil": {"calories": 884, "protein": 0, "carbs": 0, "sugar": 0},
    "peanuts": {"calories": 567, "protein": 25.8, "carbs": 16, "sugar": 4},
    "raisins": {"calories": 299, "protein": 3.1, "carbs": 79, "sugar": 59},
    "red chilli powder": {"calories": 282, "protein": 13, "carbs": 50, "sugar": 7},
    "rice": {"calories": 130, "protein": 2.7, "carbs": 28, "sugar": 0},
    "rice flour": {"calories": 366, "protein": 5.9, "carbs": 80, "sugar": 0},
    "salt": {"calories": 0, "protein": 0, "carbs": 0, "sugar": 0},
    "sesame seeds": {"calories": 573, "protein": 18, "carbs": 23, "sugar": 0.3},
    "sugar": {"calories": 387, "protein": 0, "carbs": 100, "sugar": 100},
    "toor dal": {"calories": 343, "protein": 22, "carbs": 63, "sugar": 6},
    "tomato": {"calories": 18, "protein": 0.9, "carbs": 3.9, "sugar": 2.6},
    "turmeric": {"calories": 354, "protein": 8, "carbs": 65, "sugar": 3.2},
    "water": {"calories": 0, "protein": 0, "carbs": 0, "sugar": 0},
    "wheat": {"calories": 340, "protein": 13, "carbs": 71, "sugar": 0},
    "yeast": {"calories": 325, "protein": 40, "carbs": 38, "sugar": 0},
    "yoghurt": {"calories": 61, "protein": 3.5, "carbs": 4.7, "sugar": 4.7},
}


def load_id_map():
    if ID_MAP_FILE.exists():
        with ID_MAP_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_id_map(id_map):
    with ID_MAP_FILE.open("w", encoding="utf-8") as f:
        json.dump(id_map, f)


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


def load_user_profile():
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_user_profile(profile):
    PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")


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


def calculate_nutrition_from_ingredients(cleaned_list):
    """
    Average per-100g calories, protein, carbs and sugar across all ingredients
    (after get_nutrition each).
    Returns (avg_calories, avg_protein, avg_carbs, avg_sugar, fallback_ingredient_names).
    """
    if not cleaned_list:
        return 0.0, 0.0, 0.0, 0.0, []
    cals = []
    prots = []
    cars = []
    sugs = []
    fallback_names = []
    for ing in cleaned_list:
        r = get_nutrition(ing)
        cals.append(r["calories"])
        prots.append(r["protein"])
        cars.append(r.get("carbs", 0))
        sugs.append(r.get("sugar", 0))
        if r.get("source") == "fallback":
            fallback_names.append(ing)
    n = len(cals)
    return (
        round(sum(cals) / n, 2),
        round(sum(prots) / n, 2),
        round(sum(cars) / n, 2),
        round(sum(sugs) / n, 2),
        fallback_names,
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


PAGE_WIDTH = 105 * mm
PAGE_HEIGHT = 110 * mm


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
    """18×18 pt frame; veg mark is 14×14 #008000 (matches HTML green)."""

    def __init__(self, is_vegetarian):
        Flowable.__init__(self)
        self.is_veg = is_vegetarian
        self.width = 18
        self.height = 18

    def draw(self):
        c = self.canv
        c.saveState()
        if self.is_veg:
            green = HexColor("#008000")
            c.setStrokeColor(green)
            c.setLineWidth(1.5)
            c.rect(2, 2, 14, 14, fill=0, stroke=1)
            c.setFillColor(green)
            c.circle(9, 9, 4.5, fill=1, stroke=0)
        else:
            c.setStrokeColorRGB(0.5, 0, 0)
            c.setFillColorRGB(0.5, 0, 0)
            c.setLineWidth(2)
            c.rect(0, 0, 18, 18, stroke=1, fill=0)
            p = c.beginPath()
            p.moveTo(9, 15)
            p.lineTo(16, 3)
            p.lineTo(2, 3)
            p.close()
            c.drawPath(p, stroke=0, fill=1)
        c.restoreState()


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
):
    # HTML_LABEL_VERSION = PDF_LABEL_VERSION = "v4"
    _ = include_fssai_logo

    W, H = PAGE_WIDTH, PAGE_HEIGHT

    def _paint_border(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.black)
        canvas.setLineWidth(2)
        canvas.rect(6, 6, W - 12, H - 12)
        canvas.restoreState()

    def _section_divider():
        return [
            HRFlowable(
                width="100%",
                thickness=0.5,
                color=colors.grey,
                spaceAfter=2,
                spaceBefore=2,
            ),
        ]

    qty_raw = str(quantity).strip() if quantity is not None else ""
    fq = (format_quantity_display(qty_raw) or qty_raw or "").strip()
    net_qty_display = fq if fq else "Not specified"

    mrp_raw = (mrp or "").strip()
    if mrp_raw:
        num_m = re.search(r"[\d.]+", mrp_raw)
        mrp_rs = num_m.group(0) if num_m else mrp_raw
    else:
        mrp_rs = "—"

    _addr_cap = 500
    addr_body = format_address_display(manufacturer_address).strip()
    if addr_body and len(addr_body) > _addr_cap:
        addr_body = addr_body[:_addr_cap].rstrip() + "…"

    ing_body = (ingredients or "").strip() or "Not provided"
    # Keep PDF to one A6 page; very long ingredient lists are truncated at commas.
    _ing_cap = 1000
    if len(ing_body) > _ing_cap:
        ing_body = ing_body[:_ing_cap].rsplit(",", 1)[0] + ", …"
    lic_display = (license_no or "").strip() or "Not provided"
    ptitle = (product_name or "").strip() or "Not specified"
    bn = (batch_number or "").strip() or "Not specified"
    mfg = (manufacture_date or "").strip() or "Not specified"
    bb = (best_before or "").strip() or "Not specified"
    mfr = (manufacturer_name or "").strip()
    storage_default = "Store in a cool and dry place"
    storage = (storage_instructions or "").strip() or storage_default

    if allergens:
        allergen_line = "Allergens: " + ", ".join(
            a.strip().replace("_", " ").title() for a in allergens
        )
    else:
        allergen_line = "Allergens: None"

    phone_raw = (consumer_phone or "").strip()
    email_raw = (consumer_email or "").strip()
    care_parts = []
    if phone_raw:
        care_parts.append(phone_raw)
    if email_raw:
        care_parts.append(email_raw)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=(PAGE_WIDTH, PAGE_HEIGHT),
        topMargin=5 * mm,
        bottomMargin=5 * mm,
        leftMargin=7 * mm,
        rightMargin=7 * mm,
    )
    aw = doc.width

    ss = getSampleStyleSheet()
    st_body = ParagraphStyle(
        "LblBody",
        parent=ss["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        spaceAfter=1,
        alignment=TA_LEFT,
        textColor=colors.black,
    )
    st_section = ParagraphStyle(
        "LblSection",
        parent=ss["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        spaceAfter=1,
        alignment=TA_LEFT,
        textColor=colors.black,
    )
    pname_style = ParagraphStyle(
        "pname",
        parent=ss["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=10,
        alignment=TA_CENTER,
        textColor=colors.black,
    )
    fssai_line_style = ParagraphStyle(
        "fssai_line",
        parent=ss["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        alignment=TA_RIGHT,
        textColor=colors.black,
        wordWrap="CJK",
    )
    allergen_style = ParagraphStyle(
        "allergens",
        parent=ss["Normal"],
        fontSize=7.5,
        textColor=colors.black,
        fontName="Helvetica-Bold",
        spaceAfter=2,
        leading=10,
    )
    nutr_note_style = ParagraphStyle(
        "nutr_note",
        parent=ss["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=6,
        leading=8,
        textColor=colors.black,
        spaceAfter=2,
    )
    st_care_line = ParagraphStyle(
        "LblCareLine",
        parent=ss["Normal"],
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        textColor=colors.black,
        spaceAfter=1,
        alignment=TA_LEFT,
    )

    tw2 = 22 * mm
    tw1 = 85 * mm
    if tw1 + tw2 > aw + 0.1:
        tw1 = max(40.0, aw - tw2)

    fssai_one = Paragraph(
        xml_escape(f"FSSAI Lic. No: {lic_display}"),
        fssai_line_style,
    )
    fssai_cell = Table([[fssai_one]], colWidths=[tw2])
    fssai_cell.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    product_para = Paragraph(
        f"<b><font size='13'>{xml_escape(ptitle)}</font></b>",
        pname_style,
    )
    veg_inner = Table(
        [[product_para, VegMarkFlowable(is_vegetarian)]],
        colWidths=[max(24.0, tw1 - 22), 22],
    )
    veg_inner.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    top_table = Table([[veg_inner, fssai_cell]], colWidths=[tw1, tw2])
    top_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    qw = min(51.5 * mm, aw / 2)
    qty_mrp_table = Table(
        [
            [
                f"Net Qty: {xml_escape(net_qty_display)}",
                f"MRP: Rs.{xml_escape(mrp_rs)} (Incl. of all taxes)",
            ]
        ],
        colWidths=[qw, aw - qw],
    )
    qty_mrp_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, colors.black),
            ]
        )
    )

    nutr_w1 = aw * 0.62
    nutr_w2 = aw * 0.38
    nutrition_data = [
        ["Nutrient", "Per 100g"],
        ["Energy (kcal)", str(calories)],
        ["Protein (g)", str(protein)],
        ["Carbohydrates (g)", str(carbs)],
        ["Sugar (g)", str(sugar)],
    ]
    nutrition_tbl = Table(nutrition_data, colWidths=[nutr_w1, nutr_w2])
    nutrition_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.white),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.white]),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    batch_block = Paragraph(
        f"<b>Batch No:</b> {xml_escape(bn)}<br/>"
        f"<b>MFG Date:</b> {xml_escape(mfg)}<br/>"
        f"<b>Best Before:</b> {xml_escape(bb)}",
        st_body,
    )

    story = [
        top_table,
        qty_mrp_table,
        *_section_divider(),
        Paragraph("Ingredients:", st_section),
        Paragraph(xml_escape(ing_body).replace("\n", "<br/>"), st_body),
        Paragraph(xml_escape(allergen_line), allergen_style),
        *_section_divider(),
        Paragraph("Nutrition Information (Per 100 g)", st_section),
        Paragraph("*Values are approximate", nutr_note_style),
        nutrition_tbl,
        *_section_divider(),
        batch_block,
    ]
    if mfr:
        story.append(Paragraph(f"<b>Manufacturer:</b> {xml_escape(mfr)}", st_body))
    if addr_body:
        story.append(
            Paragraph(f"<b>Address:</b> {xml_escape(addr_body)}", st_body)
        )
    story.append(Paragraph(f"<b>Storage:</b> {xml_escape(storage)}", st_body))
    if care_parts:
        ep = xml_escape(email_raw) if email_raw else ""
        pp = xml_escape(phone_raw) if phone_raw else ""
        if phone_raw and email_raw:
            care_line2 = f"Ph: {pp}  |  {ep}"
        elif phone_raw:
            care_line2 = f"Ph: {pp}"
        else:
            care_line2 = ep
        care_block = Paragraph(
            f"<b>Consumer Care:</b><br/>{care_line2}",
            st_care_line,
        )
        care_tbl = Table([[care_block]], colWidths=[aw])
        care_tbl.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        story.append(care_tbl)

    doc.build(story, onFirstPage=_paint_border, onLaterPages=_paint_border)
    PDF_PATH.write_bytes(buf.getvalue())
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


st.title("FSSAI Label Generator")
st.write("")

init_profile_session_state()

STORAGE_OPTIONS = [
    "Store in a cool and dry place",
    "Refrigerate after opening",
    "Keep frozen",
]

with st.sidebar:
    st.subheader("User profile")
    st.caption("Saved locally — auto-fills each label.")
    if not os.environ.get("GROQ_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        st.caption(
            "Optional: set GROQ_API_KEY or OPENAI_API_KEY in your environment "
            "so unknown ingredients can be estimated and cached."
        )
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

with st.form("label_form"):
    st.info(
        "You can edit all details after payment. Changing product name requires a new payment."
    )
    st.subheader("Quick label (required fields only)")
    c1, c2 = st.columns(2)
    with c1:
        product_name = st.text_input("Product Name", value="Milk Sweet")
        st.caption(
            "⚠️ Changing product name after payment requires new payment."
        )
        net_quantity = st.text_input("Net Quantity", placeholder="e.g. 200g")
        mrp = st.text_input("MRP (price)", placeholder="e.g. 29")
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
        )
        storage_instructions = st.selectbox("Storage instructions", STORAGE_OPTIONS)
        batch_override = st.text_input(
            "Batch No (optional override)",
            placeholder="Leave blank for auto BN-YYYYMMDD-XX",
        )

    ingredients = st.text_area(
        "Ingredients (comma separated)",
        value="milk, sugar, peanut oil",
        height=88,
    )
    consumer_phone = st.text_input(
        "Consumer care phone",
        placeholder="e.g. 1800-XXX-XXXX",
    )
    consumer_email = st.text_input(
        "Consumer care email",
        placeholder="e.g. support@example.com",
    )

    generate_label = st.form_submit_button("Generate label")

if "label_data" not in st.session_state:
    st.session_state.label_data = None

if generate_label:
    cleaned_ingredients = clean_ingredients(ingredients)
    detected_allergens = detect_allergens(cleaned_ingredients)
    (
        total_calories,
        total_protein,
        total_carbs,
        total_sugar,
        nutrition_fallback,
    ) = calculate_nutrition_from_ingredients(cleaned_ingredients)

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

    st.session_state.label_data = {
        "product_name": product_name,
        "ingredients": ingredients,
        "cleaned_ingredients": cleaned_ingredients,
        "allergens": detected_allergens,
        "total_calories": total_calories,
        "total_protein": total_protein,
        "total_carbs": total_carbs,
        "total_sugar": total_sugar,
        "nutrition_fallback": nutrition_fallback,
        "is_vegetarian": food_type == "Vegetarian",
        "quantity": net_quantity,
        "license_no": license_number,
        "manufacture_date": manufacture_str,
        "best_before": best_before_str,
        "shelf_life_days": int(shelf_life_days),
        "include_fssai_logo": False,
        "manufacturer_name": manufacturer_name,
        "manufacturer_address": manufacturer_address,
        "mrp": mrp,
        "batch_number": final_batch,
        "storage_instructions": storage_instructions,
        "consumer_phone": consumer_phone,
        "consumer_email": consumer_email,
    }

if st.session_state.label_data:
    label_data = st.session_state.label_data
    product_name = label_data.get("product_name", "")
    ingredients = label_data.get("ingredients", "")
    cleaned_ingredients = label_data.get("cleaned_ingredients", [])
    allergens = label_data.get("allergens", [])
    total_calories = label_data.get("total_calories", 0)
    total_protein = label_data.get("total_protein", 0)
    total_carbs = label_data.get("total_carbs", 0)
    total_sugar = label_data.get("total_sugar", 0)
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
    st.subheader("Label Preview")

    mrp_raw = (mrp or "").strip()
    if mrp_raw:
        _nm = re.search(r"[\d.]+", mrp_raw)
        mrp_rs = _nm.group(0) if _nm else mrp_raw
    else:
        mrp_rs = "—"
    label_html = build_label_html(
        product_name=product_name,
        is_vegetarian=is_vegetarian,
        license_no=license_no,
        net_qty_display=formatted_quantity or "Not specified",
        mrp_rs=mrp_rs,
        ingredients_text=ingredients,
        allergens_list=allergens,
        total_calories=total_calories,
        total_protein=total_protein,
        total_carbs=total_carbs,
        total_sugar=total_sugar,
        batch_number=batch_number,
        manufacture_date=manufacture_date,
        best_before=best_before,
        manufacturer_name=manufacturer_name,
        manufacturer_address=manufacturer_address,
        storage_instructions=storage_instructions,
        consumer_phone=consumer_phone,
        consumer_email=consumer_email,
    )
    components.html(label_html, height=780, scrolling=True)
    st.caption(
        "Nutritional values are approximate and derived from standard ingredient data."
    )
    if nutrition_fallback:
        st.caption(
            "Used default estimate (no DB / AI match) for: "
            + ", ".join(nutrition_fallback)
        )

    with st.expander("🔍 Nutrition calculation debug"):
        n_ings = len(cleaned_ingredients)
        if n_ings == 0:
            st.write("No ingredients parsed.")
        else:
            equal_weight = 1.0 / n_ings
            st.write(
                f"Method: simple arithmetic mean across {n_ings} ingredient(s). "
                f"Each ingredient contributes equal weight = "
                f"1/{n_ings} = {equal_weight:.4f}"
            )
            rows = []
            cal_sum = prot_sum = car_sum = sug_sum = 0.0
            for ing in cleaned_ingredients:
                r = get_nutrition(ing)
                cal_c = r["calories"] * equal_weight
                prot_c = r["protein"] * equal_weight
                car_c = r.get("carbs", 0) * equal_weight
                sug_c = r.get("sugar", 0) * equal_weight
                cal_sum += cal_c
                prot_sum += prot_c
                car_sum += car_c
                sug_sum += sug_c
                rows.append(
                    {
                        "ingredient": ing,
                        "weight": round(equal_weight, 4),
                        "source": r.get("source", "?"),
                        "carbs/100g": r.get("carbs", 0),
                        "carbs contribution": round(car_c, 3),
                        "sugar/100g": r.get("sugar", 0),
                        "sugar contribution": round(sug_c, 3),
                        "cal/100g": r["calories"],
                        "cal contribution": round(cal_c, 3),
                        "protein/100g": r["protein"],
                        "protein contribution": round(prot_c, 3),
                    }
                )
            st.table(rows)
            st.write(
                f"**Final totals** → Energy: {round(cal_sum, 2)} kcal  |  "
                f"Protein: {round(prot_sum, 2)} g  |  "
                f"Carbohydrates: {round(car_sum, 2)} g  |  "
                f"Sugar: {round(sug_sum, 2)} g"
            )
            st.caption(
                "Note: carbs and sugar are computed the same way as calories and protein "
                "(unweighted mean). For e.g. milk+sugar+peanut oil, carbs "
                "and sugar totals will be identical because each of those ingredients "
                "happens to have carbs/100g == sugar/100g."
            )

    # After PDF is generated, before payment section:
    current_product = product_name.strip().lower()
    locked_product = st.session_state.locked_product_name.strip().lower()

    if st.session_state.payment_done:
        if locked_product != "" and current_product != locked_product:
            st.session_state.payment_done = False
            st.session_state.locked_product_name = ""
            st.warning("⚠️ Product name changed — new payment required.")

    st.subheader("Unlock Download")
    st.markdown("Pay ₹99 to download your label")
    st.markdown("[👉 Click here to pay ₹99](https://rzp.io/rzp/J6o3Qfq1)")
    st.info(
        "After payment, you will receive a Payment ID (like pay_xxxxx). Enter it below."
    )
    payment_id = st.text_input("Enter your Payment ID (pay_xxxxx)")
    if st.button("Verify Payment"):
        pid = payment_id.strip()
        id_map = load_id_map()

        if not pid or len(pid) < 10:
            st.error("Enter a valid Payment ID")
        elif not all(c.isalnum() or c == "_" for c in pid):
            st.error("Invalid Payment ID format")
        elif pid in id_map:
            if id_map[pid] == current_product:
                st.session_state.payment_done = True
                st.session_state.locked_product_name = current_product
                st.success("✅ Payment verified! You can now download.")
            else:
                st.session_state.payment_done = False
                st.session_state.locked_product_name = ""
                st.error(
                    "❌ This Payment ID was used for a different product. Please pay again."
                )
        else:
            id_map[pid] = current_product
            save_id_map(id_map)
            st.session_state.payment_done = True
            st.session_state.locked_product_name = current_product
            st.success("✅ Payment verified! You can now download.")

    st.write("")
    if st.session_state.payment_done:
        generate_pdf(
            product_name=product_name,
            ingredients=ingredients,
            allergens=allergens,
            calories=total_calories,
            protein=total_protein,
            carbs=total_carbs,
            sugar=total_sugar,
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
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="label.pdf",
            mime="application/pdf",
        )
    else:
        st.warning("🔒 Please complete payment to download")
