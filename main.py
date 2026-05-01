import os, json, base64
from groq import Groq
from datetime import datetime

os.environ["GROQ_API_KEY"] = open('.env').read().split('=')[1].strip()
client = Groq(api_key=os.environ["GROQ_API_KEY"])

def ask(prompt, system="Sen Zeplin Media'dan Mertkan'sin. Sadece Turkce yaziyorsun."):
    return client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        max_tokens=400
    ).choices[0].message.content

def generate_report(lead):
    name = lead["name"]
    issues = ", ".join(lead["scoring"]["issues"])
    website = lead["website"].get("website_url", "YOK")
    instagram = lead["social"].get("instagram_url", "YOK")
    score = lead["scoring"]["score"]

    return ask(f"""Su isletmenin dijital varlik analizini yap ve kisa bir rapor yaz.

Isletme: {name}
Puan: {score}/100
Web sitesi: {website}
Instagram: {instagram}
Eksikler: {issues}

Maddeler halinde, max 100 kelime, Turkce.""")

def generate_email(lead):
    name = lead["name"]
    issues = ", ".join(lead["scoring"]["issues"])
    website = lead["website"].get("website_url", "YOK")
    instagram = lead["social"].get("instagram_url", "YOK")

    return ask(f"""Sana bir ornek satis maili gosterecegim. Ayni tarz ve uzunlukta yeni bir mail yaz.

ORNEK MAIL:
---
Konu: Shubra icin kucuk bir gozlem 👀

Merhaba,

Shubra'yi incelerken Instagram hesabinizin oldugunu gorduk, ancak web sitenizde SSL sertifikasi eksik. Bu kucuk detay, musteri guvenini dogrudan etkiliyor ve Google siralamalarinda sizi geri birakiyor.

Zeplin Media olarak SSL kurulumu, site hiz optimizasyonu ve sosyal medya yonetiminde uzmaniz. Kisa bir gorusmede size ucretsiz bir analiz sunabiliriz.

15 dakikaniz var mi?

Mertkan | Zeplin Media | zeplinmedia.com
---

SIMDI BU ISLETME ICIN YAZ:
Restoran adi: {name}
Web sitesi: {website}
Instagram: {instagram}
Eksikler: {issues}

Ayni format, bu isletmeye ozel Turkce mail yaz.""")

