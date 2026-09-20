import io
import json
import re
import os
import colorsys
from PIL import Image
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(BASE_DIR, "secrets", ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
FOLDER_NAME = "Current_Pageant"
SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
CONFIG_OUTPUT_PATH = os.path.join(BASE_DIR, "assets", "config.json")
FLYER_OUTPUT_PATH = os.path.join(BASE_DIR, "assets", "flyer.jpg")
CSS_OUTPUT_PATH = os.path.join(BASE_DIR, "assets", "custom.css")

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/forms.body.readonly"
]

# --- COLOR EXTRACTION & CSS GENERATION HELPERS ---

def rgb_to_hex(rgb):
    return f"#{int(rgb[0]):02x}{int(rgb[1]):02x}{int(rgb[2]):02x}"

def adjust_lightness(rgb, factor):
    """Adjusts brightness of an RGB color (factor > 1 lightens, < 1 darkens)."""
    h, s, v = colorsys.rgb_to_hsv(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)
    v = max(0.0, min(1.0, v * factor))
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))

def get_relative_luminance(hex_color):
    """Calculates relative luminance (WCAG 2.0) of a hex color."""
    hex_color = hex_color.lstrip('#')
    r, g, b = [int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)]

    # Convert sRGB to linear RGB
    r = r / 12.92 if r <= 0.04045 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.04045 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.04045 else ((b + 0.055) / 1.055) ** 2.4

    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def get_contrast_text_color(bg_hex, dark_text="#1a1a1a", light_text="#ffffff"):
    """Returns dark text for light backgrounds, light text for dark backgrounds."""
    luminance = get_relative_luminance(bg_hex)
    # Luminance threshold ~0.35 ensures WCAG 4.5:1 contrast
    return dark_text if luminance > 0.35 else light_text

def extract_color_palette(image_path, num_colors=16):
    """
    Extracts true dominant colors by analyzing pixel frequency across quantized colors.
    """
    fallback_palette = {
        "primary": "#4a154b",
        "primary_dark": "#2a0b2c",
        "secondary": "#e06d20",
        "accent": "#f4c430",
        "bg_light": "#f4f6f8"
    }

    if not os.path.exists(image_path):
        print(f"Warning: Flyer image not found at '{image_path}'. Using fallback colors.")
        return fallback_palette

    try:
        img = Image.open(image_path).convert("RGB")
        img = img.resize((200, 200))

        # Quantize image and retrieve pixel counts per color index
        quantized = img.quantize(colors=num_colors)
        palette = quantized.getpalette()
        color_counts = quantized.getcolors(maxcolors=256)

        if not color_counts:
            return fallback_palette

        # Build frequency list: [(count, (r, g, b)), ...]
        frequency_colors = []
        for count, idx in color_counts:
            r = palette[idx * 3]
            g = palette[idx * 3 + 1]
            b = palette[idx * 3 + 2]
            frequency_colors.append((count, (r, g, b)))

        # Sort by pixel count (frequency) descending
        frequency_colors.sort(key=lambda x: x[0], reverse=True)

        primary_rgb = None
        secondary_rgb = None
        accent_rgb = None

        # Filter out extreme blacks/whites to find main thematic colors
        for count, rgb in frequency_colors:
            h, s, v = colorsys.rgb_to_hsv(rgb[0]/255.0, rgb[1]/255.0, rgb[2]/255.0)

            # Skip near-black and near-white pixels
            if v < 0.12 or (v > 0.92 and s < 0.10):
                continue

            if primary_rgb is None:
                primary_rgb = rgb
                continue

            # Ensure secondary color has sufficient contrast or hue difference from primary
            p_h, p_s, p_v = colorsys.rgb_to_hsv(primary_rgb[0]/255.0, primary_rgb[1]/255.0, primary_rgb[2]/255.0)
            hue_diff = abs(h - p_h)
            if hue_diff > 0.5:
                hue_diff = 1.0 - hue_diff

            if secondary_rgb is None and (hue_diff > 0.08 or abs(v - p_v) > 0.25 or abs(s - p_s) > 0.3):
                secondary_rgb = rgb
                continue

            if secondary_rgb and accent_rgb is None and (s > 0.4 or hue_diff > 0.15):
                accent_rgb = rgb
                break

        # Fallback assignments if image is monochromatic
        if not primary_rgb:
            primary_rgb = frequency_colors[0][1]
        if not secondary_rgb:
            p_v = colorsys.rgb_to_hsv(primary_rgb[0]/255.0, primary_rgb[1]/255.0, primary_rgb[2]/255.0)[2]
            secondary_rgb = adjust_lightness(primary_rgb, 0.6 if p_v > 0.5 else 1.4)
        if not accent_rgb:
            accent_rgb = adjust_lightness(secondary_rgb, 1.3)

        primary_dark = adjust_lightness(primary_rgb, 0.4)

        return {
            "primary": rgb_to_hex(primary_rgb),
            "primary_dark": rgb_to_hex(primary_dark),
            "secondary": rgb_to_hex(secondary_rgb),
            "accent": rgb_to_hex(accent_rgb),
            "bg_light": "#f4f6f8"
        }
    except Exception as e:
        print(f"Error analyzing image colors: {e}. Using fallback palette.")
        return fallback_palette

