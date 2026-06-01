"""
팝업 HTML 구조 진단 스크립트
- 로그인 후 팝업이 뜨는 순간 HTML 소스와 스크린샷을 저장
- 저장 경로: D:\Downloads\popup_inspect\
"""
import os
import ssl
import time
import urllib3
import datetime

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

LOGIN_URL  = "https://esdr.skax-sv-ai.com/login"
LOGIN_ID   = "kukil.kang"
LOGIN_PW   = "#Skcc03477"
SAVE_DIR   = r"D:\Downloads\popup_inspect"
os.makedirs(SAVE_DIR, exist_ok=True)


class NoSSLClient(WDMHttpClient):
    def get(self, url, **kwargs):
        kwargs.pop('verify', None)
        return requests.get(url, verify=False, stream=True, **kwargs)


def create_driver():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors=yes")
    try:
        service = Service(ChromeDriverManager(http_client=NoSSLClient()).install())
        return webdriver.Chrome(service=service, options=options)
    except Exception:
        return webdriver.Chrome(options=options)


def save_snapshot(driver, label="snapshot"):
    """현재 화면의 HTML과 스크린샷을 저장"""
    ts = datetime.datetime.now().strftime("%H%M%S")
    name = f"{ts}_{label}"

    # 스크린샷 저장
    img_path = os.path.join(SAVE_DIR, f"{name}.png")
    driver.save_screenshot(img_path)
    print(f"  [스크린샷] {img_path}")

    # 전체 페이지 HTML 저장
    html_path = os.path.join(SAVE_DIR, f"{name}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print(f"  [HTML소스] {html_path}")

    # 현재 화면에서 보이는 모든 버튼 출력
    print("\n  ── 현재 페이지의 모든 <button> 목록 ──")
    buttons = driver.find_elements(By.TAG_NAME, "button")
    if buttons:
        for i, btn in enumerate(buttons):
            try:
                txt   = btn.text.strip().replace('\n', ' ')
                cls   = btn.get_attribute("class") or ""
                typ   = btn.get_attribute("type") or ""
                vis   = btn.is_displayed()
                print(f"  [{i}] text='{txt}' | class='{cls}' | type='{typ}' | visible={vis}")
            except Exception:
                print(f"  [{i}] (읽기 실패)")
    else:
        print("  (버튼 없음)")
    print()


def main():
    driver = create_driver()
    wait = WebDriverWait(driver, 15)

    try:
        # ── 1. 로그인 페이지 접속 ──────────────────────────
        print(f"\n[1] 로그인 페이지 접속: {LOGIN_URL}")
        driver.get(LOGIN_URL)
        time.sleep(2)

        # 접속 직후 스냅샷
        print("[스냅샷] 로그인 페이지 초기 상태")
        save_snapshot(driver, "01_login_page")

        # ── 2. 로그인 폼 입력 ──────────────────────────────
        print("\n[2] ID / PW 입력...")
        try:
            id_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR,
                "input[type='text'], input[name='username'], input[name='id'], "
                "input[id='username'], input[id='id']")))
        except Exception:
            id_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[1]")))

        id_field.clear()
        id_field.send_keys(LOGIN_ID)

        try:
            pw_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        except Exception:
            pw_field = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))

        pw_field.clear()
        pw_field.send_keys(LOGIN_PW)

        try:
            login_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        except Exception:
            login_btn = driver.find_element(By.XPATH,
                "//button[contains(text(),'로그인') or contains(text(),'Login')]")

        print("[3] 로그인 버튼 클릭 → 팝업 대기...")
        login_btn.click()

        # ── 3. 팝업 감지: 0.3초 간격으로 폴링 ─────────────
        print("\n[4] 팝업 / 화면 변화 감지 중 (최대 10초)...")
        deadline = time.time() + 10
        prev_url = driver.current_url
        snap_count = 0

        while time.time() < deadline:
            time.sleep(0.3)
            cur_url = driver.current_url

            # URL 변경 감지 → 즉시 스냅샷
            if cur_url != prev_url:
                snap_count += 1
                print(f"\n[URL 변경 감지] {prev_url}\n             → {cur_url}")
                save_snapshot(driver, f"0{snap_count+1}_url_change")
                prev_url = cur_url

            # 버튼 변화 감지 → 즉시 스냅샷
            buttons = driver.find_elements(By.TAG_NAME, "button")
            visible_btns = [b for b in buttons if b.is_displayed()]
            if visible_btns and snap_count == 0:
                snap_count += 1
                print(f"\n[버튼 감지] 화면에 버튼 {len(visible_btns)}개 발견")
                save_snapshot(driver, f"0{snap_count+1}_buttons_detected")

        # ── 4. 최종 상태 저장 ──────────────────────────────
        print("\n[5] 최종 상태 스냅샷 저장")
        save_snapshot(driver, "final_state")

        print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"저장 완료: {SAVE_DIR}")
        print(f"HTML 파일을 메모장/VS Code로 열어 버튼 구조를 확인하세요.")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        input("\n[Enter] 키를 누르면 브라우저를 닫습니다...")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
