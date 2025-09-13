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
import json
import json

st.set_page_config(
    page_title="Zoho Estimator", 
    layout="wide",
    initial_sidebar_state="collapsed"  # Better for mobile
)

# Add mobile-friendly CSS
st.markdown("""
<style>
    /* Mobile responsiveness improvements */
    @media (max-width: 768px) {
        .stSelectbox > div > div {
            font-size: 14px;
        }
        .stNumberInput > div > div > input {
            font-size: 14px;
        }
        .stTextInput > div > div > input {
            font-size: 14px;
        }
        .stMetric {
            background-color: #f0f2f6;
            padding: 0.5rem;
            border-radius: 0.5rem;
            margin: 0.25rem 0;
        }
        .stButton > button {
            width: 100%;
            margin: 0.25rem 0;
        }
    }
    
    /* Improve table readability on mobile */
    .stDataFrame {
        font-size: 12px;
    }
    
    /* Better spacing for mobile */
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)
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

    # Copy Estimate functionality with persistent expanded state
    if "copy_expander_expanded" not in st.session_state:
        st.session_state.copy_expander_expanded = False
    
    with st.expander("📋 Copy from Existing Estimate", expanded=st.session_state.copy_expander_expanded):
        st.write("Load all values from an existing estimate to create a similar one.")
        
        try:
            # Load estimates for copying
            copy_estimates = fetch_estimates()
            if copy_estimates:
                copy_df = pd.DataFrame(copy_estimates)
                copy_df['date'] = pd.to_datetime(copy_df['date']).dt.date
                
                # Create dropdown options with estimate number and reference
                copy_options = ["Select estimate to copy..."]
                copy_map = {}
                
                for _, row in copy_df.iterrows():
                    display_text = f"{row['estimate_number']}"
                    if row['reference_number'] and str(row['reference_number']).strip():
                        ref_clean = str(row['reference_number']).replace('\n', ' | ').strip()
                        if len(ref_clean) > 30:
                            ref_clean = ref_clean[:30] + "..."
                        display_text += f" - {ref_clean}"
                    display_text += f" (₹{row['total']:.0f})"
                    
                    copy_options.append(display_text)
                    copy_map[display_text] = row['estimate_id']
                
                selected_copy = st.selectbox(
                    "Choose Estimate to Copy",
                    copy_options,
                    help="Select an existing estimate to copy its values",
                    key="copy_estimate_selector"
                )
                
                # Keep expander open when user is actively selecting
                if selected_copy != "Select estimate to copy...":
                    st.session_state.copy_expander_expanded = True
                
                copy_button_col1, copy_button_col2 = st.columns([1, 2])
                with copy_button_col1:
                    copy_clicked = st.button("📥 Copy Estimate Values", disabled=(selected_copy == "Select estimate to copy..."), use_container_width=True)
                
                with copy_button_col2:
                    if st.button("❌ Close", use_container_width=True):
                        st.session_state.copy_expander_expanded = False
                        st.rerun()
                
                if copy_clicked and selected_copy != "Select estimate to copy...":
                    copy_estimate_id = copy_map[selected_copy]
                    
                    try:
                        with st.spinner("Copying estimate data..."):
                            # Fetch detailed estimate data
                            from zoho_api import fetch_estimate_details
                            estimate_details = fetch_estimate_details(copy_estimate_id)
                            
                            if "estimate" in estimate_details:
                                estimate = estimate_details["estimate"]
                                # Copy customer information
                                customer_name = estimate.get("reference_number", "")
                                if customer_name and '\n' in customer_name:
                                    st.session_state["copy_customer_name"] = customer_name.split('\n',1)[0]
                                else:
                                    st.session_state["copy_customer_name"] = customer_name
                                
                                # Parse reference number for capacity
                                ref_number = estimate.get("reference_number", "")
                                if ref_number and '\n' in ref_number:
                                    parts = ref_number.split('\n', 1)
                                    st.session_state["copy_capacity"] = parts[1] if len(parts) > 1 else ""
                                else:
                                    st.session_state["copy_capacity"] = ""
                                    
                                # Copy line items with proper item matching
                                copied_items = []
                                line_items = estimate.get("line_items", [])
                                
                                def find_item_by_name_or_sku(item_name, item_sku=None):
                                    """Find item in cache by name or SKU"""
                                    # First try to match by SKU if available
                                    if item_sku:
                                        for cached_item in item_data:
                                            if cached_item.get("sku") == item_sku:
                                                return cached_item
                                    
                                    # Then try to match by name (exact match)
                                    for cached_item in item_data:
                                        if cached_item.get("name") == item_name:
                                            return cached_item
                                    
                                    # Check if item exists in item_map (raw cache data)
                                    if item_name in item_map:
                                        # Convert item_map entry to item_data format
                                        raw_item = item_map[item_name]
                                        return {
                                            "name": raw_item["name"],
                                            "sku": raw_item.get("sku", ""),
                                            "rate": float(raw_item["rate"]),
                                            "item_id": raw_item["item_id"]
                                        }
                                    
                                    # Finally try partial name matching in item_data
                                    for cached_item in item_data:
                                        if item_name.lower() in cached_item.get("name", "").lower():
                                            return cached_item
                                    
                                    return None
                                
                                for item in line_items:
                                    # Skip handling and inspection charges as they'll be handled separately
                                    if item.get("name") not in ["Handling Charges", "Inspection Charges"]:
                                        item_name = item.get("name", "")
                                        item_sku = item.get("sku", "")
                                        
                                        # Find matching item in current cache
                                        matched_item = find_item_by_name_or_sku(item_name, item_sku)
                                        if matched_item:
                                            # Use matched item from cache
                                            copied_items.append({
                                                "Description": matched_item["name"],
                                                "Quantity": float(item.get("quantity", 0)),
                                                "Price": float(item.get("rate", 0)),  # Keep original price
                                                "Amount": float(item.get("quantity", 0)) * float(item.get("rate", 0))
                                            })
                                        else:
                                            # Item not found in cache, add as empty item with note
                                            copied_items.append({
                                                "Description": "",  # Empty since item not found
                                                "Quantity": float(item.get("quantity", 0)),
                                                "Price": float(item.get("rate", 0)),
                                                "Amount": float(item.get("quantity", 0)) * float(item.get("rate", 0))
                                            })
                                            # Show warning about missing item
                                            st.warning(f"⚠️ Item '{item_name}' (SKU: {item_sku}) not found in current items cache. Please select manually.")
                                
                                # Add at least one empty item if no items found
                                if not copied_items:
                                    copied_items.append({
                                        "Description": "",
                                        "Quantity": 0.0,
                                        "Price": 0.0,
                                        "Amount": 0.0
                                    })
                                
                                # Store matched items for setting dropdown selections
                                matched_items_for_selection = []
                                
                                # Re-process items to store matched items for dropdown selection
                                for idx, item in enumerate(line_items):
                                    if item.get("name") not in ["Handling Charges", "Inspection Charges"]:
                                        item_name = item.get("name", "")
                                        item_sku = item.get("sku", "")
                                        matched_item = find_item_by_name_or_sku(item_name, item_sku)
                                        matched_items_for_selection.append(matched_item)
                                    else:
                                        matched_items_for_selection.append(None)
                                
                                st.session_state.line_items = copied_items
                                
                                # Copy charges (look for them in line items)
                                handling_charge = 0.0
                                inspection_charge = 0.0
                                
                                for item in line_items:
                                    if item.get("name") == "Handling Charges":
                                        handling_charge = float(item.get("rate", 0))
                                    elif item.get("name") == "Inspection Charges":
                                        inspection_charge = float(item.get("rate", 0))
                                
                                if float(estimate.get("shipping_charge", 0)) > 0:
                                    handling_charge = float(estimate.get("shipping_charge"))
                                
                                st.session_state["copy_handling_charge"] = handling_charge
                                st.session_state["copy_inspection_charge"] = inspection_charge
                                
                                # Clear existing widget states but preserve what we need
                                keys_to_clear = [key for key in st.session_state.keys() 
                                                if key.startswith(("qty_", "price_", "amount_", "selected_item_"))]
                                for key in keys_to_clear:
                                    del st.session_state[key]
                                
                                # Set the selected items for dropdowns
                                for idx, matched_item in enumerate(matched_items_for_selection):
                                    if matched_item:
                                        st.session_state[f"selected_item_{idx}"] = matched_item
                                        
                                        # Also set the dropdown widget value to the correct option string
                                        # Find the matching option string in the cached options
                                        item_name = matched_item["name"]
                                        item_sku = matched_item.get("sku", "")
                                        item_rate = matched_item["rate"]
                                        
                                        # Create the display text that matches the dropdown options
                                        display_text = item_name
                                        if item_sku:
                                            display_text += f" (SKU: {item_sku})"
                                        display_text += f" - ₹{item_rate:.2f}"
                                        
                                        # Set the dropdown widget to this option
                                        st.session_state[f"item_dropdown_item_{idx}"] = display_text
                                
                                st.success(f"✅ Estimate copied successfully!")
                                st.info("📝 Form has been populated with the copied estimate data. You can now modify as needed.")
                                
                                # Close the expander after successful copy
                                st.session_state.copy_expander_expanded = False
                                st.rerun()
                                    
                            else:
                                st.error("❌ Failed to fetch estimate details")
                                    
                    except Exception as e:
                        st.error(f"❌ Error copying estimate: {str(e)}")
            else:
                st.info("No existing estimates found to copy from.")
                
        except Exception as e:
            st.error(f"Error loading estimates: {str(e)}")

    st.divider()

    # Get form ID for widget keys (ensures reset after submission)
    form_id = st.session_state.get("form_id", 0)
    
    # Customer information with validation (use copied values if available)
    default_customer = st.session_state.get("copy_customer_name", "")
    to_customer = st.text_input(
        "Estimate To", 
        value=default_customer, 
        placeholder="Enter customer name...",
        key=f"customer_{form_id}"
    )
    
    # Clear the copied value after using it
    if "copy_customer_name" in st.session_state:
        del st.session_state["copy_customer_name"]
    
    # Real-time validation for customer name
    customer_valid, customer_error = FormValidator.validate_customer_name(to_customer)
    if to_customer and not customer_valid:
        st.error(customer_error)
    
    estimate_date = st.date_input("Estimate Date", value=date.today(), key=f"date_{form_id}")
    
    # Capacity with copied value if available
    default_capacity = st.session_state.get("copy_capacity", "")
    capacity = st.text_input(
        "Capacity (optional)", 
        value=default_capacity, 
        placeholder="Enter capacity details...",
        key=f"capacity_{form_id}"
    )
    
    # Clear the copied value after using it
    if "copy_capacity" in st.session_state:
        del st.session_state["copy_capacity"]

    st.subheader("📦 Line Items")

    updated_items = []
    running_total = 0
    item_deleted = False

    for idx, row in enumerate(st.session_state.line_items):
        # Mobile-friendly line item layout
        st.markdown(f"**Item {idx+1}**")
        if idx > 0:  # Show running total
            st.caption(f"*Running Total: ₹{running_total:,.0f}*")
        
        # Mobile-responsive layout: stack on small screens
        with st.container():
            # Item selection (full width on mobile)
            current_search = row.get("Description", "")
            selected_item = item_selector.render_item_selector(
                key=f"item_{idx}",
                current_value=current_search
            )
            
            # Update session state if item is selected
            if selected_item:
                st.session_state[f"selected_item_{idx}"] = selected_item

            # Quantity, Price, Amount in responsive columns
            mobile_cols = st.columns([2, 2, 2, 1])
            
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
            
            # Mobile-friendly inputs
            with mobile_cols[0]:
                qty = st.number_input(
                    "Quantity", 
                    min_value=0, 
                    step=1, 
                    key=qty_key,
                    format="%d"
                )
            
            with mobile_cols[1]:
                price = st.number_input(
                    "Price", 
                    min_value=0.0, 
                    step=50.0,
                    key=price_key,
                    format="%.2f"
                )
            
            amount = float(qty) * float(price)
            
            with mobile_cols[2]:
                st.metric("Amount", f"₹{amount:,.2f}")
            
            # Delete button
            with mobile_cols[3]:
                remove = st.button("🗑️", key=f"remove_{idx}", help="Remove", use_container_width=True)

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
        pass

    col1, col2 = st.columns([1, 3])
    with col1:
        # Show quick summary of valid items
        valid_items = [item for item in st.session_state.line_items if item.get('Quantity', 0) > 0 and item.get('Description')]
        if valid_items:
            total_items = len(valid_items)
            total_qty = sum(item['Quantity'] for item in valid_items)
            st.info(f"📦 {total_items} items • Total Qty: {total_qty}")

    total_amount = sum(row["Amount"] for row in st.session_state.line_items)

    # Charges section with validation - Mobile responsive
    st.subheader("💰 Additional Charges")
    
    # Stack charges vertically on mobile, side by side on desktop
    charges_cols = st.columns([1, 1])
    
    with charges_cols[0]:
        # Use copied or default handling charge
        default_handling = st.session_state.get("copy_handling_charge", 0.0)
        
        handling_charge = st.number_input(
            "Handling Charges", 
            min_value=0.0, 
            value=default_handling, 
            step=100.0,
            help="Additional handling charges",
            key=f"handling_{form_id}"
        )
        # Clear copied value after using it
        if "copy_handling_charge" in st.session_state:
            del st.session_state["copy_handling_charge"]
    
    with charges_cols[1]:
        # Use copied or default inspection charge
        default_inspection = st.session_state.get("copy_inspection_charge", 0.0)
        
        inspection_charge = st.number_input(
            "Inspection Charges", 
            min_value=0.0, 
            value=default_inspection, 
            step=500.0,
            help="Inspection charges if applicable",
            key=f"inspection_{form_id}"
        )
        # Clear copied value after using it
        if "copy_inspection_charge" in st.session_state:
            del st.session_state["copy_inspection_charge"]

    # Multiplier field
    st.subheader("🔢 Multiplier")
    
    multiplier = st.number_input(
        "Multiplier", 
        min_value=1.0,
        max_value=100.0,
        value=1.0, 
        step=1.0,
        help="Multiply the total estimate amount (1.0 = no change, 2.0 = double, etc.)",
        key=f"multiplier_{form_id}"
    )

    # Validate charges
    charges_valid, charges_error = FormValidator.validate_charges(handling_charge, inspection_charge)
    if not charges_valid:
        st.error(charges_error)

    subtotal = total_amount + handling_charge + inspection_charge
    tax = subtotal * 0.18
    base_total = subtotal + tax
    
    # Calculate adjustment based on multiplier
    adjustment_amount = base_total * (multiplier - 1) if multiplier > 1 else 0
    final_total = base_total + adjustment_amount

    # Mobile-friendly total display using single-line format
    st.divider()
    st.subheader("💵 Estimate Summary")
    
    # Use markdown table for better mobile alignment
    summary_data = f"""
    | Description | Amount |
    |-------------|--------|
    | **Items Total:** | **₹{total_amount:,.2f}** |
    | **Handling Charges:** | **₹{handling_charge:,.2f}** |
    | **Inspection Charges:** | **₹{inspection_charge:,.2f}** |
    | **Subtotal:** | **₹{subtotal:,.2f}** |
    | **GST @18%:** | **₹{tax:,.2f}** |"""
    
    if multiplier > 1:
        summary_data += f"""
    | **Adjustment (x{multiplier:.1f}):** | **₹{adjustment_amount:,.2f}** |"""
    
    summary_data += f"""
    | **Final Total:** | **₹{final_total:,.2f}** |
    """
    
    st.markdown(summary_data)

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

            if "Handling Charges" in item_map and handling_charge > 0:
                estimate_data["shipping_charge"] = handling_charge
                estimate_data["shipping_charge_tax_id"] = "2116695000000029197"
            
            # Add adjustment if multiplier is greater than 1
            if multiplier > 1:
                estimate_data["adjustment"] = adjustment_amount
                estimate_data["adjustment_description"] = f"x{multiplier:.1f}"

            # Create estimate with progress indicator
            with st.spinner("Creating estimate..."):
                try:
                    # estimate_data["shipping_charge"] = 1.18
                    # estimate_data["shipping_charge_"]
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
                            # Enhanced estimate summary and download
                            PDFHandler.render_estimate_summary(
                                pdf_data, 
                                f"estimate_{estimate_id}_{to_customer.replace(' ', '_')}.pdf",
                                estimate_data
                            )
                            
                            # Complete form reset after successful submission
                            
                            # Clear ALL session state except essential app state
                            keys_to_keep = {"line_items"}  # Keep only essential keys
                            keys_to_clear = [key for key in st.session_state.keys() if key not in keys_to_keep]
                            
                            for key in keys_to_clear:
                                del st.session_state[key]
                            
                            # Reset line items to empty state
                            st.session_state.line_items = [{
                                "Description": "",
                                "Quantity": 0.0,
                                "Price": 0.0,
                                "Amount": 0.0,
                            }]
                            
                            # Generate new form ID to force widget reset
                            import time
                            st.session_state["form_id"] = int(time.time() * 1000)  # Unique timestamp
                            
                            # Force a complete page refresh to reset all input values
                            st.rerun()
                                
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
        


        # Mobile-friendly estimate selection
        # Create dropdown options with both estimate number and reference number
        dropdown_options = []
        option_map = {}
        
        for _, row in df.iterrows():
            # Create display text with estimate number and reference number
            display_text = f"{row['estimate_number']}"
            if row['reference_number'] and str(row['reference_number']).strip():
                # Clean up reference number (remove newlines, limit length for mobile)
                ref_clean = str(row['reference_number']).replace('\n', ' | ').strip()
                if len(ref_clean) > 40:  # Shorter for mobile
                    ref_clean = ref_clean[:40] + "..."
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
        
        # Show total amount below dropdown for mobile
        if selected:
            estimate_row = df[df['estimate_number'] == selected].iloc[0]
            st.info(f"💰 Estimate Amount: **₹{estimate_row['total']:.2f}**")
        
        if selected:
            estimate_row = df[df['estimate_number'] == selected].iloc[0]
            estimate_id = estimate_row['estimate_id']
            customer_name = estimate_row['customer_name']
            
            st.divider()
            
            # Enhanced PDF download with error handling
            success, pdf_data, error_msg = PDFHandler.download_with_progress(
                estimate_id, 
                download_estimate_pdf
            )
            
            if success:
                # Try to fetch estimate details for summary
                estimate_details = None
                try:
                    from zoho_api import fetch_estimate_details
                    details_response = fetch_estimate_details(estimate_id)
                    if "estimate" in details_response:
                        estimate_details = details_response["estimate"]
                except Exception as e:
                    st.warning(f"Could not fetch estimate details: {str(e)}")
                
                # Enhanced estimate summary and download
                PDFHandler.render_estimate_summary(
                    pdf_data, 
                    f"{selected}_{customer_name.replace(' ', '_')}.pdf",
                    estimate_details
                )
            else:
                st.error(f"❌ {error_msg}")
                st.info("Please try again or contact support if the problem persists.")