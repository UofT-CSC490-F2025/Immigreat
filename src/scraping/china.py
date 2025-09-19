import requests
from bs4 import BeautifulSoup
import sys


CN_BASE_URL = "https://www.nia.gov.cn"


def normalize_url(urls):
    normalized_urls = []

    for url in urls:
        if url.startswith("http"):
            normalized_urls.append(url)
        else:
            normalized_urls.append(CN_BASE_URL + url.replace('../../', '/'))

    return normalized_urls


def scrape_content_cn(url):

    response = requests.get(url)
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "lxml")


    content_div = soup.find("div", class_="content")
    content = content_div.get_text("\n", strip=True) if content_div else ""

    print("\nContent:\n", content)


def find_content_urls(url):
    response = requests.get(url)
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "lxml")

    list_section = soup.find("div", class_="list_bd")
    if not list_section:
        print("No div with class 'list_bd' found.")

    links = list_section.find_all("a")

    urls = [link.get("href") for link in links if link.get("href")]


    return urls


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')

    page_urls = [f"{CN_BASE_URL}/n741440/n741547/index_753309_{i}.html" for i in range(1, 6)]

    for url in page_urls:
        content_urls = find_content_urls(url)
        content_urls = normalize_url(content_urls)

        for content_url in content_urls:
            scrape_content_cn(content_url)