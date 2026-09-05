try:
    import argparse
    import json
    import time
    import random

    from selenium import webdriver
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.firefox.service import Service as FirefoxService

    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.firefox import GeckoDriverManager
except ModuleNotFoundError:
    print("Please install: pip install selenium webdriver-manager")
    exit(1)


class Pinterest:
    """
    Unified Pinterest scraper that tries multiple methods:
    1. Network interception (most reliable)
    2. Wait & poll for data (fallback)
    3. Text extraction from page (last resort)
    """
    
    @staticmethod
    def init_driver(browser_name: str, proxy: str = None, headed: bool = False, enable_network_log: bool = True):
        """Initialize browser with optional network logging"""
        
        def set_properties(browser_option, proxy=None, headed=False, enable_network_log=False):
            """Configure browser options"""
            
            user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            
            if not headed:
                browser_option.add_argument("--headless=new")
            
            # Anti-detection
            browser_option.add_argument("--disable-blink-features=AutomationControlled")
            browser_option.add_experimental_option("excludeSwitches", ["enable-automation"])
            browser_option.add_experimental_option('useAutomationExtension', False)
            
            browser_option.add_argument("--window-size=1920,1080")
            browser_option.add_argument(f"--user-agent={user_agent}")
            browser_option.add_argument("--disable-gpu")
            browser_option.add_argument("--no-sandbox")
            browser_option.add_argument("--disable-dev-shm-usage")
            browser_option.add_argument("--log-level=3")
            browser_option.add_argument("--disable-notifications")
            
            # Enable network logging for method 1
            if enable_network_log:
                browser_option.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
            
            if proxy:
                browser_option.add_argument(f"--proxy-server={proxy}")
            
            return browser_option

        name = browser_name.strip().lower()

        if name == "chrome":
            options = ChromeOptions()
            options = set_properties(options, proxy, headed, enable_network_log)

            try:
                driver = webdriver.Chrome(options=options)
            except:
                try:
                    service = ChromeService(ChromeDriverManager().install())
                    driver = webdriver.Chrome(service=service, options=options)
                except Exception as e:
                    print(f"Error starting Chrome: {e}")
                    return None
            
            # Anti-detection
            driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            return driver

        elif name == "firefox":
            options = FirefoxOptions()
            options = set_properties(options, proxy, headed, False)  # Firefox doesn't support network logs the same way

            try:
                driver = webdriver.Firefox(options=options)
            except:
                try:
                    service = FirefoxService(GeckoDriverManager().install())
                    driver = webdriver.Firefox(service=service, options=options)
                except Exception as e:
                    print(f"Error starting Firefox: {e}")
                    return None
            
            return driver

        else:
            print(f"Browser '{browser_name}' not supported.")
            return None

    @staticmethod
    def method1_network_interception(driver, username, debug=False):
        """Method 1: Intercept network requests"""
        if debug:
            print("[DEBUG] Trying Method 1: Network Interception...")
        
        try:
            logs = driver.get_log('performance')
            
            for entry in logs:
                try:
                    log = json.loads(entry['message'])
                    message = log.get('message', {})
                    method = message.get('method', '')
                    
                    if method == 'Network.responseReceived':
                        response = message.get('params', {}).get('response', {})
                        url_req = response.get('url', '')
                        
                        if 'UserResource' in url_req or f'/{username}/' in url_req:
                            request_id = message['params']['requestId']
                            
                            try:
                                response_body = driver.execute_cdp_cmd(
                                    'Network.getResponseBody',
                                    {'requestId': request_id}
                                )
                                
                                body = response_body.get('body', '')
                                if body:
                                    data = json.loads(body)
                                    
                                    if isinstance(data, dict):
                                        if 'resource_response' in data:
                                            user_data = data['resource_response'].get('data', {})
                                            if user_data.get('username') == username:
                                                if debug:
                                                    print("[DEBUG] Method 1 SUCCESS!")
                                                return user_data
                                        elif data.get('username') == username:
                                            if debug:
                                                print("[DEBUG] Method 1 SUCCESS!")
                                            return data
                            except:
                                pass
                except:
                    pass
        except Exception as e:
            if debug:
                print(f"[DEBUG] Method 1 failed: {e}")
        
        if debug:
            print("[DEBUG] Method 1 failed")
        return None

    @staticmethod
    def method2_wait_and_poll(driver, username, debug=False):
        """Method 2: Wait for data to appear in JavaScript"""
        if debug:
            print("[DEBUG] Trying Method 2: Wait & Poll...")
        
        max_attempts = 15
        for attempt in range(max_attempts):
            if debug and attempt % 3 == 0:  # Print every 3 attempts
                print(f"[DEBUG] Polling attempt {attempt + 1}/{max_attempts}...")
            
            user_data = driver.execute_script("""
                var username = arguments[0];
                
                // Check window.__PWS_DATA__
                if (window.__PWS_DATA__ && window.__PWS_DATA__.resources && window.__PWS_DATA__.resources.UserResource) {
                    if (window.__PWS_DATA__.resources.UserResource[username]) {
                        return window.__PWS_DATA__.resources.UserResource[username];
                    }
                }
                
                // Check Redux store
                if (window.initialReduxState && window.initialReduxState.users && window.initialReduxState.users[username]) {
                    return window.initialReduxState.users[username];
                }
                
                return null;
            """, username)
            
            if user_data:
                if debug:
                    print("[DEBUG] Method 2 SUCCESS!")
                return user_data
            
            time.sleep(2)
        
        if debug:
            print("[DEBUG]  Method 2 failed")
        return None

    @staticmethod
    def convert_text_to_number(text):
        """Convert '556.5k' to 556500, '1.2M' to 1200000, etc."""
        if not text:
            return None
        
        text = text.strip().upper()
        multipliers = {'K': 1000, 'M': 1000000, 'B': 1000000000}
        
        for suffix, multiplier in multipliers.items():
            if suffix in text:
                try:
                    number = float(text.replace(suffix, '').replace(',', ''))
                    return int(number * multiplier)
                except:
                    return None
        
        # No suffix, just a number
        try:
            return int(text.replace(',', ''))
        except:
            return None

    @staticmethod
    def method3_text_extraction(driver, username, debug=False):
        """Method 3: Extract data from visible page text (last resort)"""
        if debug:
            print("[DEBUG] Trying Method 3: Text Extraction...")
        
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text
            
            if debug:
                # Show what text we're working with
                print(f"[DEBUG] Page contains 'follower': {'follower' in page_text.lower()}")
                print(f"[DEBUG] Page text length: {len(page_text)} chars")
            
            stats = {"username": username, "extracted_from": "page_text"}
            
            # Try multiple patterns for follower count
            import re
            
            # Pattern 1: "556.5k followers" (with space)
            follower_match = re.search(r'([\d,\.]+[KMB]?)\s+followers?', page_text, re.IGNORECASE)
            
            # Pattern 2: "556.5kfollowers" (no space)
            if not follower_match:
                follower_match = re.search(r'([\d,\.]+[KMB]?)followers?', page_text, re.IGNORECASE)
            
            # Pattern 3: Try to find in HTML attributes
            if not follower_match:
                try:
                    elements = driver.find_elements(By.XPATH, "//*[contains(text(), 'follower')]")
                    for elem in elements:
                        text = elem.text
                        match = re.search(r'([\d,\.]+[KMB]?)', text, re.IGNORECASE)
                        if match:
                            follower_match = match
                            break
                except:
                    pass
            
            if follower_match:
                stats['follower_count_text'] = follower_match.group(1)
                if debug:
                    print(f"[DEBUG] Found follower count: {follower_match.group(1)}")
            
            # patterns for following count
            following_match = re.search(r'([\d,\.]+[KMB]?)\s+following', page_text, re.IGNORECASE)
            if not following_match:
                following_match = re.search(r'([\d,\.]+[KMB]?)following', page_text, re.IGNORECASE)
            
            if following_match:
                stats['following_count_text'] = following_match.group(1)
                if debug:
                    print(f"[DEBUG] Found following count: {following_match.group(1)}")
            
            if follower_match or following_match:
                if debug:
                    print("[DEBUG]  Method 3 SUCCESS (partial data)")
                return stats
            else:
                if debug:
                    print("[DEBUG] Could not find follower/following counts in text")
                    # Show a sample of the page text
                    print(f"[DEBUG] Sample page text: {page_text[:500]}")
        
        except Exception as e:
            if debug:
                print(f"[DEBUG] Method 3 error: {e}")
        
        if debug:
            print("[DEBUG]  Method 3 failed")
        return None

    @staticmethod
    def scrap(username: str, browser_name: str = "chrome", proxy: str = None, debug: bool = False, headed: bool = False) -> str:
        """
        Scrape Pinterest profile using multiple fallback methods
        
        Tries in order:
        1. Network interception (fastest, most reliable)
        2. Wait & poll (good fallback)
        3. Text extraction (last resort)
        """
        driver = None
        try:
            # Initialize driver with network logging
            driver = Pinterest.init_driver(browser_name, proxy, headed, enable_network_log=True)

            if driver is None:
                return json.dumps({"error": "driver_not_initialized"})

            url = f"https://www.pinterest.com/{username}/"
            
            if debug:
                print(f"[DEBUG] Loading: {url}")

            # Load homepage first for cookies
            driver.get("https://www.pinterest.com/")
            time.sleep(random.uniform(2, 3))
            
            # Load profile
            driver.get(url)
            time.sleep(5)  # Initial wait

            if debug:
                print(f"[DEBUG] Page title: {driver.title}")
                print(f"[DEBUG] Current URL: {driver.current_url}")

            # Check for redirect (bot detection)
            # Make username check case-insensitive
            if "ideas" in driver.current_url or username.lower() not in driver.current_url.lower():
                # But only error if actually redirected away from profile
                if "ideas" in driver.current_url:
                    return json.dumps({
                        "error": "redirected",
                        "hint": "Pinterest redirected - possible bot detection. Try --headed flag or different proxy.",
                        "redirected_to": driver.current_url
                    })

            # TRY METHOD 1: Network Interception
            user_data = Pinterest.method1_network_interception(driver, username, debug)
            
            # TRY METHOD 2: Wait & Poll (if method 1 failed)
            if not user_data:
                user_data = Pinterest.method2_wait_and_poll(driver, username, debug)
            
            # TRY METHOD 3: Text Extraction (if both failed)
            if not user_data:
                user_data = Pinterest.method3_text_extraction(driver, username, debug)

            if not user_data:
                return json.dumps({
                    "error": "all_methods_failed",
                    "hint": "All 3 extraction methods failed. Pinterest may have changed structure or detected automation.",
                    "username": username
                })

            # Build profile data
            profile_data = {
                "username": user_data.get("username") or username,
                "full_name": user_data.get("full_name") or user_data.get("name"),
                "follower_count": user_data.get("follower_count") or Pinterest.convert_text_to_number(user_data.get("follower_count_text")),
                "follower_count_text": user_data.get("follower_count_text"),
                "following_count": user_data.get("following_count") or Pinterest.convert_text_to_number(user_data.get("following_count_text")),
                "following_count_text": user_data.get("following_count_text"),
                "pin_count": user_data.get("pin_count"),
                "board_count": user_data.get("board_count"),
                "about": user_data.get("about") or user_data.get("bio"),
                "profile_image": user_data.get("image_xlarge_url") or user_data.get("image_large_url"),
                "website_url": user_data.get("website_url"),
                "is_verified": user_data.get("is_verified", False),
                "data_source": user_data.get("extracted_from", "api"),
            }

            # Remove None values
            profile_data = {k: v for k, v in profile_data.items() if v is not None}

            return json.dumps(profile_data, ensure_ascii=False)

        except Exception as ex:
            if debug:
                print(f"[DEBUG] Unexpected error: {ex}")
                import traceback
                traceback.print_exc()
            
            return json.dumps({
                "error": "unexpected_exception",
                "message": str(ex)
            })
        
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except:
                    pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pinterest scraper with multiple fallback methods')
    parser.add_argument("username", help="Pinterest username")
    parser.add_argument("--browser", default="chrome", help="Browser (chrome/firefox)")
    parser.add_argument("--proxy", help="Proxy server")
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    parser.add_argument("--headed", action="store_true", help="Show browser window")

    args = parser.parse_args()
    
    result = Pinterest.scrap(
        args.username,
        browser_name=args.browser,
        proxy=args.proxy,
        debug=args.debug,
        headed=args.headed
    )
    
    print(result)