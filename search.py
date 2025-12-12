import os
from serpapi import GoogleSearch
from dotenv import load_dotenv

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

def search_leads(query, num_pages=1):
    all_leads = []
    
    for page in range(num_pages):
        start = page * 20
        print(f"Searching page {page + 1} (start={start})...")
        
        params = {
            "engine": "google_maps",
            "q": query,
            "api_key": SERPAPI_KEY,
            "start": start,
            "type": "search"
        }

        search = GoogleSearch(params)
        results = search.get_dict()
        local_results = results.get("local_results", [])

        if not local_results:
            print("No more results found.")
            break

        for result in local_results:
            lead = {
                "name": result.get("title"),
                "phone": result.get("phone"),
                "address": result.get("address"),
                "website": result.get("website"),
                "rating": result.get("rating"),
                "reviews": result.get("reviews"),
                "types": ", ".join(result.get("types", [])) if result.get("types") else "",
                "search_term": query # specific sector/term used for this search
            }
            # Only add if phone number exists
            if lead["phone"]:
                # Basic Language Detection
                # +55 = PT (Brazil)
                # +595 = ES (Paraguay)
                # +54 = ES (Argentina)
                p = lead["phone"]
                if "+55" in p or p.startswith("55"):
                    lead['language'] = 'pt'
                elif "+595" in p or p.startswith("595") or "+54" in p or p.startswith("54"):
                    lead['language'] = 'es'
                else:
                    lead['language'] = 'pt' # Default to PT if unknown/local without area
                    
                all_leads.append(lead)
        
    return all_leads
