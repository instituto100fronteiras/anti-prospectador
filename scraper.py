import requests

def scrape_website(url):
    if not url:
        return None
        
    # Ensure URL has protocol
    if not url.startswith('http'):
        url = 'https://' + url
        
    jina_url = f"https://r.jina.ai/{url}"
    
    try:
        print(f"Scraping website: {url}...")
        response = requests.get(jina_url, timeout=15)
        
        if response.status_code == 200:
            content = response.text
            # Basic cleanup: limit length to avoid token limits
            # GPT-4o-mini has a large context window, but let's keep it reasonable (e.g., 5000 chars)
            return content[:5000]
        else:
            print(f"Failed to scrape {url}: Status {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None
