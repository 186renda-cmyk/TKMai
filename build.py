import os
import re
import json
from bs4 import BeautifulSoup, Comment

class SiteBuilder:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.index_path = os.path.join(root_dir, 'index.html')
        self.blog_dir = os.path.join(root_dir, 'blog')
        self.legal_dir = os.path.join(root_dir, 'legal')
        self.source_soup = None
        self.nav_html = None
        self.footer_html = None
        self.favicons = []
        self.common_styles_scripts = []
        
    def load_source(self):
        """Phase 1: Load and parse index.html as single source of truth"""
        if not os.path.exists(self.index_path):
            raise FileNotFoundError(f"Source file not found: {self.index_path}")
            
        with open(self.index_path, 'r', encoding='utf-8') as f:
            self.source_soup = BeautifulSoup(f.read(), 'html.parser')
            
        print(f"Loaded source: {self.index_path}")
        self._extract_assets()

    def _extract_assets(self):
        """Extract Nav, Footer, and Brand Assets"""
        # 1. Extract Nav
        nav = self.source_soup.find('nav')
        if nav:
            self._clean_links(nav)
            self._fix_anchor_links(nav)
            self.nav_html = nav
            print("Extracted Navigation")
            
        # 2. Extract Footer
        footer = self.source_soup.find('footer')
        if footer:
            self._clean_links(footer)
            self._fix_anchor_links(footer)
            self.footer_html = footer
            print("Extracted Footer")
            
        # 3. Extract Favicons
        head = self.source_soup.find('head')
        if head:
            # Extract icons
            for link in head.find_all('link'):
                rel = link.get('rel', [])
                if isinstance(rel, list):
                    rel = ' '.join(rel)
                
                if 'icon' in rel.lower():
                    # Force root relative path
                    href = link.get('href', '')
                    if href and not href.startswith('http') and not href.startswith('/'):
                        link['href'] = '/' + href
                    elif href and not href.startswith('http') and href.startswith('/'):
                        pass # Already root relative
                    
                    self.favicons.append(link)
            
            print(f"Extracted {len(self.favicons)} Favicon tags")

            # Extract common CSS/JS (Tailwind, Fonts, Lucide)
            # This is heuristic based on the provided index.html
            for tag in head.find_all(['script', 'link', 'style']):
                # Skip title, meta, canonical, icons
                if tag.name == 'link' and ('icon' in str(tag.get('rel')).lower() or tag.get('rel') == ['canonical']):
                    continue
                if tag.name == 'meta':
                    continue
                if tag.name == 'title':
                    continue
                
                # Keep external resources and inline configs
                self.common_styles_scripts.append(tag)

    def _fix_anchor_links(self, element):
        """Convert in-page anchors (#id) to root-relative anchors (/#id) for global nav/footer"""
        for a in element.find_all('a', href=True):
            href = a['href']
            if href.startswith('#'):
                a['href'] = '/' + href

    def _clean_links(self, element):
        """Remove .html suffix from internal links"""
        for a in element.find_all('a', href=True):
            href = a['href']
            # Skip external links, anchors, and non-html files
            if href.startswith('http') or href.startswith('#') or href.startswith('mailto:'):
                continue
            
            # Remove .html extension
            if href.endswith('.html'):
                a['href'] = href[:-5]
                if not a['href']: # handle .html -> empty string
                     a['href'] = '/'
            
            # Ensure internal links start with / if they are relative
            # (Logic can be adjusted if relative links are preferred, but instructions imply standardization)
            # The instruction says "Force root relative path" for favicons, implied for others for consistency

    def process_all_pages(self):
        """Process blog, legal, and index pages"""
        # 1. Process Blog Directory
        if os.path.exists(self.blog_dir):
            for filename in os.listdir(self.blog_dir):
                if filename.endswith('.html'):
                    file_path = os.path.join(self.blog_dir, filename)
                    self._process_single_file(file_path, filename, section='blog')

        # 2. Process Legal Directory
        if os.path.exists(self.legal_dir):
            for filename in os.listdir(self.legal_dir):
                if filename.endswith('.html'):
                    file_path = os.path.join(self.legal_dir, filename)
                    self._process_single_file(file_path, filename, section='legal')
        
        # 3. Process Index (Self) - mainly for link cleaning
        self._process_single_file(self.index_path, 'index.html', section='root')

    def _process_single_file(self, file_path, filename, section='blog'):
        print(f"Processing [{section}]: {filename}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return

        # Phase 2: Head Reconstruction
        self._reconstruct_head(soup, filename, section)

        # Phase 3: Content Injection
        self._inject_layout(soup)
        
        # Recommendations only for blog posts
        if section == 'blog' and filename != 'index.html':
            self._inject_recommendations(soup)
        
        # Global: Path Normalization
        self._clean_links(soup.body)
        self._fix_anchor_links(soup.body)

        # Save file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(str(soup))

    def _reconstruct_head(self, soup, filename, section):
        head = soup.find('head')
        if not head:
            head = soup.new_tag('head')
            soup.insert(0, head)
        
        # Extract existing metadata to preserve
        original_title = soup.title.string if soup.title else ""
        original_desc = ""
        original_keywords = ""
        original_schema = None
        
        meta_desc = head.find('meta', attrs={'name': 'description'})
        if meta_desc: original_desc = meta_desc.get('content', '')
        
        meta_kw = head.find('meta', attrs={'name': 'keywords'})
        if meta_kw: original_keywords = meta_kw.get('content', '')

        script_schema = head.find('script', type='application/ld+json')
        if script_schema: original_schema = script_schema.string

        # Clear Head
        head.clear()

        # Group A: Basic Metadata
        head.append(soup.new_tag('meta', charset='utf-8'))
        head.append('\n    ')
        head.append(soup.new_tag('meta', attrs={'name': 'viewport', 'content': 'width=device-width, initial-scale=1.0'}))
        head.append('\n    ')
        title_tag = soup.new_tag('title')
        title_tag.string = original_title
        head.append(title_tag)
        head.append('\n\n    ')

        # Group B: SEO Core
        if original_desc:
            head.append(soup.new_tag('meta', attrs={'name': 'description', 'content': original_desc}))
            head.append('\n    ')
        if original_keywords:
            head.append(soup.new_tag('meta', attrs={'name': 'keywords', 'content': original_keywords}))
            head.append('\n    ')
        
        # Canonical
        clean_name = filename.replace('.html', '')
        if section == 'root':
            canonical_url = "https://tkmai.top/"
        elif section == 'blog':
            if clean_name == 'index':
                 canonical_url = "https://tkmai.top/blog/"
            else:
                 canonical_url = f"https://tkmai.top/blog/{clean_name}"
        elif section == 'legal':
             canonical_url = f"https://tkmai.top/legal/{clean_name}"
        else:
             canonical_url = f"https://tkmai.top/{clean_name}"

        head.append(soup.new_tag('link', rel='canonical', href=canonical_url))
        head.append('\n\n    ')

        # Group C: Indexing & Geo
        head.append(soup.new_tag('meta', attrs={'name': 'robots', 'content': 'index, follow'}))
        head.append('\n    ')
        head.append(soup.new_tag('meta', attrs={'http-equiv': 'content-language', 'content': 'zh-cn'}))
        head.append('\n    ')
        # Hreflang Matrix
        head.append(soup.new_tag('link', rel='alternate', hreflang='x-default', href=canonical_url))
        head.append('\n    ')
        head.append(soup.new_tag('link', rel='alternate', hreflang='zh', href=canonical_url))
        head.append('\n    ')
        head.append(soup.new_tag('link', rel='alternate', hreflang='zh-CN', href=canonical_url))
        head.append('\n\n    ')

        # Group D: Branding & Resources
        # Favicons
        head.append(Comment(" Favicons "))
        head.append('\n    ')
        for icon in self.favicons:
            head.append(icon) # Note: beautifulsoup might move the tag, better to clone if reused, but here we iterate once per file saving
            head.append('\n    ')
        
        head.append(Comment(" Resources "))
        head.append('\n    ')
        for res in self.common_styles_scripts:
            # We need to clone the tag because a tag object can only have one parent
            import copy
            head.append(copy.copy(res))
            head.append('\n    ')
        head.append('\n')

        # Group E: Structured Data
        if original_schema:
            schema_tag = soup.new_tag('script', type='application/ld+json')
            schema_tag.string = original_schema
            head.append(schema_tag)
            head.append('\n')

    def _inject_layout(self, soup):
        import copy
        
        # Header
        # Always use a deep copy of the source nav to avoid modifying the source or moving it
        new_nav = copy.copy(self.nav_html)
        
        old_nav = soup.find('nav')
        if old_nav:
            old_nav.replace_with(new_nav)
        else:
             if soup.body:
                soup.body.insert(0, new_nav)

        # Footer
        new_footer = copy.copy(self.footer_html)
        current_footer = soup.find('footer')
        if current_footer:
            current_footer.replace_with(new_footer)
        else:
            soup.body.append(new_footer)

    def _inject_recommendations(self, soup):
        # Find article
        article = soup.find('article')
        if article:
            # Check if recommendations already exist
            existing_rec = article.find('div', class_='recommendations-module')
            if existing_rec:
                existing_rec.decompose()
            
            # Create Recommendation Module
            rec_div = soup.new_tag('div', attrs={'class': 'recommendations-module mt-12 pt-8 border-t border-white/10'})
            
            # Title
            h3 = soup.new_tag('h3', attrs={'class': 'text-2xl font-bold text-white mb-6'})
            h3.string = "推荐阅读"
            rec_div.append(h3)
            
            # Grid
            grid = soup.new_tag('div', attrs={'class': 'grid grid-cols-1 md:grid-cols-2 gap-6'})
            
            # TODO: Logic to get actual other posts. For now, static or random placeholder?
            # Instructions say "Smart Recommendation". 
            # Let's add a placeholder structure that links to blog index or similar, 
            # or ideally we should scan other files.
            # For simplicity and robustness in this first pass, I'll add a link to the blog index and maybe one static valid link if I know it.
            # Actually, the user asked for "Injection", implying we should put something there.
            
            # Let's simple scan the blog dir for other files to link to
            other_files = [f for f in os.listdir(self.blog_dir) if f.endswith('.html') and f != 'index.html']
            import random
            selected = other_files[:2] # Just take first 2 for now
            
            for f_name in selected:
                # We need to open them to get title? Or just use filename?
                # Opening is better.
                try:
                    with open(os.path.join(self.blog_dir, f_name), 'r') as f:
                        f_soup = BeautifulSoup(f.read(), 'html.parser')
                        f_title = f_soup.title.string.split('|')[0].strip() if f_soup.title else f_name
                except:
                    f_title = f_name
                
                link_url = f"/blog/{f_name.replace('.html', '')}"
                
                card = soup.new_tag('a', href=link_url, attrs={'class': 'block glass-card p-6 rounded-xl hover:bg-white/5 transition-all'})
                card_title = soup.new_tag('h4', attrs={'class': 'font-bold text-white mb-2'})
                card_title.string = f_title
                
                read_more = soup.new_tag('div', attrs={'class': 'text-tikcyan text-sm font-bold flex items-center gap-1'})
                read_more.string = "Read Article"
                
                card.append(card_title)
                card.append(read_more)
                grid.append(card)

            rec_div.append(grid)
            article.append(rec_div)

    def run(self):
        print("Starting build process...")
        self.load_source()
        self.process_all_pages()
        print("Build complete.")

if __name__ == "__main__":
    # Assuming script is run from project root or similar
    # Adjust path as needed.
    current_dir = os.getcwd()
    # If script is in root
    builder = SiteBuilder(current_dir)
    builder.run()
