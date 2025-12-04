from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from random import choice


def random_spinner():
    return choice(
        [
            "moon",
            "runner",
            "clock",
            "earth",
            "smiley",
            "monkey",
            "layer",
            "point",
            "dots12",
            "arrow",
            "bouncingBall",
        ]
    )


PROGRESS_BAR = [
    TextColumn("{task.description}"),
    BarColumn(None),
    MofNCompleteColumn(),
    TimeElapsedColumn(),
    TextColumn("•"),
    TimeRemainingColumn(True),
]
DOWNLOAD_PROGRESS_BAR = [
    TextColumn("{task.description}"),
    BarColumn(),
    TimeElapsedColumn(),
    TextColumn("•"),
    TimeRemainingColumn(True),
    DownloadColumn(True),
    TransferSpeedColumn(),
]
DOMAIN = "https://instagram.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.5",
    "X-IG-App-ID": "936619743392459",
    "X-ASBD-ID": "359341",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com",
}
