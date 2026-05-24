"""
Thai OCR Comparison: Tesseract vs EasyOCR
Compares both OCR engines on the same Thai PDF and saves results.
"""
import os
import sys
import time

# Config
PDF_PATH = "รร.บ้านหนองหญ้าปล้อง.pdf"
OUTPUT_DIR = "ocr_comparison"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Set TESSDATA_PREFIX for Tesseract Thai support
tessdata_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Tesseract-OCR", "tessdata")
if os.path.isdir(tessdata_dir):
    os.environ["TESSDATA_PREFIX"] = tessdata_dir
    print(f"  TESSDATA_PREFIX set to: {tessdata_dir}")
else:
    prog_dir = r"C:\Program Files\Tesseract-OCR\tessdata"
    if os.path.isdir(prog_dir):
        os.environ["TESSDATA_PREFIX"] = prog_dir
        print(f"  TESSDATA_PREFIX set to: {prog_dir}")


def test_tesseract():
    """Run Tesseract OCR with our enhanced pipeline."""
    print("=" * 60)
    print("  TESTING: Tesseract OCR")
    print("=" * 60)

    from pdf2image import convert_from_path
    import pytesseract
    from PIL import Image, ImageEnhance

    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    # Our enhance function from app.py
    def enhance(img):
        w, h = img.width * 2, img.height * 2
        img = img.resize((w, h), Image.LANCZOS)
        if img.mode != 'L':
            img = img.convert('L')
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
        # Otsu-like threshold
        histogram = img.histogram()
        total = sum(histogram)
        best_t = 180
        max_var = 0
        for t in range(1, 255):
            wb = sum(histogram[:t])
            if wb == 0: continue
            wf = total - wb
            if wf == 0: break
            mean_b = sum(i * histogram[i] for i in range(t)) / wb
            mean_f = sum(i * histogram[i] for i in range(t, 256)) / wf if wf > 0 else 0
            var = wb * wf * (mean_b - mean_f) ** 2
            if var > max_var:
                max_var = var
                best_t = t
        img = img.point(lambda x: 0 if x < best_t else 255, '1').convert('L')
        return img

    start = time.time()
    images = convert_from_path(PDF_PATH, dpi=400, fmt="png")
    pages = []
    for img in images:
        img = enhance(img)
        text = pytesseract.image_to_string(img, lang="tha+eng", config="--psm 6 --oem 3")
        pages.append(text)
    elapsed = time.time() - start

    full_text = "\n\n".join(pages)
    path = os.path.join(OUTPUT_DIR, "tesseract_raw.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Chars: {len(full_text)}")
    print(f"  Saved: {path}")
    return full_text, elapsed


def test_easyocr():
    """Run EasyOCR on the same PDF with Thai language."""
    print("=" * 60)
    print("  TESTING: EasyOCR (Thai)")
    print("=" * 60)

    import easyocr
    from pdf2image import convert_from_path
    from PIL import Image

    # Initialize EasyOCR with Thai language (CPU mode)
    # First call downloads models, subsequent calls use cache
    print("  Loading EasyOCR Thai model (first load may take a moment)...")
    reader = easyocr.Reader(['th', 'en'], gpu=False, verbose=False)

    start = time.time()
    images = convert_from_path(PDF_PATH, dpi=400, fmt="png")
    pages = []

    for i, img in enumerate(images):
        # Convert PIL to numpy array for EasyOCR
        import numpy as np
        img_np = np.array(img)

        # Run EasyOCR
        try:
            # EasyOCR returns list of [bbox, text, confidence]
            result = reader.readtext(img_np)
            page_texts = []
            for detection in result:
                text = detection[1]  # The recognized text
                if text.strip():
                    page_texts.append(text.strip())
            page_output = "\n".join(page_texts)
            pages.append(page_output)
            print(f"  Page {i+1}: {len(page_texts)} text blocks detected")
        except Exception as e:
            pages.append(f"[EasyOCR Error on page {i+1}: {e}]")

    elapsed = time.time() - start

    full_text = "\n\n".join(pages)
    path = os.path.join(OUTPUT_DIR, "easyocr_raw.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Chars: {len(full_text)}")
    print(f"  Saved: {path}")
    return full_text, elapsed


