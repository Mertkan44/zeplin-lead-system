import asyncio
import json
from playwright.async_api import async_playwright
from rich.console import Console
from rich.progress import track

console = Console()

async def scrape_google_maps(query: str, city: str, max_results: int = 20):
    results = []
    search_query = f"{query} {city}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        console.print(f"[cyan]Araniyor:[/cyan] {search_query}")
        await page.goto(f"https://www.google.com/maps/search/{search_query.replace(' ', '+')}")
        await page.wait_for_timeout(3000)
        
        for _ in range(5):
            await page.keyboard.press("End")
            await page.wait_for_timeout(1000)
        
        listings = await page.query_selector_all('a[href*="/maps/place/"]')
        console.print(f"[green]{len(listings)} sonuç bulundu[/green]")
        
        for listing in listings[:max_results]:
            try:
                name = await listing.get_attribute("aria-label")
                href = await listing.get_attribute("href")
                if name and href:
                    results.append({"name": name, "maps_url": href, "query": query, "city": city})
            except:
                continue
        
        await browser.close()
    
    return results

async def main():
    results = await scrape_google_maps("restoran", "Istanbul Beykoz", max_results=10)
    
    with open("leads_raw.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    console.print(f"\n[bold green]✅ {len(results)} lead kaydedildi → leads_raw.json[/bold green]")
    for r in results:
        console.print(f"  • {r['name']}")

if __name__ == "__main__":
    asyncio.run(main())
