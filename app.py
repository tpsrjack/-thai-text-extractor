"""
Thai Text Extractor by KruJack
Extract Thai text from PDF files and images using PyMuPDF + OCR (Tesseract/EasyOCR).
Supports file upload and clipboard paste.
"""
import os
import re
import unicodedata
import tempfile
import uuid
import base64
import gc
from io import BytesIO
from flask import Flask, render_template, request, jsonify, send_file

# ── Auto-detect Tesseract path ──
def _find_tesseract() -> str:
    """Find Tesseract executable on any platform."""
    # Check environment variable first
    env_path = os.environ.get("TESSERACT_PATH")
    if env_path and os.path.exists(env_path):
        return env_path
    # Linux/Docker (default install path)
    linux_paths = ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]
    for p in linux_paths:
        if os.path.exists(p):
            return p
    # Windows (common paths)
    win_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for p in win_paths:
        if os.path.exists(p):
            return p
    return "tesseract"  # fallback to PATH

TESSERACT_CMD = _find_tesseract()

# Set custom TESSDATA_PREFIX
# Docker: /usr/share/tesseract-ocr/5/tessdata
# Linux: /usr/share/tesseract-ocr/4/tessdata
# Windows: %LOCALAPPDATA%\Tesseract-OCR\tessdata
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
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max
app.config["UPLOAD_FOLDER"] = os.path.join(tempfile.gettempdir(), "pdf_extractor")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0  # no cache for downloads

# Store extracted texts for download (in memory, expires on restart)
extracted_store = {}

# Allowed image extensions
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}


# ═══════════════════════════════════════════════════════════════════
#  POST-PROCESSING - Comprehensive Thai text cleaning pipeline
# ═══════════════════════════════════════════════════════════════════

# Thai Unicode classes used in regex patterns (for readability)
# Consonants: \u0E01-\u0E2E   (ก-ฮ)
# Sara above (carry tone marks): \u0E31 (mai han akat), \u0E34-\u0E37 (sara i/ii/ue/uee)
# Sara below: \u0E38-\u0E39 (sara u/uu)
# Tone marks: \u0E48-\u0E4B (mai ek, mai tho, mai tri, mai chattawa, thanthakhat)
# Mai tai khu: \u0E47

# Characters that CAN host a tone mark above them:
# Consonants (\u0E01-\u0E2E), Sara O (\u0E2D), Mai Han Akat (\u0E31),
# Sara I through Sara Uee (\u0E34-\u0E37), Mai Tai Khu (\u0E47)
TONE_HOST = (
    "\u0E01-\u0E2F"      # consonants + \u0E2F (Pai Yan Noi / ฯ)
    "\u0E31"              # mai han akat ( ั )
    "\u0E34-\u0E37"       # sara i, ii, ue, uee ( ิ ี ึ ื )
    "\u0E47"              # mai tai khu ( ็ )
)

# Characters that are Thai script elements (for spacing detection)
# Includes all consonants, vowels, tone marks, and special signs
THAI_SCRIPT = "\u0E01-\u0E4E"

