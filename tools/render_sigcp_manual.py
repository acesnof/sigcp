import base64
import re
import subprocess
from pathlib import Path

import mammoth


ROOT = Path(__file__).resolve().parents[1]
DOCX = ROOT / "docs" / "Manual_SIGCP.docx"
HTML = ROOT / "tmp" / "Manual_SIGCP.html"
PDF = ROOT / "docs" / "Manual_SIGCP.pdf"
EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def image_converter(image):
    with image.open() as stream:
        payload = base64.b64encode(stream.read()).decode("ascii")
    return {"src": f"data:{image.content_type};base64,{payload}"}


def build_html():
    with DOCX.open("rb") as stream:
        result = mammoth.convert_to_html(
            stream,
            convert_image=mammoth.images.img_element(image_converter),
            style_map="p[style-name='Title'] => h1.cover-title:fresh",
        )
    body = result.value
    body = re.sub(r"<h1>\d+\. ", "<h1>", body)
    first_chapter = "<h1>Controlo do documento</h1>"
    cover, remainder = body.split(first_chapter, 1)
    body = f"<section class='cover'>{cover}</section>{first_chapter}{remainder}"
    body = body.replace(
        "<h1>Anexo A — Plano de screenshots</h1><table>",
        "<h1>Anexo A — Plano de screenshots</h1><table class='screenshot-plan'>",
    )
    body = re.sub(
        r"(<h1>Índice(?: — continuação)?</h1>.*?)(<table>)",
        r"\1<table class='index-table'>",
        body,
        count=2,
        flags=re.S,
    )
    body = body.replace("<h1>", "<h1><span class='chapter-mark'>|</span> ")
    css = """
    @page { size: A4; margin: 16mm 17mm 16mm 19mm; }
    * { box-sizing: border-box; }
    body { margin: 0; color: #163438; font: 10.2pt/1.35 'Aptos', 'Segoe UI', Arial, sans-serif; }
    h1, h2, h3 { break-after: avoid; font-family: Arial, sans-serif; }
    h1 { margin: 0 0 9pt; padding-top: 3pt; break-before: page; color: #073f46; font-family: Georgia, 'Times New Roman', serif; font-size: 19pt; line-height: 1.1; letter-spacing: .01em; font-kerning: none; }
    .chapter-mark { color: #b51618; font-weight: 400; }
    h2 { margin: 12pt 0 6pt; color: #0b5962; font-size: 15pt; line-height: 1.15; }
    h3 { margin: 9pt 0 4pt; color: #b51618; font-size: 11.5pt; }
    p { margin: 0 0 6pt; orphans: 3; widows: 3; }
    ul, ol { margin: 3pt 0 8pt 19pt; padding: 0; }
    li { margin: 0 0 4pt; padding-left: 2pt; }
    table { width: 100%; margin: 8pt 0 10pt; border-collapse: collapse; break-inside: avoid; }
    td, th { padding: 7pt 8pt; border: .6pt solid #b9ccce; vertical-align: top; }
    tr:first-child td, tr:first-child td *, th, th * { background: #0b5962; color: white !important; font-weight: 700; }
    tr:nth-child(even) td { background: #f4f8f8; }
    table:has(td[colspan='1']) td { text-align: center; }
    table:has(td[colspan='1']) tr:first-child td { background: #0b5962; color: white !important; }
    img { display: block; max-width: 125px; max-height: 125px; margin: 0 auto 12pt; }
    .cover-title { margin-top: 25mm; text-align: center; font-size: 34pt; letter-spacing: .02em; }
    .cover { min-height: 255mm; display: flex; flex-direction: column; justify-content: center; break-after: page; }
    .cover p { text-align: center; }
    .cover table { margin-top: 22mm; }
    .screenshot-plan { font-size: 8.5pt; }
    .screenshot-plan td { padding: 3.2pt 7pt; line-height: 1.15; }
    .index-table { font-size: 8.5pt; break-inside: auto; }
    .index-table tr { break-inside: avoid; }
    .index-table td { padding: 3pt 7pt; line-height: 1.12; }
    strong { color: #073f46; }
    a { color: #0b5962; }
    """
    HTML.parent.mkdir(parents=True, exist_ok=True)
    HTML.write_text(
        "<!doctype html><html lang='pt'><head><meta charset='utf-8'>"
        f"<style>{css}</style></head><body>{body}</body></html>",
        encoding="utf-8",
    )


def print_pdf():
    if PDF.exists():
        PDF.unlink()
    subprocess.run(
        [
            str(EDGE),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={PDF}",
            HTML.resolve().as_uri(),
        ],
        check=True,
        timeout=120,
    )


if __name__ == "__main__":
    build_html()
    print_pdf()
    print(PDF)