def update_custom_css(colors, css_path=CSS_OUTPUT_PATH):
    """Writes dynamic CSS variables and layout styles to assets/custom.css"""

    # Dynamically compute text contrast colors based on extracted palette luminance
    text_on_primary = get_contrast_text_color(colors['primary'])
    text_on_secondary = get_contrast_text_color(colors['secondary'])
    text_on_accent = get_contrast_text_color(colors['accent'])

    # Subtitle text color in header banner
    subtitle_color = "rgba(255, 255, 255, 0.85)" if text_on_primary == "#ffffff" else "rgba(0, 0, 0, 0.75)"

    css_content = f"""/* Auto-generated theme from Flyer Image */
:root {{
  --mt-primary: {colors['primary']};
  --mt-primary-dark: {colors['primary_dark']};
  --mt-secondary: {colors['secondary']};
  --mt-accent: {colors['accent']};
  --mt-bg-light: {colors['bg_light']};

  /* Dynamic Text Contrast Variables */
  --mt-text-on-primary: {text_on_primary};
  --mt-text-on-secondary: {text_on_secondary};
  --mt-text-on-accent: {text_on_accent};
  --mt-header-subtitle: {subtitle_color};
}}

body {{
  background-color: var(--mt-bg-light);
  color: #2b2b2b;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}}

/* Header Banner */
.pageant-header {{
  background: linear-gradient(135deg, var(--mt-primary) 0%, var(--mt-primary-dark) 100%);
  color: var(--mt-text-on-primary);
  padding: 32px 0;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}}

.text-gold,
.pageant-header .lead {{
  color: var(--mt-header-subtitle) !important;
}}

/* Flyer Image Card */
.flyer-card {{
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
  background: #ffffff;
}}

.flyer-img {{
  width: 100%;
  height: auto;
  display: block;
  object-fit: cover;
}}

/* Dynamic Card Headers */
.card-custom {{
  border: none;
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  overflow: hidden;
  background-color: #ffffff;
}}

.card-header-primary {{
  background-color: var(--mt-primary);
  color: var(--mt-text-on-primary);
  padding: 14px 20px;
}}

.card-header-secondary {{
  background-color: var(--mt-secondary);
  color: var(--mt-text-on-secondary);
  padding: 14px 20px;
}}

.card-header-disclaimer {{
  background-color: #343a40;
  color: #ffffff;
}}

/* Details / Accordions */
summary:hover {{
  background-color: rgba(0, 0, 0, 0.03) !important;
}}

/* Radio Cards & Selection Options */
.custom-radio-group label {{
  display: block;
  padding: 10px 14px;
  margin-bottom: 6px;
  border-radius: 6px;
  background-color: #f8f9fa;
  border: 1px solid #e9ecef;
  cursor: pointer;
  transition: all 0.2s ease;
}}

.custom-radio-group label:hover {{
  background-color: #f0e4f2;
  border-color: var(--mt-primary);
}}

.custom-radio-group input[type="radio"] {{
  accent-color: var(--mt-primary);
  margin-right: 8px;
}}

/* Rules / Disclaimer Text Box */
.disclaimer-full-text {{
  background-color: #fff8e7;
  border: 1px solid #ffe8a1;
  border-radius: 6px;
  padding: 16px;
  max-height: 200px;
  overflow-y: auto;
  font-size: 0.88rem;
  color: #444;
}}

/* Sticky Checkout Box */
.checkout-card {{
  background: linear-gradient(180deg, #1e1e2d 0%, #12121a 100%);
  border-radius: 12px;
  color: #ffffff;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.2);
}}

.total-amount-display {{
  font-size: 2.2rem;
  font-weight: 800;
  color: var(--mt-accent);
}}

/* PERMANENT INPUT BOX SIZING FIXES */
.card-body input,
.card-body textarea,
.card-body .form-control {{
  width: 100% !important;
  max-width: 100% !important;
  box-sizing: border-box !important;
  display: block !important;
}}

.card-body .Select-control,
.card-body .dash-dropdown {{
  width: 100% !important;
}}
"""
    os.makedirs(os.path.dirname(css_path), exist_ok=True)
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(css_content.strip())
    print(f"Updated '{css_path}' with extracted theme palette: {colors}")

