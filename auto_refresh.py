
#git hub push#
import os
import re
import ssl
import sys
import time

# Windows 콘솔 UTF-8 출력 설정 (cp949 인코딩 오류 방지)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import datetime
import urllib3
import ctypes
import ctypes.wintypes
import threading
import subprocess
import winsound

# 사내 SSL 프록시 환경: SSL 검증 비활성화
os.environ['WDM_SSL_VERIFY'] = '0'
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import UnexpectedAlertPresentException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.http import WDMHttpClient
import requests


class NoSSLClient(WDMHttpClient):
    def get(self, url, **kwargs):
        kwargs.pop('verify', None)
        return requests.get(url, verify=False, stream=True, **kwargs)


LOGIN_URL          = "https://esdr.skax-sv-ai.com/login"
TARGET_URL         = "https://esdr.skax-sv-ai.com/device-management/monitoring-edge-device-view-admin"
LOGIN_ID           = "kukil.kang"
LOGIN_PW           = "#Skcc03477"
START_HOUR         = 8    # 오전 8시
START_MINUTE       = 0    # 0분 (정각)
END_HOUR           = 17   # 오후 5시 자동 종료
KEEPALIVE_INTERVAL = 30   # 초
DRONE_ALTITUDE_M   = 100  # 드론 고도 가정값 (m)

# Windows SetThreadExecutionState 플래그
ES_CONTINUOUS       = 0x80000000  # 지속 유지
ES_SYSTEM_REQUIRED  = 0x00000001  # 시스템 절전 방지
ES_DISPLAY_REQUIRED = 0x00000002  # 화면보호기/디스플레이 절전 방지


def prevent_screensaver():
    """화면보호기 및 절전 모드 비활성화 (앱 실행 중 유지)"""
    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED
    )
    print(f"[{_ts()}] 화면보호기 비활성화 설정 완료")


def reset_screensaver():
    """화면보호기 및 절전 모드 원래 설정으로 복원"""
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
    print(f"[{_ts()}] 화면보호기 설정 복원 완료")


# ──────────────────────────────────────────────
# 팝업 처리
# ──────────────────────────────────────────────

def dismiss_browser_alert(driver, timeout=3):
    """브라우저 기본 alert 처리"""
    try:
        WebDriverWait(driver, timeout).until(EC.alert_is_present())
        alert = driver.switch_to.alert
        msg = alert.text
        alert.accept()
        print(f"[{_ts()}] [기본 팝업] 닫기: '{msg}'")
        return True
    except Exception:
        return False


def dismiss_custom_modal(driver, timeout=5):
    """커스텀 HTML 모달의 OK 버튼을 클릭.
    ① JavaScript로 화면에 보이는 'OK'/'확인' 버튼을 직접 탐색·클릭 (프레임워크 무관)
    ② JS 실패 시 XPath fallback
    """
    # ── 방법 1: JavaScript 직접 탐색 (가장 확실) ──────────────────────────
    js_click = """
        var okTexts = ['OK', 'Ok', '확인'];
        var buttons = Array.from(document.querySelectorAll('button'));
        for (var i = 0; i < buttons.length; i++) {
            var btn = buttons[i];
            var txt = btn.textContent.trim();
            var rect = btn.getBoundingClientRect();
            var visible = rect.width > 0 && rect.height > 0
                          && window.getComputedStyle(btn).visibility !== 'hidden'
                          && window.getComputedStyle(btn).display !== 'none';
            if (visible && okTexts.indexOf(txt) !== -1) {
                btn.click();
                return txt;
            }
        }
        return null;
    """
    # timeout 동안 폴링하며 OK 버튼 대기
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = driver.execute_script(js_click)
            if result:
                print(f"[{_ts()}] [커스텀 모달] JS로 닫기: '{result}' 버튼 클릭")
                time.sleep(1.0)
                return True
        except Exception:
            pass
        time.sleep(0.5)

    # ── 방법 2: XPath fallback ─────────────────────────────────────────────
    for xpath in [
        "//button[normalize-space(text())='OK']",
        "//button[normalize-space(text())='Ok']",
        "//button[normalize-space(text())='확인']",
        "//button[contains(@class,'p-button-primary')]",   # PrimeVue
        "//button[contains(@class,'btn-primary')]",        # Bootstrap
        "//button[contains(@class,'el-button--primary')]", # Element UI
    ]:
        try:
            btn = driver.find_element(By.XPATH, xpath)
            if btn.is_displayed() and btn.is_enabled():
                btn.click()
                print(f"[{_ts()}] [커스텀 모달] XPath로 닫기: {xpath}")
                time.sleep(1.0)
                return True
        except Exception:
            continue

    return False


def dismiss_any_popup(driver, timeout=5):
    """기본 alert + 커스텀 모달을 모두 처리. 팝업이 연속으로 뜰 수 있어 반복 확인."""
    dismiss_browser_alert(driver, timeout=2)
    dismissed = dismiss_custom_modal(driver, timeout=timeout)
    if dismissed:
        # 팝업 닫은 후 추가 팝업이 연달아 뜰 수 있으므로 한 번 더 확인
        time.sleep(0.5)
        dismiss_browser_alert(driver, timeout=2)
        dismiss_custom_modal(driver, timeout=3)


# ──────────────────────────────────────────────
# 드라이버 / 로그인 / 페이지 이동
# ──────────────────────────────────────────────

def _ts():
    return datetime.datetime.now().strftime('%H:%M:%S')


def is_active_time():
    now = datetime.datetime.now()
    start = now.replace(hour=START_HOUR, minute=START_MINUTE, second=0, microsecond=0)
    end   = now.replace(hour=END_HOUR,   minute=0,            second=0, microsecond=0)
    return start <= now < end


