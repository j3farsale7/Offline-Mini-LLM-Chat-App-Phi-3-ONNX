import os
import asyncio
import httpx
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from readability import Document
import aiofiles
import logging

logging.basicConfig(level=logging.INFO, filename="search.log", filemode="w",
                    format="%(asctime)s - %(levelname)s - %(message)s")


os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.getcwd(), "ms-playwright")



#domains to skip (paywalls, social media, etc.)
BAD_DOMAINS = {
    "facebook.com", "x.com", "instagram.com",
    "linkedin.com", "youtube.com", "wikipedia.org",
    "amazon.", "reddit.com", "tiktok.com", "news.google.com"
}

def is_valid_url(url):
    """
    Check if URL is valid and not from unwanted domains.
    Return:
        bool: True if URL is valid and acceptable.
    """
    if not url.startswith(("http://", "https://")): 
        return False
    
    for domain in BAD_DOMAINS:
        if domain in url:
            return False
            
    return True

async def fetch_page_content(session, url, force=False):
    """
    Fetch and extract readable content from a single URL using httpx.
    
    Args:
        session (httpx.AsyncClient): HTTP client session
        url (str): URL to fetch
        force (bool): Whether to lower word threshold for content extraction
    
    Return:
        str: Extracted text content or None
    """
    try:
        response = await session.get(url, timeout=20)
        
        if response.status_code == 200:
            html = response.text
            min_words = 10 if force else 100
            content = extract_clean_text(html, min_words=min_words)
            return content
        else:
            logging.warning(f"Failed to load {url} - Status code: {response.status_code}")
            return None
            
    except Exception as e:
        logging.error(f"Error fetching {url}: {e}")
        return None

async def fetch_page_content_with_playwright(url):
    """
    Use Playwright to render JS-heavy pages and extract any visible text.
    
    Args:
        url (str): URL to fetch via browser rendering
    
    Return:
        str: Extracted text content or None
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            await page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            
            await page.goto(url, timeout=20000)
            await page.wait_for_timeout(3000)  # Wait for JS to load
            html = await page.content()
            await browser.close()
            
            soup = BeautifulSoup(html, "html.parser")
            body = soup.body
            
            if body:
                text = body.get_text(separator=" ", strip=True)
                words = text.split()
                
                if len(words) >= 5:
                    return " ".join(words[:200])  # Return first 200 words
                    
            return None
            
    except Exception as e:
        logging.error(f"Error fetching via Playwright: {e}")
        return None

def extract_clean_text(html, min_words=100):
    """
    Use Readability-lxml to extract article body and check length.
    
    Args:
        html (str): HTML content
        min_words (int): Minimum number of words required for valid content
        
    Return:
        str: Cleaned text or None
    """
    try:
        doc = Document(html)
        summary = doc.summary()
        soup = BeautifulSoup(summary, "html.parser")
        text = soup.get_text(separator=" ").strip()
        
        if len(text.split()) < min_words:
            return None
            
        return text
        
    except Exception as e:
        logging.error(f"Error extracting text: {e}")
        return None

async def perform_web_search(query):
    """
    Search Bing and extract top results, trying up to 15 links to find maybe 7 good ones.
    
    Args:
        query (str): Search query
    
    Return:
        tuple: (usable_results, bad_domain_results)
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.set_viewport_size({"width": 1200, "height": 800})
        
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0 Safari/537.36"
        })
        
        search_url = f"https://www.bing.com/search?q={query}"
        await page.goto(search_url)
        await page.wait_for_selector(".b_algo", timeout=10000)
        html = await page.content()
        await browser.close()
    
    soup = BeautifulSoup(html, "html.parser")
    all_results = soup.select(".b_algo")
    usable_results = []
    bad_domain_results = []
    
    logging.info("Filtering Bing results (up to 15 total, looking for 7 usable ones)...")
    
    count = 0
    for result in all_results:
        if count >= 15:
            break
            
        title_tag = result.select_one("h2 a")
        url_tag = result.select_one("a")
        
        if not title_tag or not url_tag:
            continue
            
        title = title_tag.text.strip()
        url = url_tag.get("href")
        
        if not url or not url.startswith(("http://", "https://")):
            continue
            
        item = {"title": title, "url": url}
        count += 1
        
        if any(domain in url for domain in BAD_DOMAINS):
            bad_domain_results.append(item)
        else:
            usable_results.append(item)
            
            if len(usable_results) >= 7:
                logging.info("Found 7 usable results within first %d links.", count)
                break
    
    if len(usable_results) < 7:
        logging.warning("Only found %d usable results in first 15 links.", len(usable_results))
    
    return usable_results[:7], bad_domain_results

async def run_web_search(query):
    """
    Main function to run web search and save results.
    
    Args:
        query (str): Search query
        
    Return:
        str: Path to output directory containing search results
    """
    base_output_dir = "web_searches"
    os.makedirs(base_output_dir, exist_ok=True)
    
    existing_attempts = [d for d in os.listdir(base_output_dir) if d.startswith("search_attempt_")]
    attempt_number = len(existing_attempts) + 1
    output_dir = os.path.join(base_output_dir, f"search_attempt_{attempt_number}")
    os.makedirs(output_dir, exist_ok=True)
    
    logging.info("Searching Bing for: '%s'", query)
    
    initial_results, bad_domain_results = await perform_web_search(query)
    logging.info("Found %d usable links (after filtering first 15).", len(initial_results))
    logging.info("Also found %d link(s) from blacklisted domains.", len(bad_domain_results))
    
    urls_file = os.path.join(output_dir, "urls_n_headlines.txt")
    
    async with aiofiles.open(urls_file, "w", encoding="utf-8") as f:
        for item in initial_results:
            await f.write(f"{item['title']}\n{item['url']}\n\n")
    
    logging.info("Saved URLs and titles to: %s", urls_file)
    
    #first batch: process usable results !first 7! 
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        tasks = [fetch_page_content(client, item['url']) for item in initial_results]
        contents = await asyncio.gather(*tasks)
    
    saved_count = 0
    
    for idx, (item, content) in enumerate(zip(initial_results, contents)):
        if content:
            filename = f"search_data_{saved_count+1}.txt"
            filepath = os.path.join(output_dir, filename)
            
            async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
                await f.write(f"Title: {item['title']}\nURL: {item['url']}\n{content}")
                
            logging.info("Saved: %s (%d words)", item['title'], len(content.split()))
            saved_count += 1
        else:
            logging.warning("Skipped: %s (insufficient or unreadable content)", item['title'])
    
    #second batch: handle bad-domain results !even small content!
    if bad_domain_results:
        logging.info("Processing %d blacklisted domain results...", len(bad_domain_results))
        
        for idx, item in enumerate(bad_domain_results):
            logging.info("Trying hard to get content from BAD DOMAIN: %s", item['title'])
            content = await fetch_page_content_with_playwright(item['url'])
            
            if content:
                filename = f"search_data_{saved_count + 1}.txt"
                filepath = os.path.join(output_dir, filename)
                
                async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
                    await f.write(f"Title: {item['title']}\nURL: {item['url']}\n{content}")
                    
                logging.info("Saved from BAD DOMAIN: %s (%d words)", item['title'], len(content.split()))
                saved_count += 1
            else:
                logging.warning("Skipped from BAD DOMAIN: %s", item['title'])
    
    logging.info("All files saved in: %s", output_dir)
    logging.info("Done. Total saved documents: %d", saved_count)
    
    return output_dir

#wrapper to run async function in a thread
def start_web_search(query):
    return asyncio.run(run_web_search(query))