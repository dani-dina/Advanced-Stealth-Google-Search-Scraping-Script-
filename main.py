import os
import time
import csv
import random
import requests
import urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from dotenv import load_dotenv

load_dotenv()
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/113.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:116.0) Gecko/20100101 Firefox/116.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
]

def solve_recaptcha(site_key, page_url):
    print("Solving CAPTCHA via 2captcha...")
    in_payload = {
        "key": CAPTCHA_API_KEY,
        "method": "userrecaptcha",
        "googlekey": site_key,
        "pageurl": page_url,
        "json": 1
    }
    resp = requests.post("http://2captcha.com/in.php", data=in_payload).json()
    if resp.get("status") != 1:
        raise Exception(f"2captcha API error: {resp.get('request')}")

    captcha_id = resp["request"]
    print(f"Captcha ID: {captcha_id}. Waiting for solution...")

    for i in range(24):
        time.sleep(5)
        res = requests.get(
            f"http://2captcha.com/res.php?key={CAPTCHA_API_KEY}&action=get&id={captcha_id}&json=1"
        ).json()
        if res.get("status") == 1:
            print("CAPTCHA solved.")
            return res["request"]
        elif res.get("request") == "CAPCHA_NOT_READY":
            print("Captcha not ready yet...")
            continue
        else:
            raise Exception(f"2captcha error: {res.get('request')}")

    raise Exception("CAPTCHA solving timed out")

def init_driver():
    options = Options()

    # Disable headless during debugging; enable for production
    # options.add_argument("--headless=new")  

    user_agent = random.choice(USER_AGENTS)
    options.add_argument(f"user-agent={user_agent}")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    service = Service("C:\\Users\\Kibret\\Downloads\\chromedriver-win64\\chromedriver-win64\\chromedriver.exe")
    driver = webdriver.Chrome(service=service, options=options)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        """
    })

    return driver

def get_recaptcha_sitekey(driver):
    # Try iframe src
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for iframe in iframes:
        src = iframe.get_attribute("src")
        if src and "recaptcha" in src:
            parsed = urllib.parse.urlparse(src)
            params = urllib.parse.parse_qs(parsed.query)
            if "k" in params:
                return params["k"][0]

    # Fallback: data-sitekey attribute
    try:
        elem = driver.find_element(By.CSS_SELECTOR, "[data-sitekey]")
        sitekey = elem.get_attribute("data-sitekey")
        if sitekey:
            return sitekey
    except NoSuchElementException:
        pass

    return None

def is_captcha_page(driver):
    url = driver.current_url.lower()
    source = driver.page_source.lower()
    if "sorry" in url or "captcha" in url or "unusual traffic" in source:
        return True
    return False

def bypass_captcha(driver):
    site_key = get_recaptcha_sitekey(driver)
    if not site_key:
        print("Could not find reCAPTCHA sitekey on page.")
        return False

    try:
        solution_token = solve_recaptcha(site_key, driver.current_url)
    except Exception as e:
        print(f"CAPTCHA solving failed: {e}")
        return False

    # Inject token into textarea if present
    driver.execute_script('''
        var el = document.getElementById("g-recaptcha-response");
        if(el){
            el.style.display = '';
            el.value = arguments[0];
        }
    ''', solution_token)

    # Submit any form present
    driver.execute_script('''
        var forms = document.getElementsByTagName("form");
        if(forms.length > 0){
            forms[0].submit();
        }
    ''')

    time.sleep(8)
    return True

def search_google(query, driver):
    driver.get("https://www.google.com/")
    time.sleep(2)

    search_box = driver.find_element(By.NAME, "q")
    search_box.clear()
    search_box.send_keys(query)
    search_box.send_keys(Keys.RETURN)
    time.sleep(3)

    if is_captcha_page(driver):
        print("CAPTCHA page detected, attempting to solve...")
        if bypass_captcha(driver):
            print("CAPTCHA bypassed, continuing search...")
            time.sleep(5)
        else:
            print("CAPTCHA bypass failed, skipping query.")
            return []

    results = []
    try:
        links = driver.find_elements(By.CSS_SELECTOR, "div.g")
        for link in links:
            try:
                title = link.find_element(By.TAG_NAME, "h3").text
                href = link.find_element(By.TAG_NAME, "a").get_attribute("href")
                snippet = link.find_element(By.CLASS_NAME, "VwiC3b").text
                results.append((title, href, snippet))
            except:
                continue
    except Exception as e:
        print(f"Error extracting results: {e}")
    return results

def read_domains():
    with open("domains.csv", "r", newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return [row["domain"] for row in reader]

def main():
    driver = init_driver()

    domains = read_domains()
    total = len(domains)
    all_results = []
    success_count = 0
    fail_count = 0

    for i, domain in enumerate(domains, start=1):
        query = f'site:{domain} "cdmo"'
        print(f"[{i}/{total}] Searching: {query}")

        try:
            results = search_google(query, driver)
            if results:
                for title, href, snippet in results:
                    all_results.append({
                        "domain": domain,
                        "title": title,
                        "url": href,
                        "snippet": snippet
                    })
                print(f"Success: {len(results)} results found.")
                success_count += 1
            else:
                print("No results or blocked.")
                fail_count += 1
        except Exception as e:
            print(f"Error on domain {domain}: {e}")
            fail_count += 1

        time.sleep(random.uniform(5, 10))  # Random delay between queries

    driver.quit()

    with open("results.csv", "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["domain", "title", "url", "snippet"])
        writer.writeheader()
        writer.writerows(all_results)

    print("\nSummary:")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Results saved to results.csv")

if __name__ == "__main__":
    main()
