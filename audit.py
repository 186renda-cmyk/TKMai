import os
import sys
import re
import json
import time
import concurrent.futures
from urllib.parse import urlparse, urljoin, unquote
from pathlib import Path
from collections import defaultdict, Counter

try:
    import requests
    from bs4 import BeautifulSoup
    from colorama import init, Fore, Style
except ImportError:
    print("Missing dependencies. Please run: pip install beautifulsoup4 requests colorama")
    sys.exit(1)

# Initialize colorama
init(autoreset=True)

class Config:
    def __init__(self):
        self.root_dir = Path.cwd()
        self.base_url = None
        self.keywords = []
        self.ignore_paths = {'.git', 'node_modules', '__pycache__', '.idea', '.vscode', 'venv', 'env'}
        self.ignore_url_prefixes = ('/go/', '/cdn-cgi/', 'javascript:', 'mailto:', 'tel:', '#')
        self.ignore_files_contain = ['google', '404.html']
        self.external_links = set()
        self.internal_pages = {} # path -> {title, h1_count, has_schema, has_breadcrumb, links, inbound_count}
        self.file_mapping = {} # relative_path_str -> absolute_path
        self.dead_links = [] # (source, href)
        self.warnings = [] # (source, message)
        self.score = 100

    def detect_config(self):
        index_path = self.root_dir / 'index.html'
        if index_path.exists():
            try:
                with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
                    soup = BeautifulSoup(f, 'html.parser')
                    
                    # Detect Base URL
                    canonical = soup.find('link', rel='canonical')
                    if canonical and canonical.get('href'):
                        self.base_url = canonical['href'].rstrip('/')
                    else:
                        og_url = soup.find('meta', property='og:url')
                        if og_url and og_url.get('content'):
                            self.base_url = og_url['content'].rstrip('/')
                        else:
                            print(f"{Fore.YELLOW}[WARN] Could not detect Base URL from index.html (canonical or og:url).")
                    
                    # Detect Keywords
                    meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
                    if meta_keywords and meta_keywords.get('content'):
                        self.keywords = [k.strip() for k in meta_keywords['content'].split(',')]
            except Exception as e:
                print(f"{Fore.RED}[ERROR] Failed to read index.html: {e}")

