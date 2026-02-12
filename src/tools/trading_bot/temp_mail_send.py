import os
import smtplib
from email.message import EmailMessage

# 1. Setup paths (Matching your previous logic)
today_folder = datetime.today().strftime("%d-%m-%Y")
pdf_path = os.path.join(today_folder, "Final_Stock_Analysis.pdf")

# 2. Extract Tickers for Response
# Assuming df is your filtered dataframe from previous steps
best_stock_tickers = df['Symbol'].tolist()

# --- EMAIL SENDING LOGIC ---
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL = "knpatel0707@gmail.com"
APP_PASSWORD = "ules habb jtdm jvni"

msg = EmailMessage()
msg["Subject"] = f"Best Stocks for Tomorrow - {today_folder}"
msg["From"] = EMAIL
msg["To"] = "kevalnpatel070@gmail.com"

# Plain text body
body_content = f"""Hello,

Please find the attached PDF for today's best stock analysis.

Best Stock Tickers:
{', '.join(best_stock_tickers)}

Technically Strong Stocks:
{', '.join(filtered_stocks_list)}

Best regards,
Stock Scanner Bot"""

msg.set_content(body_content)

# 3. Attach the PDF file
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
    except Exception as e:
        print(f"Failed to send email: {e}")
else:
    print(f"Error: PDF file not found at {pdf_path}. Email not sent.")

# 4. Response Output
print("\n--- Summary ---")
print(f"Best Stock Tickers: {best_stock_tickers}")
print(f"Filtered (Technically Strong): {filtered_stocks_list}")