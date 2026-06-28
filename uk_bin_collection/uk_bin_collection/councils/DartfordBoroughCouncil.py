import re

import requests
from bs4 import BeautifulSoup

from uk_bin_collection.uk_bin_collection.common import *
from uk_bin_collection.uk_bin_collection.get_bin_data import AbstractGetBinDataClass


class CouncilClass(AbstractGetBinDataClass):
    """
    Dartford Borough Council bin collection scraper.

    The council portal (Verj.io e-form) requires a two-step flow:
      1. GET the UPRN URL to establish a JSESSIONID session cookie and
         extract the time-based 'ebz' token from the form action.
      2. POST the user's postcode (required by the form) to the ebz URL
         within the same session to receive the results page.

    The UPRN is passed as a config parameter; the postcode must also be
    supplied (stored in the 'number' field for backwards-compatibility
    with the HA integration config flow).
    """

    def parse_data(self, page: str, **kwargs) -> dict:

        try:
            user_uprn = kwargs.get("uprn")
            check_uprn(user_uprn)
            user_postcode = kwargs.get("postcode")
            if not user_postcode:
                raise ValueError("Postcode is required for Dartford Borough Council")
        except Exception as e:
            raise ValueError(f"Error getting identifier: {str(e)}")

        base_url = "https://windmz.dartford.gov.uk/ufs/WS_CHECK_COLLECTIONS.eb"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.5",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        session = requests.Session()
        session.headers.update(headers)

        # Step 1: GET UPRN page — establishes JSESSIONID cookie and ebz token
        r1 = session.get(base_url, params={"UPRN": user_uprn}, timeout=10)
        soup1 = BeautifulSoup(r1.text, "html.parser")

        form = soup1.find("form", {"name": "RW"})
        if not form:
            return {"bins": []}

        action = form.get("action", "")
        ebz_match = re.search(r"ebz=(1_\d+)", action)
        if not ebz_match:
            return {"bins": []}
        ebz = ebz_match.group(1)

        # Step 2: POST postcode in same session to get results
        post_url = f"https://windmz.dartford.gov.uk/ufs/WS_CHECK_COLLECTIONS.eb?ebz={ebz}"
        post_data = {
            "CTRL:KseGry05:_:A": user_postcode,
            "CTRL:2nvfUnaN:_": "Find",
        }
        r2 = session.post(post_url, data=post_data, timeout=10)
        soup2 = BeautifulSoup(r2.text, "html.parser")

        # Step 3: Parse the results table
        bin_data = {"bins": []}

        table = soup2.find(
            "table", {"class": lambda c: c and "eb-EVDNdR1G-tableContent" in c}
        )

        if table:
            rows = table.find_all(
                "tr", class_=lambda c: c and "eb-EVDNdR1G-tableRow" in c
            )
            for row in rows:
                columns = row.find_all("td")
                if len(columns) >= 4:
                    collection_type = columns[1].get_text(strip=True)
                    collection_date = columns[3].get_text(strip=True)
                    if re.match(r"\d{2}/\d{2}/\d{4}", collection_date):
                        bin_data["bins"].append(
                            {
                                "type": collection_type,
                                "collectionDate": collection_date,
                            }
                        )

        return bin_data
