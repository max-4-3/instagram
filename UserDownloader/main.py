import aiohttp, asyncio, json, random, os, re, yarl, warnings, aiofiles, io, PIL.Image, random
from colorama import Fore
from urllib.parse import urlparse
from fake_useragent import UserAgent

warnings.filterwarnings("ignore", category=DeprecationWarning)
USER_GRAPH_QL_URL = "https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
MEDIA_DETAIL_URL = "https://www.instagram.com/graphql/query/"
MEDIA_DETAIL_HESH = "c6809c9c025875ac6f02619eae97a80e"  # No longer works
DOC_ID = 7950326061742207
linux = os.name.lower() not in ['windows', 'nt']
android = linux and os.path.exists('/sdcard/')
if linux and not android:
    # For Linux (Arch, Mint, Debian, etc)
    DOWNLOAD_PATH_BASE = os.path.expanduser('~')
elif linux and android:
    # For Android (Termux, etc)
    DOWNLOAD_PATH_BASE = os.path.abspath('/sdcard/')
else:
    # For Windows (duh?)
    DOWNLOAD_PATH_BASE = os.getenv("USERPROFILE") or os.path.join(os.getenv('HOMEDRIVE'), os.getenv('HOMEPATH'))
# Makes full path
DOWNLOAD_PATH = os.path.join(DOWNLOAD_PATH_BASE, "Downloads" if not android else "Download", "Instagram", "Users")  # In Android its "Download" not "Downloads"

def broadcast_scanner_event(p: str):
    command = f'am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{p} >/dev/null 2>&1'
    return os.system(command)

def load_json(fp: str):
    with open(fp, 'r', errors='ignore', encoding='utf-8') as file:
        return json.load(file)

def clear():
    os.system('cls' if os.name in ['nt', 'windows'] else 'clear')

def preety_print(data: dict):
    print(json.dumps(data, ensure_ascii=False, indent=4))

def save_json(data, fp: str):
    with open(fp + ('.json' if not fp.endswith('.json') else ''), 'w', errors='ignore', encoding='utf-8') as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

def save_webpage(page: str, fp: str):
    with open(fp + '.html', 'w', errors='ignore', encoding='utf-8') as file:
        file.write(page)

def sanitize_filename(filename: str, replacement: str = '_', max_length: int = 255) -> str:
    """
    Sanitize a string for use as a filename on Windows/Linux, ensuring it adheres to length restrictions.

    Args:
        filename (str): The input string to sanitize.
        replacement (str): The character to replace invalid characters with.
        max_length (int): The maximum allowable length for the filename.

    Returns:
        str: A sanitized and truncated filename.
    """
    # Characters invalid in filenames on Windows and Linux
    invalid_chars = r'[<>:"/\\|?*\n\r\t]'
    # Replace invalid characters with the replacement character
    sanitized = re.sub(invalid_chars, replacement, filename).strip(' .')
    # Truncate to the maximum length if necessary
    if len(sanitized) > max_length:
        extension = ''
        if '.' in sanitized:
            # Separate file extension
            sanitized, extension = sanitized.rsplit('.', 1)
            extension = '.' + extension
        # Adjust length to accommodate the extension
        sanitized = sanitized[:max_length - len(extension)].rstrip(' .') + extension
    return sanitized

def get_username(t: str) -> str | None:
    if not t or t is None:
        return
    
    match = re.search(r'instagram\.com/([^/?]+)', t)
    if match:
        return match.group(1)

