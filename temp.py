import json
from models import *
from rich.console import Console


def parse_post(raw_post):
    node = raw_post["node"]
    node_type = node["__typename"]

    liked_by = node.get("edge_liked_by", {})
    comments = node.get("edge_media_to_comment", {})

    tagged = node.get("edge_media_to_tagged_user", {}).get("edges", [])

    media = []
    match node_type:
        case "GraphImage":
            media.append(
                BaseGraphMedia(
                    url=node["display_url"],
                    width=node.get("dimensions", {}).get("width", 0),
                    height=node.get("dimensions", {}).get("height", 0)
                )
            )
        case "GraphVideo":
            media.append(
                BaseGraphMedia(
                    url=node["video_url"],
                    width=node.get("dimensions", {}).get("width", 0),
                    height=node.get("dimensions", {}).get("height", 0)
                )
            )
        case "GraphSidecar":
            for children_item in node.get("edge_sidecar_to_children", {}).get("edges", []):
                children = children_item["node"]
                children_type = children["__typename"]
                children_owner = BaseUser(
                    id=int(children["owner"]["id"]),
                    username=children["owner"]["username"],
                    pfp=None
                )
                match children_type:
                    case "GraphImage":
                        media.append(
                            SideCarMedia(
                                id=int(children["id"]),
                                shortcode=children["shortcode"],
                                is_video=False,
                                type=children_type,
                                url=children["display_url"],
                                width=children.get(
                                    "dimensions", {}).get("width", 0),
                                height=children.get(
                                    "dimensions", {}).get("height", 0),
                                owner=children_owner
                            )
                        )
                    case "GraphVideo":
                        media.append(
                            SideCarMedia(
                                id=int(children["id"]),
                                shortcode=children["shortcode"],
                                is_video=True,
                                type=children_type,
                                url=children["video_url"],
                                width=children.get(
                                    "dimensions", {}).get("width", 0),
                                height=children.get(
                                    "dimensions", {}).get("height", 0),
                                owner=children_owner

                            )
                        )
        case _:
            pass

    post = Post(
        id=int(node["id"]),
        type=node_type,
        shortcode=node["shortcode"],
        owner=BaseUser(**node["owner"]),
        title=node["edge_media_to_caption"]["edges"][0]["node"]["text"] if node["edge_media_to_caption"]["edges"] else "",
        timestamp=node["taken_at_timestamp"],
        likes=liked_by.get("count", 0),
        comments=comments.get("count", 0),
        thumbnail=node["thumbnail_src"],
        tagged_users=[
            TaggedUser(
                id=int(tagged_user["node"]["user"]["id"]),
                username=tagged_user["node"]["user"]["username"],
                full_name=tagged_user["node"]["user"]["full_name"],
                pfp=PFP(
                    pic=tagged_user["node"].get(
                        "user", {}).get("profile_pic_url", ""),
                    hd=tagged_user["node"].get("user", {}).get(
                        "profile_pic_url_hd", tagged_user["node"].get("user", {}).get("profile_pic_url", ""))
                )
            )
            for tagged_user in tagged
            if tagged_user and tagged_user not in [None, {}] and isinstance(tagged_user, dict)
        ],
        media=media
    )

    return post


def get_owner(data):
    followed_by = data.get("edge_followed_by", {})
    follow = data.get("edge_follow", {})

    owner = Owner(
        id=int(data["id"]),
        fb_id=int(data["id"]),
        eimu_id=int(data["eimu_id"]),
        username=data["username"],
        fullname=data["full_name"],
        bio=data["biography"],
        bio_links=[
            BioLink(
                url=link["url"],
                title=link["title"],
                type=link.get("link_type", "external")
            )
            for link in data.get("external_url_links", data.get("bio_links", []))
            if link not in [None, {}]
        ],

        followers=followed_by.get("count", 0),
        following=follow.get("count", 0),

        is_private=data["is_private"],
        is_verified=data["is_verified"],

        pfp=PFP(
            pic=data["profile_pic_url"],
            hd=data.get("profile_pic_url_hd", data["profile_pic_url"])
        ),
        pronouns=data.get("pronouns", []),
        posts_count=data.get(
            "edge_owner_to_timeline_media", {}).get("count", 0),
        bussiness_email=data.get("business_email", None),
        bussiness_phone=data.get("business_phone_number", None),
    )

    return owner


with open("./save_path/official_kareena_17_posts.json", "r") as file:
    data = json.load(file)
    console = Console()
    console.print(type(data))
    for d in data:
        console.print(parse_post(d))
        console.input("Press enter to continue...")
        console.clear()
