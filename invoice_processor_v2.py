import os
import tempfile
import shutil
import zipfile
import time
from datetime import datetime
import uuid
import pandas as pd
from invoice_extractor import InvoiceExtractor

class InvoiceProcessorV2:
    """
    Advanced Invoice Processor using OCR-based extraction
    Based on the independent site implementation
    """

    def __init__(self):
        pass

    def process_pdf_file(self, file_path, results_list):
        """Process a single PDF file and return the new filename"""

        try:
            # Try OCR extraction first
            data = InvoiceExtractor(file_path).extract()

            if data.empty or ("开票日期" not in data.columns and "价税合计(小写)" not in data.columns):
                raise ValueError("Not a standard invoice, OCR extraction failed.")

            # Extract information for filename
            try:
                inv_value = data["价税合计(小写)"].to_list()[0]
            except:
                inv_value = "Error"

            try:
                _prov = data["销售方名称"].to_list()[0]
                inv_provider = _prov[3:] if "：" in _prov else _prov
            except:
                inv_provider = "Error"

            try:
                inv_date = data["开票日期"].to_list()[0]
            except:
                inv_date = "Error"

            new_filename = "_".join([inv_date, inv_value, inv_provider]) + ".pdf"

            # Store the extracted data for reporting
            results_list.append({
                'original_filename': os.path.basename(file_path),
                'new_filename': new_filename,
                'date': inv_date,
                'amount': inv_value,
                'issuer': inv_provider,
                'status': 'success',
                'method': 'OCR'
            })

            return new_filename

        except Exception as e:
            print(f"OCR failed for {os.path.basename(file_path)}: {e}")

            # Instead of using GPT, rename as OCRError + number
            original_filename = os.path.basename(file_path)
            new_filename = f"OCRError_{original_filename}"

            # Store the failed result
            results_list.append({
                'original_filename': original_filename,
                'new_filename': new_filename,
                'date': 'N/A',
                'amount': 'N/A',
                'issuer': 'N/A',
                'status': 'failed',
                'method': 'OCR'
            })

            return new_filename

    def process_batch(self, files):
        """
        Process multiple PDF files uploaded via Flask

        Args:
            files: List of FileStorage objects from Flask request.files.getlist('files')

        Returns:
            dict: Processing results with job_id, zip_path, results, etc.
        """
        job_id = str(uuid.uuid4())
        temp_dir = tempfile.mkdtemp()
        processed_files = []
        results_list = []

        try:
            for file in files:
                if file and self._allowed_file(file.filename):
                    # Save the uploaded file
                    filename = self._secure_filename(file.filename)
                    file_path = os.path.join(temp_dir, filename)
                    file.save(file_path)

                    # Process the file
                    new_filename = self.process_pdf_file(file_path, results_list)
                    new_file_path = os.path.join(temp_dir, new_filename)

                    # Handle duplicate filenames
                    counter = 1
                    while os.path.exists(new_file_path):
                        base, ext = os.path.splitext(new_filename)
                        new_filename = f"{base}_{counter}{ext}"
                        new_file_path = os.path.join(temp_dir, new_filename)
                        counter += 1

                    # Update the result with the final filename
                    if results_list:
                        results_list[-1]['new_filename'] = new_filename

                    # Move file to new name with retry mechanism for Windows
                    self._safe_move_file(file_path, new_file_path)
                    processed_files.append(new_file_path)

            # Create ZIP file
            zip_path = os.path.join(temp_dir, 'processed_invoices.zip')
            with zipfile.ZipFile(zip_path, 'w') as zip_file:
                for file_path in processed_files:
                    zip_file.write(file_path, os.path.basename(file_path))

            # Calculate statistics
            total_files = len(results_list)
            successful_files = len([r for r in results_list if r['status'] == 'success'])
            failed_files = total_files - successful_files

            return {
                'success': True,
                'job_id': job_id,
                'zip_path': zip_path,
                'temp_dir': temp_dir,
                'results': results_list,
                'total_files': total_files,
                'successful_files': successful_files,
                'failed_files': failed_files,
                'timestamp': (datetime.now() + pd.Timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
            }

        except Exception as e:
            # Clean up on error
            shutil.rmtree(temp_dir, ignore_errors=True)
            return {
                'success': False,
                'error': str(e)
            }

    def _allowed_file(self, filename):
        """Check if file extension is allowed"""
        ALLOWED_EXTENSIONS = {'pdf'}
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

    def _secure_filename(self, filename):
        """Secure filename to prevent path traversal attacks"""
        # Use werkzeug's secure_filename for proper security
        from werkzeug.utils import secure_filename
        return secure_filename(filename)

    def _safe_move_file(self, src_path, dest_path, max_retries=5, delay=0.5):
        """Safely move file with retry mechanism for Windows file locking issues"""
        for attempt in range(max_retries):
            try:
                # Ensure destination directory exists
                dest_dir = os.path.dirname(dest_path)
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)

                # Try to move the file
                shutil.move(src_path, dest_path)
                return True

            except (OSError, PermissionError) as e:
                if attempt < max_retries - 1:
                    print(f"Attempt {attempt + 1} failed to move {src_path}: {e}. Retrying in {delay}s...")
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                else:
                    print(f"Failed to move {src_path} after {max_retries} attempts: {e}")
                    # As a fallback, try copying and then deleting
                    try:
                        shutil.copy2(src_path, dest_path)
                        os.unlink(src_path)
                        return True
                    except Exception as fallback_error:
                        print(f"Fallback copy+delete also failed: {fallback_error}")
                        raise e
        return False

    def sort_results_by_date(self, results):
        """Sort results: successful ones by date first, then failed ones at the end"""

        successful_results = [r for r in results if r['status'] == 'success']
        failed_results = [r for r in results if r['status'] == 'failed']

        def parse_chinese_date(date_str):
            try:
                if date_str == 'Error' or date_str == 'N/A':
                    return datetime(9999, 12, 31)

                import re
                match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_str)
                if match:
                    year, month, day = match.groups()
                    return datetime(int(year), int(month), int(day))
                else:
                    return datetime(9999, 12, 31)
            except:
                return datetime(9999, 12, 31)

        try:
            successful_results.sort(key=lambda x: parse_chinese_date(x['date']))
        except:
            pass

        return successful_results + failed_results

# Global processor instance
processor_v2 = InvoiceProcessorV2()