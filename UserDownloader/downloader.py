# Standard libs
import asyncio, os
from urllib.parse import urlparse

# Non Standard libs (pip install -r requirments.txt)
import aiohttp, aiofiles, yarl

# Custom files
from functions import sanitize_filename, broadcast_scanner_event, convert_all_images, save_json
from config import android

async def download_media(sem: asyncio.Semaphore, session: aiohttp.ClientSession, idx: int, title: str, type: str, url: str, download_path: str, chuck_size: int = 1024 * 8):
    type = type if type.strip() not in ['', ' ', '.', '. ', None, ' .', '.'] else '.jpg'
    filename = (
        sanitize_filename(title) +
        (
            type.strip() if type[0] == '.' else '.' + type.strip() 
        )
    )
    async with sem:
        print(f'{idx}. Downloading "{filename}" in "{download_path}"...')
        filepath = os.path.join(download_path, filename)
        if not url.startswith('http'):
            print(f'{idx}. Invalid url: {url}')
            return 0
        try:
            async with session.get(yarl.URL(url, encoded=True), allow_redirects=True) as r:
                if r.status != 200:
                    print(f'[{r.status}] Unable to download from: {url}')
                    return 0
                
                l = 0
                async with aiofiles.open(filepath, 'wb') as file:
                    while True:
                        chunk = await r.content.read(chuck_size)
                        if not chunk:
                            break
                        await file.write(chunk)
                        l += len(chunk)

                print(f'{idx}. Succesfully Downloaded "{filename}"! [{l / (1024 ** 2):.2f}MB]')
                return l
        except Exception as e:
            print(f'{idx}. Error Occured while downloading "{filename}": {e}')
            return 0

async def download_user(sem, session: aiohttp.ClientSession, data: dict, download_dir: str):
    name = data['username']
    root_path = os.path.join(download_dir, name)
    posts_path = os.path.join(root_path, (f'{name}__' if android else '') + 'posts')
    media_path = os.path.join(root_path, (f'{name}__' if android else '') + 'media')

    download_size = 0
    tasks = []

    posts = data.get('posts')
    updated_posts = []
    if len(posts) > 0:
        os.makedirs(posts_path, exist_ok=True)
        for idx, post in enumerate(posts, start=1):
            base_title = post['owner']['username'] + '__' + str(post['id'])
            new_medias = []
            for media in post['media']:
                media_url = media.get('url', '')
                file_type_from_url = urlparse(media_url).path.split('.')[-1] if '.' in urlparse(media_url).path else ''
                file_type = '.mp4' if post.get('is_video') else (f".{file_type_from_url if file_type_from_url else 'jpg'}")
                title = base_title
                if post['type'] == 'GraphSideCar':
                    title += '_' + str(media['id'])
                    file_type = '.mp4' if media['is_video'] else (f".{file_type_from_url if file_type_from_url else 'jpg'}")
                if not media['downloaded']:
                    tasks.append(asyncio.create_task(download_media(sem, session, idx, title, file_type, media_url, posts_path)))
                    new_media = {key: value for key, value in media.items()}
                    new_media['downloaded'] = True
                    new_medias.append(new_media)
            new_post = {key: value for key, value in post.items()}
            new_post['media'] = new_medias
            updated_posts.append(new_post)

    user_media = data['profile_pic']
    if isinstance(user_media, dict):
        os.makedirs(media_path, exist_ok=True)
        for idx, (key, value) in enumerate(user_media.items(), start=1):
            tasks.append(
                asyncio.create_task(download_media(sem, session, idx, f"{name}_profile_pic_{key}", '.jpg', value, media_path))
            )
    
    download_size += sum(await asyncio.gather(*tasks)) if tasks else 0
    data['posts'] = updated_posts

    print(f'Converting all not ".jpeg" images to ".jpeg"...')
    print(f"Converted \"{len(await convert_all_images(posts_path))}\" Images!")

    save_json(data, os.path.join(root_path, name))
    print(f"Downloaded \"{data['fullname'] or data['username']}\" in \"{os.path.abspath(root_path)}\" [{download_size / (1024**2):.2f}MB]")

    if android:
        print(f'Reindexing Media Database...')
        if broadcast_scanner_event(os.path.abspath(root_path)) != 0:
            print(f'Reindexing UnSuccessfull!')
        else:
            print(f'Reindexing Successfull!')

    return download_size

