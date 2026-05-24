"""
Thai Text Extractor by KruJack (Clipboard-only version)
Extract Thai text from clipboard images using OCR (Tesseract / EasyOCR).
Simplified for lower memory usage on Render (512MB limit).
"""
import os
import re
import unicodedata
import uuid
import base64
import tempfile
from io import BytesIO
from flask import Flask, render_template, request, jsonify, send_file


# ── Auto-detect Tesseract path ──
def _find_tesseract() -> str:
    """Find Tesseract executable on any platform."""
    env_path = os.environ.get("TESSERACT_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    for p in ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]:
        if os.path.exists(p):
            return p
    win_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for p in win_paths:
        if os.path.exists(p):
            return p
    return "tesseract"


TESSERACT_CMD = _find_tesseract()

# Set custom TESSDATA_PREFIX
_tessdata_candidates = [
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tesseract-ocr/4/tessdata",
    "/usr/share/tesseract-ocr/tessdata",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tesseract-OCR", "tessdata"),
]
for td in _tessdata_candidates:
    if os.path.exists(td):
        os.environ["TESSDATA_PREFIX"] = td
        break

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# In-memory store for extracted texts (reset on restart)
extracted_store = {}


# ═══════════════════════════════════════════════════════════════════
#  POST-PROCESSING - Thai text cleaning pipeline
# ═══════════════════════════════════════════════════════════════════

TONE_HOST = (
    "\u0E01-\u0E2F"      # consonants + Pai Yan Noi
    "\u0E31"              # mai han akat
    "\u0E34-\u0E37"       # sara i, ii, ue, uee
    "\u0E47"              # mai tai khu
)

THAI_SCRIPT = "\u0E01-\u0E4E"

OCR_WORD_CORRECTIONS = [
    # --- Sara E (เ) vs Sara AE (แ) confusion ---
    ("คำเเนะนำ", "คำแนะนำ"),
    ("เเนะนำ", "แนะนำ"),
    ("เเนะ", "แนะ"),
    ("เเนอ", "แนะ"),
    # --- ท/ฒ confusion ---
    ("พัฒนำ", "พัฒนา"),
    # --- ฎ/ฏ confusion ---
    ("ปฎิบัติ", "ปฏิบัติ"),
    ("วัฎจักร", "วัฏจักร"),
    # --- Common OCR spacing errors ---
    ("ศึกษา", "ศึกษา"),  # (keep)
    ("กิจกรรม", "กิจกรรม"),
    ("ครูผู้สอน", "ครูผู้สอน"),
    ("การเรียนรู้", "การเรียนรู้"),
    ("ส่งเสริม", "ส่งเสริม"),
    ("สนับสนุน", "สนับสนุน"),
    ("สำนักงาน", "สำนักงาน"),
    ("ทำงาน", "ทำงาน"),
    ("กำหนด", "กำหนด"),
    ("ชัดเจน", "ชัดเจน"),
    ("ปัญหา", "ปัญหา"),
    ("ประเมิน", "ประเมิน"),
    ("ดำเนินการ", "ดำเนินการ"),
    ("เรียบร้อย", "เรียบร้อย"),
    ("สะทอน", "สะท้อน"),
    ("สม่ำเสมอ", "สม่ำเสมอ"),
    ("ต้อง", "ต้อง"),
    ("ได้", "ได้"),
    ("ที่สำคัญ", "ที่สำคัญ"),
    ("สำคัญ", "สำคัญ"),
    ("สำหรับ", "สำหรับ"),
    ("ประสิทธิภาพ", "ประสิทธิภาพ"),
    ("การศึกษา", "การศึกษา"),
    # --- Misplaced tone marks ---
    ("ขึน", "ขึ้น"),
    ("เพือ", "เพื่อ"),
    ("เพิม", "เพิ่ม"),
    # --- Duplicate / misread characters ---
    ("การร", "การ"),
    ("กาน", "การ"),
    ("และะ", "และ"),
    # --- Specific project words ---
    ("โรงเรียน", "โรงเรียน"),
    ("บ้านหนองหญ้าปล้อง", "บ้านหนองหญ้าปล้อง"),
    ("สำนักงานเขตพื้นที่", "สำนักงานเขตพื้นที่"),
    ("ประถม", "ประถม"),
    ("บุรีรัมย์", "บุรีรัมย์"),
    ("นิเทศ", "นิเทศ"),
    ("บาทถ้วน", "บาทถ้วน"),
]


def clean_thai_text(text: str) -> tuple[str, dict]:
    """Comprehensive Thai OCR text cleaning pipeline."""
    stats = {
        "null_chars": 0,
        "orphan_tones_removed": 0,
        "spacing_fixes": 0,
        "dict_corrections": 0,
    }

    # 1️⃣ Remove null bytes
    original = text
    text = text.replace('\u0000', '')
    stats["null_chars"] = len(original) - len(text)

    # 2️⃣ Unicode NFC normalization
    text = unicodedata.normalize('NFC', text)

    # 3️⃣ pythainlp normalize
    try:
        from pythainlp.util import normalize as thai_normalize
        text = thai_normalize(text)
    except ImportError:
        pass

    # 4️⃣ Remove orphaned tone marks
    tone_before = sum(1 for c in text if '\u0E48' <= c <= '\u0E4B')
    orphan_pattern = re.compile(
        r'(?<![' + TONE_HOST + r'])'
        r'[\u0E48-\u0E4B]'
    )
    text = orphan_pattern.sub('', text)
    tone_after = sum(1 for c in text if '\u0E48' <= c <= '\u0E4B')
    stats["orphan_tones_removed"] = tone_before - tone_after

    # 5️⃣ Fix inter-character spacing
    old_len = len(text)
    text = re.sub(r'([' + THAI_SCRIPT + r'])\s+(?=[' + THAI_SCRIPT + r'])', r'\1', text)
    stats["spacing_fixes"] = old_len - len(text)
    text = re.sub(r'[ \t]+', ' ', text)

    # 6️⃣ Dictionary corrections
    for wrong, correct in OCR_WORD_CORRECTIONS:
        count = text.count(wrong)
        if count > 0:
            text = text.replace(wrong, correct)
            stats["dict_corrections"] += count

    # 7️⃣ Fix duplicate Sara E/AE
    text = re.sub(r'([\u0E40\u0E41])\1+', r'\1', text)

    # 8️⃣ Final cleanup
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text, stats


# ═══════════════════════════════════════════════════════════════════
#  IMAGE PRE-PROCESSING - Enhance image before OCR
# ═══════════════════════════════════════════════════════════════════

def enhance_image_for_ocr(img):
    """
    Enhance image for better Thai OCR accuracy.
    Upscale 2x -> grayscale -> contrast -> Otsu threshold.
    """
    from PIL import Image, ImageEnhance

    w, h = img.width * 2, img.height * 2
    img = img.resize((w, h), Image.LANCZOS)

    if img.mode != 'L':
        img = img.convert('L')

    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)

    histogram = img.histogram()
    total = sum(histogram)

    best_threshold = 180
    max_variance = 0

    for t in range(1, 255):
        weight_bg_t = sum(histogram[:t])
        if weight_bg_t == 0:
            continue
        weight_fg_t = total - weight_bg_t
        if weight_fg_t == 0:
            break
        sum_bg_t = sum(i * histogram[i] for i in range(t))
        mean_bg = sum_bg_t / weight_bg_t
        mean_fg = (sum(i * histogram[i] for i in range(t, 256)) / weight_fg_t) if weight_fg_t > 0 else 0
        variance = weight_bg_t * weight_fg_t * (mean_bg - mean_fg) ** 2
        if variance > max_variance:
            max_variance = variance
            best_threshold = t

    img = img.point(lambda x: 0 if x < best_threshold else 255, '1')
    img = img.convert('L')
    return img


