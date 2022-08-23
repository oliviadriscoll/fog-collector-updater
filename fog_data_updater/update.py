import argparse
import datetime
import json
import logging
import os
import pprint


import googleapiclient.discovery
from google.oauth2 import service_account
import requests


SPREADSHEET_ID = "1e_qMx2egdqsUFI_46u0JW1daivNzeVteudA5BwY-8oM"
DEVICE_SN = "z6-07496"


# Returns: [[port 1 timestamps], [port 1 values], [port 2 timestamps], [port 2 values], ...]
def query_zentra_one(token, start_date, end_date, page_num, per_page):
    url = "https://zentracloud.com/api/v3/get_readings/"
    headers = {"content-type": "application/json", "Authorization": f"Token {token}"}
    params = {
        "device_sn": DEVICE_SN,
        "start_date": start_date,
        "end_date": end_date,
        "page_num": page_num,
        "per_page": per_page,
    }
    response = requests.get(url, params=params, headers=headers)
    return json.loads(response.content)


# end_date = datetime.datetime.today()
# start_date = end_date - datetime.timedelta(days=4)


def query_zentra_all(token, start_date, end_date):
    page_num = 1
    per_page = 5
    data = query_zentra_one(token, start_date, end_date, page_num, per_page)["data"]["Precipitation"]

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


def cell_update_from_data(data):
    return [{"values": [{"userEnteredValue": {"numberValue": value}} for value in row]} for row in data]


def main():
    logging.basicConfig(level=os.environ.get("PYTHON_LOG", "INFO"))

    parser = argparse.ArgumentParser()
    parser.add_argument("secret_file")
    args = parser.parse_args()

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = service_account.Credentials.from_service_account_file(args.secret_file)
    creds = creds.with_scopes(scopes)
    service = googleapiclient.discovery.build("sheets", "v4", credentials=creds)

    metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheets = metadata.get("sheets", "")
    sheet_id = sheets[0].get("properties", {}).get("sheetId", 0)

    # https://googleapis.github.io/google-api-python-client/docs/dyn/sheets_v4.spreadsheets.html
    # https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets/batchUpdate
    # https://stackoverflow.com/questions/38245714/get-list-of-sheets-and-latest-sheet-in-google-spreadsheet-api-v4-in-python
    body = {
        "requests": [
            {
                "deleteRange": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "startColumnIndex": 0,
                    },
                    "shiftDimension": "ROWS",
                },
            },
            {
                "appendCells": {
                    "sheetId": sheet_id,
                    "rows": [
                        {
                            "values": [
                                {"userEnteredValue": {"numberValue": 10}},
                                {"userEnteredValue": {"numberValue": 20}},
                            ]
                        },
                        {
                            "values": [
                                {"userEnteredValue": {"numberValue": 30}},
                                {"userEnteredValue": {"numberValue": 40}},
                            ]
                        },
                    ],
                    "fields": "userEnteredValue",
                }
            },
        ]
    }
    try:
        response = (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=SPREADSHEET_ID, body=body)
            .execute()
        )
    except Exception as e:
        print("Caught the following exception:")
        print(e)

    logging.info(pprint.pformat(response))


if __name__ == "__main__":
    main()
