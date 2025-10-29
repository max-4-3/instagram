import random
from pathlib import Path
from asyncio import run, sleep, Semaphore, gather
from aiohttp import ClientSession
from rich.console import Console
from rich.progress import Progress

from extractor import Extractor
from downloader import Downloader
from static import HEADERS
from models import Owner


async def download_user(user: Owner, session: ClientSession, console: Console, save_path: Path):
    """Download all posts for a given user with batched parallelism."""
    downloader = Downloader(Semaphore(3), session, save_path)
    batch_size = 5

    with Progress(console=console) as post_progress:
        total_task = post_progress.add_task("Post downloaded", total=user.posts_count + (1 if user.pfp else 0))  # +1 for pfp

        with Progress(console=console, transient=True) as progress_bar:
            async def download_post_with_progress(post):
                task_id = progress_bar.add_task(f"{user.username}-{post.id}", total=None)
                download_size = await downloader.download_post(
                    post,
                    lambda total, done: progress_bar.update(
                        task_id, total=total, completed=done
                    )
                )
                post_progress.advance(total_task, 1)
                progress_bar.remove_task(task_id)
                return download_size

            for i in range(0, len(user.posts), batch_size):
                batch = user.posts[i:i + batch_size]
                await gather(*(download_post_with_progress(p) for p in batch))

                # gentle randomized pause between batches
                delay = downloader.delay + random.uniform(0.3, 1.0)
                console.log(f"[yellow]Pausing {delay:.2f}s before next batch...[/yellow]")
                await sleep(delay)

            # Download pfp at the very end
            if user.pfp:
                pfp_task = progress_bar.add_task(f"{user.username}-avatar", start=False)
                await downloader.__download__(user.pfp.hd or user.pfp.pic, save_path / f"{user.username}-avatar.png", lambda total, done: progress_bar.update(pfp_task, total=total, completed=done))
                post_progress.advance(total_task, 1)
                progress_bar.remove_task(pfp_task)


async def main():
    console = Console()
    console.clear()

    try:
        username = console.input("[bold cyan]Enter username:[/bold cyan] ").strip()
        if not username:
            console.print("[red]Username cannot be empty.[/red]")
            return

        async with ClientSession(headers=HEADERS) as session:
            extractor = Extractor(session)
            console.print("[blue]Extracting user info...[/blue]")
            user_data = await extractor.get_user(username)

            console.print(f"[cyan]Fetching posts for {username}...[/cyan]")
            posts = []
            async for chunk in extractor.get_posts(user_data):
                posts.extend(chunk)
                console.log(f"Extracted {len(posts)} posts so far...")

            user_data.posts = posts
            user_path = Path("~/Downloads/Instagram/Users").expanduser() / username
            user_path.mkdir(parents=True, exist_ok=True)
            extractor.save_data(user_data, str(user_path / f"{username}.json"))

            console.print(f"[green]Starting downloads for {len(posts)} posts.[/green]")
            await download_user(user_data, session, console, user_path / "posts")

            console.print("[bold green]All downloads completed successfully![/bold green]")

    except KeyboardInterrupt:
        console.print("\n[red]Download interrupted by user.[/red]")
        exit(0)
    except Exception as e:
        console.print_exception(show_locals=False)
        console.log(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    run(main())
