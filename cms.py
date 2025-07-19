#!/usr/bin/env python3
"""
Enhanced Blog CMS Script for The Bandar Breakdowns
A robust content management system for creating and managing blog posts.
"""

import os
import re
import json
import shutil
import logging
import argparse
import datetime
import textwrap
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from dataclasses import dataclass, asdict
import hashlib
from html.parser import HTMLParser

# --- CONFIGURATION ---
@dataclass
class Config:
    """Configuration settings for the CMS."""
    blog_dir: str = "blog"
    templates_dir: str = "templates"
    backup_dir: str = "backups"
    metadata_file: str = "posts_metadata.json"
    base_url: str = "https://bandar-breakdowns.vercel.app"

    # Template files
    article_template: str = "templates/_template_article.html"
    poster_template: str = "templates/_template_poster.html"
    video_template: str = "templates/_template_video.html"

    # Post types
    post_types: List[str] = None

    # Series categories
    series_categories: Dict[str, str] = None

    def __post_init__(self):
        if self.post_types is None:
            self.post_types = ['Article', 'Poster', 'Video']

        if self.series_categories is None:
            self.series_categories = {
                'after_hours': 'After Hours',
                'cram_and_cry': 'Cram & Cry Corners',
                'food_for_heartbreak': 'Food for the Broken Hearted',
                'stressed_depressed': 'Stressed, Depressed, & Touching Grass',
                'commute_crisis': 'The Great Commute Crisis'
            }

# --- HTML PARSER CLASS ---
class BlogPostParser(HTMLParser):
    """HTML parser to extract metadata from existing blog posts."""

    def __init__(self):
        super().__init__()
        self.meta_tags = {}
        self.title = ""
        self.author = ""
        self.post_date = ""
        self.content = ""
        self.youtube_id = ""
        self.series = ""
        self.current_tag = ""
        self.in_title = False
        self.in_author = False
        self.in_date = False
        self.in_content = False
        self.content_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        # Extract meta tags
        if tag == 'meta':
            name = attrs_dict.get('name', '')
            property_val = attrs_dict.get('property', '')
            content = attrs_dict.get('content', '')

            if name:
                self.meta_tags[name] = content
            elif property_val:
                self.meta_tags[property_val] = content

        # Extract title
        elif tag == 'title':
            self.in_title = True

        # Look for author in post meta
        elif tag == 'span' and attrs_dict.get('class') == 'post-author':
            self.in_author = True

        # Look for date in post meta
        elif tag == 'span' and attrs_dict.get('class') == 'post-date':
            self.in_date = True

        # Look for main content areas
        elif tag == 'div' and 'article-content' in attrs_dict.get('class', ''):
            self.in_content = True
            self.content_depth = 1
        elif tag == 'div' and 'video-container' in attrs_dict.get('class', ''):
            self.in_content = True
            self.content_depth = 1
        elif tag == 'div' and 'poster-container' in attrs_dict.get('class', ''):
            self.in_content = True
            self.content_depth = 1

        # Look for YouTube embeds
        elif tag == 'iframe' and 'youtube.com/embed/' in attrs_dict.get('src', ''):
            src = attrs_dict.get('src', '')
            match = re.search(r'youtube\.com/embed/([a-zA-Z0-9_-]+)', src)
            if match:
                self.youtube_id = match.group(1)

        # Track content depth
        elif self.in_content and tag == 'div':
            self.content_depth += 1

        self.current_tag = tag

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        elif tag == 'span' and self.in_author:
            self.in_author = False
        elif tag == 'span' and self.in_date:
            self.in_date = False
        elif tag == 'div' and self.in_content:
            self.content_depth -= 1
            if self.content_depth <= 0:
                self.in_content = False

        self.current_tag = ""

    def handle_data(self, data):
        data = data.strip()
        if not data:
            return

        if self.in_title:
            self.title += data
        elif self.in_author:
            self.author += data
        elif self.in_date:
            self.post_date += data
        elif self.in_content:
            self.content += data + " "

# --- LOGGING SETUP ---
def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Set up logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('cms.log')
        ]
    )
    return logging.getLogger(__name__)

# --- UTILITY FUNCTIONS ---
def print_header(title: str, width: int = 80) -> None:
    """Print a formatted header."""
    print("\n" + "="*width)
    print(f"   {title}".center(width))
    print("="*width)

def print_separator(width: int = 80) -> None:
    """Print a separator line."""
    print("-" * width)

def print_success(message: str) -> None:
    """Print a success message."""
    print(f"\n✅ {message}")

def print_error(message: str) -> None:
    """Print an error message."""
    print(f"\n❌ {message}")

def print_warning(message: str) -> None:
    """Print a warning message."""
    print(f"\n⚠️  {message}")

def print_info(message: str) -> None:
    """Print an info message."""
    print(f"\nℹ️  {message}")

def get_user_choice(prompt: str, valid_choices: List[str]) -> str:
    """Get user choice with validation."""
    while True:
        choice = input(f"{prompt}: ").strip().lower()
        if choice in [c.lower() for c in valid_choices]:
            return choice
        print_error(f"Invalid choice. Please select from: {', '.join(valid_choices)}")

