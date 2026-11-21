# GPU Rental Price Data Layer

เก็บข้อมูลราคาเช่า GPU เพื่อใช้เป็นสัญญาณความต้องการ AI compute 

## ไฟล์

| ไฟล์ | หน้าที่ |
|---|---|
| `models.py` | ตารางแมปโมเดลเดียวที่ใช้ทั้งโปรเจกต์ (GetDeploying slug / RunPod id / Vast gpu_name), ชื่อหุ้น, attribution |
| `collect_daily.py` | ดึง RunPod + Vast.ai หนึ่งครั้ง -> `data/daily/YYYY-MM-DD.json` (วันที่ = UTC; รันซ้ำวันเดียวกันจะเขียนทับ) ถ้า source ไหนล้มจะบันทึก error ในไฟล์แล้วทำต่อ |
| `build_data.py` | โหลด weekly.csv (cache ที่ `data/cache/`) + snapshot รายวัน + ราคาหุ้น (yfinance) -> `site/gpu_data.json` |

## วิธีรัน

```
python collect_daily.py     # วันละครั้ง (ใช้เวลา ~3-5 นาที เพราะ Vast จำกัด 64 offers/query จึงต้องแบ่งช่วงราคา)
python build_data.py        # หลังเก็บข้อมูล หรือรันเมื่อไหร่ก็ได้
```

ต้องมี Python 3.11 + pandas, numpy, yfinance. ไม่ต้องใช้ API key.

## แหล่งข้อมูล

- GetDeploying weekly dataset (ราคามัธยฐานรายสัปดาห์ ON_DEMAND / SPOT / RESERVATION) — **CC BY 4.0 ต้องแสดง attribution ทุกที่ที่นำข้อมูลไปแสดง:**
  `GetDeploying, GPU rental price history, https://getdeploying.com/gpus, CC BY 4.0`
  (ข้อความนี้อยู่ใน `gpu_data.json` -> `meta.attribution`)
- RunPod public GraphQL `gpuTypes` (ราคา 0/null = ไม่มีขาย -> null)
- Vast.ai marketplace (`dph_total / num_gpus` = ราคาต่อ GPU ต่อชั่วโมง)
- ราคาหุ้น NVDA, CRWV, NBIS, ORCL จาก yfinance

## ข้อควรระวัง

- ข้อมูลรายสัปดาห์ของ GetDeploying ที่ใช้อยู่เริ่ม 2025-11-17 (53 สัปดาห์) ไม่ใช่ 2024-07
- Vast.ai ไม่มี MI300X
- ประวัติรายวันของเราเริ่มสะสมตั้งแต่วันแรกที่รัน `collect_daily.py` เท่านั้น
- วันที่เปิดตัวรุ่น GPU ใน `models.py` เป็นค่าประมาณ

## หน้าเว็บและกติกาคำนวณ

- หน้าจริง = `site/index.html` (อ่านข้อมูลจาก `site/gpu_data.json`)
- `drafts/` = ตัวอย่างเก่า/ที่ไม่เลือก (ไม่ publish พร้อม `site/`); `drafts/_draft-summary-1.html` คือต้นฉบับที่อนุมัติ
- กติกาคำนวณอยู่ที่ `build_data.py` ที่เดียว หน้าเว็บใช้ค่าที่คำนวณไว้ใน `derived` ก่อน (ถ้าไม่มี field จึงคำนวณเองฝั่งหน้าเว็บ)
- field ใน `derived` ต่อโมเดล (หน้าต่าง N = 4, 13, 26 สัปดาห์):
  - `price_change_{N}w_pct`, `offering_change_{N}w_pct`, `provider_change_{N}w_pct` (offering/provider ใช้ค่าเฉลี่ย 3 สัปดาห์)
  - `spot_discount_{N}w_ago_pct`, `spot_unreliable_{N}w_ago`, `spot_unreliable_latest` (สัปดาห์ที่ spot > on-demand = เทียบไม่ได้)
  - `regime_{N}w` = `loosening` / `tightening` / `demandUp` / `demandDown` / `mixed` (เกณฑ์ 2% ใช้ค่าไม่ปัดเศษ)
  - `early_warning` = `null` หรือ `{r4, r13}` (ภาพ 4 สัปดาห์ไม่ใช่ mixed, ต่างจาก 13 สัปดาห์, และเหมือนเดิมเมื่อสัปดาห์ก่อน)
  - `supply_regime` = `regime_13w`

## ระบบอัตโนมัติ (GitHub ล้วน)

- `.github/workflows/daily.yml` รันวันละ 2 รอบ (08:17 และ 20:47 เวลาไทย) และกดรันเองได้
- รอบแรกของวันเก็บราคา RunPod + Vast.ai → `data/daily/YYYY-MM-DD.json` (วันที่ UTC)
- รอบที่สองข้ามการเก็บถ้าวันนี้เก็บครบแล้ว แค่สร้าง `site/gpu_data.json` ใหม่
- bot commit ข้อมูลกลับเข้า repo แล้ว publish โฟลเดอร์ `site/` ขึ้น GitHub Pages
- GitHub cron คลาดได้หลายชั่วโมง ไม่เป็นไรเพราะเก็บวันละครั้ง
- `drafts/` (ตัวอย่างเก่า) ไม่ขึ้น repo

## กันข้อมูลค้างเงียบ ๆ

- `check_health.py` รันท้ายทุกรอบ ถ้าราคารายวันวันนี้ไม่มีหรือเก็บไม่ครบ, โหลดไฟล์ GetDeploying ไม่ได้, หรือข้อมูลรายสัปดาห์เก่าเกิน 10 วัน → งานจบเป็น "ล้มเหลว" แล้ว GitHub ส่งอีเมลแจ้ง
- ข้อมูลที่เก็บได้ยังถูกบันทึกและขึ้นเว็บก่อนตรวจ
- หน้าเว็บมีป้ายแดง "ข้อมูลค้าง" ข้างวันที่ เมื่อระบบไม่ได้อัปเดตเกิน 2 วัน, ราคารายวันเก่าเกิน 2 วันหรือเก็บไม่ครบ, หรือราคารายสัปดาห์เก่าเกิน 10 วัน (ชี้ที่ป้ายเพื่อดูรายละเอียด)