class Auditor:
    def __init__(self):
        self.config = Config()
        self.config.detect_config()
        self.files_to_scan = []

    def is_ignored_path(self, path):
        for part in path.parts:
            if part in self.config.ignore_paths:
                return True
        return False

    def is_ignored_file(self, filename):
        for keyword in self.config.ignore_files_contain:
            if keyword in filename:
                return True
        return False

    def scan_files(self):
        print(f"{Fore.CYAN}[INFO] Scanning files in {self.config.root_dir}...")
        for root, dirs, files in os.walk(self.config.root_dir):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if d not in self.config.ignore_paths]
            
            for file in files:
                if not file.endswith('.html'):
                    continue
                if self.is_ignored_file(file):
                    continue
                
                file_path = Path(root) / file
                if self.is_ignored_path(file_path):
                    continue
                
                self.files_to_scan.append(file_path)
                # Map relative path to absolute path for resolution
                rel_path = file_path.relative_to(self.config.root_dir)
                self.config.file_mapping[str(rel_path)] = file_path
                
                # Initialize page data
                self.config.internal_pages[str(file_path)] = {
                    'rel_path': str(rel_path),
                    'h1_count': 0,
                    'has_schema': False,
                    'has_breadcrumb': False,
                    'links': [],
                    'inbound_count': 0
                }

    def check_link_resolution(self, source_file, href):
        # 1. Check ignore list
        if href.startswith(self.config.ignore_url_prefixes):
            return

        # 2. External Links
        parsed = urlparse(href)
        if parsed.scheme in ('http', 'https'):
            # Check if it matches our base URL (internal link disguised as absolute)
            if self.config.base_url and href.startswith(self.config.base_url):
                # Treat as internal, strip domain
                path = href[len(self.config.base_url):]
                if not path: path = "/"
                self.check_internal_link(source_file, path, is_absolute_url=True)
            else:
                self.config.external_links.add(href)
            return

        # 3. Internal Links
        self.check_internal_link(source_file, href)

    def check_internal_link(self, source_file, href, is_absolute_url=False):
        # Remove query params and hash
        href_clean = href.split('#')[0].split('?')[0]
        if not href_clean:
            return

        # Warning: Absolute URL for internal link
        if is_absolute_url:
            self.config.warnings.append((str(source_file.relative_to(self.config.root_dir)), 
                                       f"Internal link using absolute URL: {href} (should be relative or root-relative)"))
            self.config.score -= 2

        # Warning: .html extension
        if href_clean.endswith('.html') or href_clean.endswith('.htm'):
             self.config.warnings.append((str(source_file.relative_to(self.config.root_dir)), 
                                        f"Link contains .html extension: {href} (should use Clean URL)"))
             self.config.score -= 2
        
        # Warning: Relative path usage (preference for root-relative /)
        if not href.startswith('/') and not is_absolute_url:
             self.config.warnings.append((str(source_file.relative_to(self.config.root_dir)), 
                                        f"Relative path used: {href} (recommend starting with /)"))
             self.config.score -= 2

        # Resolution Logic
        target_found = False
        
        # Determine potential file paths
        potential_paths = []
        
        if href_clean.startswith('/'):
            # Root relative
            path_part = href_clean.lstrip('/')
            # Case 1: /blog/post -> root/blog/post.html
            potential_paths.append(self.config.root_dir / f"{path_part}.html")
            # Case 2: /blog/post -> root/blog/post/index.html
            potential_paths.append(self.config.root_dir / path_part / "index.html")
            # Case 3: exact match (if it refers to a file like image or existing html)
            potential_paths.append(self.config.root_dir / path_part)
        else:
            # Relative to current file
            parent_dir = source_file.parent
            # Case 1: blog/post -> parent/blog/post.html
            potential_paths.append(parent_dir / f"{href_clean}.html")
            # Case 2: blog/post -> parent/blog/post/index.html
            potential_paths.append(parent_dir / href_clean / "index.html")
            # Case 3: exact match
            potential_paths.append(parent_dir / href_clean)

        target_file = None
        for p in potential_paths:
            if p.exists() and p.is_file():
                target_found = True
                target_file = p
                break
        
        if target_found:
            # Add to graph
            if str(target_file) in self.config.internal_pages:
                self.config.internal_pages[str(target_file)]['inbound_count'] += 1
        else:
            self.config.dead_links.append((str(source_file.relative_to(self.config.root_dir)), href))
            self.config.score -= 10

    def parse_content(self):
        print(f"{Fore.CYAN}[INFO] Parsing {len(self.files_to_scan)} files...")
        for file_path in self.files_to_scan:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    page_data = self.config.internal_pages[str(file_path)]
                    
                    # H1 Check
                    h1s = soup.find_all('h1')
                    page_data['h1_count'] = len(h1s)
                    if len(h1s) == 0:
                        self.config.warnings.append((page_data['rel_path'], "Missing H1 tag"))
                        self.config.score -= 5
                    elif len(h1s) > 1:
                        self.config.warnings.append((page_data['rel_path'], "Multiple H1 tags found"))
                        # Multiple H1 is less critical than missing, usually not penalized heavily in modern SEO but good to note
                    
                    # Schema Check
                    schemas = soup.find_all('script', type='application/ld+json')
                    if schemas:
                        page_data['has_schema'] = True
                    else:
                        self.config.warnings.append((page_data['rel_path'], "Missing Schema (application/ld+json)"))
                        self.config.score -= 2
                        
                    # Breadcrumb Check
                    # Check for aria-label="breadcrumb" or class="breadcrumb"
                    has_breadcrumb = False
                    if soup.find(attrs={"aria-label": "breadcrumb"}) or soup.find(class_=re.compile("breadcrumb", re.I)):
                        has_breadcrumb = True
                    page_data['has_breadcrumb'] = has_breadcrumb
                    
                    # Extract Links
                    for a in soup.find_all('a', href=True):
                        href = a['href'].strip()
                        self.check_link_resolution(file_path, href)
                        
            except Exception as e:
                print(f"{Fore.RED}[ERROR] Processing file {file_path}: {e}")

    def check_external_links_async(self):
        links = list(self.config.external_links)
        if not links:
            return

        print(f"{Fore.CYAN}[INFO] Checking {len(links)} external links (Async)...")
        
        def check_url(url):
            try:
                headers = {'User-Agent': 'SEOAuditBot/1.0'}
                response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                if response.status_code >= 400:
                    # Retry with GET just in case HEAD is blocked
                    response = requests.get(url, headers=headers, timeout=5, stream=True)
                    if response.status_code >= 400:
                        return url, response.status_code
                return url, 200
            except Exception:
                return url, 0 # Connection error

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {executor.submit(check_url, url): url for url in links}
            for future in concurrent.futures.as_completed(future_to_url):
                url, status = future.result()
                if status >= 400 or status == 0:
                    status_msg = str(status) if status > 0 else "Connection Error"
                    self.config.dead_links.append(("External", f"{url} (Status: {status_msg})"))
                    self.config.score -= 5

    def analyze_graph(self):
        # Orphans
        orphans = []
        for path, data in self.config.internal_pages.items():
            # Ignore index.html from orphan check
            if path.endswith('index.html'):
                continue
            if data['inbound_count'] == 0:
                orphans.append(data['rel_path'])
                self.config.warnings.append((data['rel_path'], "Orphan page (No inbound links)"))
                self.config.score -= 5
        
        # Top Pages
        sorted_pages = sorted(self.config.internal_pages.items(), key=lambda x: x[1]['inbound_count'], reverse=True)
        self.top_pages = sorted_pages[:10]

    def print_report(self):
        # Ensure score is not negative
        final_score = max(0, self.config.score)
        
        print("\n" + "="*60)
        print(f"{Style.BRIGHT}SEO AUDIT REPORT{Style.RESET_ALL}")
        print("="*60)
        
        # Configuration Info
        print(f"Base URL: {Fore.GREEN}{self.config.base_url or 'Not Detected'}")
        print(f"Files Scanned: {len(self.files_to_scan)}")
        print("-" * 60)

        # 1. Dead Links
        if self.config.dead_links:
            print(f"\n{Fore.RED}[ERROR] Dead Links Found ({len(self.config.dead_links)}):")
            for source, link in self.config.dead_links:
                print(f"  - In {Fore.YELLOW}{source}{Fore.RESET}: {Fore.RED}{link}")
        else:
            print(f"\n{Fore.GREEN}[SUCCESS] No dead links found.")

        # 2. Warnings (Semantics, URL structure, Orphans)
        if self.config.warnings:
            print(f"\n{Fore.YELLOW}[WARN] Issues Found ({len(self.config.warnings)}):")
            # Group by type to make it cleaner? For now just list
            # Limit output if too many
            limit = 20
            for source, msg in self.config.warnings[:limit]:
                print(f"  - {source}: {msg}")
            if len(self.config.warnings) > limit:
                print(f"  ... and {len(self.config.warnings) - limit} more warnings.")
        else:
            print(f"\n{Fore.GREEN}[SUCCESS] No warnings found.")

        # 3. Top Pages
        print(f"\n{Fore.BLUE}[INFO] Top Pages by Internal Links:")
        for path, data in self.top_pages:
            print(f"  - {data['rel_path']}: {data['inbound_count']} links")

        # 4. Final Score
        score_color = Fore.GREEN
        if final_score < 60: score_color = Fore.RED
        elif final_score < 90: score_color = Fore.YELLOW
        
        print("\n" + "="*60)
        print(f"FINAL SCORE: {score_color}{final_score}/100{Style.RESET_ALL}")
        print("="*60)
        
        if final_score < 100:
            print(f"{Fore.MAGENTA}Actionable Advice:{Fore.RESET}")
            print("Run 'python fix_links.py' (if available) or check the errors above manually.")

def main():
    start_time = time.time()
    auditor = Auditor()
    auditor.scan_files()
    auditor.parse_content()
    auditor.check_external_links_async()
    auditor.analyze_graph()
    auditor.print_report()
    print(f"\nAudit completed in {time.time() - start_time:.2f} seconds.")

if __name__ == "__main__":
    main()
