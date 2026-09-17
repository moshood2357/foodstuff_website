import os
import requests

import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

BREVO_API_KEY = os.getenv("BREVO_API_KEY") 


def send_email(to, subject, html_content, sender_name="Judith Ethnic Store", sender_email=None):
    """
    Send transactional email via Brevo API
    """

    if not sender_email:
        sender_email = os.getenv("BREVO_SENDER_EMAIL")

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    payload = {
        "sender": {
            "name": sender_name,
            "email": sender_email
        },
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html_content
    }

    try:
        response = requests.post(BREVO_API_URL, json=payload, headers=headers)

        if response.status_code not in [200, 201, 202]:
            print("Email failed:", response.text)

        return {
            "success": response.status_code in [200, 201, 202],
            "status_code": response.status_code,
            "response": response.json() if response.text else {}
        }

    except Exception as e:
        print("Email exception:", str(e))
        return {
            "success": False,
            "error": str(e)
        }


import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from flask import current_app


# =========================
# ADMIN NOTIFICATION
# =========================
def send_order_notification(order):
    """Notify admin when a new order is placed."""
    _send_email(
        to_email=current_app.config["ADMIN_EMAIL"],
        to_name="Admin",
        subject=f"New Order - {order.order_number}",
        html_content=_build_order_html(
            order,
            heading="New Order Received!",
            intro="A new order has been placed and is awaiting your review."
        )
    )


# =========================
# CUSTOMER CONFIRMATION
# =========================
def send_order_confirmation_customer(order):
    """Send confirmation email to customer when order is confirmed."""
    if order.user:
        customer_email = order.user.email
        customer_name  = order.user.first_name
    elif order.guest_email:
        customer_email = order.guest_email
        customer_name  = order.address.full_name if order.address else "Customer"
    else:
        print("No customer email found for order", order.order_number)
        return

    if order.fulfillment_type == "pickup":
        intro = (
            f"Hi {customer_name}, your order has been confirmed and is being prepared. "
            f"We will notify you when it is ready for collection at "
            f"311 High Street, Cheltenham GL50 3HW."
        )
    else:
        intro = (
            f"Hi {customer_name}, your order has been confirmed and is being processed. "
            f"We will notify you when it has been dispatched."
        )

    _send_email(
        to_email=customer_email,
        to_name=customer_name,
        subject=f"Order Confirmed — {order.order_number}",
        html_content=_build_order_html(
            order,
            heading="Your Order is Confirmed!",
            intro=intro
        )
    )


# =========================
# ORDER PREPARING
# =========================
def send_order_preparing_customer(order):
    if order.user:
        customer_email = order.user.email
        customer_name  = order.user.first_name
    elif order.guest_email:
        customer_email = order.guest_email
        customer_name  = order.address.full_name if order.address else "Customer"
    else:
        print("No customer email for preparing notification")
        return

    _send_email(
        to_email=customer_email,
        to_name=customer_name,
        subject=f"Your Order {order.order_number} is Being Prepared",
        html_content=_build_order_html(
            order,
            heading="Your Order is Being Prepared!",
            intro=f"Hi {customer_name}, great news! The kitchen has started preparing your order. It should be ready in approximately {order.prep_time} minutes."
        )
    )


# =========================
# ORDER COMPLETED
# =========================
def send_order_completed_customer(order):
    if order.user:
        customer_email = order.user.email
        customer_name  = order.user.first_name
    elif order.guest_email:
        customer_email = order.guest_email
        customer_name  = order.address.full_name if order.address else "Customer"
    else:
        print("No customer email for completed notification")
        return

    _send_email(
        to_email=customer_email,
        to_name=customer_name,
        subject=f"Your Order {order.order_number} is Ready!",
        html_content=_build_order_html(
            order,
            heading="Your Order is Ready!",
            intro=f"Hi {customer_name}, your order is ready! Thank you for choosing Judith Kitchen."
        )
    )