def seconds_until_start():
    now = datetime.datetime.now()
    start = now.replace(hour=START_HOUR, minute=START_MINUTE, second=0, microsecond=0)
    if now >= start:
        start += datetime.timedelta(days=1)
    return (start - now).total_seconds()


def create_driver():
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--allow-insecure-localhost")
    options.add_argument("--ignore-ssl-errors=yes")
    try:
        service = Service(ChromeDriverManager(http_client=NoSSLClient()).install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"[경고] webdriver_manager 실패 ({e}), 내장 드라이버 사용")
        driver = webdriver.Chrome(options=options)
    return driver


def close_all_chrome():
    """실행 중인 모든 Chrome 프로세스를 종료"""
    targets = ["chrome.exe", "chromedriver.exe"]
    for proc in targets:
        result = subprocess.run(
            ["taskkill", "/f", "/im", proc],
            capture_output=True, text=True
        )
        if "성공" in result.stdout or "SUCCESS" in result.stdout.upper():
            print(f"[{_ts()}] {proc} 종료 완료")
        else:
            print(f"[{_ts()}] {proc} 실행 중인 프로세스 없음")
    time.sleep(2)  # 프로세스 완전 종료 대기


def inject_auto_ok_observer(driver):
    """로그인 클릭 전에 MutationObserver를 DOM에 주입.
    팝업 버튼이 DOM에 추가되는 즉시(< 1ms) OK 버튼을 자동 클릭.
    폴링 방식과 달리 타이밍 문제가 없음.
    ※ native alert가 열려 있으면 execute_script가 실패하므로 먼저 닫음.
    """
    # native alert가 열려 있으면 먼저 닫기
    dismiss_browser_alert(driver, timeout=3)

    try:
        driver.execute_script("""
        if (window.__autoOkObserver) return;   // 중복 주입 방지

        var okLabels = ['OK', 'Ok', '확인'];

        function clickOkIfPresent(root) {
            var buttons = root.querySelectorAll ? root.querySelectorAll('button') : [];
            for (var i = 0; i < buttons.length; i++) {
                var btn = buttons[i];
                var txt = btn.textContent.trim();
                if (okLabels.indexOf(txt) !== -1 && !btn.disabled) {
                    console.log('[AutoOK] 버튼 자동 클릭:', txt);
                    btn.click();
                    return true;
                }
            }
            return false;
        }

        // 기존에 이미 뜬 팝업도 처리
        clickOkIfPresent(document.body);

        // 이후 DOM 변화 감시
        var observer = new MutationObserver(function(mutations) {
            for (var m = 0; m < mutations.length; m++) {
                var nodes = mutations[m].addedNodes;
                for (var n = 0; n < nodes.length; n++) {
                    if (nodes[n].nodeType === 1) {
                        if (clickOkIfPresent(nodes[n])) return;
                    }
                }
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });
        window.__autoOkObserver = observer;
        console.log('[AutoOK] MutationObserver 등록 완료');
    """)
        print(f"[{_ts()}] MutationObserver 주입 완료 (팝업 자동 클릭 대기)")
    except UnexpectedAlertPresentException:
        # JS 실행 중 alert가 새로 열린 경우 → 닫고 재시도
        dismiss_browser_alert(driver, timeout=3)
        try:
            driver.execute_script("console.log('[AutoOK] 재주입');")
        except Exception:
            pass
        print(f"[{_ts()}] [경고] alert로 인해 Observer 주입 생략 (alert 닫음)")
    except Exception as e:
        print(f"[{_ts()}] [경고] Observer 주입 실패: {e}")


def login(driver):
    print(f"[{_ts()}] 로그인 페이지 접속...")
    driver.get(LOGIN_URL)
    time.sleep(1.5)

    # ① MutationObserver 주입 → 이후 뜨는 모든 OK 팝업 즉시 자동 클릭
    inject_auto_ok_observer(driver)

    # ② 로그인 페이지 진입 시 이미 모달이 뜬 경우 (기존 세션 감지)
    #    Observer가 즉시 처리하므로 잠시 대기 후 URL 확인
    time.sleep(2)
    if LOGIN_URL not in driver.current_url:
        print(f"[{_ts()}] 기존 세션으로 자동 로그인됨 → {driver.current_url}")
        return

    # ③ 로그인 폼 입력
    wait = WebDriverWait(driver, 15)
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
            "//button[contains(text(),'로그인') or contains(text(),'Login') or contains(text(),'login')]")

    # ④ 로그인 클릭 → Observer가 팝업을 즉시 처리
    login_btn.click()
    print(f"[{_ts()}] 로그인 클릭 완료 (Observer가 팝업 자동 처리)...")

    # ⑤ 로그인 페이지에서 벗어날 때까지 대기
    try:
        WebDriverWait(driver, 15).until(EC.url_changes(LOGIN_URL))
    except Exception:
        pass

    print(f"[{_ts()}] 로그인 완료 → 현재 URL: {driver.current_url}")


def click_menu(driver, label, parent=None, timeout=10):
    """메뉴 텍스트로 클릭 가능한 요소 탐색 후 클릭.
    탐색 범위: parent 요소 내부 또는 전체 문서.
    """
    wait = WebDriverWait(parent or driver, timeout)
    xpaths = [
        f".//*[normalize-space(text())='{label}']",
        f".//*[contains(text(),'{label}')]",
        f".//*[@title='{label}']",
        f".//*[@aria-label='{label}']",
    ]
    for xpath in xpaths:
        try:
            el = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.3)
            el.click()
            print(f"[{_ts()}] 메뉴 클릭: '{label}'")
            return True
        except Exception:
            continue
    print(f"[{_ts()}] [경고] 메뉴를 찾지 못함: '{label}'")
    return False


