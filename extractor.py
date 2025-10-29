from aiohttp import ClientSession
from asyncio import Semaphore, sleep as asleep
from urllib import parse
from typing import AsyncGenerator
from datetime import datetime
from pathlib import Path
from logging import Logger, FileHandler, Formatter, getLogger
import json

from static import DOMAIN
from models import (
    Post, BioLink, Owner, PFP,
    SideCarMedia, BaseGraphMedia,
    TaggedUser, BaseUser, BaseModel
)


class Extractor:
    USER_ENDPOINT_URL = f"{DOMAIN}/api/v1/users/web_profile_info/?username={{}}"
    POST_DOC_ID = 7950326061742207

    def __init__(
        self,
        session: ClientSession,
        semaphore: Semaphore = Semaphore(2),
        logger: Logger | None = None
    ):
        self.session = session
        self.sem = semaphore
        self._save_path = Path("./save_path")
        self._cache_path = Path("./._extractor_cache_")
        self._log_path = Path("./.log")

        self._purge_cache()
        self._setup_logger(logger)

    # ---------------- Logger Setup ---------------- #
    def _setup_logger(self, logger: Logger | None):
        self._log_path.mkdir(exist_ok=True)
        if logger:
            self._logger = logger
        else:
            self._logger = getLogger(self.__class__.__name__)
            self._logger.setLevel(10)
            fh = FileHandler(self._log_path / "extractor.log", "a")
            fh.setLevel(10)
            fh.setFormatter(Formatter("%(asctime)s - %(levelname)s - %(message)s"))
            self._logger.addHandler(fh)
        self._logger.info("Extractor initialized")

    # ---------------- Cache Utils ---------------- #
    def _generate_cache_path(self, cache_name: str) -> Path:
        self._cache_path.mkdir(exist_ok=True)
        safe_name = f"._{sum(ord(n) for n in cache_name)}_cache"
        return self._cache_path / safe_name

    def _purge_cache(self):
        self._cache_path.mkdir(exist_ok=True)
        for file in self._cache_path.glob("*"):
            try:
                with open(file, "r") as f:
                    cache = json.load(f)
                    if cache.get("expire", 0) <= datetime.now().timestamp():
                        file.unlink(missing_ok=True)
            except Exception:
                file.unlink(missing_ok=True)

    def save_to_cache(self, name: str, data: dict | list, ttl_seconds: int):
        path = self._generate_cache_path(name)
        payload = {
            "data": data,
            "expire": datetime.now().timestamp() + ttl_seconds
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        self._logger.debug(f"Cached: {name} [{path}]")

    def load_from_cache(self, name: str):
        path = self._generate_cache_path(name)
        if not path.exists():
            self._logger.warning(f"Cache file not exist: {path} [{name}]") 
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                cache = json.load(f)
            cache["expired"] = cache["expire"] <= datetime.now().timestamp()
            self._logger.info(f"Cache found: {path} [{name} and is {'' if cache['expired'] else 'not'} expired]")
            return cache
        except Exception as error:
            self._logger.warning(f"Error with cache: {path} [{error}]")
            path.unlink(missing_ok=True)
            return None

    # ---------------- Saving Data ---------------- #
    def _unique_save_path(self, filename: str) -> Path:
        self._save_path.mkdir(exist_ok=True)
        base = Path(filename)
        save_path = self._save_path / base
        counter = 1

        while save_path.exists():
            save_path = self._save_path / f"{base.stem}_{counter}{base.suffix}"
            counter += 1

        return save_path

    def save_data(self, data, filename="data.json"):
        path = self._unique_save_path(filename)
        with open(path, "w", encoding="utf-8") as f:
            if isinstance(data, BaseModel):
                json.dump(json.loads(data.model_dump_json()), f, indent=4)
            elif isinstance(data, list):
                prepared = []
                for item in data:
                    if isinstance(item, BaseModel):
                        prepared.append(json.loads(item.model_dump_json()))
                    elif isinstance(item, dict):
                        prepared.append(item)
                    else:
                        prepared.append(str(item))
                json.dump(prepared, f, indent=4)
            elif isinstance(data, dict):
                json.dump(data, f, indent=4)
            else:
                f.write(str(data))
        self._logger.info(f"Saved data to {path}")

    # ---------------- HTTP ---------------- #
    async def make_request(self, *args, **kwargs):
        async with self.sem:
            return await self.session.request(*args, **kwargs)

    # ---------------- Core Logic ---------------- #
    async def get_user(self, username: str) -> Owner:
        cache = self.load_from_cache(username)
        if cache and not cache["expired"]:
            return self.parse_user(cache["data"])

        resp = await self.make_request(
            "get",
            self.USER_ENDPOINT_URL.format(username)
        )
        resp.raise_for_status()

        data = await resp.json()
        self.save_to_cache(username, data, 12 * 60 * 60)  # 12 hr TTL
        return self.parse_user(data)

    async def get_posts(
        self,
        user: BaseUser,
        after: str | None = None,
        first: int = 12,
        use_cache: bool = True
    ) -> AsyncGenerator[list[Post], None]:
        has_next = True
        user_id = str(user.id)

        while has_next:
            variables = {
                "id": user_id,
                "first": first,
                **({"after": after} if after else {})
            }
            url = f"{DOMAIN}/graphql/query/?doc_id={self.POST_DOC_ID}&variables={parse.quote(json.dumps(variables))}"

            cache = self.load_from_cache(url)
            cache_used = False
            if use_cache and cache and not cache["expired"]:
                data = cache["data"]
                cache_used = True
            else:
                resp = await self.make_request("get", url)
                data = await resp.json()
                self.save_to_cache(url, data, 30 * 60)

            if data.get("status", "") == "fail":
                msg = data.get("message", "Unknown error")
                self._logger.warning(f"Post request failed: {msg} [{json.dumps(data)}]")
                break

            user_media = next(iter(data["data"]["user"].values()))
            after = user_media["page_info"]["end_cursor"]
            has_next = user_media["page_info"]["has_next_page"]

            parsed = []
            for edge in user_media["edges"]:
                try:
                    parsed.append(self.parse_post(edge))
                except Exception as e:
                    self._logger.error(f"Error parsing post: {e}")
            yield parsed

            if not cache_used:
                await asleep(1.0)

    # ---------------- Parsers ---------------- #
    @staticmethod
    def get_or_none(data, key, default=None):
        try:
            return data[key] or default
        except Exception:
            return getattr(data, key, default)

    def parse_user(self, raw) -> Owner:
        raw_user = raw.get("data", {}).get("user", raw)
        return self._build_owner(raw_user)

    def parse_post(self, raw) -> Post:
        node = raw["node"]
        node_type = node["__typename"]
        media = []

        match node_type:
            case "GraphImage":
                media.append(BaseGraphMedia(
                    url=node["display_url"],
                    width=node.get("dimensions", {}).get("width", 0),
                    height=node.get("dimensions", {}).get("height", 0)
                ))
            case "GraphVideo":
                media.append(BaseGraphMedia(
                    url=node["video_url"],
                    width=node.get("dimensions", {}).get("width", 0),
                    height=node.get("dimensions", {}).get("height", 0)
                ))
            case "GraphSidecar":
                for child_edge in node.get("edge_sidecar_to_children", {}).get("edges", []):
                    child = self.get_or_none(child_edge, "node", {})
                    if child is None: continue
                    owner_data = child.get("owner", {"id": -1, "username": "unknown"})
                    media.append(SideCarMedia(
                        id=int(child.get("id", 0)),
                        shortcode=child.get("shortcode", "no_code"),
                        is_video=child.get("is_video", False),
                        type=child.get("__typename", "GraphImage"),
                        url=child.get("video_url") or child.get("display_url", ""),
                        width=child.get("dimensions", {}).get("width", 0),
                        height=child.get("dimensions", {}).get("height", 0),
                        owner=BaseUser(**owner_data)
                    ))

        caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
        caption = caption_edges[0]["node"]["text"] if caption_edges else ""

        tagged_users = [
            TaggedUser(
                id=int(t["node"]["user"]["id"]),
                username=t["node"]["user"]["username"],
                fullname=t["node"]["user"]["full_name"],
                pfp=PFP(
                    pic=t["node"]["user"].get("profile_pic_url", ""),
                    hd=t["node"]["user"].get("profile_pic_url_hd") or t["node"]["user"].get("profile_pic_url", "")
                )
            )
            for t in node.get("edge_media_to_tagged_user", {}).get("edges", [])
            if t and t not in [None, {}] and isinstance(t, dict)
        ]

        return Post(
            id=int(node["id"]),
            type=node_type,
            shortcode=node["shortcode"],
            owner=BaseUser(**node["owner"]),
            title=caption,
            timestamp=node["taken_at_timestamp"],
            likes=node.get("edge_liked_by", {}).get("count", 0),
            comments=node.get("edge_media_to_comment", {}).get("count", 0),
            thumbnail=node["thumbnail_src"],
            tagged=tagged_users,
            is_video=node.get("is_video", False),
            media=media
        )

    def _build_owner(self, data) -> Owner:
        return Owner(
            id=int(data["id"]),
            fb_id=int(data["id"]),
            eimu_id=int(data.get("eimu_id", -1)),
            username=data["username"],
            fullname=data.get("full_name", ""),
            bio=data.get("biography", ""),
            bio_links=[
                BioLink(
                    url=link["url"],
                    title=link.get("title", ""),
                    type=link.get("link_type", "external")
                )
                for link in data.get("external_url_links", data.get("bio_links", []))
                if link
            ],
            followers=data.get("edge_followed_by", {}).get("count", 0),
            following=data.get("edge_follow", {}).get("count", 0),
            is_private=data.get("is_private", False),
            is_verified=data.get("is_verified", False),
            pfp=PFP(
                pic=data["profile_pic_url"],
                hd=data.get("profile_pic_url_hd", data["profile_pic_url"])
            ),
            pronouns=data.get("pronouns", []),
            posts_count=data.get("edge_owner_to_timeline_media", {}).get("count", 0),
            bussiness_email=data.get("business_email"),
            bussiness_phone=data.get("business_phone_number")
        )
