"""Capture WantGoo technical charts in the supplied northeast Asia slide order."""
from base64 import b64decode
from datetime import datetime
from io import BytesIO
from pathlib import Path

import streamlit as st

BACKGROUND = Path(__file__).with_name("weekly_report_background.b64")
MARKETS = [
    ("日經指數", "https://www.wantgoo.com/global/nki"),
    ("韓股綜合", "https://www.wantgoo.com/global/kor"),
    ("香港恆生", "https://www.wantgoo.com/global/hsi"),
    ("上證A股", "https://www.wantgoo.com/global/sha"),
    ("香港國企指數", "https://www.wantgoo.com/global/hsc"),
    ("台灣加權指數", "https://www.wantgoo.com/index/0000"),
]
PERIODS = [("日線", "日線"), ("週線", "周線"), ("月線", "月線")]
# Picture rectangles measured in inches from slides 3–20 of the supplied deck.
PLACEMENTS = [
    (1.170,.985,7.975,5.826),(1.400,.961,8.012,5.850),(1.425,.900,7.938,5.800),
    (1.400,.805,8.087,5.840),(1.427,1.042,7.835,5.715),(1.288,.898,7.937,5.814),
    (1.377,.890,7.902,5.822),(1.488,.895,8.120,5.860),(1.450,.891,8.037,5.846),
    (1.488,.914,7.862,5.823),(1.377,.953,7.835,5.747),(1.462,.889,7.962,5.849),
    (1.363,.920,7.950,5.818),(1.363,.921,7.950,5.804),(1.412,.910,7.938,5.815),
    (1.475,.831,8.012,5.869),(1.500,.817,8.113,5.896),(1.450,.882,8.000,5.892),
]


def build_chart_pptx(images, selected, captured_at):
    from pptx import Presentation
    from pptx.enum.text import PP_ALIGN
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(10), Inches(7.5)
    layout = prs.slide_layouts[6]
    background = b64decode(BACKGROUND.read_text())

    def slide_with_background():
        slide = prs.slides.add_slide(layout)
        slide.shapes.add_picture(BytesIO(background), 0, 0, width=prs.slide_width, height=prs.slide_height)
        return slide

    def label(slide, value, x, y, w, h, size=18):
        frame = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)).text_frame
        frame.clear()
        frame.word_wrap = True
        paragraph = frame.paragraphs[0]
        paragraph.alignment = PP_ALIGN.CENTER
        run = paragraph.add_run()
        run.text = value
        run.font.name = "標楷體"
        run.font.size = Pt(size)
        run.font.color.rgb = RGBColor(22, 46, 68)

    if len(selected) == len(MARKETS):
        cover = slide_with_background()
        label(cover, "國際指數－週技術線圖", 1, 2.3, 8, 1, 28)
        label(cover, captured_at.strftime("%Y/%m/%d"), 2, 4, 6, .6)
        divider = slide_with_background()
        label(divider, "亞洲", 2, 2.4, 6, 1, 28)

    for name, _ in selected:
        market_index = next(i for i, (market, _) in enumerate(MARKETS) if market == name)
        for period_index, (period, _) in enumerate(PERIODS):
            picture = images[(name, period)]
            x, y, w, h = PLACEMENTS[market_index * 3 + period_index]
            slide = slide_with_background()
            slide.shapes.add_picture(BytesIO(picture), Inches(x), Inches(y), width=Inches(w), height=Inches(h))
            label(slide, f"{name} {period}", 2.0, .12, 6, .55)
            label(slide, f"資料來源：玩股網　簡報製作：{captured_at:%Y/%m/%d %H:%M}", 2.0, .60, 6, .20, 10)
    output = BytesIO()
    prs.save(output)
    return output.getvalue()


def charts_from_pptx(data):
    """Import the eighteen chart pictures from the supplied slide format."""
    from pptx import Presentation

    source = Presentation(BytesIO(data))
    if len(source.slides) < 20:
        raise ValueError("簡報至少需要封面、亞洲頁與 18 張技術線圖。")
    images = {}
    for market_index, (name, _) in enumerate(MARKETS):
        for period_index, (period, _) in enumerate(PERIODS):
            slide = source.slides[market_index * 3 + period_index + 2]
            picture = next((shape for shape in slide.shapes if shape.shape_type == 13), None)
            if picture is None:
                raise ValueError(f"第 {market_index * 3 + period_index + 3} 頁缺少 {name} {period} 的截圖。")
            title = " ".join(shape.text for shape in slide.shapes if shape.has_text_frame)
            if period not in title:
                raise ValueError(f"第 {market_index * 3 + period_index + 3} 頁週期與預期的 {period} 不符。")
            images[(name, period)] = picture.image.blob
    return images


def render_wantgoo_capture():
    st.header("📸 玩股網技術線截圖")
    st.caption("順序：日經 → 韓股 → 恆生 → 上證A股 → 香港國企 → 台灣；各市場日線 → 週線 → 月線。圖表保留均線、成交量、KD、MACD，套用合庫背景與範例的圖片位置。")
    st.warning("玩股網目前對 Streamlit Cloud 的自動截圖顯示安全驗證，無法從網站伺服器直接擷取。請上傳你在玩股網更新過的技術線 PPT；系統會依原頁序抽出圖表並套用新背景。")
    uploaded = st.file_uploader("上傳技術線 PPTX（封面＋亞洲頁＋18 張圖）", type=["pptx"], key="wantgoo_source_pptx")
    if st.button("套用新背景並製作 PPT", type="primary", key="capture_wantgoo", disabled=uploaded is None):
        try:
            images = charts_from_pptx(uploaded.getvalue())
            captured_at = datetime.now()
            st.session_state["wantgoo_deck"] = build_chart_pptx(images, MARKETS, captured_at)
            st.session_state["wantgoo_images"] = images
            st.session_state["wantgoo_captured_at"] = captured_at
            st.session_state["wantgoo_selection"] = uploaded.name
        except Exception as exc:
            st.error(f"簡報處理失敗：{exc}")
    if uploaded and st.session_state.get("wantgoo_deck") and st.session_state.get("wantgoo_selection") == uploaded.name:
        captured_at = st.session_state["wantgoo_captured_at"]
        st.success(f"已匯入 {len(st.session_state['wantgoo_images'])} 張圖表。圖表日期以原簡報為準；{captured_at:%Y/%m/%d %H:%M} 為製作時間。")
        st.download_button("下載玩股網技術線 PPT", st.session_state["wantgoo_deck"],
                           file_name=f"玩股網技術線_{captured_at:%Y%m%d_%H%M}.pptx",
                           mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        with st.expander("預覽已擷取圖表"):
            for (name, period), data in st.session_state["wantgoo_images"].items():
                st.write(f"{name} {period}")
                st.image(data, use_container_width=True)