def navigate_to_target(driver, max_retries=3):
    """메뉴 클릭으로 이동: [A] Device 관리 → [LI] 영상 실시간 View
    직접 URL 이동 시 발생하는 alert를 우회하고 실제 사용자 동작을 모방.
    """
    wait = WebDriverWait(driver, 10)

    for attempt in range(1, max_retries + 1):
        print(f"[{_ts()}] 메뉴 이동 시도 ({attempt}/{max_retries}): Device 관리 → 영상 실시간 View")

        try:
            # ① native alert 선제 처리
            dismiss_browser_alert(driver, timeout=2)

            # ② [A] 'Device 관리' 상위 메뉴 클릭
            device_menu = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//a[normalize-space(text())='Device 관리']")
            ))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", device_menu)
            time.sleep(0.3)
            device_menu.click()
            print(f"[{_ts()}] ✔ 'Device 관리' 클릭")
            time.sleep(1)
            dismiss_browser_alert(driver, timeout=2)

            # ③ [LI] '영상 실시간 View' 하위 메뉴 클릭
            # 서브메뉴 애니메이션 대기 (충분히)
            time.sleep(1.5)

            # 여러 XPath 전략 순서대로 시도
            sub_xpaths = [
                "//li[normalize-space(text())='영상 실시간 View']",
                "//li[normalize-space(.)='영상 실시간 View']",
                "//li[contains(normalize-space(.),'영상 실시간 View') and not(contains(.,'Admin')) and not(contains(.,'Device 목록'))]",
                "//*[normalize-space(text())='영상 실시간 View']",
                "//*[normalize-space(.)='영상 실시간 View']",
            ]
            sub_menu = None
            for xpath in sub_xpaths:
                try:
                    sub_menu = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.XPATH, xpath))
                    )
                    if sub_menu.is_displayed():
                        print(f"[{_ts()}] 서브메뉴 발견: {xpath}")
                        break
                    sub_menu = None
                except Exception:
                    continue

            if sub_menu is None:
                raise Exception("'영상 실시간 View' 서브메뉴를 찾지 못했습니다.")

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", sub_menu)
            time.sleep(0.3)
            # 일반 클릭 → 실패 시 JS 클릭
            try:
                sub_menu.click()
            except Exception:
                driver.execute_script("arguments[0].click();", sub_menu)
            print(f"[{_ts()}] ✔ '영상 실시간 View' 클릭")
            time.sleep(2)
            dismiss_browser_alert(driver, timeout=2)

            # ④ 페이지 정상 로드 확인
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            current = driver.current_url
            print(f"[{_ts()}] ✔ 모니터링 페이지 로드 완료: {current}")

            # ⑤ 이후 팝업 자동처리 Observer 재주입
            inject_auto_ok_observer(driver)

            # ⑥ Device 뷰 자동 설정 (첫 번째 Device 선택 + 라디오 버튼 + 지도 줌)
            setup_device_view(driver, DRONE_ALTITUDE_M)
            return True

        except UnexpectedAlertPresentException:
            dismiss_browser_alert(driver, timeout=3)
            print(f"[{_ts()}] alert 처리 후 재시도...")
            time.sleep(1)
        except Exception as e:
            print(f"[{_ts()}] 메뉴 이동 오류: {e}")
            time.sleep(2)

    print(f"[{_ts()}] [경고] 메뉴 이동 실패. 현재: {driver.current_url}")
    return False


def is_logged_in(driver):
    return LOGIN_URL not in driver.current_url


# ──────────────────────────────────────────────
# Device 뷰 자동 설정
# ──────────────────────────────────────────────

def altitude_to_zoom(altitude_m):
    """드론 고도(m) → OpenLayers 줌 레벨 변환
    고도 100m ≒ 1:1,000 축척 ≒ zoom 17
    """
    thresholds = [
        (10,  20),
        (30,  19),
        (50,  18),
        (100, 17),
        (200, 16),
        (500, 15),
        (1000, 14),
    ]
    for max_alt, zoom in thresholds:
        if altitude_m <= max_alt:
            return zoom
    return 13


def _click_by_text(driver, labels, timeout=5):
    """텍스트 일치 요소를 탐색 후 클릭.
    ① XPath element_to_be_clickable
    ② find_elements + JS click (클릭 불가 판정 우회)
    ③ JS innerHTML 전체 탐색
    """
    xpaths_exact   = [f"//*[normalize-space(text())='{t}']"             for t in labels]
    xpaths_contain = [f"//*[contains(normalize-space(text()),'{t}')]"   for t in labels]
    xpaths_dot     = [f"//*[normalize-space(.)='{t}']"                  for t in labels]

    # 방법 1: WebDriverWait + 일반 클릭
    for xpath in xpaths_exact + xpaths_dot:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.2)
            el.click()
            return el.text.strip()
        except Exception:
            continue

    # 방법 2: find_elements + JS click (클릭 불가 요소 우회)
    for xpath in xpaths_exact + xpaths_contain + xpaths_dot:
        try:
            els = driver.find_elements(By.XPATH, xpath)
            for el in els:
                if el.is_displayed():
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", el)
                    return el.text.strip()
        except Exception:
            continue

    # 방법 3: JavaScript 전체 DOM 탐색 + click
    # 토글 버튼 우선 탐색 후 전체 요소로 확장
    result = driver.execute_script("""
        var labels = arguments[0];

        function tryClick(selector) {
            var all = document.querySelectorAll(selector);
            for (var i = 0; i < all.length; i++) {
                var el = all[i];
                var rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;
                var txt = el.textContent.trim();
                for (var j = 0; j < labels.length; j++) {
                    if (txt === labels[j] || txt.indexOf(labels[j]) > -1) {
                        el.scrollIntoView({block: 'center'});
                        el.click();
                        return txt;
                    }
                }
            }
            return null;
        }

        // 토글 버튼 우선 시도
        var toggleSelectors = [
            '[class*="toggle"]', '[class*="switch"]',
            '[class*="btn"]', 'button',
            'label', 'span', 'div'
        ];
        for (var s = 0; s < toggleSelectors.length; s++) {
            var found = tryClick(toggleSelectors[s]);
            if (found) return found;
        }
        return null;
    """, labels)
    return result


