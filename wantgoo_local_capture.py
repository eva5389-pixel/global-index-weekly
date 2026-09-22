"""Local, visible-browser capture of WantGoo charts. Run on the user's Mac."""
import json
import zipfile
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

MARKETS = [
    ("日經指數", "https://www.wantgoo.com/global/nki"),
    ("韓股綜合", "https://www.wantgoo.com/global/kor"),
    ("香港恆生", "https://www.wantgoo.com/global/hsi"),
    ("上證A股", "https://www.wantgoo.com/global/sha"),
    ("香港國企指數", "https://www.wantgoo.com/global/hsc"),
    ("台灣加權指數", "https://www.wantgoo.com/index/0000"),
]
PERIODS = [("日線", "日線"), ("週線", "周線"), ("月線", "月線")]


def select_period(page, label):
    # Keep the site's own chart and settings; never attempt to solve its verification.
    for text in (label, "週線" if label == "周線" else label):
        for tag in ("button", "a", "label", "span", "div"):
            locator = page.get_by_text(text, exact=True).locator(f"xpath=ancestor-or-self::{tag}[1]")
            try:
                if locator.count() == 1 and locator.first.is_visible():
                    locator.first.click(timeout=2000)
                    page.wait_for_timeout(1200)
                    return True
            except Exception:
                continue
    return False


def pick_region(page):
    page.evaluate("""() => {
      window.__captureRegion = null;
      const mask = document.createElement('div');
      Object.assign(mask.style, {position:'fixed',inset:'0',zIndex:'2147483647',cursor:'crosshair',background:'rgba(0,0,0,.08)'});
      const help = document.createElement('div');
      help.textContent = '拖曳框選圖表（包含 KD、MACD、成交量），放開滑鼠後返回終端機';
      Object.assign(help.style,{position:'absolute',top:'8px',left:'8px',padding:'10px',background:'white',color:'black'});
      const box = document.createElement('div');
      Object.assign(box.style,{position:'absolute',border:'2px solid #3179ff',background:'rgba(49,121,255,.12)'});
      mask.append(help,box); document.body.appendChild(mask);
      let start = null;
      mask.addEventListener('pointerdown',e => {start={x:e.clientX,y:e.clientY}; mask.setPointerCapture(e.pointerId);});
      mask.addEventListener('pointermove',e => {if (!start) return;
        const x=Math.min(start.x,e.clientX), y=Math.min(start.y,e.clientY);
        Object.assign(box.style,{left:x+'px',top:y+'px',width:Math.abs(e.clientX-start.x)+'px',height:Math.abs(e.clientY-start.y)+'px'});
      });
      mask.addEventListener('pointerup',e => {if (!start) return;
        const x=Math.min(start.x,e.clientX), y=Math.min(start.y,e.clientY);
        const width=Math.abs(e.clientX-start.x),height=Math.abs(e.clientY-start.y);
        if (width >= 200 && height >= 150) {window.__captureRegion={x,y,width,height};mask.remove();}
        start=null;
      });
    }""")
    print("請在瀏覽器拖曳框選圖表，包含日線／週線／月線切換後要保留的整塊區域。")
    while True:
        region = page.evaluate("window.__captureRegion")
        if region:
            return region
        page.wait_for_timeout(300)


def main():
    target = Path.home() / "Downloads" / f"玩股網技術線截圖_{datetime.now():%Y%m%d_%H%M}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    print("將開啟本機 Chromium。若出現玩股網驗證，請自行在瀏覽器完成。")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch_persistent_context(
            str(Path.home() / ".wantgoo_capture_browser"), headless=False,
            viewport={"width": 1440, "height": 1000}, device_scale_factor=1,
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(MARKETS[0][1], wait_until="domcontentloaded", timeout=60000)
        input("確認畫面已通過驗證、圖表及 KD/MACD 已顯示後，按 Enter 繼續：")
        region = pick_region(page)
        manifest = {"captured_at": datetime.now().isoformat(timespec="seconds"),
                    "region": region, "order": []}
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for mi, (market, url) in enumerate(MARKETS):
                if mi:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(1800)
                for pi, (period, button_text) in enumerate(PERIODS):
                    selected = select_period(page, button_text)
                    print(f"{mi * 3 + pi + 1:02d}/18 {market} {period}：請檢查圖表與週期。")
                    challenge = any(phrase in page.title().lower() for phrase in ("just a moment", "attention required"))
                    if not selected or challenge:
                        print("需要在瀏覽器手動確認週期或完成安全驗證。")
                        input("畫面正確後按 Enter 繼續擷取：")
                    page.wait_for_timeout(400)
                    data = page.screenshot(clip=region, animations="disabled")
                    filename = f"{mi * 3 + pi + 1:02d}.png"
                    output.writestr(filename, data)
                    manifest["order"].append({"file": filename, "market": market,
                                              "period": period, "url": page.url})
            output.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        browser.close()
    print(f"完成：{target}\n請回到 Streamlit『📸 玩股網技術線』分頁上傳 ZIP。")


if __name__ == "__main__":
    main()
