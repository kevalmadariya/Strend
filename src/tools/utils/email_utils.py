import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import os
import jinja2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def make_html_template(data_list: list, title: str = "Stock Predictions"):
    """
    Generates an HTML report from a list of stock data dictionaries using Jinja2.
    """
    print(f"📄 [Email Utils] Generating HTML template for {len(data_list)} items.")
    try:
        template_str = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { font-family: Arial, sans-serif; }
                table { width: 100%; border-collapse: collapse; margin-top: 20px; }
                th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
                th { background-color: #f2f2f2; }
                h1 { color: #333; }
                .bullish { color: green; font-weight: bold; }
                .bearish { color: red; font-weight: bold; }
            </style>
        </head>
        <body>
            <h1>{{ title }}</h1>
            <p>Total Stocks Found: <strong>{{ data|length }}</strong></p>
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Price</th>
                        <th>Trend</th>
                        <th>Patterns</th>
                        <th>RSI</th>
                        <th>MACD</th>
                    </tr>
                </thead>
                <tbody>
                    {% for item in data %}
                    <tr>
                        <td>{{ item.ticker }}</td>
                        <td>{{ item.price }}</td>
                        <td class="{{ 'bullish' if item.trend == 1 else 'bearish' }}">
                            {{ 'Bullish' if item.trend == 1 else 'Bearish' }}
                        </td>
                        <td>{{ item.patterns if item.patterns else '-' }}</td>
                        <td>{{ "%.2f"|format(item.indicators.rsi) if item.indicators.rsi else 'N/A' }}</td>
                        <td>{{ "%.2f"|format(item.indicators.macd) if item.indicators.macd else 'N/A' }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </body>
        </html>
        """
        template = jinja2.Template(template_str)
        html_output = template.render(data=data_list, title=title)
        print("✅ [Email Utils] HTML generated successfully.")
        return html_output
    except Exception as e:
        print(f"❌ [Email Utils] Error generating HTML: {e}")
        return "<html><body><h1>Error generating report</h1></body></html>"

def send_mail(recipient: str, subject: str, body: str, attachment_path: str = None):
    """
    Sends an email with an optional attachment.
    Fetches credentials from environment variables.
    """
    print(f"📧 [Email Utils] Preparing to send email to {recipient}...")
    
    # Get config from env
    sender_email = os.getenv("EMAIL_USER")
    sender_password = os.getenv("EMAIL_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port_str = os.getenv("SMTP_PORT", "587")
    
    if not sender_email or not sender_password:
        print("⚠️ [Email Utils] EMAIL_USER or EMAIL_PASSWORD not set in .env. Mocking email send.")
        print(f"   [Mock] To: {recipient}, Subject: {subject}, Attachment: {attachment_path}")
        return True

    try:
        smtp_port = int(smtp_port_str)
        
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'html'))

        if attachment_path and os.path.exists(attachment_path):
            print(f"📎 [Email Utils] Attaching file: {attachment_path}")
            with open(attachment_path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(attachment_path))
            part['Content-Disposition'] = f'attachment; filename="{os.path.basename(attachment_path)}"'
            msg.attach(part)
        elif attachment_path:
             print(f"⚠️ [Email Utils] Attachment file not found: {attachment_path}")

        print(f"🔌 [Email Utils] Connecting to SMTP server {smtp_server}:{smtp_port}...")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print(f"✅ [Email Utils] Email sent successfully to {recipient}")
        return True
    
    except Exception as e:
        print(f"❌ [Email Utils] Failed to send email: {e}")
        return False
