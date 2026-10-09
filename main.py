import json
from datetime import datetime

from src.config import groq_client

client = None

def ask(prompt):
    global client
    if client is None:
        client = groq_client()
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
    with open('leads_final.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print('leads_final.json guncellendi (yalnizca yerel kopya).')

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

update_dashboard(results)
print("\nHer sey tamamlandi!")
