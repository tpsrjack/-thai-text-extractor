"""
Script to extract text from Thai PDF files using pdfplumber.
"""
import pdfplumber
import sys
import os

def extract_text_from_pdf(pdf_path: str) -> tuple[str, int, int]:
    """Extract text from PDF and return (text, total_pages, total_chars)"""
    if not os.path.exists(pdf_path):
        print("ERROR: File not found: " + pdf_path, file=sys.stderr)
        sys.exit(1)

    text_pages = []
    
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)

        for i, page in enumerate(pdf.pages, 1):
            page_text = page.extract_text() or ""
            text_pages.append(page_text)
            char_count = len(page_text.strip())
            line = "  Page " + str(i) + "/" + str(total_pages) + ": " + str(char_count) + " characters"
            if char_count == 0:
                line += " [NO TEXT - may be scanned image]"
            print(line)

    full_text = "\n\n".join(text_pages)
    total_chars = len(full_text.strip())
    return full_text, total_pages, total_chars


if __name__ == "__main__":
    if len(sys.argv) < 2:
        pdf_path = "\u0e23\u0e23.\u0e1a\u0e49\u0e32\u0e19\u0e2b\u0e19\u0e2d\u0e07\u0e2b\u0e0d\u0e49\u0e32\u0e1b\u0e25\u0e49\u0e2d\u0e07.pdf"
    else:
        pdf_path = sys.argv[1]

    print("=" * 60)
    print("File: " + pdf_path)
    print("=" * 60)

    result, total_pages, total_chars = extract_text_from_pdf(pdf_path)

    print("\n" + "=" * 60)
    print("DONE: " + str(total_pages) + " pages, " + str(total_chars) + " characters extracted")
    print("=" * 60)

    if result.strip():
        # Print first 2000 chars as preview
        preview = result[:2000]
        if len(result) > 2000:
            preview += "\n\n...[TRUNCATED - showing first 2000 characters]..."
        print("\nPreview:")
        print("-" * 60)
        print(preview)
        print("-" * 60)
    else:
        print("\nWARNING: No text found in PDF.")
        print("This PDF may be a scanned image. Tesseract OCR would be needed.")

    # Save to text file
    output_path = pdf_path.replace(".pdf", ".txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)
    print("\nFull text saved to: " + output_path)
