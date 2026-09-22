"""Editable weekly market report and Word/PowerPoint exports."""
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path

import streamlit as st

BACKGROUND = Path(__file__).with_name("weekly_report_background.png")
FONT = "標楷體"


def report_docx(start, end, overview, sections):
    from docx import Document
    from docx.shared import Cm, Pt
    from docx.oxml.ns import qn

    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Cm(2)
    sec.left_margin = sec.right_margin = Cm(2.2)
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(11)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    doc.add_heading("全球市場每週報告", 0)
    doc.add_paragraph(f"報告期間：{start:%Y/%m/%d}－{end:%Y/%m/%d}")
    doc.add_heading("本週重點", 1)
    doc.add_paragraph(overview or "待補充")
    for title, notes, items in sections:
        doc.add_heading(title, 1)
        if notes.strip():
            doc.add_paragraph(notes.strip())
        for item in items:
            doc.add_paragraph(item, style="List Bullet")
    doc.add_paragraph("資料說明：指數漲跌由最近可用收盤價計算；各項資料日期以條目所列為準。事件及原因請人工核對。僅供內部教育訓練與市場研究。")
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def report_pptx(start, end, overview, sections):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(10), Inches(7.5)
    blank = prs.slide_layouts[6]

    def textbox(slide, content, x, y, w, h, *, center=False, fill=None):
        if fill is not None:
            shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
            shape.fill.solid()
            shape.fill.fore_color.rgb = RGBColor(*fill)
            shape.line.fill.background()
        else:
            shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = shape.text_frame
        tf.clear()
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Inches(.12)
        tf.margin_top = tf.margin_bottom = Inches(.06)
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE if center else MSO_ANCHOR.TOP
        for i, line in enumerate(content.split("\n")):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = line
            p.alignment = PP_ALIGN.CENTER if center else PP_ALIGN.LEFT
            p.space_after = Pt(8)
            for run in p.runs:
                run.font.name = FONT
                run.font.size = Pt(18)
                run.font.color.rgb = RGBColor(15, 38, 50)
        return shape

    def new_slide(title, cover=False):
        slide = prs.slides.add_slide(blank)
        slide.shapes.add_picture(str(BACKGROUND), 0, 0, width=prs.slide_width, height=prs.slide_height)
        # Mask the fixed label in the supplied image; retain the logo and footer.
        if cover:
            textbox(slide, title, 1.45, 2.18, 7.1, 1.35, center=True, fill=(237, 246, 255))
        else:
            textbox(slide, "", 1.1, 1.54, 7.8, 5.08, fill=(255, 255, 255))
            textbox(slide, title, 1.35, 1.57, 7.3, .5, center=True)
        return slide

    cover = new_slide("全球市場每週報告", cover=True)
    textbox(cover, f"{start:%Y/%m/%d}－{end:%Y/%m/%d}", 1.8, 4.15, 6.4, .6, center=True)

    def add_text_pages(title, text):
        # 18 pt Chinese text fits about 34 characters per line in the content area.
        lines = []
        for paragraph in (text.strip().splitlines() or ["待補充"]):
            if not paragraph:
                lines.append("")
            else:
                while len(paragraph) > 34:
                    lines.append(paragraph[:34])
                    paragraph = paragraph[34:]
                lines.append(paragraph)
        chunks = [lines[i:i + 10] for i in range(0, len(lines), 10)] or [["待補充"]]
        for index, chunk in enumerate(chunks):
            slide = new_slide(title + (f"（續 {index + 1}）" if index else ""))
            textbox(slide, "\n".join(chunk), 1.35, 2.27, 7.3, 4.2)

    add_text_pages("本週重點", overview or "待補充")
    for title, notes, items in sections:
        content = "\n".join(([notes.strip()] if notes.strip() else []) + ["• " + item for item in items])
        add_text_pages(title, content or "待補充")
    add_text_pages("資料與使用說明", "指數漲跌由最近可用收盤價計算；各項資料日期以條目所列為準。事件及原因請人工核對。\n僅供內部教育訓練與市場研究。")
    output = BytesIO()
    prs.save(output)
    return output.getvalue()


def render_weekly_report(cache, markets):
    st.header("📝 每週市場報告")
    st.caption("依目前取得的行情整理草稿；事件與漲跌原因由你補充並核對後再下載。PPT 採提供的背景，內文為標楷體 18 點。")
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    a, b = st.columns(2)
    start = a.date_input("週起日", monday, key="report_start")
    end = b.date_input("週迄日", monday + timedelta(days=6), key="report_end")
    if start > end:
        st.error("週起日不能晚於週迄日。")
        return
    overview = st.text_area("本週重點摘要（可編輯）", placeholder="例如：主要市場走勢、政策與產業事件，以及下週觀察事項。", height=115, key="report_overview")
    sections = []
    for region, names in markets.items():
        with st.expander(region, expanded=region in ("🇹🇼 台灣", "🇯🇵 日本")):
            notes = st.text_area("事件／原因與下週觀察（人工核對）", key=f"report_notes_{region}", height=100)
            items = []
            for name in names:
                x, _, _ = cache.get(name, (None, None, None))
                if x:
                    items.append(f"{name}：最新 {x['最新']:,.2f}；本週 {x['本週%']:+.2f}%；近一月 {x['近1月%']:+.2f}%；趨勢{x['趨勢']}。資料日期：{x['日期']}。")
                else:
                    items.append(f"{name}：行情暫缺，待核對。")
            st.write("\n\n".join(items))
            sections.append((region, notes, items))
    if not any(cache.get(name, (None,))[0] for names in markets.values() for name in names):
        st.warning("目前沒有取得行情。仍可編輯摘要並下載空白報告，市場條目會標示資料暫缺。")
    st.caption("下載檔案會使用畫面上當前填寫的內容；文字欄位只在此瀏覽器工作階段保留。")
    c1, c2 = st.columns(2)
    c1.download_button("下載 Word 報告", report_docx(start, end, overview, sections),
                       file_name=f"每週市場報告_{start:%Y%m%d}.docx",
                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    c2.download_button("下載 PPT 簡報", report_pptx(start, end, overview, sections),
                       file_name=f"每週市場報告_{start:%Y%m%d}.pptx",
                       mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
