import urllib.request
import json
import xml.etree.ElementTree as ET
import ssl

# Configuration
SITEMAP_FILE = "sitemap.xml"
API_KEY = "484713f1a8f647c3a41a395399edd71e"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
HOST = "tkmai.top"
KEY_LOCATION = f"https://{HOST}/{API_KEY}.txt"

def get_urls_from_sitemap(file_path):
    """Parses the sitemap.xml and returns a list of URLs."""
    urls = []
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Define namespace usually found in sitemaps
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        for url in root.findall('ns:url', namespace):
            loc = url.find('ns:loc', namespace)
            if loc is not None and loc.text:
                urls.append(loc.text.strip())
                
    except Exception as e:
        print(f"Error parsing sitemap: {e}")
        return []
    
    return urls

def push_to_indexnow(urls):
    """Pushes the list of URLs to IndexNow."""
    if not urls:
        print("No URLs found to push.")
        return

    data = {
        "host": HOST,
        "key": API_KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": urls
    }

    json_data = json.dumps(data).encode('utf-8')
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": len(json_data)
    }

    req = urllib.request.Request(INDEXNOW_ENDPOINT, data=json_data, headers=headers, method="POST")

    try:
        # Create a context that doesn't verify certificates if needed (optional, but standard usually works)
        # context = ssl._create_unverified_context() 
        with urllib.request.urlopen(req) as response:
            if response.status == 200 or response.status == 202:
                print(f"Successfully pushed {len(urls)} URLs to IndexNow.")
                print("Response code:", response.status)
            else:
                print(f"Failed to push URLs. Status code: {response.status}")
                print("Response:", response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} - {e.reason}")
        print(e.read().decode('utf-8'))
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    print(f"Reading URLs from {SITEMAP_FILE}...")
    urls = get_urls_from_sitemap(SITEMAP_FILE)
    
    if urls:
        print(f"Found {len(urls)} URLs.")
        print("Pushing to IndexNow...")
        push_to_indexnow(urls)
    else:
        print("No URLs found in sitemap.")
