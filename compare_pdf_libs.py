"""
Compare Thai PDF text extraction across different libraries:
1. pdfplumber
2. pypdf
3. PyMuPDF (fitz)
"""
import sys
import os

pdf_path = "\u0e23\u0e23.\u0e1a\u0e49\u0e32\u0e19\u0e2b\u0e19\u0e2d\u0e07\u0e2b\u0e0d\u0e49\u0e32\u0e1b\u0e25\u0e49\u0e2d\u0e07.pdf"

if not os.path.exists(pdf_path):
    print("ERROR: PDF not found: " + pdf_path)
    sys.exit(1)

print("=" * 60)
print("Comparing Thai PDF extraction methods")
print("PDF: " + pdf_path)
print("=" * 60)

# Method 1: pdfplumber
print("\n[1/3] pdfplumber:")
try:
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        texts = []
        for page in pdf.pages:
            t = page.extract_text() or ""
            texts.append(t)
        result = "\n\n".join(texts)
    print("  Chars: " + str(len(result)))
    print("  Preview: " + result[:300].replace("\n", "|"))
except Exception as e:
    print("  ERROR: " + str(e))

# Method 2: pypdf
print("\n[2/3] pypdf:")
try:
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    texts = []
    for page in reader.pages:
        t = page.extract_text() or ""
        texts.append(t)
    result = "\n\n".join(texts)
    print("  Chars: " + str(len(result)))
    print("  Preview: " + result[:300].replace("\n", "|"))
except Exception as e:
    print("  ERROR: " + str(e))

# Method 3: PyMuPDF (fitz)
print("\n[3/3] PyMuPDF (fitz):")
try:
    import fitz
    doc = fitz.open(pdf_path)
    texts = []
    for page in doc:
        t = page.get_text() or ""
        texts.append(t)
    result = "\n\n".join(texts)
    print("  Chars: " + str(len(result)))
    print("  Preview: " + result[:300].replace("\n", "|"))
    doc.close()
except Exception as e:
    print("  ERROR: " + str(e))

print("\n" + "=" * 60)
print("Done!")
