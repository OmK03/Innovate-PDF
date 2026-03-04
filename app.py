import os
import logging
from io import BytesIO
from datetime import datetime

from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from werkzeug.utils import secure_filename
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.errors import PdfReadError
from PIL import Image

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf"}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB per file
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB total request


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_pdf_content(file_stream) -> bool:
    """Validate that the file is actually a PDF by checking magic bytes."""
    try:
        file_stream.seek(0)
        header = file_stream.read(5)
        file_stream.seek(0)
        return header == b'%PDF-'
    except Exception:
        return False


def create_app() -> Flask:
    app = Flask(__name__)
    
    # Security configuration
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", os.urandom(24).hex())
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    
    # Logging configuration
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    @app.errorhandler(413)
    def request_entity_too_large(error):
        flash("File size exceeds the maximum limit of 50MB.", "error")
        return redirect(url_for("index"))

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/merge", methods=["POST"])
    def merge_pdfs():
        """Merge multiple PDF files into one."""
        files = request.files.getlist("merge_files")
        valid_files = [f for f in files if f and allowed_file(f.filename)]

        if len(valid_files) < 2:
            flash("Please upload at least two PDF files to merge.", "error")
            return redirect(url_for("index"))

        writer = PdfWriter()
        try:
            total_pages = 0
            for f in valid_files:
                # Validate file content
                if not validate_pdf_content(f.stream):
                    flash(f"Invalid PDF file: {f.filename}", "error")
                    return redirect(url_for("index"))
                
                reader = PdfReader(f.stream)
                for page in reader.pages:
                    writer.add_page(page)
                    total_pages += 1

            output = BytesIO()
            writer.write(output)
            output.seek(0)
            
            flash(f"Successfully merged {len(valid_files)} PDFs ({total_pages} pages total)!", "success")
        except PdfReadError as e:
            app.logger.error(f"PDF read error during merge: {e}")
            flash("One or more files are corrupted or not valid PDFs.", "error")
            return redirect(url_for("index"))
        except Exception as e:
            app.logger.error(f"Error merging PDFs: {e}")
            flash("There was an error while merging the PDFs.", "error")
            return redirect(url_for("index"))

        return send_file(
            output,
            as_attachment=True,
            download_name=f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mimetype="application/pdf",
        )

    @app.route("/split", methods=["POST"])
    def split_pdf():
        """Split PDF by extracting specific pages."""
        file = request.files.get("split_file")
        pages_range = request.form.get("pages_range", "").strip()

        if not file or not allowed_file(file.filename):
            flash("Please upload a valid PDF file to split.", "error")
            return redirect(url_for("index"))

        if not pages_range:
            flash("Please specify pages to keep, for example: 1-3,5", "error")
            return redirect(url_for("index"))

        try:
            # Validate file content
            if not validate_pdf_content(file.stream):
                flash("Invalid PDF file.", "error")
                return redirect(url_for("index"))
            
            reader = PdfReader(file.stream)
            writer = PdfWriter()

            # Parse page ranges like "1-3,5,7-9"
            pages_to_keep = set()
            for part in pages_range.split(","):
                part = part.strip()
                if "-" in part:
                    start_str, end_str = part.split("-", 1)
                    start = int(start_str)
                    end = int(end_str)
                    for p in range(start, end + 1):
                        pages_to_keep.add(p - 1)
                else:
                    pages_to_keep.add(int(part) - 1)

            max_index = len(reader.pages) - 1
            pages_to_keep = [p for p in sorted(pages_to_keep) if 0 <= p <= max_index]

            if not pages_to_keep:
                flash("No valid pages were specified.", "error")
                return redirect(url_for("index"))

            for page_index in pages_to_keep:
                writer.add_page(reader.pages[page_index])

            output = BytesIO()
            writer.write(output)
            output.seek(0)
            
            flash(f"Successfully extracted {len(pages_to_keep)} pages!", "success")
        except ValueError:
            flash("Invalid page range format. Use format like: 1-3,5,7-9", "error")
            return redirect(url_for("index"))
        except PdfReadError as e:
            app.logger.error(f"PDF read error during split: {e}")
            flash("The PDF file is corrupted or invalid.", "error")
            return redirect(url_for("index"))
        except Exception as e:
            app.logger.error(f"Error splitting PDF: {e}")
            flash("There was an error while splitting the PDF. Check your page range.", "error")
            return redirect(url_for("index"))

        return send_file(
            output,
            as_attachment=True,
            download_name=f"split_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mimetype="application/pdf",
        )

    @app.route("/extract-text", methods=["POST"])
    def extract_text():
        """Extract text from PDF."""
        file = request.files.get("text_file")
        if not file or not allowed_file(file.filename):
            flash("Please upload a valid PDF file to extract text.", "error")
            return redirect(url_for("index"))

        try:
            # Validate file content
            if not validate_pdf_content(file.stream):
                flash("Invalid PDF file.", "error")
                return redirect(url_for("index"))
            
            reader = PdfReader(file.stream)
            extracted = []
            for i, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    extracted.append(f"--- Page {i} ---\n{text.strip()}\n")

            result = "\n".join(extracted).strip()
            if not result:
                result = "No extractable text was found in this PDF."
                flash("No text found in the PDF.", "warning")
            else:
                flash(f"Successfully extracted text from {len(reader.pages)} pages!", "success")

            output = BytesIO(result.encode("utf-8"))
            output.seek(0)
        except PdfReadError as e:
            app.logger.error(f"PDF read error during text extraction: {e}")
            flash("The PDF file is corrupted or invalid.", "error")
            return redirect(url_for("index"))
        except Exception as e:
            app.logger.error(f"Error extracting text: {e}")
            flash("There was an error while extracting text from the PDF.", "error")
            return redirect(url_for("index"))

        return send_file(
            output,
            as_attachment=True,
            download_name=f"extracted_text_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mimetype="text/plain; charset=utf-8",
        )

    @app.route("/rotate", methods=["POST"])
    def rotate_pdf():
        """Rotate PDF pages by specified degrees."""
        file = request.files.get("rotate_file")
        rotation = request.form.get("rotation", "90")

        if not file or not allowed_file(file.filename):
            flash("Please upload a valid PDF file to rotate.", "error")
            return redirect(url_for("index"))

        try:
            rotation_degrees = int(rotation)
            if rotation_degrees not in [90, 180, 270]:
                flash("Rotation must be 90, 180, or 270 degrees.", "error")
                return redirect(url_for("index"))

            # Validate file content
            if not validate_pdf_content(file.stream):
                flash("Invalid PDF file.", "error")
                return redirect(url_for("index"))

            reader = PdfReader(file.stream)
            writer = PdfWriter()

            for page in reader.pages:
                page.rotate(rotation_degrees)
                writer.add_page(page)

            output = BytesIO()
            writer.write(output)
            output.seek(0)
            
            flash(f"Successfully rotated {len(reader.pages)} pages by {rotation_degrees}°!", "success")
        except ValueError:
            flash("Invalid rotation value.", "error")
            return redirect(url_for("index"))
        except PdfReadError as e:
            app.logger.error(f"PDF read error during rotation: {e}")
            flash("The PDF file is corrupted or invalid.", "error")
            return redirect(url_for("index"))
        except Exception as e:
            app.logger.error(f"Error rotating PDF: {e}")
            flash("There was an error while rotating the PDF.", "error")
            return redirect(url_for("index"))

        return send_file(
            output,
            as_attachment=True,
            download_name=f"rotated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mimetype="application/pdf",
        )

    @app.route("/protect", methods=["POST"])
    def protect_pdf():
        """Add password protection to PDF."""
        file = request.files.get("protect_file")
        password = request.form.get("password", "").strip()

        if not file or not allowed_file(file.filename):
            flash("Please upload a valid PDF file to protect.", "error")
            return redirect(url_for("index"))

        if not password or len(password) < 4:
            flash("Password must be at least 4 characters long.", "error")
            return redirect(url_for("index"))

        try:
            # Validate file content
            if not validate_pdf_content(file.stream):
                flash("Invalid PDF file.", "error")
                return redirect(url_for("index"))

            reader = PdfReader(file.stream)
            writer = PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            # Encrypt the PDF
            writer.encrypt(user_password=password, owner_password=None, algorithm="AES-256")

            output = BytesIO()
            writer.write(output)
            output.seek(0)
            
            flash("Successfully added password protection to PDF!", "success")
        except PdfReadError as e:
            app.logger.error(f"PDF read error during protection: {e}")
            flash("The PDF file is corrupted or invalid.", "error")
            return redirect(url_for("index"))
        except Exception as e:
            app.logger.error(f"Error protecting PDF: {e}")
            flash("There was an error while protecting the PDF.", "error")
            return redirect(url_for("index"))

        return send_file(
            output,
            as_attachment=True,
            download_name=f"protected_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mimetype="application/pdf",
        )

    @app.route("/compress", methods=["POST"])
    def compress_pdf():
        """Compress PDF by reducing image quality."""
        file = request.files.get("compress_file")

        if not file or not allowed_file(file.filename):
            flash("Please upload a valid PDF file to compress.", "error")
            return redirect(url_for("index"))

        try:
            # Validate file content
            if not validate_pdf_content(file.stream):
                flash("Invalid PDF file.", "error")
                return redirect(url_for("index"))

            reader = PdfReader(file.stream)
            writer = PdfWriter()

            for page in reader.pages:
                page.compress_content_streams()
                writer.add_page(page)

            # Compress images in the PDF
            for page in writer.pages:
                for img in page.images:
                    try:
                        # This is a basic compression - pypdf has limited image manipulation
                        img.replace(img.image, quality=50)
                    except Exception:
                        pass  # Skip if image compression fails

            output = BytesIO()
            writer.write(output)
            output.seek(0)
            
            original_size = len(file.stream.read())
            file.stream.seek(0)
            compressed_size = len(output.getvalue())
            reduction = ((original_size - compressed_size) / original_size) * 100
            
            flash(f"PDF compressed! Size reduced by {reduction:.1f}%", "success")
        except PdfReadError as e:
            app.logger.error(f"PDF read error during compression: {e}")
            flash("The PDF file is corrupted or invalid.", "error")
            return redirect(url_for("index"))
        except Exception as e:
            app.logger.error(f"Error compressing PDF: {e}")
            flash("There was an error while compressing the PDF.", "error")
            return redirect(url_for("index"))

        return send_file(
            output,
            as_attachment=True,
            download_name=f"compressed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mimetype="application/pdf",
        )

    @app.route("/metadata", methods=["POST"])
    def edit_metadata():
        """Edit PDF metadata."""
        file = request.files.get("metadata_file")
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        subject = request.form.get("subject", "").strip()

        if not file or not allowed_file(file.filename):
            flash("Please upload a valid PDF file to edit metadata.", "error")
            return redirect(url_for("index"))

        try:
            # Validate file content
            if not validate_pdf_content(file.stream):
                flash("Invalid PDF file.", "error")
                return redirect(url_for("index"))

            reader = PdfReader(file.stream)
            writer = PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            # Add metadata
            metadata = {}
            if title:
                metadata["/Title"] = title
            if author:
                metadata["/Author"] = author
            if subject:
                metadata["/Subject"] = subject
            
            writer.add_metadata(metadata)

            output = BytesIO()
            writer.write(output)
            output.seek(0)
            
            flash("Successfully updated PDF metadata!", "success")
        except PdfReadError as e:
            app.logger.error(f"PDF read error during metadata edit: {e}")
            flash("The PDF file is corrupted or invalid.", "error")
            return redirect(url_for("index"))
        except Exception as e:
            app.logger.error(f"Error editing metadata: {e}")
            flash("There was an error while editing PDF metadata.", "error")
            return redirect(url_for("index"))

        return send_file(
            output,
            as_attachment=True,
            download_name=f"metadata_updated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            mimetype="application/pdf",
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)