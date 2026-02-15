import asyncio
import json
import sys
from pathlib import Path
from typing import Mapping
from aiohttp import (
    ClientSession,
    FormData,
    CookieJar,
    TraceConfig,
    TraceRequestEndParams,
)
from aiohttp.abc import AbstractCookieJar


def append_to_file(data: str):
    Path("./request.log").open("a").write(data + "\n")


def dump_cookie_jar(jar: AbstractCookieJar):
    return [{"key": c.key, "value": c.value, "domain": c.get("domain")} for c in jar]


def pick_keys(mapping: Mapping, *keys: str) -> dict:
    return {
        key if len(key.split(":", 1)) != 2 else key.split(":", 1)[0].strip(): str(
            mapping.get(key)
        )
        for key in set(keys)
    }


def parse_items(items: list[dict]) -> list[dict]:
    parsed = []
    # fmt: off
    keys = [
        "id",
        "code",
        "caption",
        "owner",
        "taken_at",
        "pk",
        "play_count",
        "clips_metadata",               # Music BS
        "media_type",
        "media_attributions_data",
        "product_type",
        "video_dash_manifest",          # DASH INFO <https://en.wikipedia.org/wiki/Dynamic_Adaptive_Streaming_over_HTTP>
        "video_duration",
        "video_versions",               # Similar to DASH but has direct video links?
        "number_of_qualities",
        "display_uri",                  # thumbnail
    ]
    # fmt: on

    for item in items:
        if (media := item.get("media")) and isinstance(media, dict):
            parsed.append(pick_keys(media, *keys))
    return parsed


async def log_req_end(
    session: ClientSession, trace_config_ctx, params: TraceRequestEndParams
):
    resp = params.response

    data = {
        "code": resp.status,
        "reason": resp.reason,
        "url": str(resp.url),
        "elapsed": getattr(trace_config_ctx, "start", None),
        "headers_response": dict(resp.headers),
        "headers_session": dict(session.headers),
        "cookies_session": dump_cookie_jar(session.cookie_jar),
    }

    if resp.status >= 400 and resp.content_type.endswith("json"):
        try:
            data["response"] = await resp.text()
        except Exception:
            data["response"] = "<failed to read body>"

    append_to_file(json.dumps(data, default=str, ensure_ascii=False))


async def req_end(session: ClientSession, _, params: TraceRequestEndParams):
    if csrf := params.response.cookies.get("csrftoken"):
        session.headers.update({"X-CSRFToken": csrf.value})


def save_items(username, user_id, total_items):
    save_path = f"save_path/{user_id}-{username}.json"
    Path(save_path).open("a").write(
        json.dumps(
            total_items, indent=2, default=str, ensure_ascii=False, sort_keys=True
        )
        + "\n"
    )
    print(f"Saved to {save_path} {len(total_items)} items")


async def main():
    try:
        username = sys.argv[1]
        user_id = sys.argv[2]
    except IndexError:
        print("ERROR: provide a username and user_id")
        print(f"USAGE: {sys.argv[0]} <username> <user_id>")
        exit(1)

    domain = "https://www.instagram.com"
    headers = {
        "X-IG-App-ID": "936619743392459",
        "X-ASBD-ID": "359341",
        "X-IG-WWW-Claim": "0",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-GPC": "1",
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": f"{domain}/",
    }

    trace_config = TraceConfig()

    trace_config.on_request_end.append(req_end)
    trace_config.on_request_end.append(log_req_end)

    cookiejar = CookieJar(unsafe=True)
    async with ClientSession(
        base_url=domain,
        headers=headers,
        cookie_jar=cookiejar,
        trace_configs=[trace_config],
    ) as session:
        # Setup CSRF Token
        await session.get("/")
        session.headers.update({"Referer": f"{domain}/{username}/reels/"})

        total_items = []
        current_items = []

        should_stop = False
        max_id = None

        while not should_stop:
            current_items.clear()

            data = FormData()
            data.add_field("include_feed_video", False)
            data.add_field("page_size", 11)  # Cap is 11
            data.add_field("target_user_id", user_id)

            if max_id is not None:
                data.add_field("max_id", max_id)

            resp = await session.post(
                "/api/v1/clips/user/",
                data=data,
            )
            try:
                if resp.ok:
                    data = await resp.json()

                    # Paging
                    if (
                        (page := data.get("paging_info"))
                        and isinstance(page, dict)
                        and (new_max_id := page.get("max_id"))  # No id, either done or failed
                        and new_max_id != max_id                # we are looping
                    ):
                        max_id = new_max_id
                        should_stop = not page.get("more_available", False)
                    else:
                        max_id = None
                        should_stop = True

                    # Items Parsing
                    if (items := data.get("items")) and isinstance(items, list):
                        current_items.extend(parse_items(items))
                    else:
                        max_id = None
                        should_stop = True

                    # write to file JIC (just in case)
                    append_to_file(
                        json.dumps(
                            {
                                "current": current_items,
                                "max_id": max_id,
                                "should_stop": should_stop,
                            }
                        )
                    )
                    print(f"{len(total_items) + len(current_items) = }")
                else:
                    print(
                        resp.status,
                        resp.reason,
                        resp.request_info.headers,
                        resp.cookies,
                        await resp.content.read(),
                        sep="\n--------------\n",
                    )
                    resp.raise_for_status()

                total_items.extend(current_items)
                await asyncio.sleep(1)
            except (KeyboardInterrupt, asyncio.CancelledError):
                print("Quiting...")
                break
            except Exception as e:
                print(f"Error Happened: {e}")
                save_items(username, user_id, total_items)
                raise e

        save_items(username, user_id, total_items)


if __name__ == "__main__":
    asyncio.run(main())
