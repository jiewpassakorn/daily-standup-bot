---

# 📄 Project Specification (Local Version)

## 🏷 Project Name

`gsheet-local-export`

---

# 🎯 Objective

สร้าง CLI script สำหรับใช้งานบนเครื่อง local ที่:

1. รับ Google Sheets URL
2. ดึง Spreadsheet ID + gid อัตโนมัติ
3. Export เป็น PDF แบบ:

   * margin = 0
   * no header/footer
   * fit to width
4. Convert PDF → PNG (default) หรือ JPG (600 dpi)
5. Auto trim white margin
6. รองรับ multi-page
7. Option รวมเป็นภาพเดียว

ไม่ต้องรองรับ OAuth / Service Account
รองรับ sheet ที่ต้อง login ผ่าน `--cookie` หรือ `--cookie-file` (ใช้ cookie จาก browser)

---

# 🛠 Tech Stack

* Python 3.12+
* Typer (CLI framework)
* requests (HTTP client)
* PyMuPDF (PDF → Image conversion)
* Pillow (trim / merge images)

---

# ⚙️ CLI Usage

```bash
# Public sheet
python main.py \
  --url "https://docs.google.com/spreadsheets/d/XXXX/edit#gid=12345" \
  --dpi 600 \
  --merge

# Private sheet (ต้อง login) — วิธีที่ 1: cookie-file (แนะนำ ปลอดภัยกว่า)
python main.py \
  --url "https://docs.google.com/spreadsheets/d/XXXX/edit#gid=12345" \
  --cookie-file ~/.gsheet-cookie

# Private sheet — วิธีที่ 2: cookie string (จะโชว์ใน shell history)
python main.py \
  --url "https://docs.google.com/spreadsheets/d/XXXX/edit#gid=12345" \
  --cookie "SID=xxx; HSID=xxx; SSID=xxx; ..."
```

---

# 📥 Input Parameters

| Flag     | Required | Default  | Description            |
| -------- | -------- | -------- | ---------------------- |
| --url         | ✅        | -        | Google Sheet URL                                      |
| --cookie      | ❌        | -        | Cookie string จาก browser (สำหรับ private sheet)        |
| --cookie-file | ❌        | -        | Path ไปไฟล์ที่เก็บ cookie (ปลอดภัยกว่า --cookie)         |
| --dpi         | ❌        | 600      | Image DPI                                             |
| --format      | ❌        | png      | Output format: png หรือ jpg                             |
| --portrait    | ❌        | false    | ใช้แนวตั้ง (default เป็น landscape)                      |
| --merge       | ❌        | false    | รวมทุกหน้าเป็นภาพเดียว                                  |
| --output      | ❌        | ./output | โฟลเดอร์เก็บไฟล์                                        |

---

# 🧠 Logic Flow

## Step 1: Parse URL

Extract Spreadsheet ID และ GID จาก URL รองรับหลาย format:

```text
# gid ใน fragment (เก่า)
https://docs.google.com/spreadsheets/d/{ID}/edit#gid=123

# gid ใน query param (ใหม่)
https://docs.google.com/spreadsheets/d/{ID}/edit?gid=123

# ไม่มี gid → default เป็น 0 (sheet แรก)
https://docs.google.com/spreadsheets/d/{ID}/edit
```

---

## Step 2: Generate Export URL

```text
https://docs.google.com/spreadsheets/d/{ID}/export?format=pdf
```

With params:

```text
gid={gid}
portrait={true if --portrait else false}
fitw=true
sheetnames=false
printtitle=false
pagenumbers=false
gridlines=false
fzr=false
top_margin=0
bottom_margin=0
left_margin=0
right_margin=0
```

---

## Step 3: Download PDF

ใช้ requests พร้อมแนบ cookie header (ถ้ามี)

```python
headers = {}
if cookie:
    headers["Cookie"] = cookie

response = requests.get(export_url, headers=headers, timeout=(10, 30))
response.raise_for_status()

# ตรวจสอบว่าได้ PDF จริง ไม่ใช่ HTML login page
content_type = response.headers.get("Content-Type", "")
if "text/html" in content_type:
    raise RuntimeError("ได้ HTML แทน PDF — cookie อาจหมดอายุหรือไม่มีสิทธิ์")
```

Save as:

```
sheet.pdf
```

---

## Step 4: Convert to Image + Trim

ใช้ PyMuPDF อ่าน PDF แล้ว Pillow trim ขอบขาว:

```python
import pymupdf
from PIL import Image, ImageChops

doc = pymupdf.open("sheet.pdf")
zoom = dpi / 72
mat = pymupdf.Matrix(zoom, zoom)

for i, page in enumerate(doc):
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # Auto trim white margin
    bg = Image.new("RGB", img.size, (255, 255, 255))
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()
    if bbox:
        img = img.crop(bbox)

    # format = "png" (default, lossless) หรือ "jpg"
    ext = format  # png | jpg
    save_args = {"quality": 95} if ext == "jpg" else {}
    img.save(f"page_{i+1:03d}.{ext}", **save_args)
```

---

## Step 5 (Optional Merge)

If --merge ใช้ Pillow ต่อภาพแนวตั้ง:

```python
def merge_vertical(images: list[Image.Image]) -> Image.Image:
    width = max(img.width for img in images)
    height = sum(img.height for img in images)
    merged = Image.new("RGB", (width, height), (255, 255, 255))
    y = 0
    for img in images:
        merged.paste(img, (0, y))
        y += img.height
    return merged
```

---

# 📂 Project Structure (Minimal)

```
├── main.py           # CLI entry point (Typer)
├── gsheet.py         # parse URL + download PDF
├── converter.py      # PDF → Image + trim + merge
└── requirements.txt
```

---

# ❗ Error Handling

* Invalid URL
* Network failure
* No gid found
* Response เป็น HTML แทน PDF (cookie หมดอายุ / ไม่มีสิทธิ์)
* HTTP 429 rate limit
* PDF เสียหาย / อ่านไม่ได้

---

# 📦 Installation

```bash
pip install -r requirements.txt
```

---

# 🧪 Expected Output

```
output/
 ├── sheet.pdf
 ├── page_001.png        (หรือ .jpg ถ้า --format jpg)
 ├── page_002.png
 └── merged.png (if --merge)
```

---

# 🧾 Claude CLI Prompt (Local Version)

คัดลอกไปใช้ได้เลย:

```
Create a minimal local CLI tool called "gsheet-local-export".

Requirements:
- Python 3.12+
- Use Typer for CLI, requests for HTTP, PyMuPDF for PDF rendering, Pillow for image manipulation
- No external system dependencies (no ImageMagick, no Ghostscript, pure pip install)
- Accept Google Sheets URL as input (support #gid=, ?gid=, and no-gid formats, default gid=0)
- Generate export PDF URL with zero margins
- Download PDF using requests with timeout=(10, 30) and response.raise_for_status()
- Validate response is PDF not HTML login page
- Convert PDF to high-quality images (600 dpi) using PyMuPDF with alpha=False
- Default output format PNG (lossless), support --format jpg
- Auto-trim white margins using Pillow
- Optional --merge to combine pages vertically
- Support --cookie and --cookie-file for private sheets (cookie-file is safer, won't appear in shell history)
- Support --portrait flag (default landscape)
- Simple error handling
- No OAuth
- Local use only
```

---