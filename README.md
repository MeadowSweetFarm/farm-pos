# Multi-Vendor Market POS System

Self-hosted system for multi-vendor markets. One checkout, automatic vendor split, variable marketing fees, inventory tracking, settlements, barcode labels, PDF/Excel reports, and Stripe Connect payout structure.

## Features

**Admin**
- Vendor management (fee %, PIN, Stripe account ID)
- Full inventory + low stock alerts
- Checkout / POS with barcode scanning
- Settlements with PDF, Excel, and CSV export
- Sales, product performance, and inventory history reports
- Stripe Connect payout preparation

**Vendors**
- Add/edit products with auto or custom barcodes
- Inventory adjustments with reason logging
- Own inventory and sales reports (gross / fee / net)
- Barcode label PDF download
- Excel and CSV exports

**Exports & Printing**
- Barcode label PDFs (individual or bulk)
- Settlement PDFs
- Excel (.xlsx) and CSV for all major reports

**Payments**
- Stripe Connect structure: store vendor connected account IDs and prepare transfers based on net settlements

## Quick Start

```bash
pip install -r requirements.txt
streamlit run market_pos_system.py
```

Open the URL (usually http://localhost:8501).

**Login**
- Admin → “Admin Login”
- Vendor → “Vendor Login” → select vendor → PIN (default `1234`)

## Stripe Connect Setup

1. Create a Stripe account and enable Connect.
2. Use test mode keys while developing.
3. In the app go to **Settings** and paste your Secret Key.
4. Vendors create Stripe Express or Standard accounts; store their `acct_...` IDs on the vendor record.
5. On the Settlements page you can prepare transfers (the code shows what would be sent). In production you would call `stripe.Transfer.create` with the connected account as destination.

**Important**: Real money movement requires production keys, proper Connect onboarding, and compliance with Stripe’s terms.

## Deployment

- Streamlit Community Cloud (free public/private URL)
- Local computer at the market + Wi-Fi
- Small VPS or always-on device

The SQLite database (`market_pos.db`) is created next to the script — back it up regularly.
