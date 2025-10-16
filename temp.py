from threading import Thread
import random
import time
from rich.progress import Progress


def download(progress_callback, filesize, speed):
    downloaded = 0
    while downloaded < filesize:
        downloaded += speed
        time.sleep(random.uniform(0.05, 0.09))
        progress_callback(min(downloaded, filesize), filesize)


def main():
    download_tasks = 100
    batch_size = 5

    with Progress(transient=True, expand=False) as progress_bar:
        main_pbar = progress_bar.add_task("Total Downloads:", True, download_tasks)
        with Progress(transient=True) as pbar_task:
            for _ in range(0, download_tasks, batch_size):
                tasks = []

                for _ in range(batch_size):
                    filesize = random.randint(200, 2000)
                    speed = random.randint(20, 200)
                    task_id = pbar_task.add_task("Downloading", total=None)

                    def callback(completed, total, task_id=task_id):
                        pbar_task.update(task_id, completed=completed, total=filesize)

                    t = Thread(target=download, daemon=True, args=(callback, filesize, speed))
                    t.start()
                    tasks.append([t, task_id])

                for t, tid in tasks:
                    t.join()
                    progress_bar.advance(main_pbar, 1)
                    pbar_task.remove_task(tid)


if __name__ == "__main__":
    main()
