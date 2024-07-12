"""
    Github OAuth plugin.
    This follows the workflow described at: https://developer.github.com/apps/building-oauth-apps/authorizing-oauth-apps
    To make this work, please set up an application at https://github.com/settings/applications/
    copy the client ID and secret to your boxer.yaml's oauth configuration, as such:
    oauth:
      github_client_id: abcdef123456
      github_client_secret: bcfdgefa572564576
"""

import plugins.basetypes
import typing
import aiohttp

async def process(
    formdata, session, server: plugins.basetypes.Server
) -> typing.Optional[dict]:
    formdata["client_id"] = server.config.oauth.github_client_id
    formdata["client_secret"] = server.config.oauth.github_client_secret

    async with aiohttp.ClientSession() as session:
            headers = {'Accept': 'application/json', "Authorization": f"token {server.config.github.token}"}
            async with session.post("https://github.com/login/oauth/access_token", headers=headers, data=formdata) as rv:
                 response = await rv.json()
                 if 'access_token' in response:
                    async with session.get("https://api.github.com/user", headers={'Authorization': "token %s" % response['access_token']}) as rv:
                        js = await rv.json()
                        # Check for API rate limit exceeded, this is VERY RARE and a per-login issue. We cannot fix
                        if 'message' in js and 'API rate limit exceeded' in js['message']:
                            raise AssertionError("API rate limit reached for your personal account. Please try again later.")
                        js["oauth_domain"] = "github.com"
                        # Full name and email address might not always be available to us. Fake it till you make it.
                        js["name"] = js.get("name", js["login"])
                        js["email"] = js["email"] or "%s@users.github.com" % js["login"]
                        return js
    return None