def _diagnose_buttons(driver):
    """버튼/라디오 관련 요소를 모두 출력 (디버깅용)"""
    try:
        items = driver.execute_script("""
            var res = [];
            var seen = new Set();
            document.querySelectorAll(
                'button, input[type="radio"], label, ' +
                '[class*="radio"], [class*="toggle"], [class*="btn"], ' +
                '[class*="switch"], [role="radio"], [role="button"]'
            ).forEach(function(el) {
                var txt = el.textContent.trim().replace(/\\s+/g,' ');
                if (txt && !seen.has(txt) && txt.length < 40) {
                    seen.add(txt);
                    res.push({
                        tag: el.tagName,
                        txt: txt,
                        cls: (el.className||'').substring(0,60),
                        vis: el.offsetParent !== null
                    });
                }
            });
            return res;
        """)
        print(f"[{_ts()}] ── 버튼/라디오 요소 목록 ──")
        for item in (items or []):
            print(f"         [{item['tag']}] '{item['txt']}'  "
                  f"class='{item['cls']}'  visible={item['vis']}")
    except Exception as e:
        print(f"[{_ts()}] 진단 오류: {e}")


def setup_device_view(driver, altitude_m=DRONE_ALTITUDE_M):
    """① Device List 첫 번째 항목 선택
    ② 선택 후 '실시간 화면 꺼짐' 토글 버튼 클릭
    ③ '드론 추적 꺼짐' 토글 버튼 클릭
    ④ 드론 고도에 맞는 지도 자동 확대/축소
    """
    zoom = altitude_to_zoom(altitude_m)
    time.sleep(2)   # 페이지 렌더링 대기

    # ── ① 첫 번째 Device 항목 선택 ─────────────────────────────────────
    device_selected = None
    try:
        # 페이지 텍스트에서 deviceName(Connected|Disconnected) 패턴 항목 탐색
        # 가장 첫 번째 매칭 요소 클릭
        device_xpaths = [
            # 텍스트 노드가 "name(Status)" 형태인 요소
            "//*[contains(text(),'(Connected)') or contains(text(),'(Disconnected)')]"
            "[not(self::script)][not(self::style)]",
            # 리스트 항목 중 Device List 섹션 첫 번째
            "//li[contains(text(),'(Connected)') or contains(text(),'(Disconnected)')]",
            "//*[contains(@class,'item') or contains(@class,'row') or contains(@class,'card')]"
            "[contains(text(),'(Connected)') or contains(text(),'(Disconnected)')]",
        ]
        for xpath in device_xpaths:
            try:
                els = driver.find_elements(By.XPATH, xpath)
                visible = [e for e in els if e.is_displayed()]
                if visible:
                    first = visible[0]
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", first)
                    time.sleep(0.3)
                    first.click()
                    device_selected = first.text.strip()[:60]
                    print(f"[{_ts()}] ✔ Device 선택: '{device_selected}'")
                    time.sleep(3)   # 선택 후 토글 버튼 렌더링 대기
                    break
            except Exception:
                continue

        if not device_selected:
            print(f"[{_ts()}] [경고] Device 항목을 찾지 못했습니다.")
    except Exception as e:
        print(f"[{_ts()}] Device 선택 오류: {e}")

    # ── ② 실시간 화면 꺼짐 토글 버튼 ───────────────────────────────────
    realtime_result = None
    try:
        realtime_result = _click_by_text(driver,
            ['실시간 화면 꺼짐', '실시간화면꺼짐', '실시간 화면 OFF', '실시간화면OFF'])
        if realtime_result:
            print(f"[{_ts()}] ✔ 실시간 화면 버튼 클릭: '{realtime_result}'")
            time.sleep(0.5)
        else:
            print(f"[{_ts()}] [경고] '실시간 화면 꺼짐' 버튼을 찾지 못했습니다.")
            _diagnose_buttons(driver)   # 실제 버튼 목록 출력
    except Exception as e:
        print(f"[{_ts()}] 실시간 화면 버튼 오류: {e}")

    # ── ③ 드론 추적 꺼짐 토글 버튼 ─────────────────────────────────────
    tracking_result = None
    try:
        tracking_result = _click_by_text(driver,
            ['드론 추적 꺼짐', '드론추적꺼짐', '드론 추적 OFF', '드론추적OFF'])
        if tracking_result:
            print(f"[{_ts()}] ✔ 드론 추적 버튼 클릭: '{tracking_result}'")
            time.sleep(0.5)
        else:
            print(f"[{_ts()}] [경고] '드론 추적 꺼짐' 버튼을 찾지 못했습니다.")
            _diagnose_buttons(driver)   # 실제 버튼 목록 출력
    except Exception as e:
        print(f"[{_ts()}] 드론 추적 버튼 오류: {e}")

    # ── ④ OpenLayers 지도 줌 설정 ───────────────────────────────────────
    try:
        map_result = driver.execute_script("""
            var zoom = arguments[0];
            var mapFound = false;

            // 전략 1: window 전역 객체
            ['map','olMap','mapInstance'].forEach(function(k){
                try{
                    if(!mapFound && window[k] && typeof window[k].getView==='function'){
                        window[k].getView().setZoom(zoom);
                        mapFound = 'global:'+k;
                    }
                }catch(e){}
            });

            // 전략 2: window 속성 전체 스캔
            if(!mapFound){
                for(var key in window){
                    try{
                        var v=window[key];
                        if(v&&typeof v==='object'&&typeof v.getView==='function'){
                            v.getView().setZoom(zoom);
                            mapFound='scan:'+key; break;
                        }
                    }catch(e){}
                }
            }

            // 전략 3: OL viewport 부모 속성
            if(!mapFound){
                var vp=document.querySelector('.ol-viewport');
                if(vp&&vp.parentElement){
                    for(var p in vp.parentElement){
                        try{
                            if(p.indexOf('ol_')===0){
                                var o=vp.parentElement[p];
                                if(o&&typeof o.getView==='function'){
                                    o.getView().setZoom(zoom);
                                    mapFound='ol_prop'; break;
                                }
                            }
                        }catch(e){}
                    }
                }
            }

            // 전략 4: Vue 인스턴스
            if(!mapFound){
                document.querySelectorAll('[class*="map"],.ol-viewport').forEach(function(el){
                    if(mapFound) return;
                    var vm=el.__vue__||el.__vueParentComponent;
                    if(vm){
                        var m=(vm.$data&&vm.$data.map)||(vm.setupState&&vm.setupState.map);
                        if(m&&typeof m.getView==='function'){
                            m.getView().setZoom(zoom); mapFound='vue';
                        }
                    }
                });
            }

            // 전략 5 (fallback): 줌 버튼 클릭
            if(!mapFound){
                var diff=zoom-15;
                var sel=diff>0?'.ol-zoom-in':'.ol-zoom-out';
                var btn=document.querySelector(sel);
                for(var n=0;n<Math.abs(diff)&&btn;n++) btn.click();
                mapFound='btn:'+zoom;
            }

            return mapFound;
        """, zoom)
        print(f"[{_ts()}] ✔ 지도 줌 설정: zoom {zoom} "
              f"(고도 {altitude_m}m, 방식: {map_result})")
    except Exception as e:
        print(f"[{_ts()}] 지도 줌 설정 오류: {e}")


