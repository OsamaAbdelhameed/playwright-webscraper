import asyncio
import json
import os
from playwright.async_api import async_playwright

BASE_URL = "https://www.totalpromote.com"
LINKS_FILE = "links_map.json"
OUTPUT_FILE = "totalpromote_filters.json"

async def scrape_filters(page, frame, title):
    features = []
    colors = []

    try:
        await frame.wait_for_selector("div.filter-section", timeout=15000)
    except:
        print(f"   ⚠ No filters found in iframe for {title}")
        return features, colors

    sections = await frame.query_selector_all("div.filter-section")
    for sec in sections:
        header = await sec.query_selector("h2")
        if not header:
            continue

        name = (await header.inner_text()).strip().lower()

        try:
            show_more = await sec.query_selector("a.show-more")
            if show_more:
                await show_more.click()
                await page.wait_for_timeout(600)
        except:
            pass

        labels = await sec.query_selector_all("div.checkbox span")
        for lbl in labels:
            txt = (await lbl.inner_text()).strip()
            if txt:
                if "features" in name:
                    features.append(txt)
                elif "colors" in name:
                    colors.append(txt)

    # dedupe
    features = list(dict.fromkeys(features))
    colors = list(dict.fromkeys(colors))

    return features, colors


async def process_link(sem, context, cat_name, title, href, results, file_lock):
    """Worker function that handles a single link and saves incrementally."""
    
    # 1. Skip if already processed
    if title in results:
        print(f" ⏭ Skipping '{title}' (Already in {OUTPUT_FILE})")
        return

    async with sem:
        print(f" → Visiting {title} ({cat_name})")
        page = await context.new_page()
        try:
            await page.goto(href, wait_until="domcontentloaded", timeout=60000)
            
            # wait for the iframe to appear
            await page.wait_for_selector("iframe#WE_Frame", timeout=60000)
            frame_elem = await page.query_selector("iframe#WE_Frame")
            
            if not frame_elem:
                print(f"    ⚠ Could not find iframe element for {title}")
                return

            frame = await frame_elem.content_frame()
            await page.wait_for_timeout(1000)

            feats, cols = await scrape_filters(page, frame, title)
            print(f"   ✔ Done {title} - features: {len(feats)}, colors: {len(cols)}")

            # Update results dictionary
            results[title] = {
                "category": cat_name,
                "features": feats,
                "colors": cols
            }

            # 2. Incrementally save to file safely (using Lock to prevent concurrent write corruption)
            async with file_lock:
                with open(OUTPUT_FILE, "w") as f:
                    json.dump(results, f, indent=2)

        except Exception as e:
            print(f"    ❌ Failed {title}: {str(e)}")
        finally:
            await page.close()


async def main():
    results = {}
    all_links_to_visit = []

    # Load existing results to know what to skip
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r") as f:
                results = json.load(f)
            print(f"✔ Loaded {len(results)} existing records from {OUTPUT_FILE}")
        except json.JSONDecodeError:
            print(f"⚠ Warning: Could not parse {OUTPUT_FILE}. Starting fresh.")

    # Load existing links if available
    if os.path.exists(LINKS_FILE):
        try:
            with open(LINKS_FILE, "r") as f:
                all_links_to_visit = json.load(f)
        except json.JSONDecodeError:
            pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        # 3. Use links array if it has > 1 element, otherwise fetch from homepage
        if len(all_links_to_visit) > 1:
            print(f"✔ Found {len(all_links_to_visit)} links in {LINKS_FILE}. Skipping homepage extraction.")
        else:
            print("→ No valid links found. Opening homepage to extract URLs...")
            page = await context.new_page()
            await page.goto(BASE_URL, wait_until="commit", timeout=60000)

            nav_container = await page.query_selector("div#navbarNav ul.navbar-nav.mx-auto")
            dropdowns = await nav_container.query_selector_all("li.nav-item.dropdown.yamm-fw")
            print("Found categories:", len(dropdowns))

            for cat in dropdowns:
                nav_link = await cat.query_selector("a.nav-link")
                cat_name = (await nav_link.inner_text()).strip()
                print(f"Reading links for CATEGORY: {cat_name}")

                try:
                    await cat.hover()
                    await page.wait_for_timeout(300)
                except:
                    pass

                links = await cat.query_selector_all("div.dropdown-menu .nav-content a.nav-link")

                for link in links:
                    title = (await link.inner_text()).strip()
                    href  = await link.get_attribute("href")
                    if not href:
                        continue
                    if not href.startswith("http"):
                        href = BASE_URL + href
                    
                    all_links_to_visit.append({
                        "category": cat_name,
                        "title": title,
                        "url": href
                    })

            await page.close()

            # Save newly mapped links
            with open(LINKS_FILE, "w") as f:
                json.dump(all_links_to_visit, f, indent=2)
            print(f"✔ Saved {len(all_links_to_visit)} links to {LINKS_FILE}")

        # Start parallel extraction
        print("\n→ Starting parallel extraction (max 7 concurrent tabs)...")
        sem = asyncio.Semaphore(7)
        file_lock = asyncio.Lock() 
        
        tasks = [
            process_link(sem, context, item["category"], item["title"], item["url"], results, file_lock)
            for item in all_links_to_visit
        ]
        
        await asyncio.gather(*tasks)

        print(f"\n✔ Extraction complete! All data successfully saved to {OUTPUT_FILE}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())