# =========================
# SHARED HTML BUILDER
# =========================
def _build_order_html(order, heading, intro):
    items_html = ""

    for item in order.items:
        items_html += f"""
        <tr>
            <td style="padding:10px;border-bottom:1px solid #f1f5f9;">
                <div style="font-weight:600;color:#0f172a;">{item.product_name}</div>
            </td>
            <td style="padding:10px;text-align:center;border-bottom:1px solid #f1f5f9;">
                {item.quantity}
            </td>
            <td style="padding:10px;text-align:right;border-bottom:1px solid #f1f5f9;">
                &#163;{float(item.price):.2f}
            </td>
            <td style="padding:10px;text-align:right;border-bottom:1px solid #f1f5f9;font-weight:600;">
                &#163;{float(item.price * item.quantity):.2f}
            </td>
        </tr>
        """

    address = order.address

    if address:
        address_html = f"""
            {address.full_name}<br>
            {address.address_line_1}<br>
            {f"{address.address_line_2}<br>" if address.address_line_2 else ""}
            {address.city}, {address.state}<br>
            {address.postal_code}<br>
            {address.country}<br>
            {address.phone}
        """
    else:
        address_html = "No address provided"

    fulfillment = (
        "Click &amp; Collect &#8212; 311 High Street, Cheltenham GL50 3HW"
        if order.fulfillment_type == "pickup"
        else "Home Delivery"
    )

    # Build collection/delivery section
    if order.fulfillment_type == "pickup":
        collection_html = """
        <div style="background:#f0fdf4;border:1px solid #22c55e;border-radius:8px;padding:16px;margin-bottom:20px;">
            <h3 style="color:#0f5c2e;margin:0 0 8px;font-size:1rem;">
                Collection Address
            </h3>

            <p style="color:#475569;margin:0;line-height:1.8;font-size:0.9rem;">
                Judith Ethnic Food Store<br>
                311 High Street<br>
                Cheltenham GL50 3HW<br>
                Tel: +44 7306 011093
            </p>
        </div>
        """

        delivery_html = ""

    else:
        collection_html = ""

        delivery_html = f"""
        <h3 style="color:#0f172a;font-size:1rem;border-bottom:2px solid #f0fdf4;padding-bottom:10px;margin-bottom:16px;">
            Delivery Address
        </h3>

        <p style="line-height:1.9;color:#475569;font-size:0.9rem;background:#f8fafc;padding:16px;border-radius:8px;">
            {address_html}
        </p>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{heading}</title>
    </head>

    <body style="margin:0;padding:0;background:#ffffff;">

        <div style="font-family:Arial,Helvetica,sans-serif;max-width:600px;margin:0 auto;color:#1e293b;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;">

            <!-- HEADER -->
            <div style="background:#0f5c2e;padding:28px 24px;text-align:center;">

                <img src="https://judithethnicstore.co.uk/static/images/ethnic.png"
                     alt="Judith Ethnic Store"
                     style="height:50px;margin-bottom:12px;display:block;margin:0 auto 12px;">

                <h1 style="color:#fff;margin:0;font-size:1.3rem;font-weight:700;">
                    {heading}
                </h1>

            </div>

            <!-- BODY -->
            <div style="padding:28px 24px;">

                <p style="font-size:0.95rem;color:#475569;margin-bottom:20px;line-height:1.6;">
                    {intro}
                </p>

                <!-- ORDER DETAILS -->
                <table style="width:100%;border-collapse:collapse;margin-bottom:24px;border-radius:8px;overflow:hidden;border:1px solid #e2e8f0;">

                    <tr style="background:#f0fdf4;">
                        <td style="padding:12px 16px;font-weight:700;width:40%;color:#0f5c2e;">
                            Order Number
                        </td>

                        <td style="padding:12px 16px;font-weight:700;color:#0f172a;">
                            {order.order_number}
                        </td>
                    </tr>

                    <tr style="background:#fff;">
                        <td style="padding:12px 16px;font-weight:600;color:#64748b;">
                            Date
                        </td>

                        <td style="padding:12px 16px;color:#0f172a;">
                            {order.created_at.strftime("%d %b %Y, %I:%M %p")}
                        </td>
                    </tr>

                    <tr style="background:#f8fafc;">
                        <td style="padding:12px 16px;font-weight:600;color:#64748b;">
                            Fulfilment
                        </td>

                        <td style="padding:12px 16px;color:#0f172a;">
                            {fulfillment}
                        </td>
                    </tr>

                    <tr style="background:#fff;">
                        <td style="padding:12px 16px;font-weight:600;color:#64748b;">
                            Payment
                        </td>

                        <td style="padding:12px 16px;">

                            <span style="background:#dcfce7;color:#166534;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700;">
                                {order.payment_status.value.upper()}
                            </span>

                        </td>
                    </tr>

                </table>

                <!-- ITEMS -->
                <h3 style="color:#0f172a;font-size:1rem;border-bottom:2px solid #f0fdf4;padding-bottom:10px;margin-bottom:16px;">
                    &#128722; Your Items
                </h3>

                <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">

                    <thead>
                        <tr style="background:#0f5c2e;color:#fff;">

                            <th style="padding:10px 12px;text-align:left;font-size:13px;">
                                Product
                            </th>

                            <th style="padding:10px 12px;text-align:center;font-size:13px;">
                                Qty
                            </th>

                            <th style="padding:10px 12px;text-align:right;font-size:13px;">
                                Price
                            </th>

                            <th style="padding:10px 12px;text-align:right;font-size:13px;">
                                Total
                            </th>

                        </tr>
                    </thead>

                    <tbody>
                        {items_html}
                    </tbody>

                </table>

                <!-- TOTALS -->
                <table style="width:100%;margin-bottom:24px;border-top:1px solid #e2e8f0;padding-top:12px;">

                    <tr>
                        <td style="padding:6px 0;color:#64748b;font-size:14px;">
                            Subtotal
                        </td>

                        <td style="padding:6px 0;text-align:right;font-size:14px;">
                            &#163;{float(order.subtotal or 0):.2f}
                        </td>
                    </tr>

                    <tr>
                        <td style="padding:6px 0;color:#64748b;font-size:14px;">
                            Delivery
                        </td>

                        <td style="padding:6px 0;text-align:right;font-size:14px;">
                            {
                                "Free (Collection)"
                                if order.fulfillment_type == "pickup"
                                else f"&#163;{float(order.shipping_fee or 0):.2f}"
                            }
                        </td>
                    </tr>

                    <tr>
                        <td style="padding:6px 0;color:#64748b;font-size:14px;">
                            Tax
                        </td>

                        <td style="padding:6px 0;text-align:right;font-size:14px;">
                            &#163;{float(order.tax or 0):.2f}
                        </td>
                    </tr>

                    <tr style="font-weight:800;font-size:1.1em;border-top:2px solid #0f5c2e;margin-top:8px;">

                        <td style="padding-top:12px;color:#0f172a;">
                            Total
                        </td>

                        <td style="padding-top:12px;text-align:right;color:#0f5c2e;">
                            &#163;{float(order.total_amount or 0):.2f}
                        </td>

                    </tr>

                </table>

                <!-- ADDRESS / COLLECTION -->
                {collection_html}
                {delivery_html}

                <!-- CTA -->
                <div style="text-align:center;margin-top:24px;">

                    <a href="https://judithethnicstore.co.uk/shop"
                       style="background:#0f5c2e;color:#fff;padding:12px 28px;border-radius:8px;
                              text-decoration:none;font-weight:700;font-size:14px;display:inline-block;">
                        Continue Shopping
                    </a>

                </div>

            </div>

            <!-- FOOTER -->
            <div style="background:#0f172a;padding:20px 24px;text-align:center;">

                <p style="color:#94a3b8;font-size:12px;margin:0 0 8px;">
                    Judith Ethnic Food Store Ltd &middot; 311 High Street &middot; Cheltenham &middot; GL50 3WS
                </p>

                <p style="color:#64748b;font-size:11px;margin:0;">
                    +44 7306 011093 &middot; judithethnicstore.co.uk
                </p>

                <p style="color:#475569;font-size:11px;margin:8px 0 0;">
                    Powered by
                    <a href="https://r2systemsolution.co.uk"
                       style="color:#22c55e;text-decoration:none;">
                        R2 System Solution Ltd
                    </a>
                </p>

            </div>

        </div>

    </body>
    </html>
    """