# ═══════════════════════════════════════════════════════════════════
#  EASYOCR READER (lazy singleton — only loaded when 'detailed' chosen)
# ═══════════════════════════════════════════════════════════════════

_easyocr_reader = None


def _get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        _easyocr_reader = easyocr.Reader(['th', 'en'], gpu=False, verbose=False)
    return _easyocr_reader


# ═══════════════════════════════════════════════════════════════════
#  OCR FUNCTIONS (for clipboard PIL images only — no PDF support)
# ═══════════════════════════════════════════════════════════════════

def _ocr_image_pil(img, method: str = "tesseract") -> str:
    """
    Run OCR on a PIL Image object.
    method: 'tesseract' (default, fast, low memory) or 'easyocr' (detailed, ~500MB memory)
    """
    if method == "easyocr":
        import numpy as np
        reader = _get_easyocr_reader()
        img_np = np.array(img)
        result = reader.readtext(img_np)
        texts = [detection[1].strip() for detection in result if detection[1].strip()]
        return "\n".join(texts)
    else:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        img = enhance_image_for_ocr(img)
        custom_config = r'--psm 6 --oem 3'
        return pytesseract.image_to_string(img, lang="tha+eng", config=custom_config)


def _extract_text_from_pil(img, filename: str, method: str = "fast") -> dict:
    """
    Extract text from a PIL Image object using OCR.
    Methods:
      - 'fast' (default): Tesseract OCR (faster, less memory)
      - 'detailed': EasyOCR (slower, better Thai accuracy, but ~500MB RAM)
    """
    method_used = ""
    extracted = ""

    if method == "detailed":
        try:
            extracted = _ocr_image_pil(img, method="easyocr")
            method_used = "EasyOCR"
        except Exception:
            extracted = ""
        if not extracted.strip():
            try:
                extracted = _ocr_image_pil(img, method="tesseract")
                method_used = "Tesseract"
            except Exception as e:
                return {"success": False, "error": f"OCR failed: {e}"}
    else:  # fast (default)
        try:
            extracted = _ocr_image_pil(img, method="tesseract")
            method_used = "Tesseract"
        except Exception as e:
            return {"success": False, "error": f"OCR failed: {e}"}

    pages = [{
        "number": 1,
        "text": extracted,
        "char_count": len(extracted.strip())
    }]

    raw_text = extracted
    cleaned_text, clean_stats = clean_thai_text(raw_text)

    download_id = str(uuid.uuid4())
    extracted_store[download_id] = cleaned_text

    return {
        "success": True,
        "total_pages": 1,
        "total_chars": len(cleaned_text),
        "cleaned_text": cleaned_text,
        "download_id": download_id,
        "filename": filename,
        "method": method_used,
        "clean_stats": clean_stats,
    }


