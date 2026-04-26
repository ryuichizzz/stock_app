from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_NAME = "JP"


def _wrap_text(c, text: str, max_width: float, font: str, size: int):
    """日本語を文字単位で折り返す"""
    if not text:
        return [""]

    c.setFont(font, size)

    lines = []
    cur = ""
    for ch in text:
        nxt = cur + ch
        if c.stringWidth(nxt, font, size) <= max_width:
            cur = nxt
        else:
            lines.append(cur)
            cur = ch

    if cur:
        lines.append(cur)

    return lines


def build_simple_pdf(data: dict, font_path: str, submit_mode: bool = True) -> bytes:
    """
    submit_mode=True: 提出用（個人番号をPDFに出さない）
    submit_mode=False: 社内用（個人番号も出す）
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    pdfmetrics.registerFont(TTFont(FONT_NAME, font_path))

    margin = 40
    x = margin
    y = H - margin

    line_h = 16
    label_w = 160
    value_x = x + label_w
    value_w = W - margin - value_x

    # タイトル
    c.setFont(FONT_NAME, 16)
    title = "労働者名簿（テキスト出力）"
    if submit_mode:
        title += "［提出用：個人番号非表示］"
    c.drawString(x, y, title)
    y -= 28

    # 項目（18項目のうち、提出用では「個人番号」を除外）
    fields = [
        ("氏名", data.get("name", "")),
        ("ふりがな", data.get("name_kana", "")),
        ("生年月日", data.get("birth_date", "")),
        ("住所", data.get("address", "")),
        ("電話番号", data.get("phone", "")),
        ("従事する業務の種類", data.get("job_type", "")),
        ("雇入れ年月日", data.get("hire_date", "")),
        ("雇入れの経緯", data.get("hire_story", "")),
        ("履歴", data.get("history", "")),
        ("免許資格", data.get("license", "")),
        # ("個人番号", data.get("my_number", "")),  ← 提出用は出さない
        ("健康保険番号", data.get("health_ins", "")),
        ("基礎年金番号", data.get("pension_base", "")),
        ("厚生年金番号", data.get("welfare_pension", "")),
        ("雇用保険番号", data.get("employment_ins", "")),
        ("退職日", data.get("leave_date", "")),
        ("退職の事由", data.get("leave_reason", "")),
        ("備考", data.get("remarks", "")),
    ]

    if not submit_mode:
        # 社内用だけ「個人番号」も入れる（位置は免許資格の直後に合わせる）
        fields.insert(10, ("個人番号", data.get("my_number", "")))

    def ensure_space(n_lines: int):
        nonlocal y
        if y - n_lines * line_h < margin:
            c.showPage()
            c.setFont(FONT_NAME, 10)
            y = H - margin

    c.setFont(FONT_NAME, 10)

    for label, value in fields:
        value = value or ""

        ensure_space(2)
        c.drawString(x, y, f"{label}：")

        wrapped = []
        for part in str(value).splitlines() or [""]:
            wrapped.extend(_wrap_text(c, part, value_w, FONT_NAME, 10))

        ensure_space(len(wrapped))

        for line in wrapped:
            c.drawString(value_x, y, line)
            y -= line_h

        y -= 6

    c.showPage()
    c.save()
    return buf.getvalue()