# ─── Dictionary: Common Thai OCR word corrections ────────────────
# Format: (wrong_pattern, correct_word)
# Ordered from most specific to least specific to avoid false matches
OCR_WORD_CORRECTIONS = [
    # --- Sara E (เ) vs Sara AE (แ) confusion ---
    ("คา\u0E40\u0E19\u0E30นำ", "คำแนะนำ"),       # คาเเนะนำ
    ("คํา\u0E40\u0E19\u0E30นำ", "คำแนะนำ"),       # คําเเนะนำ
    ("\u0E40\u0E19\u0E30นำ", "แนะนำ"),             # เเนะนำ
    ("\u0E40\u0E19\u0E30", "แนะ"),                 # เเนะ
    ("\u0E40\u0E19\u0E2D", "แนะ"),                 # เเนอ

    # --- ท/ฒ confusion ---
    ("พั ฒ นา", "พัฒนา"),
    ("พฒั นา", "พัฒนา"),
    ("พฒั น", "พัฒน"),

    # --- ฎ/ฏ confusion ---
    ("ปฎิบัติ", "ปฏิบัติ"),
    ("ปฎบิ ัติ", "ปฏิบัติ"),
    ("ปฎบิ ตั ิ", "ปฏิบัติ"),
    ("วัฎจักร", "วัฏจักร"),
    ("วัฎ", "วัฏ"),
    ("ปฎิ", "ปฏิ"),

    # --- Common OCR spacing errors (word level) ---
    ("ศกึ ษา", "ศึกษา"),
    ("กจิ กรรม", "กิจกรรม"),
    ("ครผู ู้ สอน", "ครูผู้สอน"),
    ("ครผู ู้สอน", "ครูผู้สอน"),
    ("ครผู สู้ อน", "ครูผู้สอน"),
    ("การเรยีนรู้", "การเรียนรู้"),
    ("สง่ เสรมิ", "ส่งเสริม"),
    ("สนบั สนนุ", "สนับสนุน"),
    ("สํานักงาน", "สำนักงาน"),
    ("สาํ นักงาน", "สำนักงาน"),
    ("ทาํ งาน", "ทำงาน"),
    ("ทํางาน", "ทำงาน"),
    ("กาํ หนด", "กำหนด"),
    ("ชดั เจน", "ชัดเจน"),
    ("ปญั หา", "ปัญหา"),
    ("ปญหา", "ปัญหา"),
    ("ประเมนิ", "ประเมิน"),
    ("ผลการดาํ เนินงาน", "ผลการดำเนินงาน"),
    ("ดาํ เนินการ", "ดำเนินการ"),
    ("ดาํ เนิน", "ดำเนิน"),
    ("เรยี บร้อย", "เรียบร้อย"),
    ("สะทอน", "สะท้อน"),
    ("สม่ําเสมอ", "สม่ำเสมอ"),
    ("สมํ่าเสมอ", "สม่ำเสมอ"),
    ("ตอ้ ง", "ต้อง"),
    ("ตอ ้ง", "ต้อง"),
    ("ได ้", "ได้"),
    ("ทีส่ ําคญั", "ที่สำคัญ"),
    ("สาํ คญั", "สำคัญ"),
    ("สําคัญ", "สำคัญ"),
    ("สาํ หรับ", "สำหรับ"),
    ("สําหรับ", "สำหรับ"),
    ("ประสทิ ธิภาพ", "ประสิทธิภาพ"),
    ("ประสทิ ธิผล", "ประสิทธิผล"),
    ("การศกึ ษา", "การศึกษา"),
    ("ก ารศึกษา", "การศึกษา"),
    ("การศ ึกษา", "การศึกษา"),
    ("ก าร", "การ"),
    ("ป ระกอบ", "ประกอบ"),
    ("ป ระเมินผล", "ประเมินผล"),
    ("ป ระเมิน", "ประเมิน"),

    # --- Misplaced tone marks ---
    ("ข้ึน", "ขึ้น"),
    ("เพ่ือ", "เพื่อ"),
    ("เพอื่", "เพื่อ"),
    ("เพอ่ื", "เพื่อ"),
    ("เพิ่ ม", "เพิ่ม"),
    ("เพิม่", "เพิ่ม"),
    ("เพม่ิ", "เพิ่ม"),
    ("เพม่ิ เตมิ", "เพิ่มเติม"),
    ("เพม่ิเติม", "เพิ่มเติม"),

    # --- Duplicate / misread characters ---
    ("การร", "การ"),
    ("กาน", "การ"),
    ("และะ", "และ"),
    ("และ และ", "และ"),

    # --- Specific project words ---
    ("บ้านหนองหญาปลอ ง", "บ้านหนองหญ้าปล้อง"),
    ("บ้านหนองหญ้าปลอ ง", "บ้านหนองหญ้าปล้อง"),
    ("บ้านหนองหญ้าปล้อง", "บ้านหนองหญ้าปล้อง"),
    ("โรงเร ยน", "โรงเรียน"),
    ("โรงเรยีน", "โรงเรียน"),
    ("โรงเรยีนบ้าน", "โรงเรียนบ้าน"),
    ("โรงเรยีนบา้น", "โรงเรียนบ้าน"),
    ("โรงเรยีนหนอง", "โรงเรียนหนอง"),
    ("สำนักงานเขตพืน้ ที่", "สำนักงานเขตพื้นที่"),
    ("สํานกั งานเขตพื้นท่ี", "สำนักงานเขตพื้นที่"),
    ("สพป", "สพป"),
    ("ประดถดม", "ประถม"),
    ("ประดถ", "ประถม"),
    ("บร ีร มย์", "บุรีรัมย์"),
    ("บร ร มย์", "บุรีรัมย์"),
    ("เขตพนื ที", "เขตพื้นที่"),
    ("บร ีรีมย์", "บุรีรัมย์"),
    ("นเทศ", "นิเทศ"),
    ("บาทถวน", "บาทถ้วน"),
    ("บาทถว น", "บาทถ้วน"),
]


