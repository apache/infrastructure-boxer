# Generic OAuth plugin for services such as Apache OAuth
import re
import requests
import aiohttp

ASF_OAUTH_URL = "https://oauth.apache.org/token"
OAUTH_DOMAIN = "apache.org"

async def process(formdata, session, server):
    js = None
    url = ASF_OAUTH_URL
    headers = {"User-Agent": "ASF Boxer OAuth Agent/0.1"}
    # This is a synchronous process, so we offload it to an async runner in order to let the main loop continue.
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=formdata) as rv:
            js = await rv.json()
            assert rv.status == 200, f"Unexpected return code for GET on {url}: {rv.status}"
            js["oauth_domain"] = OAUTH_DOMAIN
            js["authoritative"] = True
            return js