def confirm_action(message: str) -> bool:
    """Get user confirmation."""
    return get_user_choice(f"{message} (y/n)", ['y', 'n']) == 'y'

# --- DATA CLASSES ---
@dataclass
class PostMetadata:
    """Metadata for a blog post."""
    slug: str
    title: str
    author: str
    post_type: str
    description: str
    keywords: str
    image_url: str
    series: str = ""  # NEW: Series category
    youtube_id: str = ""
    created_date: str = ""
    modified_date: str = ""
    published: bool = True
    view_count: int = 0
    file_hash: str = ""
    indexed_from_file: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'PostMetadata':
        """Create from dictionary."""
        # Handle backwards compatibility for posts without series
        if 'series' not in data:
            data['series'] = ''
        return cls(**data)

# --- MAIN CMS CLASS ---
class BlogCMS:
    """Enhanced Blog Content Management System."""

    def __init__(self, config: Config):
        self.config = config
        self.logger = setup_logging()
        self.metadata_cache: Dict[str, PostMetadata] = {}
        self._ensure_directories()

        # Check if this is first run and offer to index
        if not Path(self.config.metadata_file).exists():
            self._handle_first_run()
        else:
            self._load_metadata()

    def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        directories = [
            self.config.blog_dir,
            self.config.templates_dir,
            self.config.backup_dir
        ]

        for directory in directories:
            Path(directory).mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Ensured directory exists: {directory}")

    def _handle_first_run(self) -> None:
        """Handle first run - offer to index existing files."""
        print_header("🔍 FIRST RUN DETECTED")
        print("No metadata file found. This appears to be your first time running the CMS.")

        # Check if there are existing HTML files
        blog_path = Path(self.config.blog_dir)
        if blog_path.exists():
            html_files = list(blog_path.glob("*.html"))
            html_files = [f for f in html_files if f.name != "index.html"]

            if html_files:
                print(f"\n🔍 Found {len(html_files)} existing HTML files in the blog directory:")
                for file in html_files[:5]:  # Show first 5
                    print(f"   • {file.name}")
                if len(html_files) > 5:
                    print(f"   ... and {len(html_files) - 5} more")

                print("\n💡 I can automatically index these files to create metadata for them.")
                print("This will allow you to manage them with this CMS.")

                if confirm_action("Would you like to index existing files?"):
                    self.index_existing_files()
                else:
                    print_info("Skipping indexing. Creating empty metadata file.")
                    self._save_metadata()
            else:
                print_info("No existing HTML files found. Creating empty metadata file.")
                self._save_metadata()
        else:
            print_info("Blog directory not found. Creating empty metadata file.")
            self._save_metadata()

    def _load_metadata(self) -> None:
        """Load posts metadata from JSON file."""
        metadata_path = Path(self.config.metadata_file)

        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.metadata_cache = {
                        slug: PostMetadata.from_dict(post_data)
                        for slug, post_data in data.items()
                    }
                self.logger.info(f"Loaded {len(self.metadata_cache)} posts from metadata")
            except (json.JSONDecodeError, KeyError) as e:
                self.logger.error(f"Error loading metadata: {e}")
                self.metadata_cache = {}
        else:
            self.logger.info("No existing metadata file found")

    def _save_metadata(self) -> None:
        """Save posts metadata to JSON file."""
        try:
            data = {
                slug: post.to_dict()
                for slug, post in self.metadata_cache.items()
            }

            with open(self.config.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self.logger.info("Metadata saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving metadata: {e}")

    def detect_series_from_content(self, title: str, content: str, keywords: str) -> str:
        """Detect series from content using keywords and patterns."""
        text_to_search = f"{title} {content} {keywords}".lower()

        # Define patterns for each series
        series_patterns = {
            'after_hours': ['night', 'evening', 'late', 'pasar malam', 'after hours', 'nightlife'],
            'cram_and_cry': ['study', 'cram', 'cafe', 'coffee', 'library', 'exam', 'studying'],
            'food_for_heartbreak': ['food', 'eat', 'heartbreak', 'comfort', 'restaurant', 'meal'],
            'stressed_depressed': ['stress', 'depression', 'mental health', 'overwhelm', 'crisis', 'burnout'],
            'commute_crisis': ['commute', 'transport', 'bus', 'train', 'travel', 'journey', 'brt']
        }

        # Score each series based on keyword matches
        series_scores = {}
        for series, patterns in series_patterns.items():
            score = sum(1 for pattern in patterns if pattern in text_to_search)
            if score > 0:
                series_scores[series] = score

        # Return the series with highest score, or empty string if no matches
        if series_scores:
            return max(series_scores, key=series_scores.get)

        return ""

    def parse_html_file(self, filepath: Path) -> Optional[PostMetadata]:
        """Parse an HTML file to extract metadata."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            parser = BlogPostParser()
            parser.feed(content)

            # Extract slug from filename
            slug = filepath.stem

            # Clean up title (remove site name)
            title = parser.title.replace(" - The Bandar Breakdowns", "").strip()

            # Determine post type from content structure
            post_type = "Article"  # default
            if "poster-container" in content:
                post_type = "Poster"
            elif "video-container" in content or parser.youtube_id:
                post_type = "Video"
            elif "article-content" in content:
                post_type = "Article"

            # Extract metadata with fallbacks
            description = (
                parser.meta_tags.get('description', '') or
                parser.meta_tags.get('og:description', '') or
                parser.content[:200] + "..." if len(parser.content) > 200 else parser.content
            )

            keywords = parser.meta_tags.get('keywords', 'bandar sunway, blog')

            image_url = (
                    parser.meta_tags.get('og:image', '') or
                    parser.meta_tags.get('twitter:image', '') or
                    'https://via.placeholder.com/800x400/cccccc/000000?text=No+Image'
            )

            author = parser.author or "The Team"

            # Parse date
            created_date = ""
            if parser.post_date:
                try:
                    # Try to parse different date formats
                    for fmt in ["%b %d, %Y", "%B %d, %Y", "%d %b %Y"]:
                        try:
                            date_obj = datetime.datetime.strptime(parser.post_date, fmt)
                            created_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
                            break
                        except ValueError:
                            continue
                except:
                    pass

            # Use file modification time if no date found
            if not created_date:
                mod_time = filepath.stat().st_mtime
                created_date = datetime.datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M:%S")

            # Detect series from content
            series = self.detect_series_from_content(title, parser.content, keywords)

            # Calculate file hash
            file_hash = hashlib.md5(content.encode()).hexdigest()

            metadata = PostMetadata(
                slug=slug,
                title=title or f"Untitled ({slug})",
                author=author,
                post_type=post_type,
                description=description,
                keywords=keywords,
                image_url=image_url,
                series=series,
                youtube_id=parser.youtube_id,
                created_date=created_date,
                modified_date=created_date,
                published=True,
                file_hash=file_hash,
                indexed_from_file=True
            )

            return metadata

        except Exception as e:
            self.logger.error(f"Error parsing {filepath}: {e}")
            return None

    def index_existing_files(self) -> None:
        """Index existing HTML files in the blog directory."""
        print_header("🔍 INDEXING EXISTING FILES")

        blog_path = Path(self.config.blog_dir)
        if not blog_path.exists():
            print_error("Blog directory not found")
            return

        html_files = list(blog_path.glob("*.html"))
        html_files = [f for f in html_files if f.name != "index.html"]

        if not html_files:
            print_info("No HTML files found to index")
            return

        print(f"📁 Found {len(html_files)} files to index...")

        indexed_count = 0
        skipped_count = 0
        error_count = 0

        for file_path in html_files:
            print(f"🔍 Processing: {file_path.name}")

            slug = file_path.stem

            # Skip if already in metadata
            if slug in self.metadata_cache:
                print(f"   ⏭️  Already indexed, skipping")
                skipped_count += 1
                continue

            # Parse the file
            metadata = self.parse_html_file(file_path)

            if metadata:
                self.metadata_cache[slug] = metadata
                series_info = f" | Series: {self.config.series_categories.get(metadata.series, 'None')}" if metadata.series else ""
                print(f"   ✅ Indexed: {metadata.title} ({metadata.post_type}){series_info}")
                indexed_count += 1
            else:
                print(f"   ❌ Failed to parse")
                error_count += 1

        # Save metadata
        if indexed_count > 0:
            self._save_metadata()

        # Show summary
        print_separator()
        print(f"📊 Indexing Complete:")
        print(f"   ✅ Successfully indexed: {indexed_count}")
        print(f"   ⏭️  Skipped (already indexed): {skipped_count}")
        print(f"   ❌ Errors: {error_count}")

        if indexed_count > 0:
            print_success(f"Successfully indexed {indexed_count} files!")
            print("You can now manage these posts with the CMS.")

    def reindex_files(self) -> None:
        """Re-index all files, updating existing metadata."""
        print_header("🔄 RE-INDEXING ALL FILES")

        if not confirm_action("This will update metadata for all files. Continue?"):
            print_info("Re-indexing cancelled")
            return

        # Create backup of current metadata
        backup_path = f"{self.config.metadata_file}.backup.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if Path(self.config.metadata_file).exists():
            shutil.copy2(self.config.metadata_file, backup_path)
            print_info(f"Created metadata backup: {backup_path}")

        # Clear current metadata for indexed files
        original_metadata = self.metadata_cache.copy()

        blog_path = Path(self.config.blog_dir)
        html_files = list(blog_path.glob("*.html"))
        html_files = [f for f in html_files if f.name != "index.html"]

        print(f"📁 Re-indexing {len(html_files)} files...")

        updated_count = 0
        error_count = 0

        for file_path in html_files:
            print(f"🔄 Processing: {file_path.name}")

            slug = file_path.stem
            metadata = self.parse_html_file(file_path)

            if metadata:
                # Preserve some original metadata if it exists
                if slug in original_metadata:
                    original = original_metadata[slug]
                    # Preserve view count and manual modifications
                    metadata.view_count = original.view_count
                    if not original.indexed_from_file:
                        # This was manually created, preserve more data
                        metadata.created_date = original.created_date
                        metadata.author = original.author
                        metadata.series = original.series  # Preserve manual series selection

                self.metadata_cache[slug] = metadata
                print(f"   ✅ Updated: {metadata.title}")
                updated_count += 1
            else:
                print(f"   ❌ Failed to parse")
                error_count += 1

        # Save updated metadata
        if updated_count > 0:
            self._save_metadata()

        print_separator()
        print(f"📊 Re-indexing Complete:")
        print(f"   ✅ Successfully updated: {updated_count}")
        print(f"   ❌ Errors: {error_count}")

        if updated_count > 0:
            print_success(f"Successfully re-indexed {updated_count} files!")

    def create_slug(self, title: str) -> str:
        """Generate a URL-friendly slug from title."""
        slug = title.lower().strip()
        slug = re.sub(r'[\s]+', '-', slug)
        slug = re.sub(r'[^\w\-]+', '', slug)
        slug = re.sub(r'\-\-+', '-', slug)
        slug = slug.strip('-')

        # Ensure uniqueness
        original_slug = slug
        counter = 1
        while slug in self.metadata_cache:
            slug = f"{original_slug}-{counter}"
            counter += 1

        return slug

    def validate_url(self, url: str) -> bool:
        """Validate URL format."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

    def validate_youtube_id(self, youtube_id: str) -> bool:
        """Validate YouTube video ID format."""
        pattern = r'^[a-zA-Z0-9_-]{11}$'
        return bool(re.match(pattern, youtube_id))

    def get_user_input(self, edit_post: Optional[PostMetadata] = None) -> Tuple[PostMetadata, str]:
        """Gather post data from user input with validation."""
        print_header("BLOG POST CREATOR" if not edit_post else "EDIT BLOG POST")

        # Post type selection
        if not edit_post:
            print("\n📝 Select post type:")
            for i, post_type in enumerate(self.config.post_types, 1):
                print(f"   {i}. {post_type}")

            while True:
                try:
                    choice = int(input(f"\nEnter your choice (1-{len(self.config.post_types)}): ").strip())
                    if 1 <= choice <= len(self.config.post_types):
                        post_type = self.config.post_types[choice - 1]
                        break
                    else:
                        print_error(f"Please select a number between 1 and {len(self.config.post_types)}")
                except ValueError:
                    print_error("Please enter a valid number")
        else:
            post_type = edit_post.post_type
            print(f"\n📝 Post type: {post_type}")

        # Title input
        while True:
            default_title = edit_post.title if edit_post else ""
            prompt = f"📄 Enter post title"
            if default_title:
                prompt += f" [{default_title}]"

            title = input(f"{prompt}: ").strip()
            if not title and edit_post:
                title = default_title

            if title:
                break
            print_error("Title cannot be empty")

        # Author input
        default_author = edit_post.author if edit_post else "The Team"
        prompt = f"👤 Enter author name"
        if default_author:
            prompt += f" [{default_author}]"

        author = input(f"{prompt}: ").strip()
        if not author:
            author = default_author

        # Series selection
        print("\n📚 Select series category:")
        series_options = list(self.config.series_categories.items())
        print("   0. None (no series)")
        for i, (series_key, series_name) in enumerate(series_options, 1):
            print(f"   {i}. {series_name}")

        while True:
            try:
                default_series = edit_post.series if edit_post else ""
                default_choice = ""
                if default_series:
                    for i, (key, _) in enumerate(series_options, 1):
                        if key == default_series:
                            default_choice = str(i)
                            break
                else:
                    default_choice = "0"

                prompt = f"Enter your choice (0-{len(series_options)})"
                if default_choice:
                    prompt += f" [{default_choice}]"

                choice = input(f"{prompt}: ").strip()
                if not choice and default_choice:
                    choice = default_choice

                choice_num = int(choice)
                if choice_num == 0:
                    series = ""
                    break
                elif 1 <= choice_num <= len(series_options):
                    series = series_options[choice_num - 1][0]
                    break
                else:
                    print_error(f"Please select a number between 0 and {len(series_options)}")
            except ValueError:
                print_error("Please enter a valid number")

        # YouTube ID for videos
        youtube_id = ""
        if post_type == 'Video':
            while True:
                default_yt = edit_post.youtube_id if edit_post else ""
                prompt = f"🎥 Enter YouTube Video ID"
                if default_yt:
                    prompt += f" [{default_yt}]"

                youtube_id = input(f"{prompt}: ").strip()
                if not youtube_id and edit_post:
                    youtube_id = default_yt

                if youtube_id and self.validate_youtube_id(youtube_id):
                    break
                elif youtube_id:
                    print_error("Invalid YouTube ID format. Should be 11 characters (e.g., dQw4w9WgXcQ)")
                else:
                    print_error("YouTube ID is required for video posts")

        # Description input
        default_desc = edit_post.description if edit_post else ""
        while True:
            prompt = f"📝 Enter description"
            if default_desc:
                prompt += f" [{default_desc}]"

            description = input(f"{prompt}: ").strip()
            if not description and edit_post:
                description = default_desc

            if description:
                break
            print_error("Description cannot be empty")

        # Keywords input
        default_keywords = edit_post.keywords if edit_post else ""
        prompt = f"🏷️  Enter keywords (comma-separated)"
        if default_keywords:
            prompt += f" [{default_keywords}]"

        keywords = input(f"{prompt}: ").strip()
        if not keywords and edit_post:
            keywords = default_keywords

        # Image URL input
        while True:
            default_img = edit_post.image_url if edit_post else ""
            prompt = f"🖼️  Enter thumbnail image URL"
            if default_img:
                prompt += f" [{default_img}]"

            image_url = input(f"{prompt}: ").strip()
            if not image_url and edit_post:
                image_url = default_img

            if image_url and self.validate_url(image_url):
                break
            elif image_url:
                print_error("Invalid URL format. Please enter a valid URL")
            else:
                print_error("Image URL is required")

        # Content input
        print(f"\n📄 Enter the main content for your {post_type.lower()}:")
        print("   Type 'ENDCONTENT' on a new line when finished")
        print_separator()

        if edit_post:
            print("Current content preview:")
            print(edit_post.description[:200] + "..." if len(edit_post.description) > 200 else edit_post.description)
            print_separator()

        content_lines = []
        while True:
            line = input()
            if line.strip().upper() == 'ENDCONTENT':
                break
            content_lines.append(line)

        content = "\n".join(content_lines)

        # Generate slug
        slug = edit_post.slug if edit_post else self.create_slug(title)

        # Create metadata object
        now = datetime.datetime.now()
        created_date = edit_post.created_date if edit_post else now.strftime("%Y-%m-%d %H:%M:%S")
        modified_date = now.strftime("%Y-%m-%d %H:%M:%S")

        metadata = PostMetadata(
            slug=slug,
            title=title,
            author=author,
            post_type=post_type,
            description=description,
            keywords=keywords,
            image_url=image_url,
            series=series,
            youtube_id=youtube_id,
            created_date=created_date,
            modified_date=modified_date,
            published=True,
            indexed_from_file=False
        )

        return metadata, content

    def create_backup(self, filepath: str) -> str:
        """Create a backup of the file before modification."""
        if not Path(filepath).exists():
            return ""

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{Path(filepath).stem}_{timestamp}.bak"
        backup_path = Path(self.config.backup_dir) / backup_name

        try:
            shutil.copy2(filepath, backup_path)
            self.logger.info(f"Backup created: {backup_path}")
            return str(backup_path)
        except Exception as e:
            self.logger.error(f"Error creating backup: {e}")
            return ""

    def load_template(self, post_type: str) -> str:
        """Load HTML template for the given post type."""
        template_mapping = {
            'Article': self.config.article_template,
            'Poster': self.config.poster_template,
            'Video': self.config.video_template
        }

        template_path = template_mapping.get(post_type)
        if not template_path:
            raise ValueError(f"Unknown post type: {post_type}")

        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Template not found: {template_path}")

    def generate_post_html(self, metadata: PostMetadata, content: str) -> str:
        """Generate HTML content for the post."""
        template = self.load_template(metadata.post_type)

        # Format date for display
        try:
            date_obj = datetime.datetime.strptime(metadata.created_date, "%Y-%m-%d %H:%M:%S")
            formatted_date = date_obj.strftime("%b %d, %Y")
        except:
            formatted_date = datetime.datetime.now().strftime("%b %d, %Y")

        # Replace placeholders
        replacements = {
            '{TITLE}': metadata.title,
            '{DESCRIPTION}': metadata.description,
            '{KEYWORDS}': metadata.keywords,
            '{SLUG}': metadata.slug,
            '{IMAGE_URL}': metadata.image_url,
            '{AUTHOR}': metadata.author,
            '{POST_DATE}': formatted_date,
            '{CONTENT}': content,
            '{YOUTUBE_ID}': metadata.youtube_id
        }

        html_content = template
        for placeholder, value in replacements.items():
            html_content = html_content.replace(placeholder, value)

        return html_content

    def create_post_file(self, metadata: PostMetadata, content: str) -> str:
        """Create the HTML file for the blog post."""
        post_filepath = Path(self.config.blog_dir) / f"{metadata.slug}.html"

        # Create backup if file exists
        if post_filepath.exists():
            self.create_backup(str(post_filepath))

        try:
            html_content = self.generate_post_html(metadata, content)

            with open(post_filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)

            # Calculate file hash for integrity checking
            metadata.file_hash = hashlib.md5(html_content.encode()).hexdigest()

            self.logger.info(f"Post file created: {post_filepath}")
            return str(post_filepath)

        except Exception as e:
            self.logger.error(f"Error creating post file: {e}")
            raise

    def generate_blog_card_html(self, metadata: PostMetadata) -> str:
        """Generate HTML for blog card."""
        # Format date
        try:
            date_obj = datetime.datetime.strptime(metadata.created_date, "%Y-%m-%d %H:%M:%S")
            formatted_date = date_obj.strftime("%b %d, %Y")
        except:
            formatted_date = datetime.datetime.now().strftime("%b %d, %Y")

        # Add data-series attribute for filtering
        data_series = f'data-series="{metadata.series}"' if metadata.series else ''

        card_html = f"""
        <div class="blog-card" {data_series}>
            <a href="{metadata.slug}.html">
                <div class="card-image-wrapper">
                    <div class="card-category">{metadata.post_type}</div>
                    <img loading="lazy" src="{metadata.image_url}" alt="{metadata.description}">
                </div>
                <div class="card-content">
                    <h3>{metadata.title}</h3>
                    <small class="card-meta">By {metadata.author} | {formatted_date}</small>
                    <p>{metadata.description}</p>
                </div>
            </a>
        </div>
        """
        return textwrap.dedent(card_html).strip()

    def update_blog_index(self) -> None:
        """Update the blog index with all posts."""
        index_path = Path(self.config.blog_dir) / "index.html"

        if not index_path.exists():
            self.logger.error(f"Blog index not found: {index_path}")
            return

        # Create backup
        self.create_backup(str(index_path))

        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Sort posts by creation date (newest first)
            sorted_posts = sorted(
                self.metadata_cache.values(),
                key=lambda x: x.created_date,
                reverse=True
            )

            # Generate all cards
            cards_html = []
            for post in sorted_posts:
                if post.published:
                    cards_html.append(self.generate_blog_card_html(post))

            # Find insertion point
            insertion_marker = '<div class="blog-grid">'
            if insertion_marker not in content:
                self.logger.error(f"Insertion marker not found in index")
                return

            # Replace blog grid content
            start_marker = insertion_marker
            end_marker = '</div>'

            start_pos = content.find(start_marker)
            if start_pos == -1:
                self.logger.error("Could not find blog grid start")
                return

            # Find the matching closing div
            start_pos += len(start_marker)
            end_pos = content.find(end_marker, start_pos)

            if end_pos == -1:
                self.logger.error("Could not find blog grid end")
                return

            # Construct new content
            new_content = (
                    content[:start_pos] +
                    '\n\n                <!-- Auto-generated blog cards -->\n\n' +
                    '\n\n                '.join(cards_html) +
                    '\n\n                <!-- End auto-generated cards -->\n\n            ' +
                    content[end_pos:]
            )

            with open(index_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

            self.logger.info("Blog index updated successfully")

        except Exception as e:
            self.logger.error(f"Error updating blog index: {e}")
            raise

    def create_post(self) -> None:
        """Create a new blog post."""
        try:
            metadata, content = self.get_user_input()

            # Show preview
            print_header("POST PREVIEW")
            print(f"📄 Title: {metadata.title}")
            print(f"👤 Author: {metadata.author}")
            print(f"📝 Type: {metadata.post_type}")
            print(f"📚 Series: {self.config.series_categories.get(metadata.series, 'None') if metadata.series else 'None'}")
            print(f"🏷️  Keywords: {metadata.keywords}")
            print(f"📝 Description: {metadata.description}")
            print(f"🔗 Slug: {metadata.slug}")

            if not confirm_action("\nDo you want to create this post?"):
                print_info("Post creation cancelled")
                return

            # Create post file
            post_filepath = self.create_post_file(metadata, content)

            # Update metadata cache
            self.metadata_cache[metadata.slug] = metadata

            # Save metadata
            self._save_metadata()

            # Update blog index
            self.update_blog_index()

            print_success(f"Successfully created post: {metadata.title}")
            print(f"   📁 File: {post_filepath}")
            print(f"   🔗 URL: {self.config.base_url}/blog/{metadata.slug}.html")

        except Exception as e:
            self.logger.error(f"Error creating post: {e}")
            print_error(f"Error creating post: {e}")

    def list_posts(self) -> None:
        """List all existing posts."""
        if not self.metadata_cache:
            print_info("No posts found")
            return

        print_header("EXISTING BLOG POSTS")

        # Sort by creation date
        sorted_posts = sorted(
            self.metadata_cache.values(),
            key=lambda x: x.created_date,
            reverse=True
        )

        for i, post in enumerate(sorted_posts, 1):
            status = "✅ Published" if post.published else "📝 Draft"
            indexed_marker = " 🔍" if post.indexed_from_file else ""
            series_info = f" | 📚 {self.config.series_categories.get(post.series, 'None')}" if post.series else ""
            print(f"\n{i:2d}. 📄 {post.title}{indexed_marker}")
            print(f"    📝 Type: {post.post_type} | 👤 Author: {post.author}{series_info}")
            print(f"    🔗 Slug: {post.slug} | Status: {status}")
            print(f"    📅 Created: {post.created_date}")
            print(f"    🏷️  Keywords: {post.keywords}")
            print_separator()

        print(f"\n📊 Total: {len(sorted_posts)} posts")
        indexed_count = sum(1 for post in sorted_posts if post.indexed_from_file)
        if indexed_count > 0:
            print(f"🔍 Indexed from existing files: {indexed_count}")

    def search_posts(self, query: str = None) -> List[PostMetadata]:
        """Search posts by title, description, keywords, or series."""
        if not query:
            query = input("🔍 Enter search query: ").strip()

        if not query:
            print_error("Search query cannot be empty")
            return []

        query_lower = query.lower()
        results = []

        for post in self.metadata_cache.values():
            series_name = self.config.series_categories.get(post.series, '') if post.series else ''
            if (query_lower in post.title.lower() or
                    query_lower in post.description.lower() or
                    query_lower in post.keywords.lower() or
                    query_lower in series_name.lower()):
                results.append(post)

        return results

    def search_and_display(self, query: str = None) -> None:
        """Search posts and display results."""
        results = self.search_posts(query)

        if results:
            print_header(f"SEARCH RESULTS ({len(results)} found)")
            for i, post in enumerate(results, 1):
                status = "✅ Published" if post.published else "📝 Draft"
                indexed_marker = " 🔍" if post.indexed_from_file else ""
                series_info = f" | 📚 {self.config.series_categories.get(post.series, 'None')}" if post.series else ""
                print(f"\n{i}. 📄 {post.title}{indexed_marker}")
                print(f"   📝 Type: {post.post_type} | 👤 Author: {post.author}{series_info}")
                print(f"   🔗 Slug: {post.slug} | Status: {status}")
                print(f"   📅 Created: {post.created_date}")
                print_separator()
        else:
            print_info(f"No posts found matching your query")

    def delete_post(self, slug: str = None) -> None:
        """Delete a post by slug."""
        if not slug:
            if not self.metadata_cache:
                print_info("No posts available to delete")
                return

            print_header("DELETE POST")
            print("Available posts:")

            post_list = list(self.metadata_cache.items())
            for i, (post_slug, post) in enumerate(post_list, 1):
                indexed_marker = " 🔍" if post.indexed_from_file else ""
                series_info = f" | {self.config.series_categories.get(post.series, 'None')}" if post.series else ""
                print(f"  {i}. {post.title}{indexed_marker}{series_info} ({post_slug})")

            while True:
                try:
                    choice = input(f"\nSelect post to delete (1-{len(post_list)}) or 'q' to quit: ").strip()
                    if choice.lower() == 'q':
                        print_info("Delete operation cancelled")
                        return

                    choice_idx = int(choice) - 1
                    if 0 <= choice_idx < len(post_list):
                        slug = post_list[choice_idx][0]
                        break
                    else:
                        print_error(f"Please select a number between 1 and {len(post_list)}")
                except ValueError:
                    print_error("Please enter a valid number or 'q' to quit")

        if slug not in self.metadata_cache:
            print_error(f"Post not found: {slug}")
            return

        post = self.metadata_cache[slug]

        # Show post details
        print_header("POST TO DELETE")
        print(f"📄 Title: {post.title}")
        print(f"👤 Author: {post.author}")
        print(f"📝 Type: {post.post_type}")
        print(f"📚 Series: {self.config.series_categories.get(post.series, 'None') if post.series else 'None'}")
        print(f"🔗 Slug: {post.slug}")
        print(f"📅 Created: {post.created_date}")
        if post.indexed_from_file:
            print(f"🔍 Source: Indexed from existing file")

        print_warning("This action cannot be undone!")

        if not confirm_action("Are you sure you want to delete this post?"):
            print_info("Delete operation cancelled")
            return

        # Final confirmation
        confirm_text = input("Type 'DELETE' to confirm: ").strip()
        if confirm_text != 'DELETE':
            print_info("Delete operation cancelled")
            return

        try:
            # Delete HTML file
            post_file = Path(self.config.blog_dir) / f"{slug}.html"
            if post_file.exists():
                self.create_backup(str(post_file))
                post_file.unlink()

            # Remove from metadata
            del self.metadata_cache[slug]

            # Save metadata
            self._save_metadata()

            # Update blog index
            self.update_blog_index()

            print_success(f"Successfully deleted post: {post.title}")

        except Exception as e:
            self.logger.error(f"Error deleting post: {e}")
            print_error(f"Error deleting post: {e}")

    def show_statistics(self) -> None:
        """Display blog statistics."""
        print_header("BLOG STATISTICS")

        total_posts = len(self.metadata_cache)
        published_posts = sum(1 for post in self.metadata_cache.values() if post.published)
        draft_posts = total_posts - published_posts
        indexed_posts = sum(1 for post in self.metadata_cache.values() if post.indexed_from_file)

        # Post type breakdown
        type_counts = {}
        for post in self.metadata_cache.values():
            type_counts[post.post_type] = type_counts.get(post.post_type, 0) + 1

        # Author breakdown
        author_counts = {}
        for post in self.metadata_cache.values():
            author_counts[post.author] = author_counts.get(post.author, 0) + 1

        # Series breakdown
        series_counts = {}
        for post in self.metadata_cache.values():
            if post.series:
                series_name = self.config.series_categories.get(post.series, post.series)
                series_counts[series_name] = series_counts.get(series_name, 0) + 1
            else:
                series_counts['No Series'] = series_counts.get('No Series', 0) + 1

        print(f"📊 Total Posts: {total_posts}")
        print(f"✅ Published: {published_posts}")
        print(f"📝 Drafts: {draft_posts}")
        print(f"🔍 Indexed from files: {indexed_posts}")

        if type_counts:
            print(f"\n📝 Posts by Type:")
            for post_type, count in type_counts.items():
                print(f"   {post_type}: {count}")

        if series_counts:
            print(f"\n📚 Posts by Series:")
            for series, count in series_counts.items():
                print(f"   {series}: {count}")

        if author_counts:
            print(f"\n👤 Posts by Author:")
            for author, count in author_counts.items():
                print(f"   {author}: {count}")

        # Recent posts
        if self.metadata_cache:
            recent_posts = sorted(
                self.metadata_cache.values(),
                key=lambda x: x.created_date,
                reverse=True
            )[:5]

            print(f"\n📅 Recent Posts:")
            for post in recent_posts:
                indexed_marker = " 🔍" if post.indexed_from_file else ""
                series_info = f" | {self.config.series_categories.get(post.series, 'None')}" if post.series else ""
                print(f"   {post.title}{indexed_marker}{series_info} ({post.created_date.split()[0]})")

def show_main_menu() -> None:
    """Display the main menu."""
    print_header("🌟 THE BANDAR BREAKDOWNS - BLOG CMS 🌟")
    print("Welcome to your enhanced blog management system!")
    print("\nChoose an option:")
    print("   1. 📝 Create New Post")
    print("   2. 📋 List All Posts")
    print("   3. 🔍 Search Posts")
    print("   4. 🗑️  Delete Post")
    print("   5. 📊 View Statistics")
    print("   6. 🔍 Index Existing Files")
    print("   7. 🔄 Re-index All Files")
    print("   8. ❓ Help")
    print("   9. 🚪 Exit")
    print_separator()

def show_help() -> None:
    """Display help information."""
    print_header("HELP & INFORMATION")
    print("This CMS helps you manage blog posts for The Bandar Breakdowns.")
    print("\n🔧 Features:")
    print("   • Create articles, posters, and video posts")
    print("   • Organize posts into series categories")
    print("   • Automatic slug generation and validation")
    print("   • URL and YouTube ID validation")
    print("   • Automatic backups before modifications")
    print("   • Search functionality (includes series)")
    print("   • Blog index auto-updates with series filtering")
    print("   • Metadata tracking with series support")
    print("   • Index existing HTML files")
    print("   • Re-index files to update metadata")
    print("\n📚 Series Categories:")
    config = Config()
    for key, name in config.series_categories.items():
        print(f"   • {name}")
    print("\n🔍 Indexing:")
    print("   • On first run, the CMS can scan existing HTML files")
    print("   • Extracts metadata from HTML tags and content")
    print("   • Auto-detects series based on content keywords")
    print("   • Creates metadata for backward compatibility")
    print("   • Preserves existing posts when re-indexing")
    print("\n📁 Required Files:")
    print("   • templates/_template_article.html")
    print("   • templates/_template_poster.html")
    print("   • templates/_template_video.html")
    print("   • blog/index.html")
    print("\n💡 Tips:")
    print("   • Use descriptive titles for better SEO")
    print("   • Include relevant keywords")
    print("   • Choose appropriate series for better organization")
    print("   • Ensure image URLs are accessible")
    print("   • YouTube IDs are 11 characters (from video URL)")
    print("   • Posts marked with 🔍 were indexed from existing files")

def interactive_menu():
    """Run the interactive menu system."""
    config = Config()
    cms = BlogCMS(config)

    while True:
        show_main_menu()

        try:
            choice = input("Enter your choice (1-9): ").strip()

            if choice == '1':
                cms.create_post()

            elif choice == '2':
                cms.list_posts()

            elif choice == '3':
                cms.search_and_display()

            elif choice == '4':
                cms.delete_post()

            elif choice == '5':
                cms.show_statistics()

            elif choice == '6':
                cms.index_existing_files()

            elif choice == '7':
                cms.reindex_files()

            elif choice == '8':
                show_help()

            elif choice == '9':
                print_success("Thanks for using The Bandar Breakdowns CMS!")
                print("Don't forget to commit and push your changes! 🚀")
                break

            else:
                print_error("Invalid choice. Please select 1-9.")

            if choice in ['1', '2', '3', '4', '5', '6', '7', '8']:
                input("\nPress Enter to continue...")

        except KeyboardInterrupt:
            print_info("\nOperation cancelled by user")
        except Exception as e:
            print_error(f"An error occurred: {e}")
            input("\nPress Enter to continue...")

def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Enhanced Blog CMS for The Bandar Breakdowns"
    )

    parser.add_argument(
        'action',
        nargs='?',
        choices=['create', 'list', 'search', 'delete', 'stats', 'index', 'reindex'],
        help='Action to perform (optional - if not provided, interactive menu will start)'
    )

    parser.add_argument(
        '--query',
        help='Search query (for search action)'
    )

    parser.add_argument(
        '--slug',
        help='Post slug (for delete action)'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )

    args = parser.parse_args()

    # If no action provided, start interactive menu
    if not args.action:
        interactive_menu()
        return

    # Initialize CMS for CLI usage
    config = Config()
    cms = BlogCMS(config)

    # Execute CLI action
    if args.action == 'create':
        cms.create_post()

    elif args.action == 'list':
        cms.list_posts()

    elif args.action == 'search':
        cms.search_and_display(args.query)

    elif args.action == 'delete':
        cms.delete_post(args.slug)

    elif args.action == 'stats':
        cms.show_statistics()

    elif args.action == 'index':
        cms.index_existing_files()

    elif args.action == 'reindex':
        cms.reindex_files()

if __name__ == "__main__":
    main()