# ──────────────────────────────────────────────
# Device 변경 감지
# ──────────────────────────────────────────────

ALERT_SAVE_DIR = r"D:\Downloads\device_alerts"
os.makedirs(ALERT_SAVE_DIR, exist_ok=True)


def save_alert_to_file(title, message, device_name, ts_str):
    """팝업 내용을 {device명}_{날짜시분초}.txt 로 저장. 저장 경로 반환."""
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', device_name)
    filename  = f"{safe_name}_{ts_str}.txt"
    filepath  = os.path.join(ALERT_SAVE_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"제목: {title}\n")
            f.write(f"{'='*50}\n")
            f.write(message)
            f.write(f"\n{'='*50}\n")
            f.write(f"저장 시각: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        print(f"[{_ts()}] 경고 내용 저장 완료: {filepath}")
        return filepath
    except Exception as e:
        print(f"[{_ts()}] 파일 저장 오류: {e}")
        return None


def save_connected_file(device_name, ts_str, connected_at, status_line):
    """Device 리스트 표시 시 개별 파일 생성 — 접속시간 기록.
    파일명: {device명}_{접속시각}_CONN.txt
    종료시간은 나중에 append_disconnect_to_file() 로 추가.
    """
    safe_name = re.sub(r'[\\/:*?"<>|]', '_', device_name)
    filename  = f"{safe_name}_{ts_str}_CONN.txt"
    filepath  = os.path.join(ALERT_SAVE_DIR, filename)
    content   = "\n".join([
        f"Device명  : {device_name}",
        "=" * 50,
        f"접속시간  : {connected_at}",
        f"종료시간  : (접속 중)",
        f"접속지속  : -",
        "=" * 50,
        status_line,
        "",
    ])
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[{_ts()}] [{device_name}] 접속시간 기록: {filepath}")
        return filepath
    except Exception as e:
        print(f"[{_ts()}] 접속 파일 저장 오류: {e}")
        return None


def append_disconnect_to_file(filepath, device_name, connected_at, disappeared_at):
    """기존 접속 파일에 종료시간 및 접속 지속시간 추가."""
    try:
        # 접속 지속 시간 계산
        try:
            fmt  = '%Y-%m-%d %H:%M:%S'
            t0   = datetime.datetime.strptime(connected_at,   fmt)
            t1   = datetime.datetime.strptime(disappeared_at, fmt)
            secs = int((t1 - t0).total_seconds())
            dur  = f"{secs // 3600}시간 {(secs % 3600) // 60}분 {secs % 60}초"
        except Exception:
            dur = "계산 불가"

        # 파일 내용 전체 교체: "종료시간: (접속 중)" → 실제 종료시간으로 업데이트
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            content = content.replace(
                "종료시간  : (접속 중)", f"종료시간  : {disappeared_at}"
            ).replace(
                "접속지속  : -", f"접속지속  : {dur}"
            )
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            # 읽기/교체 실패 시 append 방식으로 fallback
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 50 + "\n")
                f.write(f"종료시간  : {disappeared_at}\n")
                f.write(f"접속지속  : {dur}\n")
                f.write("=" * 50 + "\n")

        print(f"[{_ts()}] [{device_name}] 종료시간 기록: {filepath}")
    except Exception as e:
        print(f"[{_ts()}] 파일 업데이트 오류: {e}")


