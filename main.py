import json
from mimetypes import guess_extension
from pathlib import Path
from shutil import get_terminal_size
import sys
import time
from typing import Callable
from urllib.parse import urlparse

from requests.exceptions import HTTPError
from requests.sessions import Session

# Video_by_{{username}} [{{full_name}}@Instagram] [{{id}}]    # .mp4 (or ext) will be added by `download_media`
filename_format = "{title} [{channel}@Instagram] [{id}]"
headers = {
    "authority": "www.instagram.com",
    "schema": "https",
    "acceps": "*/*",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.8",
    "Referer": "https://www.instagram.com/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
}
root_dir = Path("./downloaded_files")
subdir = True
show_stats = False
raise_error = False


def get_urls() -> list[str]:
    if len(sys.argv) < 2:
        raise RuntimeError("Not enough arguments")

    def valid_url(url: str) -> bool:
        return (p := urlparse(url)) and (
            p.scheme in {"http", "https"} and bool(p.netloc)
        )

    urls = []
    lenght = len(sys.argv)
    count = 1
    while count < lenght:
        arg = sys.argv[count]

        if (
            arg == "-d"
            and count + 1 <= lenght
            and (next_arg := sys.argv[count + 1])
            and not valid_url(next_arg)
        ):
            global root_dir
            root_dir = Path(next_arg)
            count += 1
        elif arg == "-s":
            global subdir
            subdir = not subdir
        elif arg == "-t":
            global show_stats
            show_stats = not show_stats
        elif arg == "-e":
            global raise_error
            raise_error = not raise_error
        else:
            if valid_url(arg):
                urls.append(arg)

        count += 1

    return urls


def download_media(
    session: Session,
    media_url: str,
    filename: Path,
    cb: Callable[[int, int, int], None],
) -> tuple[Path | None, int]:
    filename.parent.mkdir(exist_ok=True, parents=True)

    with session.get(media_url, allow_redirects=True, stream=True) as resp:
        if resp.status_code != 200:
            raise HTTPError("Not ok response", request=resp.request, response=resp)

        filename = filename.with_suffix(
            guess_extension(resp.headers.get("Content-Type") or "") or ".bin"
        )
        try:
            content_length = int(resp.headers["Content-Length"])
        except (KeyError, TypeError, ValueError):
            content_length = -1
        downloaded = 0
        chunk_size = 1024 * 10

        if (
            content_length > 0
            and filename.exists()
            and filename.stat().st_size == content_length
        ):
            # Already downloaded
            downloaded = content_length

            cb(downloaded, content_length, chunk_size)
            return filename, downloaded

        with filename.open("wb") as file:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                file.write(chunk)
                downloaded += len(chunk)
                cb(
                    downloaded,
                    content_length < downloaded and downloaded or content_length,
                    chunk_size,
                )
            return filename, downloaded


COMMON_KEYS = ("id", "shortcode", "accessibility_caption")


def get_graphcommon(graph):
    return {k: graph.get(k) for k in COMMON_KEYS}


def numeric_sum(d):
    total = 0
    for v in d.values():
        try:
            total += float(v)
        except (TypeError, ValueError):
            pass
    return total


def get_highest(res):
    return max(res, key=numeric_sum, default=None)


def parse_graphmedia(graph):
    typename = graph["__typename"].removeprefix("XDT")
    data = get_graphcommon(graph)

    match typename:
        case "GraphImage":
            return {
                **data,
                "media": get_highest(graph.get("display_resources", []))
                or {"src": graph.get("display_url")},
            }
        case "GraphVideo":
            return {
                **data,
                "media": {"src": graph.get("video_url", graph.get("display_url"))},
            }
        case _:
            return data


def parse_response(resp: dict) -> dict:
    info = {}
    verb = "Post"
    pic_json = resp["data"]["xdt_shortcode_media"]
    info["type"] = pic_json["__typename"]
    info["user"] = pic_json["owner"]
    info["items"] = []

    if info["type"] == "XDTGraphSidecar":
        for sidecar_node in map(
            lambda x: x["node"], pic_json["edge_sidecar_to_children"]["edges"]
        ):
            info["items"].append(parse_graphmedia(sidecar_node))
    else:
        info["items"].append(parse_graphmedia(pic_json))

    if len(info["items"]) > 1:
        verb += "s"

    info["title"] = f"{verb} by {info['user'].get('username')}"
    info["items"] = list(filter(bool, info["items"]))
    return info


# https://stackoverflow.com/questions/1094841/get-a-human-readable-version-of-a-file-size#1094933
def sizeof_fmt(num, suffix="B"):
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def main():
    urls = get_urls()
    atty = sys.stdout.isatty()

    with Session() as session:
        if show_stats:
            print(f"Url found: {len(urls)}")
            print(f"Output dir: {root_dir}")
            print(f"Output format: {filename_format}")
            print(f"Create subdir: {subdir}")

        for i, url in enumerate(urls, start=1):
            try:
                if atty:
                    print(("-" * get_terminal_size().columns))

                variables = {"shortcode": url.rsplit("/")[-2]}
                params = {
                    "variables": json.dumps(variables, separators=(",", ":")),
                    "doc_id": "8845758582119845",
                    "server_timestamp": "true",
                }
                session.headers.update(headers)
                resp = session.get(
                    "https://instagram.com/graphql/query",
                    params=params,
                    allow_redirects=True,
                )
                try:
                    data = parse_response(json.loads(resp.text))
                except Exception:
                    Path(
                        "./data-%s-%03d.json" % (variables["shortcode"], i)
                    ).write_text(
                        json.dumps(
                            {
                                "resp": {
                                    "url": resp.url,
                                    "status": resp.status_code,
                                    "params": params,
                                    "variables": variables,
                                    "text": resp.text,
                                },
                                "req": {"url": url},
                            },
                            indent=2,
                            ensure_ascii=False,
                        )
                    )
                    print("[%d] %s" % (resp.status_code, resp.url))
                    raise

                print(
                    "%02d. Downloading: %s (%02d)"
                    % (i, variables["shortcode"], len(data["items"]))
                )

                for idx, item in enumerate(data["items"], start=1):
                    try:

                        def show_prog(done, total, _):
                            if atty:
                                print(
                                    "↪ %02d. %s (%.1f%%)"
                                    % (idx, item["id"], (done / total) * 100),
                                    end="\r",
                                )

                        download_dir = (
                            root_dir / data["user"]["id"] if subdir else root_dir
                        )
                        filename = download_dir / filename_format.format(
                            **{
                                "id": item["shortcode"] or item["id"],
                                "title": data["title"],
                                "channel": data["user"].get("full_name"),
                                "uploader": data["user"].get("username"),
                            }
                        )
                        media_url = item["media"]["src"]
                        d, t = download_media(
                            session,
                            media_url,
                            filename,
                            show_prog,
                        )
                        print(
                            "↪ %02d. %s -> %s [%s]"
                            % (idx, item["id"], d, sizeof_fmt(t))
                        )
                        time.sleep(idx % 3)
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        print("\nDownload Error: %s" % (e))
                        if raise_error:
                            raise e
            except KeyboardInterrupt:
                break
            except Exception as e:
                print("Parse Error: %s" % e)
                if raise_error:
                    raise e

            # resp = json.loads(Path('./test.json').read_text())
            # data = parse_response(resp)
            # print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
