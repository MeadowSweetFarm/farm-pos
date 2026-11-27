import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
import random
import string
import io
import barcode
from barcode.writer import ImageWriter
from PIL import Image
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side
import stripe
import os

# Database setup
DB_PATH = "market_pos.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        address TEXT,
        phone TEXT,
        email TEXT,
        admin_name TEXT,
        admin_address TEXT,
        admin_phone TEXT,
        admin_email TEXT,
        admin_pin TEXT DEFAULT '1234',
        website TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        company_name TEXT,
        address TEXT,
        phone TEXT,
        contact_name TEXT,
        fee_percent REAL DEFAULT 10.0,
        contact TEXT,
        pin TEXT DEFAULT '1234',
        stripe_account_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS location_vendors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER,
        vendor_id INTEGER,
        fee_percent REAL DEFAULT 10.0,
        pin TEXT DEFAULT '1234',
        UNIQUE(location_id, vendor_id),
        FOREIGN KEY (location_id) REFERENCES locations(id),
        FOREIGN KEY (vendor_id) REFERENCES vendors(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vendor_id INTEGER,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        barcode TEXT UNIQUE NOT NULL,
        inventory INTEGER DEFAULT 0,
        category TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (vendor_id) REFERENCES vendors(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS location_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER,
        product_id INTEGER,
        inventory INTEGER DEFAULT 0,
        UNIQUE(location_id, product_id),
        FOREIGN KEY (location_id) REFERENCES locations(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventory_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        location_id INTEGER,
        change_qty INTEGER,
        reason TEXT,
        notes TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (product_id) REFERENCES products(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location_id INTEGER,
        sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        total_amount REAL,
        payment_method TEXT,
        FOREIGN KEY (location_id) REFERENCES locations(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER,
        product_id INTEGER,
        vendor_id INTEGER,
        quantity INTEGER,
        unit_price REAL,
        line_total REAL,
        FOREIGN KEY (sale_id) REFERENCES sales(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    conn.commit()
    conn.close()

def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn

def generate_barcode():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def log_inventory_change(product_id, change_qty, reason, notes=""):
    conn = get_conn()
    conn.execute("INSERT INTO inventory_log (product_id, change_qty, reason, notes) VALUES (?, ?, ?, ?)",
                 (product_id, change_qty, reason, notes))
    conn.commit()
    conn.close()

def get_setting(key, default=""):
    conn = get_conn()
    row = pd.read_sql("SELECT value FROM settings WHERE key=?", conn, params=(key,))
    conn.close()
    return row.iloc[0,0] if not row.empty else default

def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
    conn.commit()
    conn.close()

# Ensure columns / tables exist for upgrades
try:
    conn = get_conn()
    conn.execute("ALTER TABLE sales ADD COLUMN location_id INTEGER")
    conn.execute("ALTER TABLE inventory_log ADD COLUMN location_id INTEGER")
    conn.execute("ALTER TABLE locations ADD COLUMN website TEXT")
    conn.commit()
    conn.close()
except:
    pass

init_db()

st.set_page_config(page_title="Farm Fresh Montana", layout="wide", initial_sidebar_state="expanded")

# Custom branding CSS — refined to better match the professional landing design
st.markdown("""
<style>
    .stApp {
        background-color: #F9F6F1;
    }
    h1, h2, h3, h4 {
        color: #1B4D3E !important;
        font-weight: 650;
    }
    .stButton > button {
        background-color: #1B4D3E;
        color: white;
        border-radius: 10px;
        border: none;
        font-weight: 600;
        padding: 0.55rem 1.1rem;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        background-color: #245C4A;
        transform: translateY(-1px);
    }
    [data-testid="stSidebar"] {
        background-color: #1B4D3E;
    }
    [data-testid="stSidebar"] * {
        color: #F9F6F1 !important;
    }
    .stMetric {
        background-color: white;
        padding: 16px;
        border-radius: 12px;
        border: 1px solid #E8E0D5;
        box-shadow: 0 2px 6px rgba(0,0,0,0.04);
    }
    div[data-testid="stExpander"] {
        background-color: white;
        border: 1px solid #E8E0D5;
        border-radius: 10px;
    }
    .hero-box {
        background: linear-gradient(135deg, #F9F6F1 0%, #F3EEE6 100%);
        padding: 20px 0 10px 0;
        border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)

# Consistent header across all pages
try:
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        st.image("logo_circular.jpg", width=120)
    with col_title:
        st.markdown("<h2 style='color:#1B4D3E; margin:0; padding-top:8px;'>Farm Fresh Montana</h2>", unsafe_allow_html=True)
        st.markdown("<p style='color:#5C4A3A; margin:0; font-size:0.95rem;'>Local Farms. Real Food. Strong Communities.</p>", unsafe_allow_html=True)
        if st.session_state.get("location_name"):
            st.markdown(f"<h4 style='color:#C4A35A; margin-top:6px;'>{st.session_state.location_name}</h4>", unsafe_allow_html=True)
except:
    st.title("Farm Fresh Montana")

st.markdown("---")

# Check for location detail view via query param
query_params = st.query_params
if "location_id" in query_params and st.session_state.role is None:
    try:
        loc_id = int(query_params["location_id"])
        loc = pd.read_sql("SELECT * FROM locations WHERE id=?", get_conn(), params=(loc_id,))
        if not loc.empty:
            l = loc.iloc[0]
            st.header(l["name"])
            if l.get("website"):
                st.markdown(f"**Website:** [{l['website']}]({l['website']})")
            st.markdown(f"**Address:** {l.get('address') or 'Not listed'}")
            st.markdown(f"**Phone:** {l.get('phone') or 'Not listed'}")
            st.markdown(f"**Email:** {l.get('email') or 'Not listed'}")
            if st.button("← Back to Home"):
                st.query_params.clear()
                st.rerun()
            st.stop()
    except:
        pass

# Role handling
if "role" not in st.session_state:
    st.session_state.role = None
    st.session_state.vendor_id = None
    st.session_state.vendor_name = None
    st.session_state.location_id = None
    st.session_state.location_name = None

def logout():
    st.session_state.role = None
    st.session_state.vendor_id = None
    st.session_state.vendor_name = None
    st.session_state.location_id = None
    st.session_state.location_name = None
    st.rerun()

if st.session_state.role is None:
    # Professional landing page matching the design concept
    st.markdown("""
    <style>
        .hero-title { color: #1B4D3E; font-size: 2.6rem; font-weight: 700; line-height: 1.2; margin-bottom: 12px; }
        .hero-sub { color: #5C4A3A; font-size: 1.05rem; max-width: 520px; }
        .feature-icon { font-size: 1.4rem; margin-bottom: 4px; }
        .section-title { text-align: center; color: #1B4D3E; font-size: 1.8rem; margin: 20px 0 10px 0; }
    </style>
    """, unsafe_allow_html=True)
    
    # Hero section
    col_text, col_img = st.columns([1.1, 1])
    with col_text:
        st.markdown('<div class="hero-title">Buy Fresh Local<br>Farm & Ranch Products</div>', unsafe_allow_html=True)
        st.markdown('<p class="hero-sub">Welcome to Farm Fresh Montana. We connect you with small farms and ranches across Montana to bring you fresh, local, and sustainable products. Support our local producers and strengthen our communities.</p>', unsafe_allow_html=True)
        st.markdown("""
        <div style="display:flex; gap:20px; margin-top:15px; flex-wrap:wrap;">
            <div style="text-align:center;"><div class="feature-icon">🌱</div><div style="font-size:0.85rem; color:#5C4A3A;">Support Local</div></div>
            <div style="text-align:center;"><div class="feature-icon">🌿</div><div style="font-size:0.85rem; color:#5C4A3A;">Sustainable</div></div>
            <div style="text-align:center;"><div class="feature-icon">❤️</div><div style="font-size:0.85rem; color:#5C4A3A;">Montana Grown</div></div>
            <div style="text-align:center;"><div class="feature-icon">🏠</div><div style="font-size:0.85rem; color:#5C4A3A;">Farm & Ranch Raised</div></div>
        </div>
        """, unsafe_allow_html=True)
    with col_img:
        try:
            st.image("hero_illustration.jpg", use_container_width=True)
        except:
            pass
    
    st.markdown("---")
    st.markdown('<div class="section-title">Find a Market Location</div>', unsafe_allow_html=True)
    
    search_term = st.text_input("Search by ZIP code or city", placeholder="Enter ZIP code or city name", label_visibility="collapsed")
    
    # Load locations
    locations_df = pd.read_sql("SELECT id, name, address, phone, email, website FROM locations", get_conn())
    
    if search_term:
        search_lower = search_term.lower()
        filtered = locations_df[
            locations_df["name"].str.lower().str.contains(search_lower, na=False) |
            locations_df["address"].str.lower().str.contains(search_lower, na=False)
        ]
    else:
        filtered = locations_df
    
    st.markdown("### Nearby Market Locations")
    if filtered.empty:
        st.info("No market locations found. Try a different ZIP code or city, or check back later.")
    else:
        for _, loc in filtered.iterrows():
            website_link = f" · [Website]({loc['website']})" if loc.get("website") else ""
            st.markdown(f"""
            **📍 [{loc['name']}](?location_id={loc['id']})**{website_link}  
            {loc['address'] or 'Address not listed'} · {loc['phone'] or ''}
            """)
    
    st.markdown("---")
    st.markdown('<div class="section-title">Quick Access</div>', unsafe_allow_html=True)
    
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        if st.button("System Manager\nStaff Access", use_container_width=True):
            st.session_state.role = "system_manager"
            st.rerun()
    with q2:
        if st.button("Location Admin\nManage Your Market", use_container_width=True):
            st.session_state.role = "location_select"
            st.rerun()
    with q3:
        if st.button("Vendor Login\nManage Your Products", use_container_width=True):
            st.session_state.role = "vendor_select"
            st.rerun()
    with q4:
        if st.button("Customer Checkout\nView Cart & Checkout", use_container_width=True):
            st.session_state.role = "customer_select"
            st.rerun()
    
    st.markdown("<br><p style='text-align:center; color:#8A7A68; font-size:0.9rem;'>Supporting Montana Farms & Ranches · Local. Fresh. Trusted.</p>", unsafe_allow_html=True)
    st.stop()

if st.session_state.role == "location_select":
    st.subheader("Select Location")
    locations = pd.read_sql("SELECT id, name FROM locations", get_conn())
    if locations.empty:
        st.warning("No locations yet. System Manager must create one first.")
        if st.button("Back"): logout()
        st.stop()
    sel = st.selectbox("Choose Location", locations["name"].tolist())
    pin = st.text_input("Admin PIN", type="password")
    if st.button("Login"):
        lrow = locations[locations.name == sel].iloc[0]
        conn = get_conn()
        actual = pd.read_sql("SELECT admin_pin FROM locations WHERE id=?", conn, params=(int(lrow.id),)).iloc[0,0]
        conn.close()
        if pin == (actual or "1234"):
            st.session_state.role = "location_admin"
            st.session_state.location_id = int(lrow.id)
            st.session_state.location_name = sel
            st.rerun()
        else:
            st.error("Incorrect PIN")
    if st.button("Back"): logout()
    st.stop()

if st.session_state.role == "customer_select":
    st.subheader("Select Location for Checkout")
    locations = pd.read_sql("SELECT id, name FROM locations", get_conn())
    if locations.empty:
        st.warning("No locations yet.")
        if st.button("Back"): logout()
        st.stop()
    sel = st.selectbox("Location", locations["name"].tolist())
    if st.button("Start Checkout"):
        lrow = locations[locations.name == sel].iloc[0]
        st.session_state.role = "customer"
        st.session_state.location_id = int(lrow.id)
        st.session_state.location_name = sel
        st.rerun()
    if st.button("Back"): logout()
    st.stop()

if st.session_state.role == "vendor_select":
    st.subheader("Select Your Vendor")
    vendors = pd.read_sql("SELECT id, name FROM vendors", get_conn())
    if vendors.empty:
        st.warning("No vendors yet.")
        if st.button("Back"): logout()
        st.stop()
    sel = st.selectbox("Choose Vendor", vendors["name"].tolist())
    pin = st.text_input("PIN", type="password", value="")
    if st.button("Login"):
        vrow = vendors[vendors.name == sel].iloc[0]
        conn = get_conn()
        actual_pin = pd.read_sql("SELECT pin FROM vendors WHERE id=?", conn, params=(int(vrow.id),)).iloc[0,0]
        conn.close()
        if pin == (actual_pin or "1234"):
            st.session_state.role = "vendor"
            st.session_state.vendor_id = int(vrow.id)
            st.session_state.vendor_name = sel
            st.rerun()
        else:
            st.error("Incorrect PIN")
    if st.button("Back"): logout()
    st.stop()

st.sidebar.success(f"Logged in as: **{(st.session_state.role or '').upper().replace('_',' ')}**" + 
                   (f" — {st.session_state.location_name}" if st.session_state.get("location_name") else "") +
                   (f" ({st.session_state.vendor_name})" if st.session_state.role == "vendor" else ""))
if st.sidebar.button("Logout"): logout()

if st.session_state.role == "system_manager":
    pages = ["All Locations", "Add Location", "All Vendors", "Dashboard", "Settings"]
elif st.session_state.role == "location_admin":
    pages = ["Location Dashboard", "Vendors", "All Inventory", "Checkout / POS", "Settlements & Payments", "Reports"]
elif st.session_state.role == "vendor":
    pages = ["My Inventory", "Add / Edit Products", "My Sales Report"]
else:
    pages = ["Checkout"]

page = st.sidebar.radio("Menu", pages)

# ==================== HELPER FUNCTIONS ====================
def create_barcode_image(code):
    try:
        bc = barcode.get('code128', code, writer=ImageWriter())
        buf = io.BytesIO()
        bc.write(buf)
        buf.seek(0)
        return buf
    except:
        return None

def generate_labels_pdf(products_df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 1*inch
    for _, row in products_df.iterrows():
        if y < 2*inch:
            c.showPage()
            y = height - 1*inch
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1*inch, y, row["name"][:40])
        c.setFont("Helvetica", 10)
        c.drawString(1*inch, y-15, f"${row['price']:.2f}  |  {row.get('vendor_name','')}")
        img_buf = create_barcode_image(row["barcode"])
        if img_buf:
            img = Image.open(img_buf)
            img_path = f"/tmp/bc_{row['barcode']}.png"
            img.save(img_path)
            c.drawImage(img_path, 1*inch, y-80, width=2.5*inch, height=0.6*inch)
        c.drawString(1*inch, y-95, row["barcode"])
        y -= 1.4*inch
    c.save()
    buffer.seek(0)
    return buffer

def generate_settlement_pdf(settlements, d1, d2, total_fees):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph(f"Settlement Report: {d1} to {d2}", styles["Title"]))
    elements.append(Spacer(1, 12))
    data = [["Vendor", "Gross Sales", "Fee %", "Fee", "Net to Vendor", "Items Sold"]]
    for _, r in settlements.iterrows():
        data.append([r["Vendor"], f"${r['Gross_Sales']:.2f}", f"{r['fee_percent']}%",
                     f"${r['Fee']:.2f}", f"${r['Net_to_Vendor']:.2f}", str(int(r["Items_Sold"]))])
    data.append(["TOTAL FEES TO YOU", "", "", f"${total_fees:.2f}", "", ""])
    t = Table(data, colWidths=[1.8*inch, 1.2*inch, 0.8*inch, 1*inch, 1.3*inch, 1*inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.grey),
        ("TEXTCOLOR", (0,0), (-1,0), colors.whitesmoke),
        ("ALIGN", (1,0), (-1,-1), "RIGHT"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,-1), (-1,-1), colors.lightgrey),
    ]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer

def to_excel(df, sheet_name="Data"):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]
        for col in worksheet.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 40)
            worksheet.column_dimensions[column].width = adjusted_width
        for cell in worksheet[1]:
            cell.font = Font(bold=True)
    output.seek(0)
    return output

# ==================== SYSTEM MANAGER PAGES ====================
if st.session_state.role == "system_manager":
    if page == "All Locations":
        st.header("All Locations")
        locs = pd.read_sql("SELECT id, name, address, phone, email, admin_name, admin_email FROM locations", get_conn())
        if not locs.empty:
            st.dataframe(locs, use_container_width=True)
        else:
            st.info("No locations yet.")

    elif page == "Add Location":
        st.header("Add New Location")
        with st.form("add_loc"):
            name = st.text_input("Location Name*")
            address = st.text_area("Address")
            phone = st.text_input("Phone")
            email = st.text_input("Email")
            website = st.text_input("Website (e.g. https://example.com)")
            st.markdown("**Location Administrator**")
            admin_name = st.text_input("Admin Name")
            admin_address = st.text_area("Admin Address")
            admin_phone = st.text_input("Admin Phone")
            admin_email = st.text_input("Admin Email")
            admin_pin = st.text_input("Admin PIN", value="1234")
            if st.form_submit_button("Create Location") and name:
                try:
                    conn = get_conn()
                    conn.execute("""INSERT INTO locations 
                        (name, address, phone, email, website, admin_name, admin_address, admin_phone, admin_email, admin_pin)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                 (name, address, phone, email, website or None, admin_name, admin_address, admin_phone, admin_email, admin_pin))
                    conn.commit()
                    conn.close()
                    st.success(f"Location '{name}' created.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Location name already exists.")

    elif page == "All Vendors":
        st.header("All Vendors (System-wide)")
        vendors = pd.read_sql("SELECT id, name, company_name, contact_name, phone FROM vendors", get_conn())
        st.dataframe(vendors, use_container_width=True)

    elif page == "Dashboard":
        st.header("System Dashboard")
        conn = get_conn()
        n_loc = pd.read_sql("SELECT COUNT(*) FROM locations", conn).iloc[0,0]
        n_ven = pd.read_sql("SELECT COUNT(*) FROM vendors", conn).iloc[0,0]
        n_prod = pd.read_sql("SELECT COUNT(*) FROM products", conn).iloc[0,0]
        conn.close()
        c1, c2, c3 = st.columns(3)
        c1.metric("Locations", n_loc)
        c2.metric("Vendors", n_ven)
        c3.metric("Products", n_prod)

    elif page == "Settings":
        st.header("System Settings")
        st.info("Stripe and other global settings can be managed here.")

# ==================== LOCATION ADMIN PAGES ====================
elif st.session_state.role == "location_admin":
    loc_id = st.session_state.location_id
    loc_name = st.session_state.location_name

    if page == "Location Dashboard":
        st.header(f"{loc_name} Dashboard")
        conn = get_conn()
        n_ven = pd.read_sql("SELECT COUNT(*) FROM location_vendors WHERE location_id=?", conn, params=(loc_id,)).iloc[0,0]
        conn.close()
        st.metric("Vendors at this location", n_ven)

    elif page == "Vendors":
        st.header(f"{loc_name} — Vendors")
        tab1, tab2 = st.tabs(["Add Vendor", "Current Vendors"])
        with tab1:
            mode = st.radio("Add", ["New Vendor", "Existing Vendor from any location"])
            if mode == "New Vendor":
                with st.form("new_v"):
                    name = st.text_input("Vendor / Business Name*")
                    company_name = st.text_input("Company Name")
                    contact_name = st.text_input("Contact Person")
                    phone = st.text_input("Phone")
                    address = st.text_area("Address")
                    fee = st.number_input("Marketing Fee %", 0.0, 50.0, 10.0)
                    pin = st.text_input("Vendor PIN", value="1234")
                    if st.form_submit_button("Create & Add") and name:
                        conn = get_conn()
                        c = conn.cursor()
                        c.execute("""INSERT INTO vendors (name, company_name, contact_name, phone, address, fee_percent, pin)
                                     VALUES (?,?,?,?,?,?,?)""",
                                  (name, company_name, contact_name, phone, address, fee, pin))
                        vid = c.lastrowid
                        c.execute("INSERT INTO location_vendors (location_id, vendor_id, fee_percent, pin) VALUES (?,?,?,?)",
                                  (loc_id, vid, fee, pin))
                        conn.commit()
                        conn.close()
                        st.success("Vendor created and added to this location.")
                        st.rerun()
            else:
                existing = pd.read_sql("SELECT id, name FROM vendors", get_conn())
                if not existing.empty:
                    sel_v = st.selectbox("Select Vendor", existing["name"].tolist())
                    fee = st.number_input("Fee % for this location", 0.0, 50.0, 10.0)
                    pin = st.text_input("PIN for this location", value="1234")
                    if st.button("Add to Location"):
                        vrow = existing[existing.name == sel_v].iloc[0]
                        try:
                            conn = get_conn()
                            conn.execute("INSERT INTO location_vendors (location_id, vendor_id, fee_percent, pin) VALUES (?,?,?,?)",
                                         (loc_id, int(vrow.id), fee, pin))
                            conn.commit()
                            conn.close()
                            st.success("Vendor added to this location.")
                            st.rerun()
                        except:
                            st.error("Already at this location.")
        with tab2:
            curr = pd.read_sql("""
                SELECT v.name, lv.fee_percent, lv.pin
                FROM location_vendors lv JOIN vendors v ON lv.vendor_id=v.id
                WHERE lv.location_id=?
            """, get_conn(), params=(loc_id,))
            st.dataframe(curr, use_container_width=True)

    elif page == "All Inventory":
        st.header(f"{loc_name} — Inventory")
        st.info("Inventory is tracked per location. Products appear once a vendor is added and products are created.")
        # Simplified view for now
        prods = pd.read_sql("""
            SELECT v.name as Vendor, p.name as Product, p.price, p.barcode,
                   COALESCE(li.inventory, 0) as inventory
            FROM location_vendors lv
            JOIN vendors v ON lv.vendor_id=v.id
            JOIN products p ON p.vendor_id=v.id
            LEFT JOIN location_inventory li ON li.product_id=p.id AND li.location_id=?
            WHERE lv.location_id=?
        """, get_conn(), params=(loc_id, loc_id))
        st.dataframe(prods, use_container_width=True)

    elif page == "Checkout / POS":
        st.header(f"{loc_name} — Checkout")
        st.info("Checkout uses location-specific inventory.")
        # Reuse similar cart logic; full implementation continues below in shared section if needed

    elif page == "Settlements & Payments":
        st.header(f"{loc_name} — Settlements")
        st.info("Settlements are calculated for this location only.")

    elif page == "Reports":
        st.header(f"{loc_name} — Reports")
        st.info("Location-scoped reports.")

# ==================== VENDOR & CUSTOMER (unchanged structure, scoped where possible) ====================
elif st.session_state.role in ("vendor", "customer"):
    if page == "Dashboard":
        st.header("Admin Dashboard")
        conn = get_conn()
        vendors_count = pd.read_sql("SELECT COUNT(*) as c FROM vendors", conn).iloc[0,0]
        products_count = pd.read_sql("SELECT COUNT(*) as c FROM products", conn).iloc[0,0]
        total_inv = pd.read_sql("SELECT SUM(inventory) as s FROM products", conn).iloc[0,0] or 0
        today_sales = pd.read_sql("SELECT COALESCE(SUM(total_amount),0) as s FROM sales WHERE date(sale_date)=date('now')", conn).iloc[0,0]
        conn.close()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Vendors", vendors_count)
        c2.metric("Products", products_count)
        c3.metric("Total Units", int(total_inv))
        c4.metric("Today's Sales", f"${today_sales:.2f}")
        
        low = pd.read_sql("""
            SELECT v.name as Vendor, p.name as Product, p.inventory, p.barcode
            FROM products p JOIN vendors v ON p.vendor_id=v.id WHERE p.inventory < 5 ORDER BY p.inventory
        """, get_conn())
        if not low.empty:
            st.subheader("Low Stock (< 5)")
            st.dataframe(low, use_container_width=True)

    elif page == "Vendors":
        st.header("Vendor Management")
        with st.expander("➕ Add New Vendor", expanded=True):
            with st.form("add_vendor"):
                name = st.text_input("Vendor / Business Name*")
                company_name = st.text_input("Company Name (if different)")
                contact_name = st.text_input("Contact Person Name")
                phone = st.text_input("Phone Number")
                address = st.text_area("Address")
                fee = st.number_input("Marketing Fee %", 0.0, 50.0, 10.0, 0.5)
                pin = st.text_input("PIN", value="1234")
                stripe_id = st.text_input("Stripe Connected Account ID (optional)")
                if st.form_submit_button("Add Vendor") and name:
                    try:
                        conn = get_conn()
                        conn.execute("""INSERT INTO vendors 
                            (name, company_name, contact_name, phone, address, fee_percent, pin, stripe_account_id) 
                            VALUES (?,?,?,?,?,?,?,?)""",
                                     (name, company_name, contact_name, phone, address, fee, pin, stripe_id or None))
                        conn.commit()
                        conn.close()
                        st.success(f"Vendor '{name}' added.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Name exists.")
        
        vendors = pd.read_sql("""SELECT id, name, company_name, contact_name, phone, address, 
                                 fee_percent, pin, stripe_account_id FROM vendors""", get_conn())
        if not vendors.empty:
            st.dataframe(vendors[["name","company_name","contact_name","phone","fee_percent"]], use_container_width=True)
            sel = st.selectbox("Edit Vendor", vendors["name"].tolist())
            row = vendors[vendors.name==sel].iloc[0]
            new_name = st.text_input("Vendor / Business Name", value=row.name, key="en")
            new_company = st.text_input("Company Name", value=row.company_name or "", key="eco")
            new_contact_name = st.text_input("Contact Person", value=row.contact_name or "", key="ecn")
            new_phone = st.text_input("Phone", value=row.phone or "", key="eph")
            new_address = st.text_area("Address", value=row.address or "", key="ead")
            new_fee = st.number_input("Fee %", value=float(row.fee_percent), key="ef")
            new_pin = st.text_input("PIN", value=row.pin or "1234", key="ep")
            new_stripe = st.text_input("Stripe Account ID", value=row.stripe_account_id or "", key="es")
            if st.button("Save"):
                conn = get_conn()
                conn.execute("""UPDATE vendors SET name=?, company_name=?, contact_name=?, phone=?, 
                                address=?, fee_percent=?, pin=?, stripe_account_id=? WHERE id=?""",
                             (new_name, new_company, new_contact_name, new_phone, new_address, 
                              new_fee, new_pin, new_stripe or None, int(row.id)))
                conn.commit()
                conn.close()
                st.success("Saved")
                st.rerun()

    elif page == "All Inventory":
        st.header("All Inventory")
        prods = pd.read_sql("""
            SELECT p.id, v.name as Vendor, p.name as Product, p.price, p.inventory, p.barcode, p.category
            FROM products p JOIN vendors v ON p.vendor_id=v.id ORDER BY v.name, p.name
        """, get_conn())
        if not prods.empty:
            st.dataframe(prods, use_container_width=True)
            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button("Excel", to_excel(prods), "inventory.xlsx")
            with col2:
                st.download_button("CSV", prods.to_csv(index=False), "inventory.csv")
            with col3:
                if st.button("Generate Barcode Labels PDF"):
                    pdf = generate_labels_pdf(prods.rename(columns={"Product":"name","Vendor":"vendor_name"}))
                    st.download_button("Download Labels PDF", pdf, "barcode_labels.pdf")

    elif page == "Checkout / POS":
        st.header("Checkout")
        try:
            st.image("farm_fresh_montana_logo.jpg", width=400)
        except:
            pass
        if "cart" not in st.session_state:
            st.session_state.cart = []
        barcode_input = st.text_input("Scan or type barcode")
        if barcode_input:
            prod = pd.read_sql("""
                SELECT p.id, p.name, p.price, p.inventory, p.vendor_id, v.name as vendor_name
                FROM products p JOIN vendors v ON p.vendor_id=v.id WHERE p.barcode=?
            """, get_conn(), params=(barcode_input,))
            if not prod.empty and prod.iloc[0].inventory > 0:
                p = prod.iloc[0]
                existing = next((i for i in st.session_state.cart if i["product_id"]==p.id), None)
                if existing:
                    if existing["qty"] < p.inventory:
                        existing["qty"] += 1
                else:
                    st.session_state.cart.append({
                        "product_id": int(p.id), "name": p.name, "price": float(p.price),
                        "qty": 1, "vendor_id": int(p.vendor_id), "vendor_name": p.vendor_name
                    })
                st.success(f"Added {p.name}")
                st.rerun()
            else:
                st.error("Not found or out of stock")
        if st.session_state.cart:
            cart_df = pd.DataFrame(st.session_state.cart)
            cart_df["line_total"] = cart_df["price"] * cart_df["qty"]
            st.dataframe(cart_df[["vendor_name","name","qty","price","line_total"]], use_container_width=True)
            total = cart_df["line_total"].sum()
            st.metric("Total", f"${total:.2f}")
            if st.button("✅ Process Sale", type="primary"):
                conn = get_conn()
                c = conn.cursor()
                c.execute("INSERT INTO sales (total_amount, payment_method) VALUES (?,?)", (total, "Cash/Card"))
                sale_id = c.lastrowid
                for item in st.session_state.cart:
                    c.execute("""INSERT INTO sale_items (sale_id, product_id, vendor_id, quantity, unit_price, line_total)
                                 VALUES (?,?,?,?,?,?)""", (sale_id, item["product_id"], item["vendor_id"],
                                 item["qty"], item["price"], item["price"]*item["qty"]))
                    c.execute("UPDATE products SET inventory = inventory - ? WHERE id=?", (item["qty"], item["product_id"]))
                    log_inventory_change(item["product_id"], -item["qty"], "Sale", f"Sale #{sale_id}")
                conn.commit()
                conn.close()
                st.success(f"Sale #{sale_id} for ${total:.2f}")
                st.session_state.cart = []
                st.rerun()
            if st.button("Clear Cart"):
                st.session_state.cart = []
                st.rerun()

    elif page == "Settlements & Payments":
        st.header("Settlements & Stripe Payouts")
        d1 = st.date_input("From", date.today()-timedelta(days=7))
        d2 = st.date_input("To", date.today())
        settlements = pd.read_sql("""
            SELECT v.name as Vendor, v.fee_percent, v.stripe_account_id,
                   SUM(si.line_total) as Gross_Sales, SUM(si.quantity) as Items_Sold
            FROM sale_items si JOIN sales s ON si.sale_id=s.id JOIN vendors v ON si.vendor_id=v.id
            WHERE date(s.sale_date) BETWEEN ? AND ? GROUP BY v.id
        """, get_conn(), params=(d1.isoformat(), d2.isoformat()))
        if not settlements.empty:
            settlements["Fee"] = settlements["Gross_Sales"] * (settlements["fee_percent"]/100)
            settlements["Net_to_Vendor"] = settlements["Gross_Sales"] - settlements["Fee"]
            st.dataframe(settlements[["Vendor","Gross_Sales","fee_percent","Fee","Net_to_Vendor","Items_Sold","stripe_account_id"]].style.format({
                "Gross_Sales":"${:.2f}","Fee":"${:.2f}","Net_to_Vendor":"${:.2f}"
            }), use_container_width=True)
            total_fees = settlements["Fee"].sum()
            st.metric("Total Fees to You", f"${total_fees:.2f}")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button("Excel", to_excel(settlements), f"settlement_{d1}_{d2}.xlsx")
            with col2:
                st.download_button("CSV", settlements.to_csv(index=False), f"settlement_{d1}_{d2}.csv")
            with col3:
                pdf = generate_settlement_pdf(settlements, d1, d2, total_fees)
                st.download_button("PDF Report", pdf, f"settlement_{d1}_{d2}.pdf")
            
            st.subheader("Stripe Connect Payouts")
            stripe_key = get_setting("stripe_secret_key")
            if not stripe_key:
                st.warning("Add your Stripe secret key in Settings first.")
            else:
                stripe.api_key = stripe_key
                if st.button("Prepare Stripe Transfers (Test Mode)"):
                    st.info("In production this would create Transfers to each vendor's connected account.")
                    for _, r in settlements.iterrows():
                        if r["stripe_account_id"] and r["Net_to_Vendor"] > 0:
                            st.write(f"Would transfer ${r['Net_to_Vendor']:.2f} to {r['Vendor']} ({r['stripe_account_id']})")
                        else:
                            st.write(f"{r['Vendor']}: No Stripe account or zero net")

    elif page == "Reports":
        st.header("Reports")
        tab1, tab2, tab3 = st.tabs(["Sales by Vendor", "Product Performance", "Inventory History"])
        with tab1:
            d1 = st.date_input("From", date.today()-timedelta(days=30), key="r1")
            d2 = st.date_input("To", date.today(), key="r2")
            df = pd.read_sql("""
                SELECT v.name as Vendor, SUM(si.line_total) as Sales, SUM(si.quantity) as Units
                FROM sale_items si JOIN sales s ON si.sale_id=s.id JOIN vendors v ON si.vendor_id=v.id
                WHERE date(s.sale_date) BETWEEN ? AND ? GROUP BY v.id ORDER BY Sales DESC
            """, get_conn(), params=(d1.isoformat(), d2.isoformat()))
            if not df.empty:
                st.dataframe(df, use_container_width=True)
                st.bar_chart(df.set_index("Vendor")["Sales"])
                st.download_button("Excel", to_excel(df), "sales_by_vendor.xlsx")
        with tab2:
            df = pd.read_sql("""
                SELECT v.name as Vendor, p.name as Product, SUM(si.quantity) as Units_Sold,
                       SUM(si.line_total) as Revenue, p.inventory as Current_Stock
                FROM sale_items si JOIN products p ON si.product_id=p.id JOIN vendors v ON p.vendor_id=v.id
                GROUP BY p.id ORDER BY Revenue DESC
            """, get_conn())
            st.dataframe(df, use_container_width=True)
            st.download_button("Excel", to_excel(df), "product_performance.xlsx")
        with tab3:
            df = pd.read_sql("""
                SELECT p.name as Product, v.name as Vendor, il.change_qty, il.reason, il.notes, il.timestamp
                FROM inventory_log il JOIN products p ON il.product_id=p.id JOIN vendors v ON p.vendor_id=v.id
                ORDER BY il.timestamp DESC LIMIT 200
            """, get_conn())
            st.dataframe(df, use_container_width=True)
            st.download_button("Excel", to_excel(df), "inventory_history.xlsx")

    elif page == "Settings":
        st.header("Settings")
        st.subheader("Stripe Connect")
        st.write("""
        **Setup steps:**
        1. Create a Stripe account and enable Connect.
        2. Get your Secret Key (use test key for development).
        3. Vendors create Stripe Express/Standard accounts and you store their account IDs.
        4. Use Transfers or Destination Charges to send net amounts.
        """)
        current_key = get_setting("stripe_secret_key")
        new_key = st.text_input("Stripe Secret Key", value=current_key, type="password")
        if st.button("Save Stripe Key"):
            set_setting("stripe_secret_key", new_key)
            st.success("Saved")

# ==================== VENDOR PAGES ====================
elif st.session_state.role == "vendor":
    vid = st.session_state.vendor_id
    vname = st.session_state.vendor_name
    
    if page == "My Inventory":
        st.header(f"{vname} — Inventory")
        prods = pd.read_sql("SELECT id, name, price, inventory, barcode, category FROM products WHERE vendor_id=?",
                            get_conn(), params=(vid,))
        if not prods.empty:
            st.dataframe(prods, use_container_width=True)
            col1, col2 = st.columns(2)
            with col1:
                st.download_button("Excel", to_excel(prods), f"{vname}_inventory.xlsx")
            with col2:
                st.download_button("CSV", prods.to_csv(index=False), f"{vname}_inventory.csv")
            if st.button("Barcode Labels PDF"):
                pdf = generate_labels_pdf(prods.assign(vendor_name=vname))
                st.download_button("Download Labels", pdf, f"{vname}_labels.pdf")
        else:
            st.info("No products yet.")

    elif page == "Add / Edit Products":
        st.header(f"{vname} — Add / Edit Products")
        st.write("Use this page to add new products or update existing ones.")
        
        # Add form - simple, no nested issues
        st.subheader("Add New Product")
        name = st.text_input("Product Name")
        price = st.number_input("Price", min_value=0.01, value=5.0, step=0.25)
        qty = st.number_input("Initial Quantity", min_value=0, value=0)
        category = st.text_input("Category")
        if st.button("Add Product", type="primary"):
            if name:
                bc = generate_barcode()
                try:
                    conn = get_conn()
                    c = conn.cursor()
                    c.execute("INSERT INTO products (vendor_id, name, price, barcode, inventory, category) VALUES (?,?,?,?,?,?)",
                              (vid, name, price, bc, qty, category or None))
                    pid = c.lastrowid
                    conn.commit()
                    conn.close()
                    if qty:
                        log_inventory_change(pid, qty, "Initial delivery")
                    st.success(f"Added {name} (Barcode: {bc})")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error adding product: {e}")
            else:
                st.warning("Please enter a product name.")
        
        st.markdown("---")
        st.subheader("Edit Existing Products")
        
        prods = pd.read_sql("SELECT id, name, price, inventory, barcode FROM products WHERE vendor_id=?",
                            get_conn(), params=(vid,))
        
        if prods.empty:
            st.info("No products yet.")
        else:
            for idx, row in prods.iterrows():
                st.markdown(f"**{row['name']}** — ${row['price']:.2f} — Qty: {int(row['inventory'])} — {row['barcode']}")
                new_price = st.number_input("New Price", value=float(row['price']), min_value=0.01, key=f"price_{row['id']}")
                adj = st.number_input("Inventory Adjust (+/-)", value=0, step=1, key=f"adj_{row['id']}")
                if st.button("Save", key=f"save_{row['id']}"):
                    conn = get_conn()
                    conn.execute("UPDATE products SET price=?, inventory=inventory+? WHERE id=?",
                                 (new_price, adj, int(row['id'])))
                    conn.commit()
                    conn.close()
                    if adj:
                        log_inventory_change(int(row['id']), adj, "Adjustment", "")
                    st.success("Saved")
                    st.rerun()
                if st.button("Delete", key=f"del_{row['id']}"):
                    conn = get_conn()
                    conn.execute("DELETE FROM products WHERE id=?", (int(row['id']),))
                    conn.commit()
                    conn.close()
                    st.success("Deleted")
                    st.rerun()
                st.markdown("---")

    elif page == "My Sales Report":
        st.header(f"{vname} — Sales")
        d1 = st.date_input("From", date.today()-timedelta(days=30))
        d2 = st.date_input("To", date.today())
        sales = pd.read_sql("""
            SELECT date(s.sale_date) as Date, p.name as Product, si.quantity as Qty,
                   si.unit_price as Price, si.line_total as Total
            FROM sale_items si JOIN sales s ON si.sale_id=s.id JOIN products p ON si.product_id=p.id
            WHERE si.vendor_id=? AND date(s.sale_date) BETWEEN ? AND ?
            ORDER BY s.sale_date DESC
        """, get_conn(), params=(vid, d1.isoformat(), d2.isoformat()))
        if not sales.empty:
            st.dataframe(sales, use_container_width=True)
            total = sales["Total"].sum()
            fee_pct = pd.read_sql("SELECT fee_percent FROM vendors WHERE id=?", get_conn(), params=(vid,)).iloc[0,0]
            fee = total * (fee_pct/100)
            net = total - fee
            c1,c2,c3 = st.columns(3)
            c1.metric("Gross", f"${total:.2f}")
            c2.metric(f"Fee ({fee_pct}%)", f"${fee:.2f}")
            c3.metric("Net", f"${net:.2f}")
            col1, col2 = st.columns(2)
            with col1:
                st.download_button("Excel", to_excel(sales), f"{vname}_sales.xlsx")
            with col2:
                st.download_button("CSV", sales.to_csv(index=False), f"{vname}_sales.csv")
        else:
            st.info("No sales in period.")

# ==================== CUSTOMER CHECKOUT ====================
elif st.session_state.role == "customer":
    st.header("Farm Fresh Montana — Checkout")
    st.markdown("Scan or type product barcodes to add items to your order.")
    
    if "cart" not in st.session_state:
        st.session_state.cart = []
    
    barcode_input = st.text_input("Scan or type barcode", key="cust_barcode")
    if barcode_input:
        prod = pd.read_sql("""
            SELECT p.id, p.name, p.price, p.inventory, p.vendor_id, v.name as vendor_name
            FROM products p JOIN vendors v ON p.vendor_id=v.id WHERE p.barcode=?
        """, get_conn(), params=(barcode_input,))
        if not prod.empty and prod.iloc[0].inventory > 0:
            p = prod.iloc[0]
            existing = next((i for i in st.session_state.cart if i["product_id"]==p.id), None)
            if existing:
                if existing["qty"] < p.inventory:
                    existing["qty"] += 1
            else:
                st.session_state.cart.append({
                    "product_id": int(p.id), "name": p.name, "price": float(p.price),
                    "qty": 1, "vendor_id": int(p.vendor_id), "vendor_name": p.vendor_name
                })
            st.success(f"Added {p.name}")
            st.rerun()
        else:
            st.error("Not found or out of stock")
    
    if st.session_state.cart:
        cart_df = pd.DataFrame(st.session_state.cart)
        cart_df["line_total"] = cart_df["price"] * cart_df["qty"]
        st.dataframe(cart_df[["vendor_name","name","qty","price","line_total"]], use_container_width=True)
        total = cart_df["line_total"].sum()
        st.metric("Total Due", f"${total:.2f}")
        
        st.markdown("---")
        payment_method = st.selectbox("Payment Method", ["Cash", "Card", "Other"])
        
        amount_tendered = 0.0
        change_due = 0.0
        if payment_method == "Cash":
            amount_tendered = st.number_input("Amount Tendered", min_value=0.0, value=float(total), step=0.25, format="%.2f")
            change_due = max(0.0, amount_tendered - total)
            if amount_tendered >= total:
                st.success(f"Change Due: **${change_due:.2f}**")
            else:
                st.warning(f"Still owed: **${total - amount_tendered:.2f}**")
        
        col1, col2 = st.columns(2)
        with col1:
            can_complete = (payment_method != "Cash") or (amount_tendered >= total)
            if st.button("✅ Complete Purchase", type="primary", use_container_width=True, disabled=not can_complete):
                conn = get_conn()
                c = conn.cursor()
                loc_id = st.session_state.get("location_id")
                c.execute("INSERT INTO sales (location_id, total_amount, payment_method) VALUES (?,?,?)", 
                          (loc_id, total, payment_method))
                sale_id = c.lastrowid
                for item in st.session_state.cart:
                    c.execute("""INSERT INTO sale_items (sale_id, product_id, vendor_id, quantity, unit_price, line_total)
                                 VALUES (?,?,?,?,?,?)""", (sale_id, item["product_id"], item["vendor_id"],
                                 item["qty"], item["price"], item["price"]*item["qty"]))
                    c.execute("UPDATE products SET inventory = inventory - ? WHERE id=?", (item["qty"], item["product_id"]))
                    log_inventory_change(item["product_id"], -item["qty"], "Sale", f"Sale #{sale_id}")
                conn.commit()
                conn.close()
                st.success(f"Thank you! Purchase #{sale_id} for ${total:.2f} completed ({payment_method}).")
                if payment_method == "Cash" and change_due > 0:
                    st.info(f"Please give customer **${change_due:.2f}** in change.")
                st.session_state.cart = []
                st.balloons()
                st.rerun()
        with col2:
            if st.button("Clear Cart", use_container_width=True):
                st.session_state.cart = []
                st.rerun()
    else:
        st.info("Your cart is empty. Scan a product to begin.")

st.sidebar.markdown("---")
st.sidebar.caption("Barcode labels, PDF reports, Excel exports, and Stripe Connect structure included.")