def update_dashboard(data):
    json_bytes = json.dumps(data, ensure_ascii=True).encode('utf-8')
    b64 = base64.b64encode(json_bytes).decode('ascii')

    html = """<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8"><title>Zeplin Media</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0f0f0f;color:#e0e0e0;font-family:system-ui,sans-serif}header{background:#111;border-bottom:1px solid #222;padding:20px 32px;display:flex;align-items:center;gap:12px}header h1{font-size:18px;font-weight:600;color:#fff}header span{background:#FF2D78;color:#fff;font-size:11px;padding:3px 10px;border-radius:20px}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;padding:24px 32px 0}.stat{background:#161616;border:1px solid #222;border-radius:12px;padding:20px}.stat .num{font-size:32px;font-weight:700;color:#FF2D78}.stat .label{font-size:12px;color:#666;margin-top:4px}.leads{padding:24px 32px;display:grid;gap:16px}.card{background:#161616;border:1px solid #222;border-radius:12px;padding:24px}.card-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px}.card-header h2{font-size:16px;font-weight:600}.grade{width:40px;height:40px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:18px}.grade-A{background:#1a3a1a;color:#4ade80}.grade-B{background:#2a2a1a;color:#fbbf24}.grade-C{background:#2a1a1a;color:#f87171}.grade-D{background:#1a1a1a;color:#666}.issues{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}.issue{background:#1a1212;border:1px solid #3a1a1a;color:#f87171;font-size:11px;padding:4px 10px;border-radius:6px}.ops{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}.op{background:#121a12;border:1px solid #1a3a1a;color:#4ade80;font-size:11px;padding:4px 10px;border-radius:6px}.score-bar{height:6px;background:#222;border-radius:3px;margin-bottom:16px}.score-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,#FF2D78,#ff6b9d)}.btn{background:#1a1a2a;border:1px solid #2a2a4a;color:#818cf8;font-size:12px;padding:8px 16px;border-radius:8px;cursor:pointer;width:100%;text-align:left;margin-bottom:8px}.btn-green{background:#121a12;border-color:#1a3a1a;color:#4ade80}.box{background:#111;border:1px solid #222;border-radius:8px;padding:16px;font-size:13px;line-height:1.7;color:#aaa;white-space:pre-wrap;display:none;margin-bottom:8px}.links{display:flex;gap:8px;margin-top:12px}.link{font-size:11px;color:#666;text-decoration:none;border:1px solid #2a2a2a;padding:4px 10px;border-radius:6px}.meta{font-size:11px;color:#444;margin-top:8px}</style>
</head><body>
<header><h1>Zeplin Media</h1><span>Lead Dashboard</span></header>
<div class="stats" id="stats"></div>
<div class="leads" id="leads"></div>
<script>
var leads=JSON.parse(atob(\"""" + b64 + """\"));
var t=leads.length,nw=leads.filter(function(l){return !l.website.has_website}).length,ni=leads.filter(function(l){return !l.social.has_instagram}).length,av=Math.round(leads.reduce(function(a,b){return a+b.scoring.score},0)/t);
document.getElementById('stats').innerHTML='<div class=stat><div class=num>'+t+'</div><div class=label>Toplam Lead</div></div><div class=stat><div class=num>'+nw+'</div><div class=label>Web Yok</div></div><div class=stat><div class=num>'+ni+'</div><div class=label>Instagram Yok</div></div><div class=stat><div class=num>'+av+'</div><div class=label>Ort Puan</div></div>';
document.getElementById('leads').innerHTML=leads.map(function(l,i){
var s=l.scoring;
var iss=s.issues.map(function(x){return'<span class=issue>'+x+'</span>'}).join('');
var ops=s.opportunities.map(function(x){return'<span class=op>'+x+'</span>'}).join('');
var lnk='';
if(l.maps_url)lnk+='<a class=link href="'+l.maps_url+'" target=_blank>Maps</a>';
if(l.website&&l.website.website_url)lnk+='<a class=link href="'+l.website.website_url+'" target=_blank>Web</a>';
if(l.social&&l.social.instagram_url)lnk+='<a class=link href="'+l.social.instagram_url+'" target=_blank>Instagram</a>';
var ai='';
if(l.ai_report){ai='<button class=btn onclick="tog('+i+',0)">AI Raporu</button><div class=box id="r'+i+'">'+l.ai_report+'</div><button class="btn btn-green" onclick="tog('+i+',1)">Satis Maili</button><div class=box id="e'+i+'">'+l.ai_email+'</div>';}
var meta=l.last_analyzed?'<div class=meta>Son analiz: '+l.last_analyzed+'</div>':'';
return'<div class=card><div class=card-header><h2>'+l.name+'</h2><div class="grade grade-'+s.grade+'">'+s.grade+'</div></div><div class=score-bar><div class=score-fill style="width:'+s.score+'%"></div></div><div class=issues>'+iss+'</div><div class=ops>'+ops+'</div><div class=links>'+lnk+'</div>'+ai+meta+'</div>';
}).join('');
function tog(i,t){var id=t===0?'r'+i:'e'+i;var e=document.getElementById(id);e.style.display=e.style.display==='block'?'none':'block';}
</script></body></html>"""

    with open('src/dashboard/static/index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('Dashboard guncellendi!')

# --- ANA AKIS ---
with open('leads_audited.json', encoding='utf-8') as f:
    leads = json.load(f)

# Sadece ilk lead test icin
test_leads = leads[:1]

results = []
for lead in test_leads:
    print(f"\nIslem: {lead['name']}")
    
    print("  Rapor uretiliyor...")
    lead["ai_report"] = generate_report(lead)
    print("  Mail uretiliyor...")
    lead["ai_email"] = generate_email(lead)
    lead["last_analyzed"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    results.append(lead)
    print(f"  Tamamlandi!")

# Kalan leadleri ekle (raporsuz)
for lead in leads[1:]:
    results.append(lead)

with open('leads_final.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

update_dashboard(results)
print("\nHer sey tamamlandi!")
