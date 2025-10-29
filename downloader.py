import asyncio
import inspect
from functools import wraps
from pathlib import Path
from aiohttp import ClientSession
from typing import Callable

from models import Post


class Downloader:
    def __init__(
        self,
        sem: asyncio.Semaphore,
        session: ClientSession,
        root_save_path: str | Path,
        delay: float = 1.0,
        retry_limit: int = 5,
        backoff_factor: float = 2.0,
        chunk_size: int = 1024 * 1024
    ):
        self.sem = sem
        self.session = session
        self.delay = delay
        self.retry_limit = retry_limit
        self.backoff_factor = backoff_factor
        self.chunk_size = chunk_size
        self.root_path = Path(root_save_path) if not isinstance(
            root_save_path, Path) else root_save_path
        self.root_path.mkdir(parents=True, exist_ok=True)

    def retry(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            delay = self.delay
            for attempt in range(1, self.retry_limit + 2):  # +1 for final attempt
                try:
                    if inspect.iscoroutinefunction(func):
                        return await func(*args, **kwargs)
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt > self.retry_limit:
                        raise Exception(
                            f"Retry limit reached for {func.__name__}"
                        ) from e
                    await asyncio.sleep(delay)
                    delay *= self.backoff_factor
        return wrapper

    async def __download__(self, url: str, filename: Path, proc_callback: Callable[[int, int], None] | None = None) -> int:
        async with self.sem:
            async with self.session.get(url) as response:
                response.raise_for_status()

                # Efficient pre-check for already downloaded files
                content_length = response.content_length or -1
                if filename.exists() and filename.stat().st_size == content_length:
                    if callable(proc_callback):
                        proc_callback(content_length, content_length)
                    return content_length

                # Stream write with callback
                downloaded = 0
                with open(filename, "wb") as file:
                    async for chunk in response.content.iter_chunked(self.chunk_size):
                        file.write(chunk)
                        downloaded += len(chunk)
                        if callable(proc_callback):
                            proc_callback(content_length, downloaded)

                return filename.stat().st_size

    @staticmethod
    def generate_filename_from_post(post: Post):
        # safe_title = "".join(
        #     c if c.isalnum() or c in (
        #         ' ', '-', '_'
        #     ) else "_" for c in post.title
        # )
        return f"{post.id}-{post.owner.username}"

    async def download_post(self, post: Post, progress_callback: Callable[[int, int], None] | None = None):
        base_filename = self.root_path / self.generate_filename_from_post(post)
        total_size = 0

        for media in post.media:
            ext = ".mp4" if post.is_video else ".png"
            hashed_name = sum(ord(n) for n in str(media.url))
            filename = base_filename.with_name(
                f"{base_filename.name}-{hashed_name}{ext}"
            )

            total_size += await self.__download__(
                media.url,
                filename,
                progress_callback
            )

        return total_size