def apply_cleaning(text: str, label: str):
    """Apply our clean_thai_text function for fair comparison."""
    sys.path.insert(0, '.')
    from app import clean_thai_text

    cleaned, stats = clean_thai_text(text)
    path = os.path.join(OUTPUT_DIR, f"{label}_cleaned.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(cleaned)
    print(f"  {label} cleaned: {len(cleaned)} chars, stats: {stats}")
    return cleaned, stats


def save_detailed_comparison(tess_cleaned: str, easy_cleaned: str,
                              tess_raw: str, easy_raw: str,
                              tess_time: float, easy_time: float,
                              tess_stats: dict, easy_stats: dict):
    """Save a detailed comparison to a text file (avoid console encoding issues)."""
    path = os.path.join(OUTPUT_DIR, "comparison_summary.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("  THAI OCR COMPARISON: Tesseract vs EasyOCR\n")
        f.write(f"  PDF: {PDF_PATH}\n")
        f.write("=" * 60 + "\n\n")

        # Summary table
        f.write("  SUMMARY TABLE\n")
        f.write("  " + "-" * 55 + "\n")
        f.write(f"  {'Metric':<25} {'Tesseract':<15} {'EasyOCR':<15}\n")
        f.write(f"  {'-'*25} {'-'*15} {'-'*15}\n")
        f.write(f"  {'Raw chars':<25} {len(tess_raw):<15} {len(easy_raw):<15}\n")
        f.write(f"  {'Cleaned chars':<25} {len(tess_cleaned):<15} {len(easy_cleaned):<15}\n")
        f.write(f"  {'Time (seconds)':<25} {tess_time:<15.1f} {easy_time:<15.1f}\n")
        f.write(f"  {'Spacing fixes':<25} {tess_stats.get('spacing_fixes', 0):<15} {easy_stats.get('spacing_fixes', 0):<15}\n")
        f.write(f"  {'Dict corrections':<25} {tess_stats.get('dict_corrections', 0):<15} {easy_stats.get('dict_corrections', 0):<15}\n\n")

        # Raw text comparison
        f.write("=" * 60 + "\n")
        f.write("  TESSERACT RAW (first 500 chars)\n")
        f.write("=" * 60 + "\n")
        f.write(tess_raw[:500] + "\n\n")

        f.write("=" * 60 + "\n")
        f.write("  EASYOCR RAW (first 500 chars)\n")
        f.write("=" * 60 + "\n")
        f.write(easy_raw[:500] + "\n\n")

        # Cleaned text comparison
        f.write("=" * 60 + "\n")
        f.write("  TESSERACT CLEANED\n")
        f.write("=" * 60 + "\n")
        tess_lines = [l.strip() for l in tess_cleaned.split("\n") if l.strip()]
        for line in tess_lines[:25]:
            f.write("  " + line + "\n")

        f.write("\n" + "=" * 60 + "\n")
        f.write("  EASYOCR CLEANED\n")
        f.write("=" * 60 + "\n")
        easy_lines = [l.strip() for l in easy_cleaned.split("\n") if l.strip()]
        for line in easy_lines[:25]:
            f.write("  " + line + "\n")

        # Line-by-line diff
        f.write("\n" + "=" * 60 + "\n")
        f.write("  LINE-BY-LINE COMPARISON\n")
        f.write("=" * 60 + "\n")
        max_lines = min(max(len(tess_lines), len(easy_lines)), 40)
        diff_count = 0
        for i in range(max_lines):
            t = tess_lines[i] if i < len(tess_lines) else ""
            e = easy_lines[i] if i < len(easy_lines) else ""
            if t != e:
                diff_count += 1
                f.write(f"\n  Line {i+1} [DIFF #{diff_count}]:\n")
                f.write(f"    Tesseract: {t}\n")
                f.write(f"    EasyOCR  : {e}\n")
            else:
                f.write(f"\n  Line {i+1} [SAME]: {t[:120]}\n")

        f.write(f"\n  Total different lines: {diff_count} / {max_lines}\n")
        f.write("\n" + "=" * 60 + "\n")
        f.write("  Files saved:\n")
        f.write(f"  - tesseract_raw.txt / tesseract_cleaned.txt\n")
        f.write(f"  - easyocr_raw.txt / easyocr_cleaned.txt\n")
        f.write(f"  - comparison_summary.txt (this file)\n")
        f.write("=" * 60 + "\n")

    print(f"\n  Detailed comparison saved to: {path}")
    return path


if __name__ == "__main__":
    # Run both OCR engines
    tess_raw, tess_time = test_tesseract()
    print()
    easy_raw, easy_time = test_easyocr()
    print()

    # Apply cleaning pipeline to both
    print("\n" + "─" * 50)
    print("  Applying cleaning pipeline...")
    print("─" * 50)
    tess_cleaned, tess_stats = apply_cleaning(tess_raw, "tesseract")
    easy_cleaned, easy_stats = apply_cleaning(easy_raw, "easyocr")
    print()

    # Save detailed comparison to file (avoids console encoding issues with Thai)
    summary_path = save_detailed_comparison(
        tess_cleaned, easy_cleaned,
        tess_raw, easy_raw,
        tess_time, easy_time,
        tess_stats, easy_stats
    )

    # Print brief summary to console
    print("=" * 60)
    print("  QUICK SUMMARY")
    print("=" * 60)
    print(f"  Tesseract: {len(tess_raw)} chars in {tess_time:.1f}s")
    print(f"  EasyOCR  : {len(easy_raw)} chars in {easy_time:.1f}s")
    print(f"  Tesseract cleaned: {len(tess_cleaned)} chars")
    print(f"  EasyOCR cleaned  : {len(easy_cleaned)} chars")
    print()
    print(f"  → Full comparison saved to: {summary_path}")
    print("=" * 60)