def get_simplified_post(items: list[dict], old_post_ids: list | None = None):
    print(f'Analyzing {Fore.LIGHTMAGENTA_EX}{len(items)}{Fore.RESET} posts...')
    posts = []
    posts_id = old_post_ids if isinstance(old_post_ids, list) else []
    error_posts = []
    errors = 0
    for item in items:
        node = item.get('node', {})
        node_type = node['__typename']
        post = {
            'id': int(node['id']),
            'type': node_type,
            'shortcode': node['shortcode'],
            'owner': node['owner'],
            'title': node['edge_media_to_caption']['edges'][0]['node']['text'] if node['edge_media_to_caption']['edges'] else '',
            'comments': 0,
            'likes': 0,
            'timestamp': node['taken_at_timestamp'],
            'tagged': [],
            'media': []
        }
        try:
            if isinstance(node.get('edge_liked_by'), dict):
                post['likes'] = node.get('edge_liked_by').get('count', 0)

            if isinstance(node.get('edge_media_to_comment'), dict):
                post['comments'] = node['edge_media_to_comment'].get('count')

            # Extract tagged users
            tagged = node.get('edge_media_to_tagged_user', {})
            if tagged.get('edges'):
                post['tagged'] = [
                    {
                        'id': int(t['node']['user']['id']),
                        'username': t['node'].get('user', {}).get('username'),
                        'fullname': t['node'].get('user', {}).get('full_name'),
                        'verified': t['node'].get('user', {}).get('is_verified'),
                        'pfp': t['node'].get('user').get('profile_pic_url'),
                        'position': (t['node']['x'], t['node']['y']),
                    }
                    for t in tagged.get('edges', [])
                    if t and t != {} and isinstance(t, dict)
                ]

            # Prepare downloadable resources
            download_res = []

            match node_type:
                case 'GraphVideo':
                    download_res.append(
                        {
                            'width': node['dimensions']['width'],
                            'height': node['dimensions']['height'],
                            'url': node['video_url'],
                            'downloaded': False
                        }
                    )
                    post['is_video'] = True
                    post['views'] = node['video_view_count']
                case 'GraphImage':
                    download_res.append(
                        {
                            'width': node['dimensions']['width'],
                            'height': node['dimensions']['height'],
                            'url': node['display_url'],
                            'downloaded': False
                        }
                    )
                    post['is_video'] = False
                    post['views'] = 0
                case 'GraphSidecar':
                    post['is_video'] = False
                    edge_sidecar_to_children = node.get('edge_sidecar_to_children', {}).get('edges', [])
                    for children in edge_sidecar_to_children:
                        children_node = children.get('node', {})
                        if not children_node or children_node == {}:
                            continue
                        children_type = children_node.get('__typename')
                        match children_type:
                            case 'GraphImage':
                                download_res.append(
                                    {
                                        'id': int(children_node.get('id')),
                                        'shortcode': children_node.get('shortcode'),
                                        'type': children_type,
                                        'url': children_node.get('display_url'),
                                        'width': children_node['dimensions']['width'],
                                        'height': children_node['dimensions']['height'],
                                        'owner': children_node.get('owner'),
                                        'is_video': False,
                                        'views': 0,
                                        'downloaded': False
                                    }
                                )
                            case 'GraphVideo':
                                download_res.append(
                                    {
                                        'id': int(children_node.get('id')),
                                        'shortcode': children_node.get('shortcode'),
                                        'type': children_type,
                                        'url': children_node.get('video_url'),
                                        'width': children_node['dimensions']['width'],
                                        'height': children_node['dimensions']['height'],
                                        'owner': children_node.get('owner'),
                                        'is_video': True,
                                        'views': children_node.get('video_view_count', 0),
                                        'downloaded': False
                                    }
                                )
                            case _:
                                pass
                    post['views'] = sum(d.get('views', 0) for d in download_res if isinstance(d, dict))
                case _:
                    pass

            # Add downloadable media to the post
            post['media'] = download_res
            posts.append(post)
        except Exception as e:
            errors += 1
            print(f'Unable to extract info from "{post['id']}" post: {e}')
            posts.append(item)
            error_posts.append((e, item))

    print(f'Data analyzed, Caught {Fore.LIGHTRED_EX}{errors}{Fore.RESET} errors!')
    if errors > 0:
        path = os.path.join('errors/error_posts')
        os.makedirs('errors', exist_ok=True)

        save_json({
            'error_count': error_posts[0],
            'errors': [error[1] for error in error_posts],
            'items': [error[2] for error in error_posts]
        }, path)
        print(f'Error rate is not 0, therefore error info saved in: {path + ".json"}')
    
    # Sort the posts by 'views'
    posts = sorted(posts, key=lambda x: x.get('views'), reverse=True)
    posts_id.extend(k['id'] for k in posts if isinstance(k, dict))

    return posts, posts_id

async def convert_image(fp: str, file_type: str = 'jpeg', q: int = 90, o: bool = True, p: bool = True):
    try:
        async with aiofiles.open(fp, 'rb') as inFile:
            image_data = await inFile.read()
        
        new_filename = os.path.splitext(fp)[0] + (file_type.lower() if file_type[0] == '.' else '.' + file_type.lower())
        with PIL.Image.open(io.BytesIO(image_data)) as img:
            img = img.convert("RGB")
            img.save(new_filename, format=file_type.upper(), quality=q, optimize=o, progressive=p)
        
        if os.path.exists(new_filename) and os.path.exists(fp):
            try:
                os.remove(fp)
                print(f'Successfully Changed "{Fore.LIGHTCYAN_EX}{os.path.split(fp)[1]}{Fore.RESET}" to "{Fore.LIGHTGREEN_EX}{file_type.upper()}{Fore.RESET}"!')
            except:
                pass

        return new_filename if os.path.exists(new_filename) else fp
    except Exception as e:  
        print(f"Error converting \"{os.path.split(fp)[1]}\" to \"{file_type}\": {Fore.LIGHTRED_EX}{e}{Fore.RESET}")

