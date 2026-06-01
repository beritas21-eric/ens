"""
로그인 후 메뉴 구조 진단 스크립트
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import os, ssl, time, urllib3
os.environ['WDM_SSL_VERIFY'] = '0'
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.http import WDMHttpClient
import requests

LOGIN_URL = "https://esdr.skax-sv-ai.com/login"
LOGIN_ID  = "kukil.kang"
LOGIN_PW  = "#Skcc03477"
SAVE_DIR  = r"C:\Users\03477\Downloads\popup_inspect"
os.makedirs(SAVE_DIR, exist_ok=True)

class NoSSLClient(WDMHttpClient):
    def get(self, url, **kwargs):
        kwargs.pop('verify', None)
        return requests.get(url, verify=False, stream=True, **kwargs)

def create_driver():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--ignore-certificate-errors")
    try:
        return webdriver.Chrome(service=Service(ChromeDriverManager(http_client=NoSSLClient()).install()), options=options)
    except Exception:
        return webdriver.Chrome(options=options)

def dismiss_alert(driver):
    try:
        WebDriverWait(driver, 3).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        print(f"  [alert 닫기] '{alert.text}'")
        alert.accept()
    except Exception:
        pass

def save_snapshot(driver, name):
    driver.save_screenshot(os.path.join(SAVE_DIR, f"{name}.png"))
    with open(os.path.join(SAVE_DIR, f"{name}.html"), "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"  → 저장: {SAVE_DIR}\\{name}.png / .html")

def print_all_buttons(driver, label=""):
    print(f"\n── {label} 버튼 목록 ──")
    buttons = driver.find_elements(By.TAG_NAME, "button")
    for i, b in enumerate(buttons):
        try:
            print(f"  [{i}] text='{b.text.strip()}' | type='{b.get_attribute('type')}' | class='{b.get_attribute('class')}' | visible={b.is_displayed()}")
        except Exception:
            pass
    # div/span/a 중 클릭 가능한 요소도 확인
    print(f"\n── {label} 클릭 가능 요소(div·span·a) 목록 ──")
    els = driver.execute_script("""
        var res = [];
        ['a','span','div','li'].forEach(function(tag){
            document.querySelectorAll(tag).forEach(function(el){
                var txt = el.textContent.trim().replace(/\\s+/g,' ');
                var rect = el.getBoundingClientRect();
                var cursor = window.getComputedStyle(el).cursor;
                if(txt && txt.length>0 && txt.length<30 && rect.width>0 && cursor==='pointer'){
                    res.push({tag:tag, text:txt, cls:(el.className||'').substring(0,60)});
                }
            });
        });
        return res.slice(0,50);
    """)
    for e in els:
        print(f"  [{e['tag']}] \"{e['text']}\"  class='{e['cls']}'")

def inject_auto_ok(driver):
    driver.execute_script("""
        if(window.__autoOk) return;
        var labels = ['OK','Ok','확인'];
        function tryClick(root){
            (root.querySelectorAll?root.querySelectorAll('button'):[]).forEach(function(b){
                if(labels.indexOf(b.textContent.trim())>-1 && !b.disabled) b.click();
            });
        }
        tryClick(document.body);
        var obs = new MutationObserver(function(m){
            m.forEach(function(mut){
                mut.addedNodes.forEach(function(n){ if(n.nodeType===1) tryClick(n); });
            });
        });
        obs.observe(document.body,{childList:true,subtree:true});
        window.__autoOk = obs;
    """)

def main():
    driver = create_driver()
    wait = WebDriverWait(driver, 15)

    # ── 1. 로그인 페이지 접속 ──────────────────────────
    print(f"\n[1] 로그인 페이지 접속: {LOGIN_URL}")
    driver.get(LOGIN_URL)
    time.sleep(2)
    dismiss_alert(driver)
    save_snapshot(driver, "01_login_page")
    print_all_buttons(driver, "로그인 페이지")

    # ── 2. ID / PW 입력 ────────────────────────────────
    print("\n[2] ID / PW 입력...")
    # ID 필드 탐색 (모든 input 시도)
    inputs = driver.find_elements(By.TAG_NAME, "input")
    print(f"  input 필드 목록:")
    for i, inp in enumerate(inputs):
        print(f"    [{i}] type='{inp.get_attribute('type')}' name='{inp.get_attribute('name')}' id='{inp.get_attribute('id')}' placeholder='{inp.get_attribute('placeholder')}'")

    # 첫 번째 text/email input → ID, 첫 번째 password → PW
    id_field = None
    pw_field = None
    for inp in inputs:
        t = inp.get_attribute("type") or "text"
        if t in ("text", "email", "") and id_field is None:
            id_field = inp
        elif t == "password" and pw_field is None:
            pw_field = inp

    if id_field:
        id_field.clear()
        id_field.send_keys(LOGIN_ID)
        print(f"  ID 입력 완료")
    else:
        print("  [오류] ID 입력 필드를 찾지 못했습니다.")

    if pw_field:
        pw_field.clear()
        pw_field.send_keys(LOGIN_PW)
        print(f"  PW 입력 완료")
    else:
        print("  [오류] PW 입력 필드를 찾지 못했습니다.")

    # ── 3. 로그인 버튼 클릭 ────────────────────────────
    print("\n[3] 로그인 버튼 탐색 및 클릭...")
    inject_auto_ok(driver)

    login_btn = None
    # 시도 순서: submit → 텍스트 → cursor:pointer 요소
    candidates = [
        ("CSS", "button[type='submit']"),
        ("CSS", "input[type='submit']"),
        ("XPATH", "//*[contains(text(),'로그인')]"),
        ("XPATH", "//*[contains(text(),'Login')]"),
        ("XPATH", "//*[contains(text(),'login')]"),
        ("XPATH", "//*[contains(text(),'SIGN IN')]"),
        ("XPATH", "//*[contains(text(),'Sign in')]"),
        ("XPATH", "//button[last()]"),   # 마지막 버튼
    ]
    for by_type, selector in candidates:
        try:
            by = By.CSS_SELECTOR if by_type == "CSS" else By.XPATH
            el = driver.find_element(by, selector)
            if el.is_displayed():
                login_btn = el
                print(f"  로그인 버튼 발견: [{by_type}] {selector}  text='{el.text.strip()}'")
                break
        except Exception:
            continue

    if login_btn:
        login_btn.click()
        print("  클릭 완료")
    else:
        print("  [경고] 로그인 버튼을 자동으로 찾지 못했습니다.")
        print("  → 브라우저에서 직접 로그인 버튼을 눌러주세요.")
        input("  로그인 후 [Enter] 키를 누르세요...")

    # ── 4. 로그인 완료 대기 ────────────────────────────
    print("\n[4] 로그인 완료 대기...")
    try:
        wait.until(EC.url_changes(LOGIN_URL))
    except Exception:
        pass
    time.sleep(2)
    dismiss_alert(driver)
    time.sleep(1)
    dismiss_alert(driver)

    print(f"\n현재 URL: {driver.current_url}")
    save_snapshot(driver, "02_after_login")

    # ── 5. 메뉴 구조 출력 ─────────────────────────────
    print("\n" + "="*60)
    print("【 메뉴 구조 】")
    print("="*60)
    menu_items = driver.execute_script("""
        var results = [];
        var seen = new Set();
        var selectors = [
            'nav a','nav button','nav li','nav span',
            'aside a','aside li','aside span',
            '[class*="menu"] a','[class*="menu"] li','[class*="menu"] span',
            '[class*="sidebar"] a','[class*="sidebar"] li',
            '[class*="gnb"] a','[class*="lnb"] a',
            '[role="menuitem"]','[role="navigation"] a'
        ];
        selectors.forEach(function(sel){
            try {
                document.querySelectorAll(sel).forEach(function(el){
                    var txt = el.textContent.trim().replace(/\\s+/g,' ');
                    if(txt && txt.length>0 && txt.length<50 && !seen.has(txt)){
                        seen.add(txt);
                        results.push({
                            tag: el.tagName,
                            text: txt,
                            cls: (el.className||'').substring(0,80),
                            href: el.href || ''
                        });
                    }
                });
            } catch(e){}
        });
        return results;
    """)

    if menu_items:
        for item in menu_items:
            href = f"\n      href: {item['href']}" if item['href'] else ""
            print(f"  [{item['tag']}] \"{item['text']}\"\n      class: {item['cls']}{href}")
    else:
        print("  메뉴 항목을 찾지 못했습니다.")
        print_all_buttons(driver, "로그인 후 화면")

    print("\n" + "="*60)
    input("\n[Enter] 키를 누르면 종료합니다...")
    driver.quit()

if __name__ == "__main__":
    main()
