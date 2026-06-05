import asyncio
import json
import os
from playwright.async_api import async_playwright

BASE_URL = "https://www.totalpromote.com"
LINKS_FILE = "links_map.json"
OUTPUT_FILE = "totalpromote_filters.json"
TMP_FILE = "totalpromote_filters.tmp.json"

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

    features = list(dict.fromkeys(features))
    colors = list(dict.fromkeys(colors))

    return features, colors


async def process_link(sem, context, cat_name, title, href, results, file_lock):
    # Skip if we already successfully scraped this title
    if title in results:
        print(f" ⏭ Skipping '{title}' (Already saved)")
        return

    async with sem:
        print(f" → Visiting {title} ({cat_name})")
        page = await context.new_page()
        try:
            await page.goto(href, wait_until="domcontentloaded", timeout=60000)
            
            try:
                await page.wait_for_selector("iframe#WE_Frame", timeout=60000)
            except:
                pass
                
            frame_elem = await page.query_selector("iframe#WE_Frame")
            
            if not frame_elem:
                print(f"    ⚠ Could not find iframe element for {title}")
                return

            frame = await frame_elem.content_frame()
            await page.wait_for_timeout(1000)

            feats, cols = await scrape_filters(page, frame, title)
            print(f"   ✔ Done {title} - features: {len(feats)}, colors: {len(cols)}")

            # Safely update dictionary
            results[title] = {
                "category": cat_name,
                "features": feats,
                "colors": cols
            }

            # --- ATOMIC SAVE: Prevents blank files if you press Ctrl+C ---
            async with file_lock:
                with open(TMP_FILE, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2)
                os.replace(TMP_FILE, OUTPUT_FILE)

        except Exception as e:
            print(f"    ❌ Failed {title}: {str(e)}")
        finally:
            await page.close()


async def main():
    results = {}
    all_links_to_visit = []

    # 1. Load existing results so we can resume
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
            print(f"✔ Loaded {len(results)} existing records from {OUTPUT_FILE}")
        except json.JSONDecodeError:
            print(f"⚠ Warning: {OUTPUT_FILE} is corrupted or empty. Starting fresh.")

    # 2. Load existing links so we skip the homepage
    if os.path.exists(LINKS_FILE):
        try:
            with open(LINKS_FILE, "r", encoding="utf-8") as f:
                all_links_to_visit = json.load(f)
        except json.JSONDecodeError:
            pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        # 3. Verify Links
        if len(all_links_to_visit) > 1:
            print(f"✔ Found {len(all_links_to_visit)} links in {LINKS_FILE}. Skipping homepage extraction.")
        else:
            print("→ Fetching URLs from homepage for the first time...")
            page = await context.new_page()
            await page.goto(BASE_URL, wait_until="commit", timeout=60000)

            nav_container = await page.query_selector("div#navbarNav ul.navbar-nav.mx-auto")
            dropdowns = await nav_container.query_selector_all("li.nav-item.dropdown.yamm-fw")
            
            for cat in dropdowns:
                nav_link = await cat.query_selector("a.nav-link")
                cat_name = (await nav_link.inner_text()).strip()
                
                try:
                    await cat.hover()
                    await page.wait_for_timeout(300)
                except:
                    pass

                links = await cat.query_selector_all("div.dropdown-menu .nav-content a.nav-link")

                for link in links:
                    title = (await link.inner_text()).strip()
                    href  = await link.get_attribute("href")
                    if href:
                        if not href.startswith("http"):
                            href = BASE_URL + href
                        all_links_to_visit.append({
                            "category": cat_name,
                            "title": title,
                            "url": href
                        })
            
            await page.close()
            with open(LINKS_FILE, "w", encoding="utf-8") as f:
                json.dump(all_links_to_visit, f, indent=2)
            print(f"✔ Saved {len(all_links_to_visit)} links to {LINKS_FILE}")

        # 4. Process links concurrently
        print("\n→ Starting parallel extraction (max 7 concurrent tabs)...")
        sem = asyncio.Semaphore(7)
        file_lock = asyncio.Lock() 
        
        tasks = [
            process_link(sem, context, item["category"], item["title"], item["url"], results, file_lock)
            for item in all_links_to_visit
        ]
        
        await asyncio.gather(*tasks)

        print(f"\n✔ Extraction complete! All data successfully saved to {OUTPUT_FILE}")
        
        # Cleanup temp file if it exists at the very end
        if os.path.exists(TMP_FILE):
            os.remove(TMP_FILE)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())