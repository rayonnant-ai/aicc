#!/usr/bin/env python3
"""
Download 100 Picture of the Day images from Wikimedia Commons.

Uses the MediaWiki API to fetch featured images.
Saves to images/ folder with attribution in LICENSES.txt.
"""
import urllib.request
import urllib.parse
import json
import os
import time
import re

IMG_DIR = 'images'
LICENSE_FILE = os.path.join(IMG_DIR, 'LICENSES.txt')
TARGET = 100
API_URL = 'https://commons.wikimedia.org/w/api.php'


def api_query(**params):
    """Query the MediaWiki API."""
    params['format'] = 'json'
    url = API_URL + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'LLMCompImageDownloader/1.0 (https://github.com/rrezel/llmcomp)'
    })
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get_potd_filenames(count=150):
    """Get Picture of the Day filenames from recent months."""
    filenames = []

    # Query the POTD template pages for recent dates
    # Use the categorymembers API to get files from the POTD categories
    for year in [2026, 2025, 2024, 2023]:
        for month in range(12, 0, -1):
            if len(filenames) >= count:
                break

            # Get POTD for each day of the month
            for day in range(1, 32):
                if len(filenames) >= count:
                    break

                date_str = f"{year}-{month:02d}-{day:02d}"
                title = f"Template:Potd/{date_str}"

                try:
                    data = api_query(
                        action='parse',
                        page=title,
                        prop='images',
                    )
                    if 'parse' in data and 'images' in data['parse']:
                        for img in data['parse']['images']:
                            if img.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                                filenames.append(('File:' + img, date_str))
                                break
                except Exception:
                    continue

                time.sleep(1.0)  # Be polite — Wikimedia rate limits aggressively

    return filenames[:count]


def get_image_info(filename):
    """Get image URL and license info."""
    data = api_query(
        action='query',
        titles=filename,
        prop='imageinfo',
        iiprop='url|extmetadata',
        iiurlwidth=512,
    )
    pages = data.get('query', {}).get('pages', {})
    for page_id, page in pages.items():
        if 'imageinfo' not in page:
            continue
        info = page['imageinfo'][0]
        thumb_url = info.get('thumburl', info.get('url', ''))
        meta = info.get('extmetadata', {})

        artist = meta.get('Artist', {}).get('value', 'Unknown')
        # Strip HTML tags from artist
        artist = re.sub(r'<[^>]+>', '', artist).strip()
        license_name = meta.get('LicenseShortName', {}).get('value', 'Unknown')
        description = meta.get('ImageDescription', {}).get('value', '')
        description = re.sub(r'<[^>]+>', '', description).strip()[:200]

        return {
            'url': thumb_url,
            'artist': artist,
            'license': license_name,
            'description': description,
            'filename': filename,
        }
    return None


def download_image(url, path):
    """Download an image to a local path."""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'LLMCompImageDownloader/1.0 (https://github.com/rrezel/llmcomp)'
    })
    with urllib.request.urlopen(req) as resp:
        with open(path, 'wb') as f:
            f.write(resp.read())


def main():
    os.makedirs(IMG_DIR, exist_ok=True)

    print(f"Fetching Picture of the Day filenames...")
    potd_files = get_potd_filenames(TARGET + 20)  # extra in case some fail
    print(f"Found {len(potd_files)} POTD entries")

    licenses = []
    # Count existing images to resume
    existing = len([f for f in os.listdir(IMG_DIR) if f.startswith('potd_') and not f.endswith('.txt')])
    downloaded = existing
    if existing:
        print(f"Resuming from {existing} existing images")

    for i, (filename, date_str) in enumerate(potd_files):
        if downloaded >= TARGET:
            break

        print(f"[{downloaded+1}/{TARGET}] {filename}...", end=' ', flush=True)

        try:
            info = get_image_info(filename)
            if not info or not info['url']:
                print("SKIP (no URL)")
                continue

            # Download
            ext = os.path.splitext(info['url'].split('?')[0])[1] or '.jpg'
            local_name = f"potd_{downloaded+1:03d}{ext}"
            local_path = os.path.join(IMG_DIR, local_name)

            download_image(info['url'], local_path)

            # Verify it's a real image
            size = os.path.getsize(local_path)
            if size < 1000:
                print(f"SKIP (too small: {size}b)")
                os.remove(local_path)
                continue

            licenses.append(
                f"{local_name}\n"
                f"  Source: https://commons.wikimedia.org/wiki/{urllib.parse.quote(filename)}\n"
                f"  POTD: {date_str}\n"
                f"  Artist: {info['artist']}\n"
                f"  License: {info['license']}\n"
                f"  Description: {info['description']}\n"
            )

            downloaded += 1
            print(f"OK ({size//1024}KB, {info['license']})")

        except Exception as e:
            print(f"ERROR: {e}")

        time.sleep(2.0)  # Be polite — Wikimedia rate limits aggressively

    # Write license file
    with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
        f.write("Image Attribution and Licenses\n")
        f.write("=" * 60 + "\n\n")
        f.write("All images sourced from Wikimedia Commons Picture of the Day.\n")
        f.write("https://commons.wikimedia.org/wiki/Commons:Picture_of_the_day\n\n")
        for entry in licenses:
            f.write(entry + "\n")

    print(f"\nDone. Downloaded {downloaded} images to {IMG_DIR}/")
    print(f"Licenses written to {LICENSE_FILE}")


if __name__ == '__main__':
    main()