def clean_thai_text(text: str) -> tuple[str, dict]:
    """
    Comprehensive Thai OCR text cleaning pipeline.
    Returns (cleaned_text, stats_dict).
    """
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

    # 2️⃣ Unicode NFC normalization (combine characters properly)
    text = unicodedata.normalize('NFC', text)

    # 3️⃣ pythainlp normalize (handles specific Thai patterns)
    try:
        from pythainlp.util import normalize as thai_normalize
        text = thai_normalize(text)
    except ImportError:
        pass

    # 4️⃣ Remove orphaned tone marks
    # A tone mark should only follow a character that can host it:
    # consonants + specific vowels (mai han akat, sara i/ii/ue/uee) + mai tai khu
    # Count tone marks BEFORE removal for accurate stat
    tone_before = sum(1 for c in text if '\u0E48' <= c <= '\u0E4B')
    orphan_pattern = re.compile(
        r'(?<![' + TONE_HOST + r'])'   # preceded by something that's NOT a valid host
        r'[\u0E48-\u0E4B]'             # a tone mark (mai ek, tho, tri, chattawa, thanthakhat)
    )
    text = orphan_pattern.sub('', text)
    tone_after = sum(1 for c in text if '\u0E48' <= c <= '\u0E4B')
    stats["orphan_tones_removed"] = tone_before - tone_after

    # 5️⃣ Fix inter-character spacing in Thai text
    # Remove spaces between two Thai script characters (they belong together)
    old_len = len(text)
    text = re.sub(r'([' + THAI_SCRIPT + r'])\s+(?=[' + THAI_SCRIPT + r'])', r'\1', text)
    stats["spacing_fixes"] = old_len - len(text)

    # Collapse multiple horizontal spaces into one
    text = re.sub(r'[ \t]+', ' ', text)

    # 6️⃣ Apply dictionary word corrections
    for wrong, correct in OCR_WORD_CORRECTIONS:
        count = text.count(wrong)
        if count > 0:
            text = text.replace(wrong, correct)
            stats["dict_corrections"] += count

    # 7️⃣ Fix duplicate Sara E/AE (e.g., เเ -> เ, แแ -> แ)
    text = re.sub(r'([\u0E40\u0E41])\1+', r'\1', text)

    # 8️⃣ Final cleanup
    # Remove trailing whitespace per line
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines)

    # Clean up multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text, stats


# ═══════════════════════════════════════════════════════════════════
#  IMAGE PRE-PROCESSING - Enhance image before OCR
# ═══════════════════════════════════════════════════════════════════

# ─── EasyOCR Reader (lazy singleton) ────────────────────────────
# Load EasyOCR models once and reuse across requests
# This avoids reloading ~500MB of models on every extraction
_easyocr_reader = None