def show_warning_popup(title, message, device_name="unknown", ts_str=None):
    """파일 저장 → 경고음 → 팝업 표시 (Chrome 활성화 여부 무관하게 최상위 표시)"""
    if ts_str is None:
        ts_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    # ① 팝업 표시 전 파일 먼저 저장
    save_alert_to_file(title, message, device_name, ts_str)

    # ② 별도 스레드로 경고음 + 최상위 팝업 표시
    def _show():
        # 경고음 재생 (Chrome 포커스 중에도 들림)
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

        # Windows 팝업 플래그
        # MB_ICONWARNING  0x0030  경고 아이콘
        # MB_SYSTEMMODAL  0x1000  시스템 모달
        # MB_SETFOREGROUND 0x10000 포그라운드로 강제 이동
        # MB_TOPMOST      0x40000 항상 최상위 (Chrome 위에 표시)
        flags = 0x0030 | 0x1000 | 0x10000 | 0x40000

        # MessageBoxW 호출 (topmost 보장)
        ctypes.windll.user32.MessageBoxW(0, message, title, flags)

    threading.Thread(target=_show, daemon=True).start()
    print(f"[{_ts()}] ⚠ 경고 팝업 표시: {title}")


def get_device_status(driver):
    """페이지 텍스트에서 Device 수량·Connected 수·목록을 추출.

    페이지 구조 (확인됨):
      - 전체 수량 : "Device List (3)"  텍스트
      - 개별 디바이스 : "sidedoor1(Connected)", "sidedoor2(Disconnected)" 형태
      - H3 태그에 단독 숫자(전체 수량)

    반환: {'count': int, 'connected': int, 'disconnected': int,
            'items': list[str], 'source': str}
    """
    try:
        status = driver.execute_script("""
            var result = {
                count: 0, connected: 0, disconnected: 0,
                items: [], source: ''
            };

            var bodyText = document.body ? (document.body.innerText || '') : '';

            // ① "Device List (N)" 에서 전체 수량 추출
            var m = bodyText.match(/Device\\s+List\\s*\\((\\d+)\\)/i);
            if (m) {
                result.count  = parseInt(m[1]);
                result.source = 'Device List (N)';
            }

            // ② H3 태그 단독 숫자 (fallback)
            if (result.count === 0) {
                document.querySelectorAll('h3').forEach(function(h) {
                    var t = h.textContent.trim();
                    if (/^\\d+$/.test(t)) {
                        result.count  = parseInt(t);
                        result.source = 'H3 number';
                    }
                });
            }

            // ③ "deviceName(Connected)" / "deviceName(Disconnected)" 파싱
            //    bodyText 각 줄에서 "이름(상태)" 패턴 추출
            var lines = bodyText.split('\\n');
            lines.forEach(function(line) {
                line = line.trim();
                // 이름(상태) — 상태는 Connected 또는 Disconnected
                var dm = line.match(/^(.+?)\\((Connected|Disconnected)\\)$/i);
                if (dm) {
                    result.items.push(line);
                    if (/^connected$/i.test(dm[2])) {
                        result.connected++;
                    } else {
                        result.disconnected++;
                    }
                }
            });

            return result;
        """)

        if status:
            return {
                'count':        int(status.get('count',        0) or 0),
                'connected':    int(status.get('connected',    0) or 0),
                'disconnected': int(status.get('disconnected', 0) or 0),
                'items':        status.get('items', []) or [],
                'source':       status.get('source', '') or '',
            }
        return {'count': 0, 'connected': 0, 'disconnected': 0,
                'items': [], 'source': 'null'}

    except Exception as e:
        print(f"[{_ts()}] device 상태 추출 오류: {e}")
        return {'count': 0, 'connected': 0, 'disconnected': 0,
                'items': [], 'source': 'error'}