# ═══════════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract-clipboard", methods=["POST"])
def extract_clipboard():
    """
    Extract text from a clipboard image (base64-encoded).
    Expects JSON: { "image": "<base64 data URL or raw base64>", "method": "fast" }
    """
    data = request.get_json()
    if not data or "image" not in data:
        return jsonify({"success": False, "error": "No image data received"})

    image_data = data["image"]
    method = data.get("method", "fast")
    if method not in ("fast", "detailed"):
        method = "fast"

    try:
        if "," in image_data:
            image_data = image_data.split(",")[1]

        image_bytes = base64.b64decode(image_data)
        from PIL import Image
        img = Image.open(BytesIO(image_bytes))

        result = _extract_text_from_pil(img, "clipboard_image.png", method)

        if result.get("success") and len(result.get("cleaned_text", "")) > 50000:
            result["cleaned_text"] = result["cleaned_text"][:50000] + "\n\n... [ข้อความยาวมาก กรุณาดาวน์โหลดไฟล์เพื่อดูทั้งหมด]"

        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to process clipboard image: {str(e)}"})


@app.route("/download/<download_id>")
def download(download_id):
    text = extracted_store.get(download_id)
    if text is None:
        return jsonify({"error": "File not found or expired"}), 404

    filename = request.args.get("filename", "extracted_text.txt")
    if not filename.endswith(".txt"):
        base, _ = os.path.splitext(filename)
        filename = base + ".txt"

    temp_path = os.path.join(tempfile.gettempdir(), download_id + ".txt")
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(text)

    return send_file(
        temp_path,
        as_attachment=True,
        download_name=filename,
        mimetype="text/plain; charset=utf-8"
    )


if __name__ == "__main__":
    os.makedirs("templates", exist_ok=True)
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("  Thai Text Extractor by KruJack (Clipboard-only)")
    print(f"  Running on port {port} (debug={debug_mode})")
    print("  Methods: Tesseract (fast) / EasyOCR (detailed)")
    print("=" * 60)
    app.run(debug=debug_mode, host="0.0.0.0", port=port)
