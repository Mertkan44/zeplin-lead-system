import asyncio
import httpx
import json
from urllib.parse import urlparse
from rich.console import Console
from rich.table import Table

console = Console()

async def check_website(business_name: str) -> dict:
    search_url = f"https://www.google.com/search?q={business_name.replace(' ', '+')}+website"
    
    result = {
        "has_website": False,
        "website_url": None,
        "website_loads": False,
        "is_mobile_friendly": False,
        "has_ssl": False,
        "load_time_ms": None,
    }
    
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"}
            resp = await client.get(search_url, headers=headers)
            
            import re
            urls = re.findall(r'href="(https?://(?!google|youtube|facebook|instagram)[^"]+)"', resp.text)
            
            if urls:
                website = urls[0]
                result["has_website"] = True
                result["website_url"] = website
                result["has_ssl"] = website.startswith("https://")
                
                import time
                start = time.time()
                try:
                    site_resp = await client.get(website, headers=headers)
                    result["load_time_ms"] = int((time.time() - start) * 1000)
                    result["website_loads"] = site_resp.status_code == 200
                    
                    content = site_resp.text.lower()
                    result["is_mobile_friendly"] = "viewport" in content
                except:
                    pass
        except:
            pass
    
    return result

async def check_social_media(business_name: str) -> dict:
    result = {
        "has_instagram": False,
        "has_facebook": False,
        "instagram_url": None,
        "facebook_url": None,
    }
    
    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            query = business_name.replace(' ', '+')
            resp = await client.get(f"https://www.google.com/search?q={query}+instagram", headers=headers)
            
            import re
            ig = re.findall(r'href="(https://www\.instagram\.com/[^/"]+/?)"', resp.text)
            if ig:
                result["has_instagram"] = True
                result["instagram_url"] = ig[0]
            
            resp2 = await client.get(f"https://www.google.com/search?q={query}+facebook", headers=headers)
            fb = re.findall(r'href="(https://www\.facebook\.com/[^/"]+/?)"', resp2.text)
            if fb:
                result["has_facebook"] = True
                result["facebook_url"] = fb[0]
        except:
            pass
    
    return result

def calculate_score(website: dict, social: dict) -> dict:
    score = 0
    issues = []
    opportunities = []
    
    if not website["has_website"]:
        issues.append("Web sitesi YOK")
        opportunities.append("Web sitesi tasarımı — yüksek öncelik")
    else:
        score += 20
        if not website["has_ssl"]:
            issues.append("SSL sertifikası yok (http)")
            opportunities.append("SSL kurulumu + güvenlik")
        else:
            score += 10
        
        if not website["is_mobile_friendly"]:
            issues.append("Mobil uyumsuz site")
            opportunities.append("Mobil tasarım yenileme")
        else:
            score += 15
        
        if website["load_time_ms"] and website["load_time_ms"] > 3000:
            issues.append(f"Site çok yavaş ({website['load_time_ms']}ms)")
            opportunities.append("Site hız optimizasyonu")
        elif website["load_time_ms"]:
            score += 15
    
    if not social["has_instagram"]:
        issues.append("Instagram hesabı bulunamadı")
        opportunities.append("Instagram yönetimi + içerik üretimi")
    else:
        score += 20
    
    if not social["has_facebook"]:
        issues.append("Facebook sayfası bulunamadı")
        opportunities.append("Facebook sayfası kurulumu")
    else:
        score += 20
    
    return {
        "score": score,
        "max_score": 100,
        "grade": "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D",
        "issues": issues,
        "opportunities": opportunities
    }

async def audit_business(business: dict) -> dict:
    name = business["name"]
    console.print(f"[cyan]Analiz ediliyor:[/cyan] {name}")
    
    website = await check_website(name)
    social = await check_social_media(name)
    scoring = calculate_score(website, social)
    
    return {
        **business,
        "website": website,
        "social": social,
        "scoring": scoring
    }

async def audit_all(leads_file: str = "leads_raw.json"):
    with open(leads_file, encoding="utf-8") as f:
        leads = json.load(f)
    
    results = []
    for lead in leads:
        result = await audit_business(lead)
        results.append(result)
        await asyncio.sleep(1)
    
    with open("leads_audited.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    table = Table(title="Audit Sonuçları", show_header=True)
    table.add_column("İşletme", style="cyan", max_width=30)
    table.add_column("Puan", justify="center")
    table.add_column("Not", justify="center")
    table.add_column("Sorunlar", style="red")
    
    for r in results:
        s = r["scoring"]
        table.add_row(
            r["name"],
            str(s["score"]),
            s["grade"],
            ", ".join(s["issues"][:2])
        )
    
    console.print(table)
    console.print(f"\n[bold green]✅ Audit tamamlandı → leads_audited.json[/bold green]")

if __name__ == "__main__":
    asyncio.run(audit_all())
