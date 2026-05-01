import asyncio
import json
import re
import httpx
import time
from playwright.async_api import async_playwright
from rich.console import Console

console = Console()

async def find_from_google_maps(page, maps_url: str, business_name: str) -> dict:
    """Google Maps sayfasından web sitesi ve sosyal medya çek"""
    result = {
        "website_url": None,
        "phone": None,
        "address": None,
    }
    
    try:
        await page.goto(maps_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        # Web sitesi butonu
        web_btn = await page.query_selector('a[data-item-id="authority"]')
        if not web_btn:
            web_btn = await page.query_selector('a[aria-label*="web"]')
        if not web_btn:
            web_btn = await page.query_selector('a[href*="http"][data-tooltip="Web sitesini aç"]')
            
        if web_btn:
            href = await web_btn.get_attribute("href")
            if href and "google" not in href:
                result["website_url"] = href
        
        # Telefon numarası
        phone_el = await page.query_selector('button[data-item-id*="phone"]')
        if phone_el:
            result["phone"] = await phone_el.get_attribute("aria-label")
            
    except Exception as e:
        console.print(f"[red]Maps hata: {e}[/red]")
    
    return result

async def check_website(url: str) -> dict:
    result = {"has_website": True, "website_url": url, "has_ssl": False, "is_mobile_friendly": False, "load_time_ms": None, "website_loads": False}
    
    if not url:
        return {"has_website": False, "website_url": None, "has_ssl": False, "is_mobile_friendly": False, "load_time_ms": None, "website_loads": False}
    
    result["has_ssl"] = url.startswith("https")
    
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"}
            start = time.time()
            resp = await client.get(url, headers=headers)
            result["load_time_ms"] = int((time.time() - start) * 1000)
            result["website_loads"] = resp.status_code == 200
            result["is_mobile_friendly"] = "viewport" in resp.text.lower()
    except:
        pass
    
    return result

async def find_instagram(page, business_name: str, website_url: str = None) -> dict:
    result = {"has_instagram": False, "instagram_url": None, "instagram_username": None}
    
    # 1. Web sitesinde Instagram linki ara
    if website_url:
        try:
            await page.goto(website_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            content = await page.content()
            matches = re.findall(r'instagram\.com/([a-zA-Z0-9_.]{2,30})/?', content)
            blacklist = ["p", "reel", "explore", "stories", "accounts", "about", "legal", "help", "press", "api"]
            for m in matches:
                if m not in blacklist:
                    result["has_instagram"] = True
                    result["instagram_url"] = f"https://www.instagram.com/{m}/"
                    result["instagram_username"] = m
                    return result
        except:
            pass
    
    # 2. Olası username'leri dene
    name_clean = business_name.lower()
    name_clean = re.sub(r'[^a-z0-9\s]', '', name_clean.replace('ı','i').replace('ğ','g').replace('ü','u').replace('ş','s').replace('ö','o').replace('ç','c'))
    words = name_clean.split()
    
    candidates = [
        ''.join(words),
        '.'.join(words),
        '_'.join(words),
        words[0] if words else '',
        ''.join(words[:2]) if len(words) >= 2 else '',
    ]
    candidates = [c for c in candidates if len(c) >= 3]
    
    async with httpx.AsyncClient(timeout=6, follow_redirects=True) as client:
        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"}
        for username in candidates:
            try:
                resp = await client.get(f"https://www.instagram.com/{username}/", headers=headers)
                if resp.status_code == 200 and '"@type":"ProfilePage"' in resp.text:
                    result["has_instagram"] = True
                    result["instagram_url"] = f"https://www.instagram.com/{username}/"
                    result["instagram_username"] = username
                    console.print(f"    [green]✓ Instagram bulundu: @{username}[/green]")
                    return result
                await asyncio.sleep(0.5)
            except:
                continue
    
    # 3. Google'da ara - headful modda daha iyi çalışır
    try:
        await page.goto(f"https://www.google.com/search?q={business_name.replace(' ', '+')}+instagram", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        content = await page.content()
        matches = re.findall(r'instagram\.com/([a-zA-Z0-9_.]{2,30})/?', content)
        blacklist = ["p", "reel", "explore", "stories", "accounts", "about", "legal", "help", "press", "api", "sharer"]
        for m in matches:
            if m not in blacklist:
                # Doğrula
                try:
                    async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                        headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)"}
                        resp = await client.get(f"https://www.instagram.com/{m}/", headers=headers)
                        if resp.status_code == 200:
                            result["has_instagram"] = True
                            result["instagram_url"] = f"https://www.instagram.com/{m}/"
                            result["instagram_username"] = m
                            return result
                except:
                    pass
    except:
        pass
    
    return result

async def audit_all(leads_file="leads_raw.json"):
    with open(leads_file, encoding="utf-8") as f:
        leads = json.load(f)
    
    results = []
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Görünür mod — Google engellemiyor
            args=["--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="tr-TR"
        )
        page = await context.new_page()
        
        for lead in leads:
            name = lead["name"]
            maps_url = lead.get("maps_url", "")
            console.print(f"\n[bold cyan]► {name}[/bold cyan]")
            
            # Google Maps'ten web sitesi al
            maps_data = {}
            if maps_url:
                console.print("  📍 Google Maps'ten veri alınıyor...")
                maps_data = await find_from_google_maps(page, maps_url, name)
                console.print(f"  🌐 Web: {maps_data.get('website_url', 'Bulunamadı')}")
            
            # Web sitesi kontrol
            website = await check_website(maps_data.get("website_url"))
            
            # Instagram bul
            console.print("  📸 Instagram aranıyor...")
            instagram = await find_instagram(page, name, maps_data.get("website_url"))
            console.print(f"  {'✅' if instagram['has_instagram'] else '❌'} Instagram: {instagram.get('instagram_url', 'Yok')}")
            
            # Skor
            score = 0
            issues = []
            opportunities = []
            
            if website["has_website"]:
                score += 30
                if website["has_ssl"]: score += 10
                else: issues.append("SSL yok"); opportunities.append("SSL kurulumu")
                if website["is_mobile_friendly"]: score += 10
                else: issues.append("Mobil uyumsuz"); opportunities.append("Mobil tasarım yenileme")
                if website.get("load_time_ms") and website["load_time_ms"] > 3000:
                    issues.append(f"Site yavaş ({website['load_time_ms']}ms)")
                    opportunities.append("Site hız optimizasyonu")
                else:
                    score += 5
            else:
                issues.append("Web sitesi yok")
                opportunities.append("Web sitesi tasarımı — yüksek öncelik")
            
            if instagram["has_instagram"]: score += 35
            else: issues.append("Instagram hesabı yok"); opportunities.append("Instagram yönetimi + içerik üretimi")
            
            grade = "A" if score >= 80 else "B" if score >= 55 else "C" if score >= 35 else "D"
            
            result = {
                **lead,
                "website": website,
                "social": instagram,
                "scoring": {"score": score, "max_score": 100, "grade": grade, "issues": issues, "opportunities": opportunities}
            }
            results.append(result)
            await asyncio.sleep(1)
        
        await browser.close()
    
    with open("leads_audited.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    console.print(f"\n[bold green]✅ Audit tamamlandı → leads_audited.json[/bold green]")

if __name__ == "__main__":
    asyncio.run(audit_all())
