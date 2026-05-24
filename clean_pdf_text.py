"""
Script to clean extracted Thai PDF text.
Fixes:
1. Remove \u0000 (null) characters
2. Normalize Unicode (NFKC) to recombine decomposed characters
3. Fix common character corruption patterns from PDF extraction
"""
import re
import unicodedata
import sys
import os

# Common Thai character corruption patterns from PDF extraction
# These are specific to the font encoding used in this particular PDF
CORRECTIONS = {
    # Words with null chars removed
    "\u0e40\u0e04\u0e25\u0e37\u0e2d\u0e19": "\u0e40\u0e04\u0e25\u0e37\u0e48\u0e2d\u0e19",  # เคลื่อน
    "\u0e40\u0e1e\u0e37\u0e2d": "\u0e40\u0e1e\u0e37\u0e48\u0e2d",  # เพื่อ
    "\u0e02\u0e31\u0e19": "\u0e02\u0e31\u0e49\u0e19",  # ขั้น
    "\u0e40\u0e23\u0e35\u0e22\u0e19": "\u0e40\u0e23\u0e35\u0e22\u0e19\u0e23\u0e39\u0e49",  # เรียนรู้
}

def clean_text(text: str) -> str:
    """Clean extracted Thai PDF text."""
    # Step 1: Remove \u0000 (null characters)
    text = text.replace("\u0000", "")
    
    # Step 2: Remove isolated Thai tone marks on their own lines (artifact)
    text = re.sub(r'\n[\u0e48\u0e49\u0e4a\u0e4b\u0e4c]+\n', '\n', text)
    text = re.sub(r' +[\u0e48\u0e49\u0e4a\u0e4b\u0e4c]+ +', ' ', text)
    
    # Step 3: Normalize Unicode (NFKC) - recombines decomposed characters
    text = unicodedata.normalize("NFKC", text)
    
    # Step 4: Fix common Thai spacing issues
    # Remove spaces before Thai tone marks
    text = re.sub(r' \u0e48', '\u0e48', text)  #  ่
    text = re.sub(r' \u0e49', '\u0e49', text)  #  ้
    text = re.sub(r' \u0e4c', '\u0e4c', text)  #  ์
    text = re.sub(r' \u0e4a', '\u0e4a', text)  #  ๊
    text = re.sub(r' \u0e4b', '\u0e4b', text)  #  ๋
    
    # Step 5: Fix specific known words with tone mark issues
    # These are the most common words that appear corrupted
    fixes = {
        "\u0e1a\u0e32\u0e19": "\u0e1a\u0e49\u0e32\u0e19",  # บาน -> บ้าน (context dependent!)
        "\u0e41\u0e15\u0e07\u0e15\u0e31\u0e07": "\u0e41\u0e15\u0e48\u0e07\u0e15\u0e31\u0e49\u0e07",  # แตงตัง -> แต่งตั้ง
        "\u0e0a\u0e31\u0e14\u0e40\u0e08\u0e19": "\u0e0a\u0e31\u0e14\u0e40\u0e08\u0e19",  # ชัดเจน (actually correct here)
        "\u0e40\u0e1b\u0e32\u0e2b\u0e21\u0e32\u0e22": "\u0e40\u0e1b\u0e49\u0e32\u0e2b\u0e21\u0e32\u0e22",  # เปาหมาย -> เป้าหมาย
        "\u0e2a\u0e30\u0e17\u0e2d\u0e19": "\u0e2a\u0e30\u0e17\u0e49\u0e2d\u0e19",  # สะทอน -> สะท้อน
        "\u0e15\u0e34\u0e14\u0e15\u0e32\u0e21": "\u0e15\u0e34\u0e14\u0e15\u0e32\u0e21",  # ติดตาม (actually correct)
        "\u0e14\u0e49\u0e27\u0e22": "\u0e14\u0e49\u0e27\u0e22",  # ด้วย (correct)
        "\u0e43\u0e2b\u0e49": "\u0e43\u0e2b\u0e49",  # ให้ (correct)
        "\u0e40\u0e02\u0e49\u0e32": "\u0e40\u0e02\u0e49\u0e32",  # เข้า (correct)
    }
    
    # Step 6: Fix vowel order issues - some PDFs swap vowel positions
    # e.g. "เเ" -> "แ"
    text = text.replace("\u0e40\u0e40", "\u0e41")  # เเ -> แ
    
    # Step 7: Clean up multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text


def main():
    input_path = sys.argv[1] if len(sys.argv) > 1 else "\u0e23\u0e23.\u0e1a\u0e49\u0e32\u0e19\u0e2b\u0e19\u0e2d\u0e07\u0e2b\u0e0d\u0e49\u0e32\u0e1b\u0e25\u0e49\u0e2d\u0e07.txt"
    
    if not os.path.exists(input_path):
        print("ERROR: File not found: " + input_path)
        sys.exit(1)
    
    with open(input_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    
    print("=" * 60)
    print("Cleaning: " + input_path)
    print("=" * 60)
    
    cleaned = clean_text(raw_text)
    
    # Save result
    output_path = input_path.replace(".txt", "_cleaned.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cleaned)
    
    # Stats
    raw_chars = len(raw_text)
    clean_chars = len(cleaned)
    null_count = raw_text.count("\u0000")
    
    print()
    print("Stats:")
    print("  Original characters: " + str(raw_chars))
    print("  Cleaned characters:  " + str(clean_chars))
    print("  Null chars removed:  " + str(null_count))
    print()
    print("=" * 60)
    print("Cleaned text preview (first 2000 chars):")
    print("-" * 60)
    print(cleaned[:2000])
    print("-" * 60)
    print()
    print("Full text saved to: " + output_path)


if __name__ == "__main__":
    main()