def check_device_changes(driver, state):
    """현재 Device 상태와 이전 상태를 비교해 변경 시 경고 팝업 표시.
    state: {'count': int, 'connected': int, 'items': list, 'initialized': bool}
    """
    current   = get_device_status(driver)
    count        = current['count']
    connected    = current['connected']
    disconnected = current['disconnected']
    items        = current['items']
    ts_now       = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    status_line = (f"전체: {count}개 | "
                   f"Connected: {connected}개 | "
                   f"Disconnected: {disconnected}개")

    # 최초 실행: 기준값만 저장
    if not state['initialized']:
        state['count']        = count
        state['connected']    = connected
        state['disconnected'] = disconnected
        state['items']        = items
        state['initialized']  = True
        print(f"[{_ts()}] Device 기준 상태 저장 — {status_line}")
        for item in items:
            print(f"         · {item}")
        return

    # 추출값이 모두 0이면 페이지 아직 로딩 중으로 간주하고 skip
    if count == 0 and connected == 0 and len(items) == 0:
        print(f"[{_ts()}] Device 정보 미감지 (페이지 로딩 중일 수 있음)")
        return

    # items → {device명: 상태} 딕셔너리로 파싱
    def parse_statuses(item_list):
        result = {}
        for item in item_list:
            m = re.match(r'^(.+?)\((Connected|Disconnected)\)$', item, re.IGNORECASE)
            if m:
                result[m.group(1).strip()] = m.group(2)
        return result

    prev_statuses = parse_statuses(state['items'])
    curr_statuses = parse_statuses(items)

    # 상태가 변경된 Device 목록 추출
    status_changed = []
    for dev, cur_st in curr_statuses.items():
        prev_st = prev_statuses.get(dev)
        if prev_st and prev_st.lower() != cur_st.lower():
            status_changed.append((dev, prev_st, cur_st))
    for dev in prev_statuses:
        if dev not in curr_statuses:
            status_changed.append((dev, prev_statuses[dev], "제거됨"))

    ts_file      = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    ts_display   = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    alerts       = []

    # ── 개별 Device 리스트 출현/소멸 기반 파일 처리 ────────────────────────
    # ※ parse_statuses()는 (Connected|Disconnected) 형식만 파싱하므로
    #   상태 텍스트가 없는 Device는 감지 불가 → 원시 items 전체를 기준으로 탐지

    def extract_name(item_text):
        """'deviceName(Connected)' → 'deviceName',  'deviceName' → 'deviceName'"""
        m = re.match(r'^(.+?)\s*\(', item_text.strip())
        return m.group(1).strip() if m else item_text.strip()

    prev_all    = {extract_name(i) for i in state['items'] if i.strip()}
    curr_all    = {extract_name(i) for i in items          if i.strip()}
    appeared    = curr_all - prev_all   # 리스트에 새로 나타난 Device
    disappeared = prev_all - curr_all   # 리스트에서 사라진 Device

    # 새로 나타난 Device → CONN 파일 저장 및 경로 등록
    for dev in appeared:
        fp = save_connected_file(dev, ts_file, ts_display, status_line)
        if fp:
            state['connected_files'][dev] = {
                'filepath':     fp,
                'connected_at': ts_display,
            }

    # 새 Device 출현 시 첫 번째 항목 자동 선택 + 라디오 버튼 + 지도 줌 재설정
    if appeared:
        setup_device_view(driver, DRONE_ALTITUDE_M)

    # 리스트에서 사라진 Device → 기존 CONN 파일에 사라진 시각 기록
    for dev in disappeared:
        conn_info = state.get('connected_files', {}).get(dev)
        if conn_info and os.path.exists(conn_info['filepath']):
            append_disconnect_to_file(
                conn_info['filepath'],
                dev,
                conn_info['connected_at'],
                ts_display,
            )
            del state['connected_files'][dev]
        else:
            # CONN 파일 없음(초기 기동 시 이미 있던 Device) → 단독 파일 기록
            print(f"[{_ts()}] [{dev}] CONN 파일 없음 — 종료시간 단독 파일 기록")
            msg = (f"Device명  : {dev}\n"
                   f"{'='*50}\n"
                   f"접속시간  : (기록 없음 — 프로그램 시작 전 접속)\n"
                   f"종료시간  : {ts_display}\n"
                   f"접속지속  : 계산 불가\n"
                   f"{'='*50}\n"
                   f"{status_line}\n")
            save_alert_to_file(f"⚠ {dev} 종료", msg, dev, ts_file)

    # ① 전체 수량 변경 감지
    if count != state['count']:
        # 추가/제거된 Device명 목록
        added_devs   = [d for d in curr_statuses if d not in prev_statuses]
        removed_devs = [d for d in prev_statuses if d not in curr_statuses]
        dev_lines = []
        for d in added_devs:
            dev_lines.append(f"  [추가] {d}({curr_statuses[d]})")
        for d in removed_devs:
            dev_lines.append(f"  [제거] {d}({prev_statuses[d]})")
        dev_section = "\n".join(dev_lines) if dev_lines else "  (상세 정보 없음)"
        first_dev = (added_devs + removed_devs + ['unknown'])[0]

        msg = (
            f"⚠ Device 수량이 변경되었습니다!\n\n"
            f"이전: {state['count']}개  →  현재: {count}개\n\n"
            f"[변경 Device]\n{dev_section}\n\n"
            f"{status_line}\n\n"
            f"감지 시각: {ts_now}"
        )
        alerts.append(("⚠ Device 수량 변경", msg, first_dev))
        print(f"[{_ts()}] ⚠ 수량 변경: {state['count']} → {count}")
        state['count'] = count

    # ② Connected 수 변경 감지 (Device명 포함)
    if connected != state['connected'] or status_changed or appeared or disappeared:
        change_lines = []
        # 리스트에 새로 나타난 Device (이전 상태 없음 → status_changed에 포함 안 됨)
        for dev in sorted(appeared):
            change_lines.append(f"  · {dev}  :  (신규 접속)")
        # 리스트에서 사라진 Device
        for dev in sorted(disappeared):
            change_lines.append(f"  · {dev}  :  (리스트에서 사라짐)")
        # 기존 Device 상태 변경
        for dev, prev_st, cur_st in status_changed:
            change_lines.append(f"  · {dev}  :  {prev_st}  →  {cur_st}")
        change_section = "\n".join(change_lines) if change_lines else "  (상세 정보 없음)"

        # first_dev: status_changed → appeared → disappeared 순으로 fallback
        # 'unknown' 파일 생성 방지
        if status_changed:
            first_dev = status_changed[0][0]
        elif appeared:
            first_dev = sorted(appeared)[0]
        elif disappeared:
            first_dev = sorted(disappeared)[0]
        else:
            first_dev = 'unknown'

        msg = (
            f"⚠ Connected 상태가 변경되었습니다!\n\n"
            f"이전 Connected: {state['connected']}개  →  현재: {connected}개\n"
            f"이전 Disconnected: {state['disconnected']}개  →  현재: {disconnected}개\n\n"
            f"[변경 Device 목록]\n{change_section}\n\n"
            f"[전체 현재 상태]\n"
            + "\n".join(f"  · {d}({s})" for d, s in sorted(curr_statuses.items()))
            + f"\n\n{status_line}\n\n감지 시각: {ts_now}"
        )
        alerts.append(("⚠ Connected 수 변경", msg, first_dev))
        print(f"[{_ts()}] ⚠ Connected 변경: {state['connected']} → {connected}")
        for dev, prev_st, cur_st in status_changed:
            print(f"         · {dev}: {prev_st} → {cur_st}")
        state['connected']    = connected
        state['disconnected'] = disconnected
        state['items']        = items

    # ③ 목록 항목 변경 감지 (수량 변경과 중복 제외)
    prev_set = set(state['items'])
    curr_set = set(items)
    added_set   = curr_set - prev_set
    removed_set = prev_set - curr_set

    if (added_set or removed_set) and count == state['count']:
        change_lines = []
        for i in sorted(added_set):   change_lines.append(f"  + {i}")
        for i in sorted(removed_set): change_lines.append(f"  - {i}")
        first_dev = re.match(r'^(.+?)\(', sorted(added_set | removed_set)[0])
        first_dev = first_dev.group(1) if first_dev else 'unknown'

        msg = (
            "⚠ Device 목록이 변경되었습니다!\n\n"
            "[변경 내역]\n"
            + "\n".join(change_lines)
            + f"\n\n{status_line}\n\n감지 시각: {ts_now}"
        )
        alerts.append(("⚠ Device 목록 변경", msg, first_dev))
        print(f"[{_ts()}] ⚠ 목록 변경 — 추가: {added_set}, 제거: {removed_set}")
        state['items'] = items

    for title, message, device_name in alerts:
        show_warning_popup(title, message, device_name=device_name, ts_str=ts_file)

    if not alerts:
        print(f"[{_ts()}] Device 이상 없음 — {status_line}")

    # 항상 최신 items로 state 동기화 (stale state 방지)
    state['items'] = items


