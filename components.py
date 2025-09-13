import streamlit as st
import pandas as pd
from typing import List, Dict, Any, Optional
from thefuzz import process, fuzz

class ItemSelector:
    """Enhanced item selector with autocomplete and fuzzy search"""
    
    def __init__(self, items: List[Dict[str, Any]]):
        self.items = items
        self.search_index = self._build_search_index()
    
    def _build_search_index(self) -> List[str]:
        """Build searchable index with name, SKU, and combined strings"""
        index = []
        for item in self.items:
            # Add name
            index.append(item['name'])
            # Add SKU if available
            if item.get('sku'):
                index.append(item['sku'])
            # Add combined name + SKU
            combined = f"{item['name']} {item.get('sku', '')}".strip()
            if combined not in index:
                index.append(combined)
        return index
    
    def search_items(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Enhanced fuzzy search with better scoring"""
        if not query.strip():
            return self.items[:limit]
        
        # Search in multiple fields
        matches = []
        
        for item in self.items:
            scores = []
            
            # Score against name
            name_score = fuzz.partial_ratio(query.lower(), item['name'].lower())
            scores.append(name_score)
            
            # Score against SKU
            if item.get('sku'):
                sku_score = fuzz.ratio(query.lower(), item['sku'].lower())
                scores.append(sku_score)
            
            # Score against combined
            combined = f"{item['name']} {item.get('sku', '')}".strip()
            combined_score = fuzz.partial_ratio(query.lower(), combined.lower())
            scores.append(combined_score)
            
            # Use best score
            best_score = max(scores)
            
            if best_score > 40:  # Lower threshold for better results
                matches.append((item, best_score))
        
        # Sort by score and return top matches
        matches.sort(key=lambda x: x[1], reverse=True)
        return [match[0] for match in matches[:limit]]
    
    def __init__(self, items: List[Dict[str, Any]]):
        self.items = items
        self.search_index = self._build_search_index()
        # Pre-build options for better performance
        self._cached_options = None
        self._cached_item_map = None
        self._build_cached_options()
    
    def _build_cached_options(self):
        """Pre-build options and item map for better performance"""
        options = ["Select an item..."]
        item_map = {}
        
        for item in self.items:
            display_text = item['name']
            if item.get('sku'):
                display_text += f" (SKU: {item['sku']})"
            display_text += f" - ₹{item['rate']:.2f}"
            
            options.append(display_text)
            item_map[display_text] = item
        
        self._cached_options = options
        self._cached_item_map = item_map

    def render_item_selector(self, key: str, current_value: str = "", 
                           placeholder: str = "Select item...") -> Optional[Dict[str, Any]]:
        """Render single dropdown with all items (optimized)"""
        
        # Use cached options for better performance - no label or help for alignment
        selected_option = st.selectbox(
            "Item",
            options=self._cached_options,
            key=f"item_dropdown_{key}",
            label_visibility="collapsed"  # Hide label for alignment
        )
        
        # Return selected item if it's a valid selection
        if selected_option != "Select an item..." and selected_option in self._cached_item_map:
            return self._cached_item_map[selected_option]
        
        return None


class FormValidator:
    """Form validation utilities"""
    
    @staticmethod
    def validate_customer_name(name: str) -> tuple[bool, str]:
        """Validate customer name"""
        if not name or not name.strip():
            return False, "Customer name is required"
        if len(name.strip()) < 2:
            return False, "Customer name must be at least 2 characters"
        return True, ""
    
    @staticmethod
    def validate_line_items(line_items: List[Dict]) -> tuple[bool, str]:
        """Validate line items"""
        if not line_items:
            return False, "At least one line item is required"
        
        valid_items = [item for item in line_items if item.get('Quantity', 0) > 0 and item.get('Description')]
        
        if not valid_items:
            return False, "At least one line item must have a description and quantity > 0"
        
        for i, item in enumerate(line_items):
            if item.get('Quantity', 0) > 0:
                if not item.get('Description'):
                    return False, f"Line item {i+1}: Description is required when quantity > 0"
                if item.get('Price', 0) <= 0:
                    return False, f"Line item {i+1}: Price must be greater than 0"
        
        return True, ""
    
    @staticmethod
    def validate_charges(handling: float, inspection: float) -> tuple[bool, str]:
        """Validate charges"""
        if handling < 0:
            return False, "Handling charges cannot be negative"
        if inspection < 0:
            return False, "Inspection charges cannot be negative"
        return True, ""
    
    @staticmethod
    def show_validation_errors(errors: List[str]):
        """Display validation errors in a user-friendly way"""
        if errors:
            st.error("Please fix the following errors:")
            for error in errors:
                st.write(f"• {error}")


class PDFHandler:
    """Enhanced PDF handling with better error management and loading states"""
    
    @staticmethod
    def download_with_progress(estimate_id: str, download_func) -> tuple[bool, bytes, str]:
        """Download PDF with progress indicator and error handling"""
        try:
            with st.spinner("Generating PDF..."):
                pdf_data = download_func(estimate_id)
                
            if not pdf_data:
                return False, b"", "PDF generation failed - no data received"
            
            # Validate PDF data
            if not pdf_data.startswith(b'%PDF'):
                return False, b"", "Invalid PDF data received"
            
            return True, pdf_data, ""
            
        except Exception as e:
            return False, b"", f"Error generating PDF: {str(e)}"
    
    @staticmethod
    def _is_streamlit_cloud():
        """Detect if running on Streamlit Cloud"""
        import os
        return (
            os.getenv('STREAMLIT_SHARING_MODE') == 'true' or
            os.getenv('STREAMLIT_CLOUD') == 'true' or
            'streamlit.app' in os.getenv('HOSTNAME', '') or
            'streamlitapp.com' in os.getenv('HOSTNAME', '')
        )
    
    @staticmethod
    def render_pdf_preview(pdf_data: bytes, filename: str = "estimate.pdf"):
        """Render PDF preview optimized for Streamlit Cloud"""
        try:
            # Validate PDF data
            if not pdf_data or not pdf_data.startswith(b'%PDF'):
                st.error("❌ Invalid PDF data received")
                return
            
            # Show PDF info
            pdf_size = len(pdf_data)
            st.info(f"📄 PDF generated successfully ({pdf_size:,} bytes)")
            
            # Primary download button (always works)
            col1, col2 = st.columns([2, 1])
            with col1:
                st.download_button(
                    "📥 Download PDF",
                    data=pdf_data,
                    file_name=filename,
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary"
                )
            
            with col2:
                # Show file info
                st.metric("File Size", f"{pdf_size/1024:.1f} KB")
            
            # Cloud-friendly preview section
            st.subheader("📋 PDF Preview")
            
            # Check if we're on Streamlit Cloud
            is_cloud = PDFHandler._is_streamlit_cloud()
            
            if is_cloud:
                # On Streamlit Cloud - skip iframe preview, show info instead
                st.info("""
                🌐 **Running on Streamlit Cloud**
                
                PDF preview is not available on Streamlit Cloud due to security restrictions.
                
                **To view your estimate:**
                1. Click the "📥 Download PDF" button above
                2. Open the downloaded file with any PDF viewer
                3. The PDF contains your complete estimate with all details
                """)
                
                # Show estimate summary as text preview
                st.subheader("📊 Estimate Summary")
                st.success("✅ Your estimate PDF has been generated successfully and is ready for download!")
                
            else:
                # Local/other environments - try iframe preview
                preview_success = False
                
                try:
                    import base64
                    base64_pdf = base64.b64encode(pdf_data).decode('utf-8')
                    
                    # Use iframe approach for local development
                    iframe_html = f"""
                    <div style="text-align: center; padding: 20px; border: 2px dashed #ccc; border-radius: 10px;">
                        <p><strong>PDF Preview</strong></p>
                        <iframe src="data:application/pdf;base64,{base64_pdf}" 
                                width="100%" height="500px" 
                                style="border: 1px solid #ddd;">
                            <p>Your browser does not support PDF preview. Please download the file.</p>
                        </iframe>
                    </div>
                    """
                    
                    st.markdown(iframe_html, unsafe_allow_html=True)
                    preview_success = True
                    
                except Exception as e:
                    st.warning(f"PDF preview failed: {str(e)}")
                    preview_success = False
                
                # Fallback for local environments too
                if not preview_success:
                st.info("""
                🔍 **PDF Preview Not Available**
                
                PDF preview is not supported in this environment. This is common on cloud platforms due to security restrictions.
                
                **To view your estimate:**
                1. Click the "📥 Download PDF" button above
                2. Open the downloaded file with any PDF viewer
                3. The PDF contains your complete estimate with all details
                """)
                
                # Show estimate summary as text preview
                st.subheader("📊 Estimate Summary")
                st.success("✅ Your estimate PDF has been generated successfully and is ready for download!")
                
        except Exception as e:
            st.error(f"❌ Error handling PDF: {str(e)}")
            # Emergency fallback - still provide download
            if pdf_data:
                st.download_button(
                    "📥 Emergency Download",
                    data=pdf_data,
                    file_name=filename,
                    mime="application/pdf",
                    help="PDF preview failed, but download should work"
                )
    
    @staticmethod
    def show_pdf_success(estimate_id: str, customer_name: str):
        """Show success message with additional actions"""
        st.success("✅ Estimate Created Successfully!")
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"📋 Estimate ID: {estimate_id}")
        with col2:
            st.info(f"👤 Customer: {customer_name}")
        
        st.balloons()  # Celebration effect