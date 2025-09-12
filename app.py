import streamlit as st
from datetime import date
from utils import calculate_amount
from zoho_api import fetch_items, create_estimate, fetch_estimates, download_estimate_pdf
from components import ItemSelector, FormValidator, PDFHandler
import pandas as pd
import base64
from thefuzz import process
from streamlit.components.v1 import html
import tempfile

st.set_page_config(page_title="Zoho Estimator", layout="wide")
st.title("JSV DISTRIBUTERS")

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

# Initialize item selector
item_selector = ItemSelector(item_data)

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

    # Customer information with validation
    to_customer = st.text_input("Estimate To", "", placeholder="Enter customer name...")
    
    # Real-time validation for customer name
    customer_valid, customer_error = FormValidator.validate_customer_name(to_customer)
    if to_customer and not customer_valid:
        st.error(customer_error)
    
    estimate_date = st.date_input("Estimate Date", value=date.today())
    capacity = st.text_input("Capacity (optional)", "", placeholder="Enter capacity details...")

    st.subheader("📦 Line Items")

    updated_items = []
    running_total = 0
    item_deleted = False

    for idx, row in enumerate(st.session_state.line_items):
        # Compact line item layout without extra containers
        # Header row with item number and running total
        header_cols = st.columns([2, 2, 1, 1, 1, 1])
        with header_cols[0]:
            st.caption(f"**Item {idx+1}**")
        with header_cols[5]:
            if idx > 0:  # Show running total from second item onwards
                st.caption(f"*Total: ₹{running_total:,.0f}*")
        
        # Main input row - tighter spacing
        cols = st.columns([5, 1.5, 1.5, 1.5, 0.8])
        
        # Single dropdown for search and select
        with cols[0]:
            current_search = row.get("Description", "")
            selected_item = item_selector.render_item_selector(
                key=f"item_{idx}",
                current_value=current_search
            )
            
            # Update session state if item is selected
            if selected_item:
                st.session_state[f"selected_item_{idx}"] = selected_item

        # Get the selected item for this row
        current_item = st.session_state.get(f"selected_item_{idx}")
        
        # Initialize widget values in session state if not exists
        qty_key = f"qty_{idx}"
        price_key = f"price_{idx}"
        
        if qty_key not in st.session_state:
            st.session_state[qty_key] = int(row["Quantity"]) if row["Quantity"] else 0
        
        if price_key not in st.session_state:
            default_price = current_item["rate"] if current_item else row["Price"]
            st.session_state[price_key] = float(default_price) if default_price else 0.0
        
        # Auto-update price when item is selected
        if current_item and st.session_state[price_key] == 0.0:
            st.session_state[price_key] = float(current_item["rate"])
        
        # Compact inputs with aligned delete button
        qty = cols[1].number_input(
            "Qty", 
            min_value=0, 
            step=1, 
            key=qty_key,
            help="Quantity",
            format="%d",
            label_visibility="collapsed"
        )
        
        price = cols[2].number_input(
            "Price", 
            min_value=0.0, 
            step=50.0,
            key=price_key,
            help="Price per unit",
            format="%.2f",
            label_visibility="collapsed"
        )
        
        amount = float(qty) * float(price)
        
        # Compact amount display
        with cols[3]:
            st.text_input(
                "Amount",
                value=f"₹{amount:,.2f}",
                disabled=True,
                label_visibility="collapsed",
                help="Total amount",
                key=f"amount_{idx}"  # Add unique key to fix duplicate ID error
            )
        
        # Aligned delete button
        with cols[4]:
            remove = st.button("🗑️", key=f"remove_{idx}", help="Remove item", use_container_width=True)

        # Compact validation messages
        if qty > 0 and not current_item:
            st.error(f"⚠️ Select item {idx+1}", icon="⚠️")
        elif qty > 0 and price <= 0:
            st.error(f"❌ Price required for item {idx+1}", icon="❌")

        if not remove:
            updated_items.append({
                "Description": current_item["name"] if current_item else "",
                "Quantity": float(qty),
                "Price": float(price),
                "Amount": amount,
                "item_data": current_item
            })
            running_total += amount
        else:
            # Clean up session state when item is removed
            keys_to_clean = [f"selected_item_{idx}", f"qty_{idx}", f"price_{idx}"]
            for key in keys_to_clean:
                if key in st.session_state:
                    del st.session_state[key]
            item_deleted = True
        
        # Minimal spacing between items
        if idx < len(st.session_state.line_items) - 1:
            st.write("")  # Just a small gap instead of divider
    
    # Update line items
    st.session_state.line_items = updated_items
    
    # Force refresh after deletion (outside the loop)
    if item_deleted:
        st.rerun()

    # Add new line item button
    col1, col2 = st.columns([1, 3])
    with col1:
        st.button("➕ Add Line Item", on_click=lambda: st.session_state.line_items.append({
            "Description": "",
            "Quantity": 0.0,
            "Price": 0.0,
            "Amount": 0.0,
        }))
    
    with col2:
        # Show quick summary of valid items
        valid_items = [item for item in st.session_state.line_items if item.get('Quantity', 0) > 0 and item.get('Description')]
        if valid_items:
            total_items = len(valid_items)
            total_qty = sum(item['Quantity'] for item in valid_items)
            st.info(f"📦 {total_items} items • Total Qty: {total_qty}")

    total_amount = sum(row["Amount"] for row in st.session_state.line_items)

    # Charges section with validation
    st.subheader("💰 Additional Charges")
    col1, col2 = st.columns(2)
    
    with col1:
        handling_charge = st.number_input(
            "Handling Charges", 
            min_value=0.0, 
            value=0.0, 
            step=100.0,
            help="Additional handling charges"
        )
    
    with col2:
        inspection_charge = st.number_input(
            "Inspection Charges", 
            min_value=0.0, 
            value=0.0, 
            step=500.0,
            help="Inspection charges if applicable"
        )

    # Validate charges
    charges_valid, charges_error = FormValidator.validate_charges(handling_charge, inspection_charge)
    if not charges_valid:
        st.error(charges_error)

    subtotal = total_amount + handling_charge + inspection_charge
    tax = subtotal * 0.18
    grand_total = subtotal + tax

    # Enhanced total display
    st.divider()
    st.subheader("💵 Estimate Summary")
    
    summary_col1, summary_col2 = st.columns([2, 1])
    with summary_col1:
        st.write("**Items Total:**")
        st.write("**Handling Charges:**")
        st.write("**Inspection Charges:**")
        st.write("**Subtotal:**")
        st.write("**GST @18%:**")
        st.write("### **Grand Total:**")
    
    with summary_col2:
        st.write(f"₹{total_amount:.2f}")
        st.write(f"₹{handling_charge:.2f}")
        st.write(f"₹{inspection_charge:.2f}")
        st.write(f"₹{subtotal:.2f}")
        st.write(f"₹{tax:.2f}")
        st.write(f"### ₹{grand_total:.2f}")

    # Enhanced form submission with comprehensive validation
    st.divider()
    
    if st.button("🚀 Submit Estimate", use_container_width=True, type="primary"):
        # Collect all validation errors
        validation_errors = []
        
        # Validate customer name
        customer_valid, customer_error = FormValidator.validate_customer_name(to_customer)
        if not customer_valid:
            validation_errors.append(customer_error)
        
        # Validate line items
        line_items_valid, line_items_error = FormValidator.validate_line_items(st.session_state.line_items)
        if not line_items_valid:
            validation_errors.append(line_items_error)
        
        # Validate charges
        charges_valid, charges_error = FormValidator.validate_charges(handling_charge, inspection_charge)
        if not charges_valid:
            validation_errors.append(charges_error)
        
        # Show validation errors if any
        if validation_errors:
            FormValidator.show_validation_errors(validation_errors)
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

            # Create estimate with progress indicator
            with st.spinner("Creating estimate..."):
                try:
                    result = create_estimate(estimate_data)
                    
                    if "estimate" in result:
                        estimate_id = result["estimate"]["estimate_id"]
                        
                        # Show success message
                        PDFHandler.show_pdf_success(estimate_id, to_customer)
                        
                        # Download PDF with enhanced handling
                        success, pdf_data, error_msg = PDFHandler.download_with_progress(
                            estimate_id, 
                            download_estimate_pdf
                        )
                        
                        if success:
                            # Enhanced PDF preview and download
                            PDFHandler.render_pdf_preview(
                                pdf_data, 
                                f"estimate_{estimate_id}_{to_customer.replace(' ', '_')}.pdf"
                            )
                            
                            # Reset form after successful submission
                            st.session_state.line_items = [{
                                "Description": "",
                                "Quantity": 0.0,
                                "Price": 0.0,
                                "Amount": 0.0,
                            }]
                            
                            # Clear item selections
                            keys_to_clear = [key for key in st.session_state.keys() if key.startswith("selected_item_")]
                            for key in keys_to_clear:
                                del st.session_state[key]
                                
                        else:
                            st.error(f"❌ PDF Generation Failed: {error_msg}")
                            st.info("The estimate was created successfully, but PDF download failed. You can try downloading it from the 'Download Estimate' section.")
                    
                    else:
                        error_details = result.get("message", "Unknown error occurred")
                        st.error(f"❌ Failed to create estimate: {error_details}")
                        
                except Exception as e:
                    st.error(f"❌ Error creating estimate: {str(e)}")
                    st.info("Please check your internet connection and try again.")