def _get_easyocr_reader():
    """Get or create the EasyOCR Reader singleton."""
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        _easyocr_reader = easyocr.Reader(['th', 'en'], gpu=False, verbose=False)
    return _easyocr_reader

def enhance_image_for_ocr(img):
    """
    Enhance image for better Thai OCR accuracy.
    Steps: upscale 2x -> grayscale -> contrast -> Otsu threshold.
    Upscaling is critical for Thai characters with fine vowel/tone mark details.
    """
    from PIL import Image, ImageEnhance

    # Step 1: Upscale 2x for better character detail recognition
    # Thai vowels and tone marks are small - upscaling helps Tesseract see them
    w, h = img.width * 2, img.height * 2
    img = img.resize((w, h), Image.LANCZOS)

    # Step 2: Grayscale
    if img.mode != 'L':
        img = img.convert('L')

    # Step 3: Increase contrast to make text bolder
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.5)

    # Step 4: Otsu adaptive threshold
    histogram = img.histogram()
    total = sum(histogram)

    best_threshold = 180  # default fallback
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

    # Apply threshold
    img = img.point(lambda x: 0 if x < best_threshold else 255, '1')
    img = img.convert('L')

    return img


def extract_text_ocr(pdf_path: str, lang: str = "tha+eng") -> dict:
    """Extract text from PDF using Tesseract OCR (for scanned/image-based PDFs)."""
    from pdf2image import convert_from_path, pdfinfo_from_path
    import pytesseract

    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    # Better OCR config for Thai text
    # --psm 6: Assume uniform block of text (better for single-column docs)
    # --oem 3: Default LSTM engine (combined with Legacy)
    custom_config = r'--psm 6 --oem 3'

    # Reduced DPI (300) to avoid OOM on multi-page PDFs
    # Process pages ONE AT A TIME to minimize peak memory usage
    info = pdfinfo_from_path(pdf_path)
    total_pages = info['Pages']

    pages = []
    for i in range(1, total_pages + 1):
        # Convert one page at a time — saves ~50-100MB per page vs loading all at once
        page_images = convert_from_path(pdf_path, dpi=300, fmt="png",
                                         first_page=i, last_page=i)
        if not page_images:
            continue
        img = page_images[0]

        # Enhance image for better OCR
        img = enhance_image_for_ocr(img)
        text = pytesseract.image_to_string(img, lang=lang, config=custom_config)
        pages.append({
            "number": i,
            "text": text,
            "char_count": len(text.strip())
        })

        # Explicit cleanup – free the PIL image and force GC periodically
        del img
        if i % 3 == 0:
            gc.collect()

    gc.collect()
    return pages


def extract_text_easyocr(pdf_path: str) -> dict:
    """Extract text from PDF using EasyOCR (better Thai accuracy).
    Slower than Tesseract but significantly more accurate for Thai text.
    """
    import numpy as np
    from pdf2image import convert_from_path, pdfinfo_from_path

    # Get the lazy-loaded singleton Reader (models loaded once)
    reader = _get_easyocr_reader()

    # Process pages ONE AT A TIME to minimise peak memory
    info = pdfinfo_from_path(pdf_path)
    total_pages = info['Pages']

    pages = []
    for i in range(1, total_pages + 1):
        # Convert one page at a time
        page_images = convert_from_path(pdf_path, dpi=300, fmt="png",
                                         first_page=i, last_page=i)
        if not page_images:
            continue
        img = page_images[0]

        img_np = np.array(img)
        # Free PIL image before the heavy OCR call
        del img

        try:
            result = reader.readtext(img_np)
            # Free numpy array after OCR is done
            del img_np
            # Result is list of [bbox, text, confidence]
            page_texts = []
            for detection in result:
                text = detection[1]
                if text.strip():
                    page_texts.append(text.strip())
            page_output = "\n".join(page_texts)
            pages.append({
                "number": i,
                "text": page_output,
                "char_count": len(page_output.strip())
            })
        except Exception as e:
            pages.append({
                "number": i,
                "text": f"[EasyOCR Error: {e}]",
                "char_count": 0
            })

        # Free numpy array even on error — prevents cumulative memory leak
        try:
            del img_np
        except NameError:
            pass

        # Periodic garbage collection to keep memory in check
        if i % 3 == 0:
            gc.collect()

    gc.collect()
    return pages