# --- FORM & TEXT PARSING HELPERS ---

def clean_title(raw_title):
    title = raw_title.strip()
    has_letters = any(c.isalpha() for c in title)
    if has_letters and title == title.upper():
        title = title.title()

    title = re.sub(r'\bM\.t\.\b', 'M.T.', title, flags=re.IGNORECASE)
    title = re.sub(r'\bMt\b', 'MT', title, flags=re.IGNORECASE)
    title = re.sub(r'\bInc\b', 'Inc.', title, flags=re.IGNORECASE)
    title = re.sub(r'\.\.+', '.', title)
    return title.strip()

def parse_all_caps_sections(text):
    if not text:
        return []

    lines = text.split("\n")
    sections = []
    current_title = "General Information"
    current_content = []

    for line in lines:
        stripped = line.strip()
        has_letters = any(c.isalpha() for c in stripped)
        is_all_caps = has_letters and (stripped == stripped.upper()) and len(stripped) > 2

        if is_all_caps:
            content_str = "\n".join(current_content).strip()
            if content_str:
                sections.append({
                    "title": clean_title(current_title),
                    "content": content_str
                })
                current_content = []
            current_title = stripped
        else:
            current_content.append(line)

    content_str = "\n".join(current_content).strip()
    if content_str:
        sections.append({
            "title": clean_title(current_title),
            "content": content_str
        })

    return sections

def extract_price(text):
    if not text:
        return 0.0
    match = re.search(r'\$\s*(\d+(?:\.\d{2})?)', text)
    if match:
        return float(match.group(1))

    match_fallback = re.search(r'(\d+(?:\.\d{2})?)\s*(?:dollars|fee)', text, re.IGNORECASE)
    if match_fallback:
        return float(match_fallback.group(1))

    return 0.0

def detect_main_event_fee(form_description, items):
    combined_text = form_description + " " + " ".join([i.get("title", "") for i in items])

    match = re.search(r'(?:Main Event|Entry Fee|Registration Fee|Main Title)[^\n\$]*\$\s*(\d+(?:\.\d{2})?)', combined_text, re.IGNORECASE)
    if match:
        return float(match.group(1))

    match2 = re.search(r'\$\s*(\d+(?:\.\d{2})?)[^\n\.]*(?:Main Event|Entry Fee|Registration)', combined_text, re.IGNORECASE)
    if match2:
        return float(match2.group(1))

    return 50.0

def sanitize_field_id(title):
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', title).strip().lower()
    return re.sub(r'\s+', '_', clean)

# --- MAIN SYNC PIPELINE ---

