# Zeplin Media Pricing Notes

Date: 2026-05-03

This file records the market anchors used for the service catalog. Prices in the app are not a public rate card; they are KOBI-focused sales estimate bands for lead scoring and opportunity sizing.

## Market Anchors

- Web design: 2026 Turkey tables show landing pages around 8K-25K TL and corporate websites around 25K-100K+ TL, KDV excluded. Zeplin web ranges are positioned as lead-focused agency work, not low-cost template work.
  Source: https://zbtmedia.com/blog/web-tasarim-fiyatlari-2026

- Social media: professional agency retainers are commonly shown around 15K-80K TL/month. Restaurant and local business examples are often around 15K-30K TL/month, with production scope changing the price.
  Source: https://zbtmedia.com/blog/sosyal-medya-ajansi-fiyatlari

- SEO: 2026 SEO guides list technical SEO around 8K-30K TL/month, local SEO around 8.5K-15K TL/month, and comprehensive SEO around 25K-75K TL/month.
  Source: https://www.remsajans.com/blog/seo-fiyatlari/

- Google Ads: freelance management can start around 3K-8K TL/month, while agency work is commonly framed around 8K-25K TL/month or 10-20% of media spend. Larger marketplace listings can run much higher.
  Sources:
  https://www.edvido.com/tr/blog/dijital-pazarlama/google-ads-ajansi-nasil-secilir
  https://www.edvido.com/tr/hizmetler/google-ads-yonetimi

- WhatsApp Business API: implementation/service pricing should be separated from Meta/BSP message costs. Supsis lists message/conversation charges such as Business Marketing 0.44 TL and Business Utility 0.38 TL, so Zeplin prices exclude usage fees.
  Source: https://doc.supsis.live/supsis/whatsapp/whatsappBusinessAPIPricing/

## Pricing Rules Used In The App

- KDV is excluded.
- Media spend is excluded for Google/Meta Ads.
- WhatsApp API/BSP/message fees are excluded.
- One-time builds are amortized in estimated monthly potential by dividing midpoint by 12.
- Monthly retainers use the midpoint directly in estimated monthly potential.