# =========================
# SEND VIA BREVO
# =========================
def _send_email(to_email, to_name, subject, html_content):
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key["api-key"] = current_app.config["BREVO_API_KEY"]

    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": to_email, "name": to_name}],
        sender={
            "email": current_app.config["BREVO_SENDER_EMAIL"],
            "name":  "Judith Ethnic Store"
        },
        subject=subject,
        html_content=html_content
    )

    try:
        api_instance.send_transac_email(send_smtp_email)
        current_app.logger.info(f"Email sent to {to_email} - {subject}")
    except ApiException as e:
        current_app.logger.error(f"Brevo email error: {e}")


# =========================
# ORDER REJECTED
# =========================
def send_order_rejected_customer(order, reason):
    if order.user:
        customer_email = order.user.email
        customer_name  = order.user.first_name
    elif order.guest_email:
        customer_email = order.guest_email
        customer_name  = order.address.full_name if order.address else "Customer"
    else:
        print("No customer email for rejection notification")
        return

    html_content = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#1e293b;">
        <div style="background:#0f172a;padding:24px;text-align:center;">
            <h1 style="color:#fff;margin:0;font-size:1.4rem;">Order Update</h1>
        </div>
        <div style="padding:24px;">
            <p style="font-size:0.95rem;color:#475569;margin-bottom:16px;">
                Hi {customer_name}, unfortunately your order <strong>{order.order_number}</strong>
                could not be fulfilled at this time.
            </p>
            <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px;margin:16px 0;">
                <p style="margin:0;font-weight:600;color:#991b1b;">Reason:</p>
                <p style="margin:8px 0 0;color:#7f1d1d;">{reason}</p>
            </div>
            <p style="color:#475569;font-size:0.9rem;">
                If you have any questions, please contact us. We apologise for any inconvenience.
            </p>
        </div>
        <div style="background:#f8fafc;padding:16px;text-align:center;color:#94a3b8;font-size:0.82rem;border-top:1px solid #e2e8f0;">
            Judith Ethnic Store &mdash; We appreciate your patience
        </div>
    </div>
    """

    _send_email(
        to_email=customer_email,
        to_name=customer_name,
        subject=f"Your Order {order.order_number} — Update",
        html_content=html_content
    )



def send_purchase_order_email(po):
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
    from flask import current_app

    api_key = current_app.config.get("BREVO_API_KEY")
    if not api_key:
        raise Exception("BREVO_API_KEY not configured")

    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key['api-key'] = api_key
    api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )

    # build items table
    items_html = ""
    for item in po.items:
        items_html += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">{item.product_name}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{item.variant_name or '—'}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{item.quantity_ordered}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">£{float(item.unit_cost):.2f}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">£{float(item.total_cost or 0):.2f}</td>
        </tr>
        """

    html_content = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;">
        <h2 style="color:#0f5c2e;">Purchase Order — {po.po_number}</h2>
        <p>Dear {po.supplier.contact_name or po.supplier.name},</p>
        <p>Please find below our purchase order details:</p>

        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
            <tr style="background:#f8fafc;">
                <th style="padding:10px;text-align:left;border-bottom:2px solid #e5e7eb;">PO Number</th>
                <td style="padding:10px;">{po.po_number}</td>
            </tr>
            <tr>
                <th style="padding:10px;text-align:left;border-bottom:1px solid #e5e7eb;">Date</th>
                <td style="padding:10px;">{po.created_at.strftime('%d/%m/%Y')}</td>
            </tr>
            <tr style="background:#f8fafc;">
                <th style="padding:10px;text-align:left;border-bottom:1px solid #e5e7eb;">Expected Delivery</th>
                <td style="padding:10px;">{po.expected_date.strftime('%d/%m/%Y') if po.expected_date else 'TBD'}</td>
            </tr>
        </table>

        <h3 style="color:#0f172a;">Order Items</h3>
        <table style="width:100%;border-collapse:collapse;">
            <thead>
                <tr style="background:#0f5c2e;color:#fff;">
                    <th style="padding:10px;text-align:left;">Product</th>
                    <th style="padding:10px;text-align:left;">Variant</th>
                    <th style="padding:10px;text-align:left;">Qty</th>
                    <th style="padding:10px;text-align:left;">Unit Cost</th>
                    <th style="padding:10px;text-align:left;">Total</th>
                </tr>
            </thead>
            <tbody>
                {items_html}
            </tbody>
            <tfoot>
                <tr style="background:#f8fafc;font-weight:bold;">
                    <td colspan="4" style="padding:10px;text-align:right;">Total:</td>
                    <td style="padding:10px;">£{float(po.total_cost or 0):.2f}</td>
                </tr>
            </tfoot>
        </table>

        {f'<p><strong>Notes:</strong> {po.notes}</p>' if po.notes else ''}

        <hr style="margin:30px 0;border:none;border-top:1px solid #e5e7eb;">
        <p style="color:#64748b;font-size:13px;">
            Judith Ethnic Food Store<br>
            311 High Street, Cheltenham GL50 3WS<br>
            +44 7306 011093
        </p>
    </div>
    """

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": po.supplier.email, "name": po.supplier.contact_name or po.supplier.name}],
        sender={
            "email": current_app.config.get("BREVO_SENDER_EMAIL"),
            "name": "Judith Ethnic Food Store"
        },
        reply_to={
            "email": current_app.config.get("BREVO_SENDER_EMAIL"),
            "name": "Judith Ethnic Food Store"
        },
        subject=f"Purchase Order {po.po_number} — Judith Ethnic Food Store",
        html_content=html_content,
    )

    api_instance.send_transac_email(send_smtp_email)



def send_purchase_order_whatsapp(po):
    from twilio.rest import Client
    from flask import current_app

    account_sid = current_app.config.get("TWILIO_ACCOUNT_SID")
    auth_token  = current_app.config.get("TWILIO_AUTH_TOKEN")
    from_number = current_app.config.get("TWILIO_WHATSAPP_FROM")

    if not all([account_sid, auth_token, from_number]):
        raise Exception("Twilio credentials not configured")

    if not po.supplier.phone:
        raise Exception("Supplier has no phone number")

    # format phone number
    phone = po.supplier.phone.strip().replace(' ', '')
    if not phone.startswith('+'):
        phone = '+' + phone

    # build message
    items_text = ""
    for item in po.items:
        items_text += f"\n• {item.product_name}"
        if item.variant_name:
            items_text += f" ({item.variant_name})"
        items_text += f" — Qty: {item.quantity_ordered} @ £{float(item.unit_cost):.2f}"

    message = f"""
*Purchase Order — {po.po_number}*
From: Judith Ethnic Food Store
Date: {po.created_at.strftime('%d/%m/%Y')}
Expected Delivery: {po.expected_date.strftime('%d/%m/%Y') if po.expected_date else 'TBD'}

*Items Ordered:*{items_text}

*Total: £{float(po.total_cost or 0):.2f}*

{f'Notes: {po.notes}' if po.notes else ''}

Please confirm receipt of this order.
Thank you.
    """.strip()

    client = Client(account_sid, auth_token)
    client.messages.create(
        from_=from_number,
        to=f"whatsapp:{phone}",
        body=message
    )