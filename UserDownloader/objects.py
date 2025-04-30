# Standard libs
import os

# Custom files
from functions import save_json

def get_simplified_post(items: list[dict], old_post_ids: list | None = None):
    print(f'Analyzing {len(items)} posts...')
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

    print(f'Data analyzed, Caught {errors} errors!')
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
