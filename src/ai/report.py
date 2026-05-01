import json
import requests
from rich.console import Console

console = Console()

def generate_report(business: dict) -> str:
    name = business["name"]
    scoring = business["scoring"]
    website = business["website"]
    social = business["social"]
    
    prompt = f"""Sen Zeplin Media adlı dijital ajansın satış uzmanısın. 
Bir işletmenin dijital varlık analizini inceleyip kısa, ikna edici bir Türkçe satış raporu yaz.

İŞLETME: {name}
DİJİTAL PUAN: {scoring['score']}/100 (Not: {scoring['grade']})
WEB SİTESİ: {"Var - " + str(website['website_url']) if website['has_website'] else "YOK"}
SSL: {"Var" if website['has_ssl'] else "Yok"}
MOBİL UYUMLU: {"Evet" if website['is_mobile_friendly'] else "Hayır"}
INSTAGRAM: {"Var" if social['has_instagram'] else "YOK"}
FACEBOOK: {"Var" if social.get('has_facebook', False) else "YOK"}
TESPİT EDİLEN SORUNLAR: {', '.join(scoring['issues'])}

Şunları içeren kısa bir rapor yaz (max 150 kelime):
1. İşletmenin mevcut durumu (1-2 cümle)
2. En kritik 2-3 eksik
3. Zeplin Media olarak neler sunabileceğimiz
4. Güçlü bir kapanış cümlesi

Samimi, profesyonel ve ikna edici yaz."""

    response = requests.post("http://localhost:11434/api/generate", json={
        "model": "mistral",
        "prompt": prompt,
        "stream": False
    })
    
    return response.json()["response"]

def generate_sales_email(business: dict, report: str) -> str:
    name = business["name"]
    
    prompt = f"""Zeplin Media dijital ajans olarak {name} işletmesine gönderilecek kısa satış e-postası yaz.

İşletme analizi: {report}

E-posta şunları içermeli:
- Kısa, dikkat çekici konu başlığı
- Samimi selamlama  
- 2-3 cümle ile sorunu belirt
- Çözüm olarak Zeplin Media'yı sun
- Net bir aksiyon çağrısı (toplantı, demo vs.)
- İmza: Mertkan | Zeplin Media

Maksimum 100 kelime, doğal Türkçe."""

    response = requests.post("http://localhost:11434/api/generate", json={
        "model": "mistral",
        "prompt": prompt,
        "stream": False
    })
    
    return response.json()["response"]

def process_all(audited_file: str = "leads_audited.json"):
    with open(audited_file, encoding="utf-8") as f:
        leads = json.load(f)
    
    results = []
    
    for lead in leads:
        console.print(f"\n[cyan]Rapor üretiliyor:[/cyan] {lead['name']}")
        
        report = generate_report(lead)
        console.print(f"[green]✓ Analiz raporu hazır[/green]")
        
        email = generate_sales_email(lead, report)
        console.print(f"[green]✓ Satış e-postası hazır[/green]")
        
        lead["ai_report"] = report
        lead["ai_email"] = email
        results.append(lead)
        
        console.print(f"\n[bold]--- {lead['name']} RAPORU ---[/bold]")
        console.print(report)
        console.print(f"\n[bold yellow]--- SATIŞ E-POSTASI ---[/bold yellow]")
        console.print(email)
        console.print("─" * 60)
    
    with open("leads_final.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    console.print(f"\n[bold green]✅ Tüm raporlar hazır → leads_final.json[/bold green]")

if __name__ == "__main__":
    process_all()
