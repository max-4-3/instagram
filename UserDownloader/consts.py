import ssl, aiohttp

IP = '66.254.114.41'
DOMAIN = 'www.pornhub.org'
HEADERS = {
    'User-Agent': r'Mozilla/5.0 (Windows NT x.y; Win64; x64; rv:10.0) Gecko/20100101 Firefox/10.0',
    'Host': DOMAIN
}
BASE_URL = 'https://' + IP

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE
