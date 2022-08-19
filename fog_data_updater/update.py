import argparse
import datetime
import json
import pprint


import googleapiclient.discovery
from google.oauth2 import service_account
import requests


SPREADSHEET_ID = "1e_qMx2egdqsUFI_46u0JW1daivNzeVteudA5BwY-8oM"
DEVICE_SN = "z6-07496"


# Returns: [[port 1 timestamps], [port 1 values], [port 2 timestamps], [port 2 values], ...]
def query_zentra(token):
    url = "https://zentracloud.com/api/v3/get_readings/"
    headers = {"content-type": "application/json", "Authorization": token}
    end_date = datetime.datetime.today()
    start_date = end_date - datetime.timedelta(days=4)
    page_num = 1
    per_page = 5
    params = {
        "device_sn": DEVICE_SN,
        "start_date": start_date,
        "end_date": end_date,
        "page_num": page_num,
        "per_page": per_page,
    }
    print("fetching...")
    response = requests.get(url, params=params, headers=headers)
    print("decoding...")
    data = json.loads(response.content)["data"]["Precipitation"]

    result = []
    for port_data in data:
        readings = port_data["readings"]
        times = []
        values = []
        for reading in readings:
            times.append(reading["timestamp_utc"])
            values.append(reading["value"])
        result.append(times)
        result.append(values)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("secret_file")
    args = parser.parse_args()

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = service_account.Credentials.from_service_account_file(args.secret_file)
    creds = creds.with_scopes(scopes)
    service = googleapiclient.discovery.build("sheets", "v4", credentials=creds)

    range_name = "Sheet1!A1:D2"
    values = [
        ["a1", "b1", "c1", 123],
        ["a2", "b2", "c2", 456],
    ]
    data = {"values": values}
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        body=data,
        range=range_name,
        valueInputOption="USER_ENTERED",
    ).execute()


if __name__ == "__main__":
    main()
