from playwright.async_api import async_playwright
import asyncio
import os

async def convert_html_to_pdf(html_file_path, output_pdf_path):
    async with async_playwright() as p:
        # Launch headless browser
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Load the local HTML file
        # Use an absolute path for the file URL
        absolute_html_path = os.path.abspath(html_file_path)
        await page.goto(f"file:///{absolute_html_path}")

        # Wait for images to load before printing
        await page.wait_for_load_state("networkidle")

        # Emulate print media for A4 size
        await page.pdf(
            path=output_pdf_path,
            format="A4",
            print_background=True, # Critical for CSS colors and backgrounds
            margin={"top": "1cm", "right": "1cm", "bottom": "1cm", "left": "1cm"},
            display_header_footer=False
        )

        await browser.close()
        print(f"PDF successfully created at: {output_pdf_path}")

# --- Execution ---
html_path = os.path.join(today_folder, "stock_analysis_report.html")
pdf_path = os.path.join(today_folder, "Final_Stock_Analysis.pdf")

# Generate the PDF
await convert_html_to_pdf(html_path, pdf_path)