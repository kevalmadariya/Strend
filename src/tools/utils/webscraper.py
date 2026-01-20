import requests
from bs4 import BeautifulSoup
from tempfile import tempdir
import yfinance as yf

def WebScaping(ticker, ratios, charts, holdings, analysis):
          #utility functions =============================================================

          def remove_extra_space_and_characters(input_string):
            characters_to_remove = [' ','\n', '\t', '\r', '\xa0','Cr.','₹','%'] # Removed 'Promoters\xa0+'
            output = input_string.strip()
            for char in characters_to_remove:
              output = output.replace(char, '')
            # Handle 'NA' or empty strings by returning 0.0
            if output == 'NA' or output == '':
                return 0.0
            try:
                return float(output)
            except ValueError:
                print(f"Could not convert to float: {output}")
                return 0.0


          def mainContentRatio(id):
            main_body = body[0].find('div',id=id)
            kv = main_body.text.strip().replace('\n\n','').split('\n')
            key = kv[0].strip()
            value = kv[1]
            ratios[key] = remove_extra_space_and_characters(value)

          def chart_ratio(yearly_values, name):
            for year in yearly_values:
              y = year.text.strip().split('Year')
              key = name + " " + y[0] + "Year"
              value = y[1].replace('%','')
              charts[key] = float(value)


          #TICKER body extract ==============================================================
          url = f'https://ticker.finology.in/company/{ticker}'

          headers = {
              "User-Agent": (
                  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/122.0.0.0 Safari/537.36"
              )
          }

          # Add try-except block to handle HTTPError
          try:
              # Get the page
              response = requests.get(url, headers=headers)
              response.raise_for_status()

              # Wrap in BeautifulSoup
              soup = BeautifulSoup(response.text, "html.parser")
              body = soup.select('body')

              #Screener extract =================================================================
              url2 = f'https://www.screener.in/company/{ticker}/consolidated/'
              response2 = requests.get(url2, headers=headers)
              response2.raise_for_status()
              soup2 = BeautifulSoup(response2.text, "html.parser")
              body2 = soup2.select('body')


              # Define the ticker symbol
              ticker_NS = ticker + ".NS"  # ".NS" is for NSE India
              stock = yf.Ticker(ticker_NS)

              # Get the industry information
              industry = stock.info.get('industry', 'Industry not found')
              long_description = stock.info.get('longBusinessSummary','Description Not found')
              ratios["Industry"] = industry
              ratios["Description"] = long_description

              #extract sector
              sector = body[0].find_all(id='mainContent_compinfoId')[0].select('a')[0].text.strip()
              ratios["Sector"] = sector

              #Price extract
              price = float(body[0].find(id="mainContent_clsprice").find_all('span')[-1].text.strip())
              ratios["Price"] = price

              main_ratio_section = body[0].find(id="companyessentials")

              inner_divs_1 = main_ratio_section.find_all('div', recursive=False)
              inner_divs_2 = inner_divs_1[1].find_all('div', recursive=False)

              quick_ratio = stock.info.get('quickRatio')
              ratios["QuickRatio"] = quick_ratio

              trailingPegRatio = stock.info.get('trailingPegRatio')
              ratios["PEG"] = trailingPegRatio

              #main ratios ======================================================================
              for inner_div in inner_divs_2:
                small_tag = inner_div.find('small')
                if small_tag is not None:
                  ratio = small_tag.text.strip()
                  p_tag = inner_div.find('p')
                  if p_tag is not None:
                    ratios[ratio] = remove_extra_space_and_characters(p_tag.text.strip())

              #More raios =======================================================================
              mainContentRatio('mainContent_divCFOPAT')
              mainContentRatio('mainContent_divDebtEquity')
              mainContentRatio('mainContent_divICR')


              #charts ===========================================================================
              charts_section = body[0].find_all(class_='card cardscreen cardsmall')

              Sales_growth_chart = charts_section[0]
              chart = Sales_growth_chart.find('canvas')

              chart_ratio(charts_section[0].find_all('div',class_='ratiosingle'),'SalesGrowth')
              chart_ratio(charts_section[1].find_all('div',class_='ratiosingle'),'ROE')
              chart_ratio(charts_section[2].find_all('div',class_='ratiosingle'),'ROCE')
              chart_ratio(charts_section[3].find_all('div',class_='ratiosingle'),'ProfitGrowth')


              #share-holding-pattern ============================================================
              Shareholding_Pattern = body[0].find(id="mainContent_DivShp").find('tbody')

              rows = Shareholding_Pattern.find_all('tr')
              for row in rows:
                cells = row.find_all('td')
                key = cells[0].text.strip()
                temp_dic = {}
                sub_key = "Promoter"
                # Modified to handle 'Promoters\xa0+' specifically before converting to float
                value = cells[1].text.strip().replace('Promoters\xa0+', '').replace('%', '').replace(',', '')
                temp_dic[sub_key] = float(value) if value else 0.0 # Convert to float only if value is not empty
                sub_key = "Pledge"
                value = cells[2].text.strip().replace('%', '').replace(',', '')
                temp_dic[sub_key] = float(value) if value else 0.0 # Convert to float only if value is not empty
                holdings[key] = temp_dic


              #More-share-holding-pattern =======================================================
              section = body2[0].find(id="shareholding")
              table = section.find('tbody')
              header = section.find('thead')
              cols = header.find_all('th')

              keys = []
              for col in cols:
                keys.append(col.text.strip())

              keys = keys[-5:]

              rows = table.find_all('tr')

              for data in rows:
                recent_data = data.find_all('td')
                first = recent_data[0].text.strip().split('\n')[0].replace('\xa0+','')
                last_five = recent_data[-5:]

                # epochs = 5 # Removed fixed epochs
                temp_dic = {}
                # Iterate only up to the length of last_five
                for epoch in range(len(last_five)):
                  # Modified to handle potential empty strings after replacement and the specific string
                  value_str = last_five[epoch].text.strip().replace('%','').replace(',','').replace('Promoters\xa0+', '')
                  # Check if keys[epoch] is a valid non-empty string before using it as a key
                  if keys and epoch < len(keys) and keys[epoch]:
                      holdings[keys[epoch]][first] = float(value_str) if value_str else 0.0
                  else:
                      # Added a print statement to help diagnose which key is causing the issue
                      print(f"Warning: Skipping data for {first} due to invalid key '{keys[epoch] if epoch < len(keys) else 'Index out of bounds'}' at epoch {epoch}")


              #strengt-and-limitation ===========================================================
              strength_and_limitaion_section = body[0].find_all('div',class_='card cardscreenFixed overflow-hidden')
              strength_section = strength_and_limitaion_section[0]
              limitation_section = strength_and_limitaion_section[1]

              strength = []
              limitation = []

              for li in strength_section.find_all('ul')[0].find_all('li'):
                strength.append(li.text.strip())

              for li in limitation_section.find_all('ul')[0].find_all('li'):
                limitation.append(li.text.strip())

              strength_and_limitaion_section2 = body2[0].find('section',id='analysis')
              strength_and_limitaion_section2

              pros = strength_and_limitaion_section2.find('div',class_='pros').find_all('li')
              cons = strength_and_limitaion_section2.find('div',class_='cons').find_all('li')

              for pro in pros:
                strength.append(pro.text.strip())

              for con in cons:
                limitation.append(con.text.strip())

              analysis["Strength"] = strength
              analysis["Limitation"] = limitation


              #news =============================================================================
              # News_section = body[0].find_all("div",class_="card cardscreen")[-1]
              # News_pointers = News_section.find_all("p")
              # News_section2 = body[0].find_all("div",class_="card cardscreen")[-2]
              # News_pointers2 = News_section.find_all("li")
              # News_pointers = News_pointers + News_pointers2
              # pointers = []
              # for pointer in News_pointers:
              #   pointers.append(pointer.text.strip().replace('\xa0',''))

              # analysis["NEWS"] = pointers

          except requests.exceptions.HTTPError as e:
              print(f"HTTP Error occurred for ticker {ticker}: {e}")
              # Return empty dictionaries if HTTPError occurs
              return {}, {}, {}, {}
          except Exception as e:
              print(f"An unexpected error occurred for ticker {ticker}: {e}")
              # Return empty dictionaries for any other unexpected errors
              return {}, {}, {}, {}


          print(ratios)
          print(charts)
          print(holdings)
          print(analysis)

          return ratios,charts, holdings, analysis