async def convert_all_images(image_folder: str, file_type: str = 'JPEG', quality: int = 90, optimize: bool = True, progressive: bool = True):
    try:
        files = [file for file in os.listdir(image_folder) if os.path.splitext(file)[1] not in ['.mp4', '.png', '.jpg']]

        tasks = []
        for file in files:
            tasks.append(asyncio.create_task(convert_image(os.path.join(image_folder, file), file_type, quality, optimize, progressive)))
        
        new_filename = await asyncio.gather(*tasks)
        return new_filename
    except Exception as e:
        print(f'Unable to Convert Any Images to Supported Formats (".jpg", ".png"): {e}')
        return []

async def setup_session():
    """
    Sets up a robust session for interacting with Instagram, including handling
    retries, rate-limiting, and backoff strategies for transient errors.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",  # Do Not Track,
        "Referer": "https://www.instagram.com"
    }
    cookie_jar = aiohttp.CookieJar()

    timeout = aiohttp.ClientTimeout(
        total=1800,  # Total request timeout (30 minutes)
        connect=10,  # Time to establish connection
        sock_read=1800,  # Maximum time to read data from the server (30 minutes)
        sock_connect=10,  # Time for socket connection
    )

    retry_options = {
        "retries": 5,  # Maximum retries
        "backoff_factor": 0.5,  # Initial backoff delay (in seconds)
        "status_forcelist": {429, 500, 502, 503, 504},  # Transient errors
    }

    class RetryClientSession(aiohttp.ClientSession):
        async def _request(self, method, url, **kwargs):
            attempt = 0
            while attempt < retry_options["retries"]:
                try:
                    response = await super()._request(method, url, **kwargs)
                    if response.status == 429:
                        print(
                            f"Rate limit encountered. Retrying {attempt + 1}/{retry_options['retries']}..."
                        )
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        attempt += 1
                        continue
                    elif response.status in retry_options["status_forcelist"]:
                        print(
                            f"Transient error {response.status}. Retrying {attempt + 1}/{retry_options['retries']}..."
                        )
                        await asyncio.sleep(
                            retry_options["backoff_factor"] * (2 ** attempt)
                        )
                        attempt += 1
                        continue
                    return response
                except (
                    aiohttp.ClientResponseError,
                    aiohttp.ServerTimeoutError,
                    aiohttp.ServerDisconnectedError,
                ) as e:
                    print(f"Retry error: {e}")
                    await asyncio.sleep(
                        retry_options["backoff_factor"] * (2 ** attempt)
                    )
                    attempt += 1
            raise Exception(f"Max retries exceeded for URL: {url}")

    return RetryClientSession(headers=headers, timeout=timeout, cookie_jar=cookie_jar)

async def download_media(sem: asyncio.Semaphore, session: aiohttp.ClientSession, idx: int, title: str, type: str, url: str, download_path: str, chuck_size: int = 1024 * 8):
    type = type if type.strip() not in ['', ' ', '.', '. ', None, ' .', '.'] else '.jpg'
    filename = (
        sanitize_filename(title) +
        (
            type.strip() if type[0] == '.' else '.' + type.strip() 
        )
    )
    async with sem:
        print(f'{idx}. Downloading "{Fore.LIGHTCYAN_EX}{filename}{Fore.RESET}" in "{Fore.LIGHTBLUE_EX}{download_path}{Fore.RESET}"...')
        filepath = os.path.join(download_path, filename)
        if not url.startswith('http'):
            print(f'{idx}. Invalid url: {Fore.LIGHTRED_EX}{url}{Fore.RESET}')
            return 0
        try:
            async with session.get(yarl.URL(url, encoded=True), allow_redirects=True) as r:
                if r.status != 200:
                    print(f'[{Fore.LIGHTRED_EX}{r.status}{Fore.RESET}] Unable to download from: {url}')
                    return 0
                
                l = 0
                async with aiofiles.open(filepath, 'wb') as file:
                    while True:
                        chunk = await r.content.read(chuck_size)
                        if not chunk:
                            break
                        await file.write(chunk)
                        l += len(chunk)

                print(f'{idx}. Succesfully Downloaded "{Fore.LIGHTGREEN_EX}{filename}{Fore.RESET}"! [{Fore.LIGHTMAGENTA_EX}{l / (1024 ** 2):.2f}MB{Fore.RESET}]')
                return l
        except Exception as e:
            print(f'{idx}. Error Occured while downloading "{filename}": {Fore.LIGHTRED_EX}{e}{Fore.RESET}')
            return 0

async def get(sem: asyncio.Semaphore, session: aiohttp.ClientSession, url: str, as_json: bool = True):
    async with sem:
        async with session.get(url) as response:
            if response.status != 200:
                print(f'[{response.status}] Unable to retrive from url: {url}')
                return
            return await response.json() if as_json else await response.text()

async def get_posts(sem: asyncio.Semaphore, session: aiohttp.ClientSession, user_id: int, first: int = 50, after = None, total = None, post_ids = None):
    """Returns post along with their ids (tuple[posts: list[dict], post_ids: set[int]])"""
    posts = []
    known_posts = post_ids if isinstance(post_ids, list) else []
    has_next_page = True
    page = 1

    while has_next_page:
        try:
            variables = {
                'id': user_id,
                'first': first,
                'after': after
            }
            print(f'{page}. Extracting posts from {Fore.LIGHTGREEN_EX}{user_id}{Fore.RESET}...' if not total else f'{page}. Extracting posts from {Fore.LIGHTGREEN_EX}{user_id}{Fore.RESET}... [{total} total, {len(posts)} scraped]')
            next_url = f"{MEDIA_DETAIL_URL}?doc_id={DOC_ID}&variables={json.dumps(variables)}"  # Originally it was "MEDIA_DETAIL_URL?query_id={MEDIA_QUERY_HASH}"
            response = await get(sem, session, next_url)

            if not response:
                print(f'\tManaged to extract {Fore.LIGHTMAGENTA_EX}{len(posts)}{Fore.RESET} posts!'.expandtabs(2))
                break

            data = response.get("data", {}).get("user", {}).get("edge_owner_to_timeline_media", {})
            edges = data.get("edges", [])
            
            # Checks if the post id is not in scarped ones
            new_posts = [edge for edge in edges if int(edge["node"]["id"]) not in known_posts]
            if not new_posts:
                print(f'\tNo new posts found. Stopping scraping.'.expandtabs(2))
                break

            posts.extend(new_posts)
            has_next_page = data.get("page_info", {}).get("has_next_page", False)
            after = data.get("page_info", {}).get("end_cursor")
            print(f'\tExtracted {Fore.LIGHTMAGENTA_EX}{len(new_posts)}{Fore.RESET} posts!'.expandtabs(2))
            page += 1

            if not has_next_page:
                print(f'\tManaged to extract {Fore.LIGHTMAGENTA_EX}{len(posts)}{Fore.RESET} posts!'.expandtabs(2))
                break

            await asyncio.sleep(random.randint(1, 3) + random.random())
        except KeyboardInterrupt:
            break

    print(f'Analyzing scraped data...')
    return get_simplified_post(posts, old_post_ids=known_posts)

async def get_user(sem, session: aiohttp.ClientSession, username: str, all_posts: bool = True):
    
    print(f'Extracting user for username: {Fore.LIGHTCYAN_EX}{username}{Fore.RESET}...')
    data = await get(sem, session, USER_GRAPH_QL_URL.format_map({'username': username}), True)
    if not isinstance(data.get('data'), dict):
        print(f'Unable to extract user for: {username}')
        return {}

    data = data['data'].get('user')

    # Parse the data obj
    user = {
        'id': int(data['id']),
        'fb_id': int(data['fbid']),
        'username': data['username'],
        'fullname': data['full_name'],
        'eimu_id': int(data['eimu_id']),
        'bio': data['biography'],
        'bio_links':[
            {
                'title': link['title'],
                'url': link['url'],
                'type': link['link_type']
            } for link in data['bio_links'] if link and link != {}
        ],
        'bio_with_entities': data['biography_with_entities'],
        'followers': 0,
        'following': 0,
        'url': f'https://www.instagram.com/{data["username"]}',
        'posts': [],
        'private': data['is_private'],
        'verified': data['is_verified'],
        'profile_pic': {
            'pic': data['profile_pic_url'],
            'hd': data['profile_pic_url_hd']
        },
        'pronouns': data['pronouns'],
        'bussines_email': data['business_email'],
        'business_phone': data['business_phone_number']
    }
    edge_followed_by = data.get('edge_followed_by', {})
    if isinstance(edge_followed_by, dict):
        follow_count = edge_followed_by.get('count')
        if isinstance(follow_count, (str, int)):
            user['followers'] = int(follow_count)
    
    edge_follow = data.get('edge_follow', {})
    if isinstance(edge_follow, dict):
        follow_count = edge_follow.get('count')
        if isinstance(follow_count, (str, int)):
            user['following'] = int(follow_count)
    
    initial_edge = data['edge_owner_to_timeline_media']
    user['total_posts'] = initial_edge['count']
    if all_posts:
        print(f"Extracting {Fore.LIGHTBLUE_EX}{user['total_posts']}{Fore.RESET} posts for {Fore.LIGHTCYAN_EX}{user['fullname'] or user['username']}{Fore.RESET}...")
        posts = await get_posts(sem, session, user['id'], total=user['total_posts'])
    else:
        posts = get_simplified_post(initial_edge.get('edges'))
    
    user['posts'], user['posts_ids'] = posts
    return user

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

    print(f'Converting all not "{Fore.LIGHTCYAN_EX}.jpeg{Fore.RESET}" images to "{Fore.LIGHTMAGENTA_EX}.jpeg{Fore.RESET}"...')
    print(f"Converted \"{Fore.LIGHTGREEN_EX}{len(await convert_all_images(posts_path))}{Fore.RESET}\" Images!")

    save_json(data, os.path.join(root_path, name))
    print(f"Downloaded \"{Fore.LIGHTCYAN_EX}{data['fullname'] or data['username']}{Fore.RESET}\" in \"{Fore.LIGHTGREEN_EX}{os.path.abspath(root_path)}{Fore.RESET}\" [{Fore.LIGHTMAGENTA_EX}{download_size / (1024**2):.2f}MB{Fore.RESET}]")

    if android:
        print(f'{Fore.LIGHTCYAN_EX}Reindexing{Fore.LIGHTGREEN_EX} Media Database{Fore.RESET}...')
        if broadcast_scanner_event(os.path.abspath(root_path)) != 0:
            print(f'{Fore.LIGHTCYAN_EX}Reindexing {Fore.LIGHTRED_EX}UnSuccessfull{Fore.RESET}!')
        else:
            print(f'{Fore.LIGHTCYAN_EX}Reindexing {Fore.LIGHTGREEN_EX}Successfull{Fore.RESET}!')

    return download_size

async def load_from_file(sem, session: aiohttp.ClientSession, fp: str):
    data = load_json(fp)
    data['posts'], data['posts_ids'] = await get_posts(sem, session, data['id'], post_ids=data['posts_ids'])
    return data

async def main():
    try:
        sem = asyncio.Semaphore(3)
        download_sem = asyncio.Semaphore(4)
        headers = {
            'User-Agent': UserAgent().firefox,
            'X-IG-App-ID': '936619743392459',
            'X-IG-WWW-Claim': '0',
            'X-Requested-With': 'XMLHttpRequest'
        }
        download_session = await setup_session()

        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                while True:
                    clear()
                    try:
                        data = None
                        username_input = input(f'{Fore.LIGHTYELLOW_EX}Enter a username (or url) to scrape: {Fore.RESET}')
                        
                        if username_input.lower().strip() == "file":
                            # Loads data from file
                            data = await load_from_file(sem, session, input(f'{Fore.LIGHTYELLOW_EX}Enter the file path (.json): {Fore.RESET}').strip())                           
                            username = data['username']
                        else:
                            username = get_username(username_input)
                            if not username:
                                print(f'"{Fore.LIGHTRED_EX}{username_input}{Fore.RESET}" is not valid!')
                                continue

                            # Get user data
                            data = await get_user(sem, session, username)
                            save_json(data, f'{username}_initial_prop.json')
                        
                        # Download user data
                        downloaded_count = await download_user(download_sem, download_session, data, DOWNLOAD_PATH)
                        
                        if downloaded_count > 0 and os.path.exists(f'{username}_initial_prop.json'):
                            try:
                                os.remove(f'{username}_initial_prop.json')
                                print(f'Cleaned up {username}_initial_prop.json')
                            except OSError as file_err:
                                print(f"Failed to delete temp file: {file_err}")
                    except KeyboardInterrupt:
                        print("Scraping interrupted by user.")
                        break
                    except Exception as e:
                        print(f'Something went wrong while scraping: {Fore.LIGHTRED_EX}{e}{Fore.RESET}')
                        break
                    finally:
                        input('Press Enter to continue...')
            finally:
                await download_session.close()
    except KeyboardInterrupt:
        print("\nProgram interrupted. Exiting gracefully...")
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