# ═══════════════════════════════════════════════════════════════════
#  TEXT EXTRACTION (PyMuPDF)
# ═══════════════════════════════════════════════════════════════════

def extract_text_pymupdf(pdf_path: str) -> dict:
    """Extract text from PDF using PyMuPDF (for text-based PDFs)."""
    import fitz
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        page_text = page.get_text() or ""
        pages.append({
            "number": page.number + 1,
            "text": page_text,
            "char_count": len(page_text.strip())
        })
    doc.close()
    return pages


# ═══════════════════════════════════════════════════════════════════
#  IMAGE OCR EXTRACTION (for standalone image files / clipboard)
# ═══════════════════════════════════════════════════════════════════

def _ocr_image_pil(img, method: str = "easyocr") -> str:
    """
    Run OCR on a PIL Image object.
    method: 'easyocr' (default) or 'tesseract'
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


def _extract_text_from_pil(img, filename: str, method: str = "detailed") -> dict:
    """
    Extract text from a PIL Image object using OCR.
    Internal helper used by both file-upload and clipboard routes.
    Methods:
      - 'fast': Tesseract OCR (faster, okay accuracy)
      - 'detailed': EasyOCR (slower, better Thai accuracy)
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
    else:  # fast
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

    # Store for download
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


def extract_text_from_image(image_path: str, method: str = "detailed") -> dict:
    """
    Extract text from a standalone image file using OCR.
    Methods: 'fast' (Tesseract) or 'detailed' (EasyOCR).
    Returns same format as extract_pdf_text.
    """
    from PIL import Image

    try:
        img = Image.open(image_path)
        return _extract_text_from_pil(img, os.path.basename(image_path), method)
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
#  MAIN EXTRACTOR
# ═══════════════════════════════════════════════════════════════════

