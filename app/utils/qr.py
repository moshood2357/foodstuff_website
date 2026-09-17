import os
import qrcode
import barcode
from barcode.writer import ImageWriter
from flask import current_app


def generate_product_qr(product):
    """Generate QR code that opens product page when scanned."""
    qr_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'qrcodes')
    os.makedirs(qr_dir, exist_ok=True)

    url = f"https://judithethnicstore.co.uk/product/{product.slug}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img      = qr.make_image(fill_color="black", back_color="white")
    filename = f"qr_{product.slug}.png"
    img.save(os.path.join(qr_dir, filename))

    return filename


def generate_product_barcode(product):
    """Generate Code128 barcode for ePOS scanning."""
    barcode_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'qrcodes')
    os.makedirs(barcode_dir, exist_ok=True)

    sku     = product.sku or f"JES-{str(product.id).zfill(5)}"
    code128 = barcode.get('code128', sku, writer=ImageWriter())

    filename = f"barcode_{product.slug}"
    filepath = os.path.join(barcode_dir, filename)

    code128.save(filepath, options={
         # Make the barcode physically wider
            "module_width": 3.0,

            # Make the bars taller
            "module_height": 30,

            # Human-readable barcode number
            "font_size": 14,

            # Space between barcode and number
            "text_distance": 5,

            # White space around barcode
            "quiet_zone": 6,

            # Display the SKU underneath
            "write_text": True,

            # Higher resolution
            "dpi": 300,
    })

    return filename + ".png"


def generate_both(product):
    """Generate both QR code and barcode. Returns (qr_filename, barcode_filename)."""
    qr_file      = generate_product_qr(product)
    barcode_file = generate_product_barcode(product)
    return qr_file, barcode_file


def generate_variant_qr(product, variant):
    """Generate QR code for a variant — opens product page with variant param."""
    qr_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'qrcodes')
    os.makedirs(qr_dir, exist_ok=True)

    url = f"https://judithethnicstore.co.uk/product/{product.slug}?variant={variant.id}"

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)

    img      = qr.make_image(fill_color="black", back_color="white")
    filename = f"qr_{product.slug}_v{variant.id}.png"
    img.save(os.path.join(qr_dir, filename))

    return filename


def generate_variant_barcode(variant):
    """Generate Code128 barcode for a variant using its SKU — for POS scanning."""
    barcode_dir = os.path.join(current_app.root_path, 'static', 'uploads', 'qrcodes')
    os.makedirs(barcode_dir, exist_ok=True)

    sku     = variant.sku or f"JES-V{str(variant.id).zfill(5)}"
    code128 = barcode.get('code128', sku, writer=ImageWriter())

    filename = f"barcode_v{variant.id}"
    filepath = os.path.join(barcode_dir, filename)

    code128.save(filepath, options={
         # Make the barcode physically wider
            "module_width": 3.0,

            # Make the bars taller
            "module_height":30,

            # Human-readable barcode number
            "font_size": 14,

            # Space between barcode and number
            "text_distance": 4,

            # White space around barcode
            # Keep this large enough for scanners
            "quiet_zone": 6,

            # Display the SKU underneath
            "write_text": True,

            # Higher resolution
            "dpi": 300,
    })

    return filename + ".png"