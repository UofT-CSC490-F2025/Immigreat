"""
Constants for the immigration data scraping project.

This file contains shared configuration values used across multiple scrapers.
"""

# =====================
# URL CONFIGURATIONS
# =====================

# Immigration forms webpage URLs
FORMS_WEBPAGES = [
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5710.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1295.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5583.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5686.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5708.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5557.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/cit0001.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/cit0002.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/cit0003.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1344.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5533.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5257.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5645.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5409.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5476.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5475.html"
]

# IRCC main website URLs for content scraping
IRCC_URLS = [
    "https://www.canada.ca/en/immigration-refugees-citizenship.html",
    "https://www.canada.ca/en/services/immigration-citizenship.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/visit-canada.html",
    "https://ircc.canada.ca/english/information/applications/visa.asp",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/visit-canada/apply-visitor-visa.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/visit-canada/visitor-visa.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/express-entry/apply-permanent-residence.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/family-sponsorship/spouse-partner-children.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/refugees.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/permanent-residents.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/permanent-residents/card/apply.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/permanent-residents/card.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/citizenship.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/account.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/check-status.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/account/link-paper-online.html",
    "https://ircc.canada.ca/english/helpcentre/index-featured-can.asp",
    "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/contact-ircc.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/contact-ircc/client-support-centre.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/check-processing-times.html",
    "https://ircc.canada.ca/english/information/fees/fees.asp",
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/biometrics.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/corporate/partners-service-providers/authorized-paid-representatives-portal.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/news.html",
    "https://www.canada.ca/en/immigration-refugees-citizenship/news/notices.html",
]

# =====================
# AWS S3 CONFIGURATION
# =====================

# S3 bucket name for storing scraped data
S3_BUCKET_NAME = "raw-immigreation-documents"  # Note: keeping original spelling for consistency

# S3 file keys (paths within the bucket)
S3_FORMS_DATA_KEY = "forms_scraped_data.json"
S3_IRCC_DATA_KEY = "ircc_scraped_data.json"

# =====================
# REQUEST CONFIGURATION
# =====================

# HTTP request timeouts (in seconds)
HTTP_TIMEOUT_SHORT = 20  # For webpage requests
HTTP_TIMEOUT_LONG = 30   # For PDF downloads and heavy requests

# Rate limiting delays (in seconds)
MIN_REQUEST_DELAY = 0.5
MAX_REQUEST_DELAY = 1.5

# Browser timeout for JavaScript-heavy pages (in milliseconds)
BROWSER_TIMEOUT = 60000

# =====================
# SCRAPING CONFIGURATION
# =====================

# PDF search keywords for forms
PDF_KEYWORDS = ["imm", "cit"]

# User agent string for web requests
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"

# Content filtering thresholds
MIN_CONTENT_LENGTH = 40  # Minimum character count for useful content

# File paths for output
DEFAULT_FORMS_OUTPUT = "forms_scraped_data.json"
DEFAULT_IRCC_OUTPUT = "ircc_scraped_data.json"

# =====================
# DATE FORMAT
# =====================

# Standard date format for scraped data
DATE_FORMAT = "%Y-%m-%d"