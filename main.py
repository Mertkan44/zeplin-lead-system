import os, json, base64, subprocess
from groq import Groq
from datetime import datetime

os.environ["GROQ_API_KEY"] = open('.env').read().split('=')[1].strip()
client = Groq(api_key=os.environ["GROQ_API_KEY"])

def ask(prompt):
    return client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Sen Zeplin Media'dan Mertkan'sin. Sadece Turkce yaziyorsun."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=400
    ).choices[0].message.content

def generate_email(lead):
    name = lead["name"]
    issues = ", ".join(lead["scoring"]["issues"])
    website = lead["website"].get("website_url", "YOK")
    instagram = lead["social"].get("instagram_url", "YOK")
    return ask("Sana bir ornek satis maili gosterecegim. Ayni tarz ve uzunlukta yeni bir mail yaz.\n\nORNEK MAIL:\n---\nKonu: Shubra icin kucuk bir gozlem 👀\n\nMerhaba,\n\nShubra'yi incelerken Instagram hesabinizin oldugunu gorduk, ancak web sitenizde SSL sertifikasi eksik. Bu kucuk detay, musteri guvenini dogrudan etkiliyor ve Google siralamalarinda sizi geri birakiyor.\n\nZeplin Media olarak SSL kurulumu, site hiz optimizasyonu ve sosyal medya yonetiminde uzmaniz. Kisa bir gorusmede size ucretsiz bir analiz sunabiliriz.\n\n15 dakikaniz var mi?\n\nMertkan | Zeplin Media | zeplinmedia.com\n---\n\nSIMDI BU ISLETME ICIN YAZ:\nRestoran adi: " + name + "\nWeb sitesi: " + website + "\nInstagram: " + instagram + "\nEksikler: " + issues + "\n\nAyni format, bu isletmeye ozel Turkce mail yaz.")

def generate_report(lead):
    name = lead["name"]
    issues = ", ".join(lead["scoring"]["issues"])
    website = lead["website"].get("website_url", "YOK")
    instagram = lead["social"].get("instagram_url", "YOK")
    score = lead["scoring"]["score"]
    return ask("Su isletmenin dijital varlik analizini yap.\n\nIsletme: " + name + "\nPuan: " + str(score) + "/100\nWeb: " + website + "\nInstagram: " + instagram + "\nEksikler: " + issues + "\n\nMaddeler halinde, max 100 kelime Turkce rapor yaz.")

def update_dashboard(data):
    json_bytes = json.dumps(data, ensure_ascii=True).encode('utf-8')
    b64 = base64.b64encode(json_bytes).decode('ascii')
    html = open('src/dashboard/template.html', encoding='utf-8').read()
    html = html.replace('__DATA__', b64)
    os.makedirs('public', exist_ok=True)
    with open('public/index.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print('Dashboard guncellendi!')

def git_push():
    try:
        subprocess.run(['git', 'add', 'public/index.html'], check=True)
        subprocess.run(['git', 'commit', '-m', 'dashboard update ' + datetime.now().strftime("%Y-%m-%d %H:%M")], check=True)
        subprocess.run(['git', 'push'], check=True)
        print('GitHub push tamamlandi!')
    except Exception as e:
        print('Push hatasi:', e)

# ANA AKIS
with open('leads_audited.json', encoding='utf-8') as f:
    leads = json.load(f)

# TEST: sadece ilk lead
test_leads = leads[:1]
results = []

for lead in test_leads:
    print(f"\nIslem: {lead['name']}")
    lead["ai_report"] = generate_report(lead)
    lead["ai_email"] = generate_email(lead)
    lead["last_analyzed"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    results.append(lead)
    print("Tamamlandi!")

for lead in leads[1:]:
    results.append(lead)

with open('leads_final.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

update_dashboard(results)
git_push()
print("\nHer sey tamamlandi!")
