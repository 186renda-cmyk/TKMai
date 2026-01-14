import os
from datetime import datetime

# Configuration
BASE_URL = "https://tkmai.top"
ROOT_DIR = "."
SITEMAP_FILE = "sitemap.xml"

# Function to generate URL entry
def generate_url_entry(loc, priority="0.8", changefreq="weekly"):
    lastmod = datetime.now().strftime("%Y-%m-%d")
    return f"""    <url>
        <loc>{loc}</loc>
        <lastmod>{lastmod}</lastmod>
        <changefreq>{changefreq}</changefreq>
        <priority>{priority}</priority>
    </url>"""

# Collect URLs
urls = []

# 1. Root
urls.append(generate_url_entry(f"{BASE_URL}/", priority="1.0", changefreq="daily"))

# 2. Blog
if os.path.exists("blog"):
    # Blog Index
    if os.path.exists("blog/index.html"):
        urls.append(generate_url_entry(f"{BASE_URL}/blog/", priority="0.9", changefreq="daily"))
    
    # Blog Posts
    for filename in os.listdir("blog"):
        if filename.endswith(".html") and filename != "index.html":
            urls.append(generate_url_entry(f"{BASE_URL}/blog/{filename}", priority="0.8"))

# 3. Legal
if os.path.exists("legal"):
    for filename in os.listdir("legal"):
        if filename.endswith(".html"):
            urls.append(generate_url_entry(f"{BASE_URL}/legal/{filename}", priority="0.5", changefreq="monthly"))

# Generate Content
sitemap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>"""

# Write to file
with open(SITEMAP_FILE, "w", encoding="utf-8") as f:
    f.write(sitemap_content)

print(f"Sitemap updated with {len(urls)} URLs.")
