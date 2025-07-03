import streamlit as st
from datetime import date
from utils import calculate_amount
from zoho_api import fetch_items, create_estimate, fetch_estimates, download_estimate_pdf
import pandas as pd
import base64
from thefuzz import process

st.set_page_config(page_title="Zoho Estimator", layout="wide")
st.title("Zoho Estimate Generator")

menu = st.sidebar.radio("Choose Action", ["Create New Estimate", "Download Estimate"])

# Fetch items only once
@st.cache_data
def load_items():
    raw_items = fetch_items()
    processed = []
    for name, meta in raw_items.items():
        processed.append({
            "name": name,
            "sku": meta.get("sku", ""),
            "rate": float(meta["rate"]),
            "item_id": meta["item_id"],
        })
    return processed, raw_items

item_data, item_map = load_items()

def fuzzy_match_item(query):
    """Fuzzy match item name using both name and SKU."""
    if not query.strip():
        return None
    search_list = [f"{item['name']} {item['sku']}" for item in item_data]
    match, score = process.extractOne(query, search_list)
    if score > 60:
        for item in item_data:
            if f"{item['name']} {item['sku']}" == match:
                return item
    return None

# Initialize line items state
if "line_items" not in st.session_state:
    st.session_state.line_items = [{
        "Description": "",
        "Quantity": 0.0,
        "Price": 0.0,
        "Amount": 0.0,
    }]

if menu == "Create New Estimate":
    st.header("📝 Create New Estimate")

    to_customer = st.text_input("Estimate To", "")
    estimate_date = st.date_input("Estimate Date", value=date.today())
    capacity = st.text_input("Capacity (optional)", "")

    st.subheader("📦 Line Items")

    updated_items = []

    for idx, row in enumerate(st.session_state.line_items):
        cols = st.columns([5, 2, 2, 2, 1])
        desc_input = cols[0].selectbox(
            f"Item {idx+1}",
            options=[item["name"] for item in item_data],
            index=(next((i for i, item in enumerate(item_data) if item["name"] == row["Description"]), 0) if row["Description"] else 0),
            key=f"desc_{idx}",
            help="Search by name or SKU"
        )
        # Fuzzy match from raw user text if description was typed manually
        matched_item = next((i for i in item_data if i["name"] == desc_input), None)

        qty = cols[1].number_input("Qty", min_value=0.0, step=1.0, key=f"qty_{idx}", value=row["Quantity"])
        price = cols[2].number_input("Price", min_value=0.0, step=100.0, key=f"price_{idx}", value=matched_item["rate"] if matched_item else row["Price"])
        amount = qty * price
        cols[3].markdown(f"**₹{amount:.2f}**")
        remove = cols[4].button("➖", key=f"remove_{idx}")

        if not remove:
            updated_items.append({
                "Description": matched_item["name"] if matched_item else "",
                "Quantity": qty,
                "Price": price,
                "Amount": amount,
            })
        st.divider()
    # Update line items
    st.session_state.line_items = updated_items

    st.button("➕ Add Line Item", on_click=lambda: st.session_state.line_items.append({
        "Description": "",
        "Quantity": 0.0,
        "Price": 0.0,
        "Amount": 0.0,
    }))

    # Display current line items in read-only format
    if st.session_state.line_items:
        st.subheader("📋 Item Summary")
        display_df = pd.DataFrame(st.session_state.line_items)
        display_df = display_df[["Description", "Quantity", "Price", "Amount"]]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.divider()

    total_amount = sum(row["Amount"] for row in st.session_state.line_items)

    st.divider()
    handling_charge = st.number_input("Handling Charges", min_value=0.0, value=0.0, step=100.0)
    inspection_charge = st.number_input("Inspection Charges", min_value=0.0, value=0.0, step=500.0)

    subtotal = total_amount + handling_charge + inspection_charge
    tax = subtotal * 0.18
    grand_total = subtotal + tax

    st.markdown(f"**Total Amount (Items + Charges): ₹{subtotal:.2f}**")
    st.markdown(f"**GST @18%: ₹{tax:.2f}**")
    st.markdown(f"### 🧾 Grand Total: ₹{grand_total:.2f}")

    if st.button("Submit Estimate"):
        if not to_customer.strip():
            st.warning("⚠️ Please enter a customer name.")
        elif not any(item["Quantity"] > 0 for item in st.session_state.line_items):
            st.warning("⚠️ Add at least one valid line item.")
        else:
            line_items = []
            for row in st.session_state.line_items:
                name = row["Description"]
                if name in item_map:
                    line_items.append({
                        "item_id": item_map[name]["item_id"],
                        "name": name,
                        "rate": row["Price"],
                        "quantity": row["Quantity"]
                    })

            if "Handling Charges" in item_map and handling_charge > 0:
                line_items.append({
                    "item_id": item_map["Handling Charges"]["item_id"],
                    "name": "Handling Charges",
                    "rate": handling_charge,
                    "quantity": 1
                })

            if "Inspection Charges" in item_map and inspection_charge > 0:
                line_items.append({
                    "item_id": item_map["Inspection Charges"]["item_id"],
                    "name": "Inspection Charges",
                    "rate": inspection_charge,
                    "quantity": 1
                })

            estimate_data = {
                "customer_id": 2116695000000075007,
                "reference_number": to_customer + '\n' + capacity if capacity else to_customer,
                "date": str(estimate_date),
                "line_items": line_items,
                "is_inclusive_tax": False,
                "custom_subject": to_customer + "\n" + capacity if capacity else to_customer,
            }

            result = create_estimate(estimate_data)
            if "estimate" in result:
                estimate_id = result["estimate"]["estimate_id"]
                st.success("✅ Estimate Created Successfully!")
                st.download_button("📥 Download PDF", download_estimate_pdf(estimate_id), file_name="estimate.pdf")
                st.session_state.line_items = [{
                    "Description": "",
                    "Quantity": 0.0,
                    "Price": 0.0,
                    "Amount": 0.0,
                }]
            else:
                st.error("❌ Failed to create estimate.")

elif menu == "Download Estimate":
    st.header("📂 Download Estimates")

    estimates = fetch_estimates()
    if not estimates:
        st.info("No estimates available.")
    else:
        df = pd.DataFrame(estimates)
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df[['estimate_id', 'estimate_number', 'reference_number', 'customer_name', 'date', 'total']]
        # st.dataframe(df)

        selected = st.selectbox("Select Estimate", df['estimate_number'])
        if selected:
            estimate_row = df[df['estimate_number'] == selected].iloc[0]
            estimate_id = estimate_row['estimate_id']
            pdf_data = download_estimate_pdf(estimate_id)

            base64_pdf = base64.b64encode(pdf_data).decode('utf-8')
            pdf_display = f"""
            <object data="data:application/pdf;base64,{base64_pdf}" type="application/pdf" width="100%" height="700">
                <p>It appears you don't have a PDF plugin for this browser.
                You can <a href="data:application/pdf;base64,{base64_pdf}" download="{selected}.pdf">click here to download the PDF file.</a></p>
            </object>
            """
            st.markdown(pdf_display, unsafe_allow_html=True)
