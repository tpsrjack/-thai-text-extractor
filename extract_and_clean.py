"""
Extract Thai PDF text using PyMuPDF (best results) and fix encoding issues.
"""
import os, sys, re

# Character mapping fixes for common Thai PDF font encoding issues
FIXES = {
    # Sara E (เ) vs Sara AE (แ) - common mix-up in PDF fonts
    "\u0e40\u0e19\u0e30": "\u0e41\u0e19\u0e30",  # เเนะ -> แนะ
    "\u0e40\u0e19": "\u0e41\u0e19",  # เน -> แน (context-dependent)
    
    # Tho Thong (ฎ) vs To Patak (ฏ) - visually similar in some fonts
    "\u0e0e\u0e34": "\u0e0f\u0e34",  # ฎิ -> ฏิ
    "\u0e27\u0e0e\u0e08\u0e31\u0e01\u0e23": "\u0e27\u0e31\u0e0e\u0e08\u0e31\u0e01\u0e23",  # วัฎจักร -> วัฏจักร
    
    # Sara O (โ) issues
    "\u0e42\u0e1b\u0e23\u0e42\u0e22\u0e19": "\u0e42\u0e1b\u0e23\u0e14\u0e42\u0e22\u0e19",  # pattern fix
}

def apply_fixes(text: str) -> str:
    """Apply common Thai PDF character fixes."""
    # Fix เเนะ -> แนะ (Sara E -> Sara AE before certain chars)
    text = re.sub(r'\u0e40\u0e19\u0e30', '\u0e41\u0e19\u0e30', text)  # เเนะ -> แนะ
    
    # Fix ฎิ -> ฏิ (in words like ปฎิบัติ -> ปฏิบัติ)
    text = re.sub(r'\u0e0e\u0e34', '\u0e0f\u0e34', text)  # ฎิ -> ฏิ
    
    # Fix วัฎจักร -> วัฏจักร 
    text = re.sub(r'\u0e27\u0e31\u0e0e\u0e08\u0e31\u0e01\u0e23', '\u0e27\u0e31\u0e0f\u0e08\u0e31\u0e01\u0e23', text)
    
    # Normalize multiple spaces to single space
    text = re.sub(r'  +', ' ', text)
    
    # Remove trailing whitespace on each line
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines)
    
    # Clean up multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "\u0e23\u0e23.\u0e1a\u0e49\u0e32\u0e19\u0e2b\u0e19\u0e2d\u0e07\u0e2b\u0e0d\u0e49\u0e32\u0e1b\u0e25\u0e49\u0e2d\u0e07.pdf"
    
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
    
    doc.close()
    
    raw_text = "\n\n".join(texts)
    cleaned = apply_fixes(raw_text)
    
    # Compare
    print("\nBefore fixes:")
    print("-" * 40)
    # Show specific problem areas
    for search, replacement in [
        ("\u0e40\u0e19\u0e30", "\u0e41\u0e19\u0e30"),  # เเนะ -> แนะ
        ("\u0e0e\u0e34", "\u0e0f\u0e34"),  # ฎิ -> ฏิ
    ]:
        count = raw_text.count(search)
        if count > 0:
            print("  Fixed " + str(count) + "x: " + repr(search) + " -> " + repr(replacement))
    
    print("\n" + "=" * 60)
    print("CLEANED TEXT:")
    print("=" * 60)
    print()
    print(cleaned)
    
    # Save
    output_path = pdf_path.replace(".pdf", "_final.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cleaned)
    print()
    print("=" * 60)
    print("Saved to: " + output_path)
    print("Total chars: " + str(len(cleaned)))


if __name__ == "__main__":
    main()
