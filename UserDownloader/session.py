# Standard libs
import asyncio
from contextlib import asynccontextmanager

# Not standard libs (pip install)
import aiohttp
from fake_useragent import UserAgent

async def give_nice_session(headers: dict = None, cookies_jar: aiohttp.CookieJar = None, timeout: aiohttp.ClientTimeout = None, retry_options: dict = None):
    
    headers = headers if isinstance(headers, dict) else {}
    
    cookie_jar = cookies_jar if isinstance(cookies_jar, aiohttp.CookieJar) else aiohttp.CookieJar() 

    timeout = aiohttp.ClientTimeout(
        total=1800,  # Total request timeout (30 minutes)
        connect=10,  # Time to establish connection
        sock_read=1800,  # Maximum time to read data from the server (30 minutes)
        sock_connect=10,  # Time for socket connection
    ) if not isinstance(timeout, aiohttp.ClientTimeout) else timeout

    retry_options = {
        "retries": 5,  # Maximum retries
        "backoff_factor": 0.5,  # Initial backoff delay (in seconds)
        "status_forcelist": {429, 500, 502, 503, 504},  # Transient errors
    } if not isinstance(retry_options, dict) else retry_options

    class RetryClientSession(aiohttp.ClientSession):
        async def _request(self, method, url, **kwargs):
            attempt = 0
            while attempt < retry_options["retries"]:
                try:
                    response = await super()._request(method, url, **kwargs)
                    if response.status == 429:
                        print(
                            f"Rate limit encountered. Retrying {attempt + 1}/{retry_options['retries']}..."
                        )
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        attempt += 1
                        continue
                    elif response.status in retry_options["status_forcelist"]:
                        print(
                            f"Transient error {response.status}. Retrying {attempt + 1}/{retry_options['retries']}..."
                        )
                        await asyncio.sleep(
                            retry_options["backoff_factor"] * (2 ** attempt)
                        )
                        attempt += 1
                        continue
                    return response
                except (
                    aiohttp.ClientResponseError,
                    aiohttp.ServerTimeoutError,
                    aiohttp.ServerDisconnectedError,
                ) as e:
                    print(f"Retry error: {e}")
                    await asyncio.sleep(
                        retry_options["backoff_factor"] * (2 ** attempt)
                    )
                    attempt += 1
            raise Exception(f"Max retries exceeded for URL: {url}")

    return RetryClientSession(headers=headers, timeout=timeout, cookie_jar=cookie_jar)

@asynccontextmanager
async def download_session_maker():
    headers = {
        "User-Agent": UserAgent().random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",  # Do Not Track,
        "Referer": "https://www.instagram.com"
    }
    session = await give_nice_session(headers=headers)
    try:
        yield session
    finally:
        await session.close()

@asynccontextmanager
async def main_session(*_, **kwargs):
    headers = {
        'User-Agent': UserAgent().firefox,
        'X-IG-App-ID': '936619743392459',
        'X-IG-WWW-Claim': '0',
        'X-Requested-With': 'XMLHttpRequest'
    }
    
    if kwargs.get('headers'):
        for key, value in kwargs.get('headers', {}).items():
            if key not in headers.keys():
                headers[key.strip()] = value.strip()
        del kwargs['headers']
    
    session = await give_nice_session(headers=headers)
    try:
        yield session
    finally:
        await session.close()
    