def sync_current_pageant():
    print("Authenticating with Service Account...")
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )

    drive_service = build("drive", "v3", credentials=creds)
    forms_service = build("forms", "v1", credentials=creds)

    # 1. Locate 'Current_Pageant' folder in Google Drive
    print(f"Searching for folder '{FOLDER_NAME}' in Google Drive...")
    folder_query = f"name = '{FOLDER_NAME}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    folder_result = drive_service.files().list(
        q=folder_query,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    folders = folder_result.get("files", [])

    if not folders:
        raise FileNotFoundError(f"Could not find folder '{FOLDER_NAME}'. Please ensure it is shared with your Service Account email.")

    folder_id = folders[0]["id"]
    print(f"Found folder '{FOLDER_NAME}' (ID: {folder_id})")

    # 2. Search inside folder for Google Form & Flyer Graphic
    file_query = f"'{folder_id}' in parents and trashed = false"
    files_result = drive_service.files().list(
        q=file_query,
        fields="files(id, name, mimeType)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    items = files_result.get("files", [])

    form_id = None
    image_file_id = None

    for item in items:
        mime = item.get("mimeType", "")
        name = item.get("name", "")

        if mime == "application/vnd.google-apps.form" or name.endswith(".gform"):
            form_id = item["id"]
            print(f"Found Google Form: '{name}' (ID: {form_id})")

        elif mime.startswith("image/") or name.lower().endswith((".jpg", ".jpeg", ".png")):
            image_file_id = item["id"]
            print(f"Found Flyer Graphic: '{name}' (ID: {image_file_id})")

    if not form_id:
        raise FileNotFoundError("No Google Form found in 'Current_Pageant' folder.")

    # 3. Download Flyer Graphic
    if image_file_id:
        print(f"Downloading latest flyer graphic to {FLYER_OUTPUT_PATH}...")
        os.makedirs(os.path.dirname(FLYER_OUTPUT_PATH), exist_ok=True)
        request = drive_service.files().get_media(fileId=image_file_id)

        with open(FLYER_OUTPUT_PATH, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        print("Flyer graphic download complete.")

    # 4. Extract Color Palette from Flyer & Generate Custom CSS
    print("Analyzing flyer graphic palette and updating custom.css...")
    colors = extract_color_palette(FLYER_OUTPUT_PATH)
    update_custom_css(colors, CSS_OUTPUT_PATH)

    # 5. Fetch Google Form structure via Google Forms API
    print("Fetching form schema from Google Forms API...")
    form_data = forms_service.forms().get(formId=form_id).execute()

    info = form_data.get("info", {})
    form_items = form_data.get("items", [])

    form_description = info.get("description", "")
    base_fee = detect_main_event_fee(form_description, form_items)
    print(f"Detected Main Event Base Fee: ${base_fee:.2f}")

    info_sections = parse_all_caps_sections(form_description)

    config = {
        "title": info.get("title", "Pageant Registration"),
        "description": form_description,
        "base_fee": base_fee,
        "flyer_image": "flyer.jpg",
        "theme_colors": colors,
        "info_sections": info_sections,
        "divisions": [],
        "addons": [],
        "form_fields": [],
        "disclaimer": None
    }

    ADDON_KEYWORDS = ["themewear", "talent", "photogenic", "optional", "add-on", "addon", "extra", "side award", "t-shirt", "tshirt", "fan favorite"]
    DISCLAIMER_KEYWORDS = ["agree", "disclaimer", "statement", "terms", "rules", "sportsmanship", "waiver", "refund", "bad sportsmanship"]

    # 6. Parse Questions into Structured Sections
    for item in form_items:
        title = item.get("title", "").strip()
        item_desc = item.get("description", "").strip()
        title_lower = title.lower()
        desc_lower = item_desc.lower()

        if "questionItem" in item:
            q_info = item["questionItem"]
            question = q_info.get("question", {})
            required = question.get("required", False)

            if "choiceQuestion" in question:
                choice_q = question["choiceQuestion"]
                q_type = choice_q.get("type", "")
                options = choice_q.get("options", [])
                option_labels = [opt.get("value", "").strip() for opt in options if opt.get("value")]

                if any(kw in title_lower or kw in desc_lower for kw in DISCLAIMER_KEYWORDS) or any("agree" in label.lower() for label in option_labels):
                    config["disclaimer"] = {
                        "id": sanitize_field_id(title or "disclaimer_agreement"),
                        "title": title or "Rules & Disclaimer Agreement",
                        "text": item_desc if item_desc else title,
                        "options": option_labels,
                        "required": required
                    }

                elif any(kw in title_lower for kw in ADDON_KEYWORDS):
                    addon_default_price = extract_price(title) or extract_price(item_desc)

                    addon_options = []
                    for label in option_labels:
                        opt_price = extract_price(label)
                        if opt_price == 0.0 and label.lower() not in ["no", "none", "no thanks", "i do not wish to enter"]:
                            opt_price = addon_default_price

                        addon_options.append({
                            "label": label,
                            "price": opt_price
                        })

                    config["addons"].append({
                        "id": sanitize_field_id(title),
                        "title": title,
                        "description": item_desc,
                        "default_price": addon_default_price,
                        "options": addon_options
                    })

                elif any(kw in title_lower for kw in ["division", "age", "group", "category"]):
                    for label in option_labels:
                        opt_price = extract_price(label)
                        if opt_price == 0.0 and label.lower() not in ["no", "none", "other"]:
                            opt_price = base_fee

                        config["divisions"].append({
                            "label": label,
                            "price": opt_price
                        })

                else:
                    config["form_fields"].append({
                        "id": sanitize_field_id(title),
                        "label": title,
                        "description": item_desc,
                        "type": "dropdown" if q_type == "DROP_DOWN" else "radio",
                        "options": option_labels,
                        "required": required
                    })

            elif "textQuestion" in question:
                is_paragraph = question["textQuestion"].get("paragraph", False)
                config["form_fields"].append({
                    "id": sanitize_field_id(title),
                    "label": title,
                    "description": item_desc,
                    "type": "textarea" if is_paragraph else "text",
                    "required": required
                })

    # 7. Save assets/config.json
    os.makedirs(os.path.dirname(CONFIG_OUTPUT_PATH), exist_ok=True)
    with open(CONFIG_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

    print(f"Successfully generated {CONFIG_OUTPUT_PATH} and {CSS_OUTPUT_PATH} with dynamic color palette!")

if __name__ == "__main__":
    sync_current_pageant()