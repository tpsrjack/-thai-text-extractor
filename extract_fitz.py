"""
Extract Thai PDF text using PyMuPDF (fitz) - the most accurate library tested.
"""
import os, sys

pdf_path = "\u0e23\u0e23.\u0e1a\u0e49\u0e32\u0e19\u0e2b\u0e19\u0e2d\u0e07\u0e2b\u0e0d\u0e49\u0e32\u0e1b\u0e25\u0e49\u0e2d\u0e07.pdf"
if len(sys.argv) > 1:
    pdf_path = sys.argv[1]

if not os.path.exists(pdf_path):
    print("ERROR: File not found: " + pdf_path)
    sys.exit(1)

import fitz

doc = fitz.open(pdf_path)
texts = []

print("=" * 60)
print("File: " + pdf_path)
print("Pages: " + str(len(doc)))
print("=" * 60)

for i, page in enumerate(doc, 1):
    page_text = page.get_text()
    texts.append(page_text)
    print("\n--- Page " + str(i) + " (" + str(len(page_text)) + " chars) ---")
    print(page_text)

doc.close()

# Save full text
output_path = pdf_path.replace(".pdf", "_fitz.txt")
full_text = "\n\n".join(texts)
with open(output_path, "w", encoding="utf-8") as f:
    f.write(full_text)
print("\nSaved to: " + output_path)
print("Total chars: " + str(len(full_text)))
