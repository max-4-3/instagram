import os

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
DOWNLOAD_PATH = os.path.join(DOWNLOAD_PATH_BASE, "Downloads" if not android else "Download", "Instagram", "Users")