# ──────────────────────────────────────────────
# 세션 유지
# ──────────────────────────────────────────────

def keep_session_alive(driver, device_state):
    """페이지 새로고침 없이 세션 유지 + Device 변경 감지"""
    try:
        driver.execute_script("""
            // ① 서버 세션 유지 (백그라운드 HEAD fetch)
            try {
                fetch(window.location.href, {
                    method: 'HEAD', credentials: 'include', cache: 'no-cache'
                }).catch(function(){});
            } catch(e) {}

            // ② 마우스 이동 이벤트 (실제 커서 위치 무관)
            var cx = Math.floor(window.innerWidth  / 2);
            var cy = Math.floor(window.innerHeight / 2);
            ['mousemove','mouseenter','mouseover'].forEach(function(t) {
                document.dispatchEvent(new MouseEvent(t, {
                    bubbles:true, cancelable:true, clientX:cx, clientY:cy, view:window
                }));
            });

            // ③ 키보드 이벤트 (Shift — 화면 영향 없음)
            ['keydown','keyup'].forEach(function(t) {
                document.dispatchEvent(new KeyboardEvent(t, {
                    key:'Shift', code:'ShiftLeft', bubbles:true, cancelable:true
                }));
            });

            // ④ 미세 스크롤
            window.scrollBy(0, 1); window.scrollBy(0, -1);
        """)

        dismiss_any_popup(driver, timeout=2)
        print(f"[{_ts()}] 세션 유지 신호 전송 완료")

        # Device 변경 감지
        check_device_changes(driver, device_state)

    except Exception as e:
        print(f"[{_ts()}] 세션 유지 오류: {e}")


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

def main():
    print(f"세션 유지 시작: {TARGET_URL}")
    print(f"운영 시간: {START_HOUR:02d}:{START_MINUTE:02d} ~ {END_HOUR:02d}:00, 유지 간격: {KEEPALIVE_INTERVAL}초")

    # 화면보호기 / 절전 모드 비활성화
    prevent_screensaver()

    driver = None

    # Device 변경 감지 상태 (초기화 플래그 포함)
    device_state = {
        'count':          0,     # 이전 전체 수량
        'connected':      0,     # 이전 Connected 수량
        'disconnected':   0,     # 이전 Disconnected 수량
        'items':          [],    # 이전 목록 (deviceName(Status) 형태)
        'initialized':    False, # 최초 기준값 수집 여부
        'connected_files': {}    # {device명: {'filepath': str, 'connected_at': str}}
    }

    def shutdown(reason=""):
        """브라우저 종료 후 콘솔(프로세스) 완전 종료"""
        nonlocal driver
        print(f"[{_ts()}] {reason}")
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        close_all_chrome()
        reset_screensaver()   # 화면보호기 설정 복원
        print(f"[{_ts()}] 브라우저 및 콘솔 종료합니다.")
        sys.exit(0)

    try:
        while True:
            now = datetime.datetime.now()

            # ── 17시 도달 시 즉시 종료 ──────────────────────────────────
            if now.hour >= END_HOUR:
                shutdown(f"오후 {END_HOUR}시 도달 — 자동 종료")

            if is_active_time():
                if driver is None:
                    close_all_chrome()   # 기존 Chrome 인스턴스 모두 종료
                    driver = create_driver()
                    login(driver)
                    navigate_to_target(driver)
                    # 페이지 이동 후 기준 상태 초기화
                    device_state['initialized'] = False

                time.sleep(KEEPALIVE_INTERVAL)

                # sleep 후 재확인 (sleep 중에 17시 넘었을 수 있음)
                if datetime.datetime.now().hour >= END_HOUR:
                    shutdown(f"오후 {END_HOUR}시 도달 — 자동 종료")

                if is_active_time():
                    if not is_logged_in(driver):
                        print(f"[{_ts()}] 세션 만료 감지 — 재로그인")
                        login(driver)
                        navigate_to_target(driver)
                        device_state['initialized'] = False
                    else:
                        keep_session_alive(driver, device_state)

            else:
                # 운영 시작 전(오전 8시 이전) 대기
                wait_sec = seconds_until_start()
                next_start = datetime.datetime.now() + datetime.timedelta(seconds=wait_sec)
                print(f"[{_ts()}] 대기 중... 시작 예정: {next_start.strftime('%Y-%m-%d %H:%M:%S')}")
                time.sleep(min(60, wait_sec))

    except KeyboardInterrupt:
        print("\n사용자가 종료했습니다.")
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        close_all_chrome()
        reset_screensaver()   # 화면보호기 설정 복원
        print("브라우저 종료 완료.")


if __name__ == "__main__":
    main()
