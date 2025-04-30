# Standard libs
import os, json, re, asyncio

# Non standard libs ( pip install )
import aiofiles, PIL.Image, io

# Custom files
from config import linux

def broadcast_scanner_event(p: str):
    command = f'am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file://{p} >/dev/null 2>&1'
    return os.system(command)

def clear():
    os.system('clear' if linux else 'cls')

def load_json(fp: str):
    with open(fp, 'r', errors='ignore', encoding='utf-8') as file:
        return json.load(file)

def save_json(data, fp):
    with open(fp, 'w', errors='ignore', encoding='utf-8') as file:
        json.dump(data, file, indents=4, ensure_ascii=False)

def sanitize_filename(filename: str, replacement: str = '_', max_length: int = 100) -> str:
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
                print(f'Successfully Changed "{os.path.split(fp)[1]}" to "{file_type.upper()}"!')
            except:
                pass

        return new_filename if os.path.exists(new_filename) else fp
    except Exception as e:  
        print(f"Error converting \"{os.path.split(fp)[1]}\" to \"{file_type}\": {e}")

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

