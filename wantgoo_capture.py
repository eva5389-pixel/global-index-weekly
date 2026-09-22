"""Capture WantGoo technical charts in the supplied northeast Asia slide order."""
from base64 import b64decode
from datetime import datetime
from io import BytesIO
from pathlib import Path
import shutil

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


def capture_charts(selected, progress=None):
    """Take browser screenshots of the chart panel with MA, volume, KD and MACD."""
    from playwright.sync_api import sync_playwright

    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if not chromium:
        raise RuntimeError("伺服器尚未安裝 Chromium。請確認 packages.txt 已部署。")
    images = {}
    total = len(selected) * len(PERIODS)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=chromium,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=1)
            for name, url in selected:
                response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                panel = page.locator(".technical-charts")
                try:
                    panel.locator("svg.highcharts-root").wait_for(state="visible", timeout=35000)
                except Exception as exc:
                    title = page.title()
                    text = page.locator("body").inner_text(timeout=5000)[:240].replace("\n", " ")
                    status = response.status if response else "無回應"
                    raise RuntimeError(f"{name} 圖表沒有載入（HTTP {status}，頁面：{title}；{text}）") from exc
                # The supplied sample shows the default four indicators in this order.
                selects = page.locator(".technical-wrap select")
                for index, label in enumerate(("K線及均線", "成交量", "KD", "MACD")):
                    if selects.count() > index:
                        selects.nth(index).select_option(label=label)
                for period, button in PERIODS:
                    page.locator(".technical-wrap").get_by_role("button", name=button, exact=True).click()
                    panel.locator("svg.highcharts-root").wait_for(state="visible", timeout=30000)
                    page.wait_for_timeout(1100)
                    image = panel.screenshot(timeout=30000, animations="disabled")
                    if len(image) < 10000:
                        raise RuntimeError(f"{name} {period} 圖表內容尚未載入。")
                    images[(name, period)] = image
                    if progress:
                        progress(len(images), total, name, period)
        finally:
            browser.close()
    return images


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
            label(slide, f"資料來源：玩股網　截圖：{captured_at:%Y/%m/%d %H:%M}", 2.0, .60, 6, .20, 10)
    output = BytesIO()
    prs.save(output)
    return output.getvalue()


def render_wantgoo_capture():
    st.header("📸 玩股網技術線截圖")
    st.caption("順序：日經 → 韓股 → 恆生 → 上證A股 → 香港國企 → 台灣；各市場日線 → 週線 → 月線。圖表保留均線、成交量、KD、MACD，套用合庫背景與範例的圖片位置。")
    choice = st.selectbox("截圖範圍", ["全部六個市場（18張）"] + [name for name, _ in MARKETS])
    selected = MARKETS if choice.startswith("全部") else [next(item for item in MARKETS if item[0] == choice)]
    st.info("擷取的是玩股網當下顯示的圖表。若網站需要登入、限制存取或圖表未載入，頁面會顯示原因，不會輸出空白截圖。")
    if st.button("擷取圖表並製作 PPT", type="primary", key="capture_wantgoo"):
        bar = st.progress(0, text="正在開啟玩股網圖表")
        try:
            def report_progress(done, total, name, period):
                bar.progress(done / total, text=f"已擷取 {done}/{total}：{name} {period}")
            images = capture_charts(selected, report_progress)
            captured_at = datetime.now()
            st.session_state["wantgoo_deck"] = build_chart_pptx(images, selected, captured_at)
            st.session_state["wantgoo_images"] = images
            st.session_state["wantgoo_captured_at"] = captured_at
            st.session_state["wantgoo_selection"] = choice
        except Exception as exc:
            st.error(f"圖表擷取失敗：{exc}")
        finally:
            bar.empty()
    if st.session_state.get("wantgoo_deck") and st.session_state.get("wantgoo_selection") == choice:
        captured_at = st.session_state["wantgoo_captured_at"]
        st.success(f"完成 {len(st.session_state['wantgoo_images'])} 張圖表截圖（{captured_at:%Y/%m/%d %H:%M}）")
        st.download_button("下載玩股網技術線 PPT", st.session_state["wantgoo_deck"],
                           file_name=f"玩股網技術線_{captured_at:%Y%m%d_%H%M}.pptx",
                           mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        with st.expander("預覽已擷取圖表"):
            for (name, period), data in st.session_state["wantgoo_images"].items():
                st.write(f"{name} {period}")
                st.image(data, use_container_width=True)