elif menu == "Download Estimate":
    st.header("📂 Download Estimates")

    # Load estimates with error handling
    try:
        with st.spinner("Loading estimates..."):
            estimates = fetch_estimates()
    except Exception as e:
        st.error(f"❌ Failed to load estimates: {str(e)}")
        st.stop()

    if not estimates:
        st.info("📋 No estimates available.")
    else:
        # Enhanced estimates display
        df = pd.DataFrame(estimates)
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df[['estimate_id', 'estimate_number', 'reference_number', 'customer_name', 'date', 'total']]
        
        # Show estimates table
        st.subheader("📊 Available Estimates")
        st.dataframe(
            df[['estimate_number', 'customer_name', 'reference_number', 'date', 'total']], 
            use_container_width=True,
            hide_index=True
        )
        
        st.divider()

        # Enhanced estimate selection with reference numbers
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Create dropdown options with both estimate number and reference number
            dropdown_options = []
            option_map = {}
            
            for _, row in df.iterrows():
                # Create display text with estimate number and reference number
                display_text = f"{row['estimate_number']}"
                if row['reference_number'] and str(row['reference_number']).strip():
                    # Clean up reference number (remove newlines, limit length)
                    ref_clean = str(row['reference_number']).replace('\n', ' | ').strip()
                    if len(ref_clean) > 60:
                        ref_clean = ref_clean[:60] + "..."
                    display_text += f" - {ref_clean}"
                
                dropdown_options.append(display_text)
                option_map[display_text] = row['estimate_number']
            
            selected_option = st.selectbox(
                "Select Estimate to Download", 
                dropdown_options,
                help="Choose an estimate to preview and download"
            )
            
            # Get the actual estimate number from the selected option
            selected = option_map.get(selected_option) if selected_option else None
        
        with col2:
            if selected:
                estimate_row = df[df['estimate_number'] == selected].iloc[0]
                st.metric("Total Amount", f"₹{estimate_row['total']:.2f}")
        
        if selected:
            estimate_row = df[df['estimate_number'] == selected].iloc[0]
            estimate_id = estimate_row['estimate_id']
            customer_name = estimate_row['customer_name']
            
            # Show estimate details
            st.subheader(f"📄 Estimate Details: {selected}")
            detail_col1, detail_col2 = st.columns(2)
            
            with detail_col1:
                st.write(f"**Reference:** {estimate_row['reference_number']}")
            with detail_col2:
                st.write(f"**Date:** {estimate_row['date']}")
            
            st.divider()
            
            # Enhanced PDF download with error handling
            success, pdf_data, error_msg = PDFHandler.download_with_progress(
                estimate_id, 
                download_estimate_pdf
            )
            
            if success:
                # Enhanced PDF preview and download
                PDFHandler.render_pdf_preview(
                    pdf_data, 
                    f"{selected}_{customer_name.replace(' ', '_')}.pdf"
                )
            else:
                st.error(f"❌ {error_msg}")
                st.info("Please try again or contact support if the problem persists.")