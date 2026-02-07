# PostDownloader
This small script downloads the post of instagram using graphql

## QuickStart
You must provide one (or more) instagram post url (with shortcode in them):
e.g.:
- https://www.instagram.com/p/DSrnazggfvy/
- https://www.instagram.com/p/DUGUXEJj0WB/

```bash
uv run main.py 'https://...' '...'
```

Options:
- `-s`          : No subdirectory (downloads the media in the `root_dir`)
- `-d` `<path>` : Sets the `root_dir` to `<path>`

## Requirments
- requests