def extract_pdf_text(pdf_path: str, method: str = "detailed") -> dict:
    """
    Extract text from PDF.
    Methods:
      - 'fast': PyMuPDF text extraction, fallback to Tesseract OCR (faster)
      - 'detailed': PyMuPDF text extraction, fallback to EasyOCR (better accuracy)
    """
    try:
        # Always try PyMuPDF first for text-based PDFs
        try:
            pages = extract_text_pymupdf(pdf_path)
            total_text_chars = sum(p["char_count"] for p in pages)
        except Exception:
            pages = []
            total_text_chars = 0

        # If little/no text found, likely a scanned PDF -> use OCR
        if total_text_chars < 50:
            if method == "detailed":
                # Detailed: try EasyOCR first, fallback to Tesseract
                try:
                    ocr_pages = extract_text_easyocr(pdf_path)
                    ocr_chars = sum(p["char_count"] for p in ocr_pages)
                    if ocr_chars > total_text_chars:
                        pages = ocr_pages
                        method_used = "EasyOCR"
                    else:
                        method_used = "ข้อความฝังตัว"
                except Exception:
                    try:
                        ocr_pages = extract_text_ocr(pdf_path)
                        ocr_chars = sum(p["char_count"] for p in ocr_pages)
                        if ocr_chars > total_text_chars:
                            pages = ocr_pages
                            method_used = "Tesseract"
                        else:
                            method_used = "ข้อความฝังตัว"
                    except Exception:
                        method_used = "ข้อความฝังตัว"
            else:
                # Fast: use Tesseract (faster than EasyOCR)
                try:
                    ocr_pages = extract_text_ocr(pdf_path)
                    ocr_chars = sum(p["char_count"] for p in ocr_pages)
                    if ocr_chars > total_text_chars:
                        pages = ocr_pages
                        method_used = "Tesseract"
                    else:
                        method_used = "ข้อความฝังตัว"
                except Exception:
                    method_used = "ข้อความฝังตัว"
        else:
            method_used = "ข้อความฝังตัว"

        raw_text = "\n\n".join(p["text"] for p in pages)
        cleaned_text, clean_stats = clean_thai_text(raw_text)

        # Store for download
        download_id = str(uuid.uuid4())
        extracted_store[download_id] = cleaned_text

        return {
            "success": True,
            "total_pages": len(pages),
            "total_chars": len(cleaned_text),
            "cleaned_text": cleaned_text,
            "download_id": download_id,
            "filename": os.path.basename(pdf_path),
            "method": method_used,
            "clean_stats": clean_stats,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
#  HELPER: Detect file type
# ═══════════════════════════════════════════════════════════════════

def get_file_extension(filename: str) -> str:
    """Get lowercase file extension including the dot."""
    _, ext = os.path.splitext(filename)
    return ext.lower()

def is_image_file(filename: str) -> bool:
    """Check if the file is a supported image type."""
    return get_file_extension(filename) in ALLOWED_IMAGE_EXTENSIONS

def is_pdf_file(filename: str) -> bool:
    """Check if the file is a PDF."""
    return get_file_extension(filename) == ".pdf"


# ═══════════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
def extract():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"})

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "No file selected"})

    ext = get_file_extension(file.filename)

    if not is_pdf_file(file.filename) and not is_image_file(file.filename):
        return jsonify({
            "success": False,
            "error": "Only PDF and image files are supported (PDF, PNG, JPG, JPEG, BMP, TIFF, WEBP)"
        })

    # Get extraction method from form data
    method = request.form.get("method", "detailed")
    if method not in ("fast", "detailed"):
        method = "detailed"

    # Save uploaded file
    temp_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(temp_path)

    # Extract text based on file type
    if is_image_file(file.filename):
        result = extract_text_from_image(temp_path, method)
    else:
        result = extract_pdf_text(temp_path, method)

    # Clean up temp file
    try:
        os.remove(temp_path)
    except Exception:
        pass

    # Don't send full text in response if too large, use download_id
    if result.get("success") and len(result.get("cleaned_text", "")) > 50000:
        result["cleaned_text"] = result["cleaned_text"][:50000] + "\n\n... [ข้อความยาวมาก กรุณาดาวน์โหลดไฟล์เพื่อดูทั้งหมด]"

    return jsonify(result)


@app.route("/extract-clipboard", methods=["POST"])
def extract_clipboard():
    """
    Extract text from a clipboard image (base64-encoded).
    Expects JSON: { "image": "<base64 data URL or raw base64>", "method": "auto" }
    """
    data = request.get_json()
    if not data or "image" not in data:
        return jsonify({"success": False, "error": "No image data received"})

    image_data = data["image"]
    method = data.get("method", "detailed")
    if method not in ("fast", "detailed"):
        method = "detailed"

    try:
        # Handle data URL format (data:image/png;base64,...) or raw base64
        if "," in image_data:
            image_data = image_data.split(",")[1]

        # Decode base64 to bytes and open as PIL Image directly (no disk I/O)
        image_bytes = base64.b64decode(image_data)
        from PIL import Image
        img = Image.open(BytesIO(image_bytes))

        # Extract text directly from PIL Image
        result = _extract_text_from_pil(img, "clipboard_image.png", method)

        # Truncate if needed
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
        # Replace image/pdf extension with .txt
        base, _ = os.path.splitext(filename)
        filename = base + ".txt"

    # Save to temp file for download
    temp_path = os.path.join(app.config["UPLOAD_FOLDER"], download_id + ".txt")
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
    print("  Thai Text Extractor by KruJack")
    print(f"  Running on port {port} (debug={debug_mode})")
    print("=" * 60)
    app.run(debug=debug_mode, host="0.0.0.0", port=port)
