import os
import uuid
from urllib.parse import urldefrag, urljoin, urlparse

from playwright.async_api import async_playwright

class WebCrawler:
    """
    A web crawler that recursively crawls a set of starter URLs up to a specified number of hops,
    saves the crawled page content locally, and ensures only allowed domains are visited.

    Attributes:
        starter_urls (list): The initial list of URLs to start crawling from.
        hops (int): The maximum number of link hops to follow from the starter URLs.
        allowed_domains (list): List of allowed domain suffixes for crawling.
        storage_folder (str): Path to the folder where crawled pages will be saved.
        visited_urls (set): A set to track visited URLs and prevent duplicate crawling.
        crawled_pages (list): A list of metadata for all successfully crawled pages.
    """

    def __init__(self, starter_urls, hops, allowed_domains, storage_folder):
        """
        Initialize the WebCrawler instance with given parameters.

        Args:
            starter_urls (list): Initial URLs to begin the crawl.
            hops (int): Maximum number of link hops to follow.
            allowed_domains (list): List of domain suffixes that the crawler can visit.
            storage_folder (str): Directory to save the crawled page content.
        """
        self.starter_urls = starter_urls
        self.hops = hops
        self.allowed_domains = allowed_domains
        self.storage_folder = storage_folder
        self.visited_urls = set()
        self.crawled_pages = []

        # Ensure the storage folder exists
        os.makedirs(self.storage_folder, exist_ok=True)

    def is_allowed(self, url):
        """
        Check if a given URL belongs to an allowed domain.

        Args:
            url (str): The URL to check.

        Returns:
            bool: True if the URL is allowed, False otherwise.
        """
        domain = urlparse(url).netloc
        return any(domain.endswith(allowed) for allowed in self.allowed_domains)

    def normalize_url(self, url):
        """
        Normalize a URL by removing fragments and adjusting trailing slashes.

        Args:
            url (str): The URL to normalize.

        Returns:
            str: The normalized URL.
        """
        # Remove fragment (e.g., "#section")
        url, _ = urldefrag(url)

        # Ensure trailing slash consistency for root URLs
        if url.count('/') == 2 and not url.endswith('/'):
            url += '/'
        else:
            # Remove trailing slash for other cases
            url = url.rstrip('/')

        return url

    def save_page_content(self, content, url):
        """
        Save the crawled page content to a local file and track its metadata.

        Args:
            content (str): The HTML content of the page.
            url (str): The URL of the page.

        Side Effects:
            Writes the page content to a file in the storage folder.
        """
        file_name = f"{uuid.uuid4().hex}.html"
        file_path = os.path.join(self.storage_folder, file_name)

        # Save the content to the file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)

        # Track the crawled page metadata
        self.crawled_pages.append({
            "url": url,
            "local_filepath": file_path,
            "size": len(content)
        })

    async def crawl(self):
        """
        Start the crawling process using Playwright to render and extract web page content.

        This function uses an asynchronous workflow to launch a headless Chromium browser,
        visit URLs, extract content, and follow links recursively.

        Side Effects:
            Saves crawled pages to the local storage folder.
        """
        async with async_playwright() as p:
            # Launch a headless browser
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()

            # Initialize the queue with starter URLs and their depth
            queue = [(self.normalize_url(url), 0) for url in self.starter_urls]

            while queue:
                # Dequeue the next URL and its depth
                current_url, depth = queue.pop(0)
                normalized_url = self.normalize_url(current_url)

                # Skip already visited URLs or those exceeding the hop limit
                if normalized_url in self.visited_urls or depth > self.hops:
                    continue

                print(f"Crawling: {current_url}")
                try:
                    # Open a new browser page and navigate to the URL
                    page = await context.new_page()
                    response = await page.goto(current_url, timeout=10000)

                    # Skip if the response status indicates an error
                    if response.status < 200 or response.status >= 400:
                        print(f"Failed to crawl {current_url}: {response.status}")
                        continue

                    self.visited_urls.add(normalized_url)

                    # Save the content of the visited page
                    content = await page.content()
                    self.save_page_content(content, current_url)

                    # Extract and process links
                    links = await page.locator("a[href]").element_handles()
                    for link in links:
                        href = await link.get_attribute("href")
                        if href:
                            normalized_href = self.normalize_url(urljoin(current_url, href))

                            # Add new links to the queue if they are allowed and not visited
                            if self.is_allowed(normalized_href) and normalized_href not in self.visited_urls:
                                queue.append((normalized_href, depth + 1))

                    await page.close()

                except Exception as e:
                    print(f"Failed to crawl {current_url}: {e}")

            # Close the browser
            await browser.close()