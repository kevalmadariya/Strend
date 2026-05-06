import os
import smtplib
from email.message import EmailMessage

def send_report_email(to_email, pdf_path, best_tickers, filtered_stocks_list):
    """
    Sends the analysis report email.
    """
    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 587
    EMAIL = "knpatel0707@gmail.com"
    APP_PASSWORD = "ules habb jtdm jvni"

    today_date = os.path.basename(os.path.dirname(pdf_path)) # infer date from folder if possible, or just ignore

    msg = EmailMessage()
    msg["Subject"] = f"Best Stocks for Tomorrow"
    msg["From"] = EMAIL
    msg["To"] = to_email

    # Plain text body
    body_content = f"""Hello,

Please find the attached PDF for today's best stock analysis.

Best Stock Tickers:
{', '.join(best_tickers)}

Technically Strong Stocks:
{', '.join(filtered_stocks_list)}

Best regards,
Stock Scanner Bot"""

    msg.set_content(body_content)

    # Attach the PDF file
    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            file_data = f.read()
            file_name = os.path.basename(pdf_path)
            msg.add_attachment(
                file_data,
                maintype="application",
                subtype="pdf",
                filename=file_name
            )

        # Send the Email
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(EMAIL, APP_PASSWORD)
                smtp.send_message(msg)
            print(f"Email sent successfully with attachment: {file_name}")
            return True
        except Exception as e:
            print(f"Failed to send email: {e}")
            return False
    else:
        print(f"Error: PDF file not found at {pdf_path}. Email not sent.")
        return False
