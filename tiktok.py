try:
    import argparse
    import json
    import time

    from selenium import webdriver
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.firefox.service import Service as FirefoxService

    from fake_headers import Headers
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.firefox import GeckoDriverManager
except ModuleNotFoundError:
    print("Please download dependencies from requirement.txt")
except Exception as ex:
    print(ex)


class Tiktok:
    @staticmethod
    def init_driver(browser_name: str, proxy: str = None):
        """
        Initialise a Selenium WebDriver (Chrome or Firefox).

        For Firefox we try:
          1. webdriver.Firefox(options=options)              (uses geckodriver from PATH)
          2. webdriver.Firefox(service=FirefoxService(...))  (Selenium 4 style)
          3. webdriver.Firefox(executable_path=...)          (older style)

        For Chrome we try:
          1. webdriver.Chrome(service=ChromeService(...))    (Selenium 4 style)
          2. webdriver.Chrome(ChromeDriverManager().install(), options=options) (older style)

        This makes the script more robust across different Selenium versions.
        """

        def set_properties(browser_option, proxy=None):
            ua = Headers().generate()
            # Extract real UA string from fake-headers output
            user_agent = ua.get("User-Agent") or ua.get("user-agent") or str(ua)

            browser_option.add_argument("--headless")
            browser_option.add_argument("--disable-extensions")
            browser_option.add_argument("--incognito")
            browser_option.add_argument("--disable-gpu")
            browser_option.add_argument("--log-level=3")
            browser_option.add_argument(f"--user-agent={user_agent}")
            browser_option.add_argument("--disable-notifications")
            browser_option.add_argument("--disable-popup-blocking")

            if proxy:
                browser_option.add_argument(f"--proxy-server={proxy}")
            return browser_option

        name = browser_name.strip().lower()
        last_err = None

        # ---------------- FIREFOX ----------------
        if name == "firefox":
            options = FirefoxOptions()
            options = set_properties(options, proxy)

            # Attempt 1: plain Firefox (uses geckodriver from PATH, e.g. brew install geckodriver)
            try:
                driver = webdriver.Firefox(options=options)
                return driver
            except Exception as e:
                last_err = e

            # Attempt 2: Selenium 4 style with Service + GeckoDriverManager
            try:
                service = FirefoxService(GeckoDriverManager().install())
                driver = webdriver.Firefox(service=service, options=options)
                return driver
            except TypeError as e:
                last_err = e
            except Exception as e:
                last_err = e

            # Attempt 3: older style executable_path + GeckoDriverManager
            try:
                driver = webdriver.Firefox(
                    executable_path=GeckoDriverManager().install(),
                    options=options,
                )
                return driver
            except Exception as e:
                last_err = e

            print("Error while initialising Firefox WebDriver:", last_err)
            return None

        # ---------------- CHROME ----------------
        elif name == "chrome":
            options = ChromeOptions()
            options = set_properties(options, proxy)

            # Attempt 1: Selenium 4 style with Service
            try:
                service = ChromeService(ChromeDriverManager().install())
                driver = webdriver.Chrome(service=service, options=options)
                return driver
            except TypeError as e:
                last_err = e
            except Exception as e:
                last_err = e

            # Attempt 2: older style (path as first arg)
            try:
                driver = webdriver.Chrome(
                    ChromeDriverManager().install(),
                    options=options,
                )
                return driver
            except Exception as e:
                last_err = e

            print("Error while initialising Chrome WebDriver:", last_err)
            return None

        else:
            print(f"Browser '{browser_name}' not supported. Use chrome or firefox.")
            return None

    @staticmethod
    def scrap(username: str, browser_name: str, proxy: str = None, debug: bool = False) -> str:
        """
        Scrape TikTok profile data using window['SIGI_STATE'] if available.
        Returns a JSON string (either profile data or an error object).
        """

        driver = None
        try:
            url = f"https://www.tiktok.com/@{username}"
            driver = Tiktok.init_driver(browser_name, proxy)

            if driver is None:
                return json.dumps(
                    {
                        "error": "driver_not_initialized",
                        "hint": f"Failed to start {browser_name}. Check Selenium/webdriver setup.",
                    }
                )

            if debug:
                print(f"[DEBUG] Opening URL: {url}")
                if proxy:
                    print(f"[DEBUG] Using proxy: {proxy}")

            driver.get(url)

            # Wait for the body to be present (page loaded)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # SOLUTION 1: Wait longer for JavaScript to fully execute
            if debug:
                print("[DEBUG] Waiting 5 seconds for JavaScript to load...")
            time.sleep(5)

            if debug:
                print("[DEBUG] Page title:", driver.title)

            # SOLUTION 2: Check what global objects are available
            available_objects = driver.execute_script("""
                return Object.keys(window).filter(key => 
                    key.toUpperCase().includes('STATE') || 
                    key.toUpperCase().includes('DATA') || 
                    key.toUpperCase().includes('INITIAL') ||
                    key.toUpperCase().includes('SIGI') ||
                    key.toUpperCase().includes('UNIVERSAL') ||
                    key.toUpperCase().includes('PROPS') ||
                    key.toUpperCase().includes('NEXT')
                );
            """)

            if debug:
                print("[DEBUG] Available TikTok data objects:", available_objects)

            # Try to read TikTok's global state object safely - try multiple sources
            state_data = driver.execute_script("""
                return window.__$UNIVERSAL_DATA$__ || 
                       window.SIGI_STATE || 
                       window.__UNIVERSAL_DATA_FOR_REHYDRATION__ || 
                       window.__DEFAULT_SCOPE__ ||
                       window.__INITIAL_STATE__ ||
                       null;
            """)

            if debug:
                print("[DEBUG] Current URL from Selenium:", driver.current_url)
                html = driver.page_source
                print("[DEBUG] First 500 chars of HTML:")
                print(html[:500])
                
                if state_data:
                    print("[DEBUG] Found state data!")
                    print("[DEBUG] State data type:", type(state_data))
                    if isinstance(state_data, dict):
                        print("[DEBUG] Top-level keys:", list(state_data.keys()))
                else:
                    print("[DEBUG] No state data found in any known location")
                    
                    # Try to find script tags that might contain data
                    script_tags = driver.execute_script("""
                        var scripts = document.getElementsByTagName('script');
                        var found = [];
                        for(var i = 0; i < scripts.length; i++) {
                            var text = scripts[i].textContent || scripts[i].innerText;
                            if (text && (text.includes('UserModule') || text.includes('userData') || text.includes('userInfo'))) {
                                found.push(scripts[i].id || 'script_' + i);
                            }
                        }
                        return found;
                    """)
                    print("[DEBUG] Script tags that might contain user data:", script_tags)

            if not state_data:
                return json.dumps(
                    {
                        "error": "SIGI_STATE_not_found",
                        "hint": "TikTok may have changed their frontend or this page is serving a different layout (e.g., error / region / cookie notice).",
                        "username": username,
                        "available_objects": available_objects,
                    }
                )

            # Handle new TikTok data structure
            if "__DEFAULT_SCOPE__" in state_data:
                default_scope = state_data.get("__DEFAULT_SCOPE__", {})
                if debug:
                    print("[DEBUG] Found __DEFAULT_SCOPE__, exploring structure...")
                    if isinstance(default_scope, dict):
                        print("[DEBUG] __DEFAULT_SCOPE__ keys:", list(default_scope.keys())[:20])  # Show first 20 keys
                
                # Try to find user data in the new structure
                # Common paths in new TikTok structure
                user_module = (
                    default_scope.get("webapp.user-detail", {}) or
                    default_scope.get("UserModule") or
                    {}
                )
                
                if debug:
                    print("[DEBUG] user_module type:", type(user_module))
                    if isinstance(user_module, dict):
                        print("[DEBUG] user_module keys:", list(user_module.keys()))
            else:
                user_module = state_data.get("UserModule")
            
            if not isinstance(user_module, dict):
                return json.dumps(
                    {
                        "error": "UserModule_missing",
                        "hint": "UserModule key not present in state data. Structure changed.",
                        "username": username,
                        "top_level_keys": list(state_data.keys()),
                        "default_scope_keys": list(state_data.get("__DEFAULT_SCOPE__", {}).keys())[:30] if "__DEFAULT_SCOPE__" in state_data else [],
                    }
                )

            users = user_module.get("users", {}) or {}
            stats = user_module.get("stats", {}) or {}

            user_key = username.lower()

            # Check if we're dealing with the new structure (webapp.user-detail)
            if "userInfo" in user_module:
                if debug:
                    print("[DEBUG] Using new TikTok data structure (webapp.user-detail)")
                
                user_info = user_module.get("userInfo", {})
                user_data = user_info.get("user", {})
                stats_data = user_info.get("stats", {})
                
                if debug:
                    print("[DEBUG] user_data keys:", list(user_data.keys()) if user_data else "None")
                    print("[DEBUG] stats_data keys:", list(stats_data.keys()) if stats_data else "None")
                
                if not user_data:
                    return json.dumps(
                        {
                            "error": "user_data_not_found",
                            "hint": "Could not find user data in new structure.",
                            "username": username,
                            "userInfo_keys": list(user_info.keys()) if user_info else [],
                        }
                    )
                
                # Build profile data from new structure
                profile_data = {
                    "sec_id": user_data.get("secUid"),
                    "id": user_data.get("id"),
                    "is_secret": user_data.get("secret"),
                    "username": user_data.get("uniqueId"),
                    "nickname": user_data.get("nickname"),
                    "bio": user_data.get("signature"),
                    "avatar_image": user_data.get("avatarMedium") or user_data.get("avatarLarger") or user_data.get("avatarThumb"),
                    "following": stats_data.get("followingCount"),
                    "followers": stats_data.get("followerCount"),
                    "hearts": stats_data.get("heart") or stats_data.get("heartCount"),
                    "heart_count": stats_data.get("heartCount"),
                    "video_count": stats_data.get("videoCount"),
                    "is_verified": user_data.get("verified"),
                }
                
                return json.dumps(profile_data, ensure_ascii=False)
            
            # Old structure handling
            user_data = users.get(user_key)
            stats_data = stats.get(user_key)

            if debug:
                print("[DEBUG] Found users keys:", list(users.keys()))
                print("[DEBUG] Found stats keys:", list(stats.keys()))

            if not user_data or not stats_data:
                return json.dumps(
                    {
                        "error": "user_not_in_SIGI_STATE",
                        "hint": "The username key was not found under UserModule.users/stats.",
                        "username": username,
                        "known_user_keys": list(users.keys()),
                    }
                )

            # Build profile data defensively with .get()
            profile_data = {
                "sec_id": user_data.get("secUid"),
                "id": user_data.get("id"),
                "is_secret": user_data.get("secret"),
                "username": user_data.get("uniqueId"),
                "bio": user_data.get("signature"),
                "avatar_image": user_data.get("avatarMedium"),
                "following": stats_data.get("followingCount"),
                "followers": stats_data.get("followerCount"),
                "hearts": stats_data.get("heart"),
                "heart_count": stats_data.get("heartCount"),
                "video_count": stats_data.get("videoCount"),
                "is_verified": user_data.get("verified"),
            }

            return json.dumps(profile_data, ensure_ascii=False)

        except Exception as ex:
            if debug:
                print("[DEBUG] Unexpected error while scraping TikTok:", ex)
            return json.dumps(
                {
                    "error": "unexpected_exception",
                    "message": str(ex),
                    "username": username,
                }
            )
        finally:
            if driver is not None:
                try:
                    driver.close()
                except Exception:
                    pass
                try:
                    driver.quit()
                except Exception:
                    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("username", help="username to search")
    parser.add_argument(
        "--browser",
        help="What browser your PC has? (chrome or firefox)",
    )
    parser.add_argument(
        "--proxy",
        help="Proxy server (format: protocol://ip:port, e.g., socks5://192.241.156.17:1080 or http://34.124.190.108:8080)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print debug information to stdout",
    )

    args = parser.parse_args()
    browser_name = args.browser if args.browser is not None else "chrome"
    proxy = args.proxy if args.proxy else None

    print(Tiktok.scrap(args.username, browser_name, proxy=proxy, debug=args.debug))