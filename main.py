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
        else:
            if valid_url(arg):
                urls.append(arg)

        count += 1

    return urls


def download_media(
    session: Session,
    parsed_graph: dict,
    root_dir: Path,
    cb: Callable[[int, int, int], None],
) -> tuple[Path | None, int]:
    media_url = parsed_graph["media"]["src"]
    filename = root_dir / str(parsed_graph["id"])
    filename.parent.mkdir(exist_ok=True, parents=True)

    with session.get(media_url, allow_redirects=True, stream=True) as resp:
        if resp.status_code != 200:
            raise HTTPError("Not ok response", request=resp.request, response=resp)
        try:
            content_length = int(resp.headers["Content-Length"])
        except (KeyError, TypeError, ValueError):
            content_length = -1
        downloaded = 0

        with filename.open("wb") as file:
            chunk_size = 1024 * 10
            for chunk in resp.iter_content(chunk_size=chunk_size):
                file.write(chunk)
                downloaded += len(chunk)
                cb(
                    downloaded,
                    content_length < downloaded and downloaded or content_length,
                    chunk_size,
                )

            filename.rename(
                filename.with_suffix(
                    guess_extension(resp.headers["Content-Type"]) or ".bin"
                )
            )
            filename = filename.with_suffix(
                guess_extension(resp.headers["Content-Type"]) or ".bin"
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
    pic_json = resp["data"]["xdt_shortcode_media"]
    info["type"] = pic_json["__typename"]  # XDT: ->
    info["user"] = pic_json["owner"]
    info["items"] = []

    if info["type"] == "XDTGraphSidecar":
        for sidecar_node in map(
            lambda x: x["node"], pic_json["edge_sidecar_to_children"]["edges"]
        ):
            info["items"].append(parse_graphmedia(sidecar_node))
    else:
        info["items"].append(parse_graphmedia(pic_json))

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
                    ).write_text(resp.text)
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
                                    "\r↪ %02d. %s (%.1f%%)"
                                    % (idx, item["id"], (done / total) * 100),
                                    end="",
                                )

                        download_dir = (
                            root_dir / ("%s" % data["user"]["id"])
                            if subdir
                            else root_dir
                        )
                        d, t = download_media(
                            session,
                            item,
                            download_dir,
                            show_prog,
                        )
                        print(
                            "\n%02d. %s -> %s [%s]"
                            % (idx, item["id"], d, sizeof_fmt(t))
                        )
                        time.sleep(idx % 3)
                    except KeyboardInterrupt:
                        break
                    except Exception as e:
                        print("\nDownload Error: %s" % (e))
                        continue
            except KeyboardInterrupt:
                break
            except Exception as e:
                print("Parse Error: %s" % e)
                continue

            # resp = json.loads(Path('./test.json').read_text())
            # data = parse_response(resp)
            # print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
