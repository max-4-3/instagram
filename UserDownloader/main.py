import asyncio, json, random, os, warnings, random
from urllib.parse import urlparse

# Non Standard libs ( pip install -r requirments.txt )
import aiohttp
from rich import print

# Customs
from config import DOC_ID, DOWNLOAD_PATH, MEDIA_DETAIL_URL, USER_GRAPH_QL_URL
from functions import get_username, load_json, save_json, clear
from downloader import download_user
from objects import get_simplified_post
from session import download_session_maker, main_session

warnings.filterwarnings("ignore", "DeprecationWarning")

async def get(sem: asyncio.Semaphore, session: aiohttp.ClientSession, url: str, as_json: bool = True):
    async with sem:
        async with session.get(url) as response:
            try:
                response.raise_for_status()
                return await response.json() if as_json else await response.text()
            except:
                print(f'[{response.status}] Unable to retrive from url: {url}')
                return 

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
            print(f'{page}. Extracting posts from {user_id}...' if not total else f'{page}. Extracting posts from {user_id}... [{total} total, {len(posts)} scraped]')
            next_url = f"{MEDIA_DETAIL_URL}?doc_id={DOC_ID}&variables={json.dumps(variables)}"  # Originally it was "MEDIA_DETAIL_URL?query_id={MEDIA_QUERY_HASH}"
            response = await get(sem, session, next_url)

            if not response:
                print(f'\tManaged to extract {len(posts)} posts!'.expandtabs(2))
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
            print(f'\tExtracted {len(new_posts)} posts!'.expandtabs(2))
            page += 1

            if not has_next_page:
                print(f'\tManaged to extract {len(posts)} posts!'.expandtabs(2))
                break

            await asyncio.sleep(random.randint(1, 3) + random.random())
        except KeyboardInterrupt:
            break

    print(f'Analyzing scraped data...')
    return get_simplified_post(posts, old_post_ids=known_posts)

async def get_user(sem, session: aiohttp.ClientSession, username: str, all_posts: bool = True):
    
    print(f'Extracting user for username: {username}...')
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
        print(f"Extracting {user['total_posts']} posts for {user['fullname'] or user['username']}...")
        posts = await get_posts(sem, session, user['id'], total=user['total_posts'])
    else:
        posts = get_simplified_post(initial_edge.get('edges'))
    
    user['posts'], user['posts_ids'] = posts
    return user

async def load_from_file(sem, session: aiohttp.ClientSession, fp: str):
    data = load_json(fp)
    data['posts'], data['posts_ids'] = await get_posts(sem, session, data['id'], post_ids=data['posts_ids'])
    return data

async def main():
    try:
        sem = asyncio.Semaphore(3)
        download_sem = asyncio.Semaphore(4)
        
        async with main_session() as session:
            async with download_session_maker() as download_session:
                try:
                    while True:
                        clear()
                        try:
                            data = None
                            username_input = input(f'Enter a username (or url) to scrape: ')
                            
                            if username_input.lower().strip() == "file":
                                # Loads data from file
                                data = await load_from_file(sem, session, input(f'Enter the file path (.json): ').strip())                           
                                username = data['username']
                            else:
                                username = get_username(username_input)
                                if not username:
                                    print(f'"{username_input}" is not valid!')
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
                                except Exception as file_err:
                                    print(f"Failed to delete temp file: {file_err}")
                        except KeyboardInterrupt:
                            print("Scraping interrupted by user.")
                            break
                        except Exception as e:
                            print(f'Something went wrong while scraping: {e}')
                            break
                        finally:
                            input('Press Enter to continue...')
                finally:
                    pass
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
